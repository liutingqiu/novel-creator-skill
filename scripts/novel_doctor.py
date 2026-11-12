#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""开写前环境自检：一条命令回答"现在能不能开始写"。

    python3 scripts/novel_doctor.py --project-root /home/liutingqiu/store

只读检查，不改项目文件；退出码 0 表示没有 FAIL（WARN 不阻塞）。
"""

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

REQUIRED_SCRIPTS = [
    "novel_flow_executor.py",
    "novel_rag_core.py",
    "obsidian_graph_bridge.py",
    "plot_rag_retriever.py",
    "chapter_gate_check.py",
]
REQUIRED_MEMORY = ["novel_plan.md", "world_state.md", "character_tracker.md"]


class Doctor:
    def __init__(self, project_root: Path):
        self.root = Path(project_root).expanduser().resolve()
        self.checks: List[Dict[str, str]] = []

    def add(self, name: str, status: str, detail: str, fix: str = ""):
        self.checks.append({"name": name, "status": status, "detail": detail, "fix": fix})

    # ---- 单项检查 ----
    def check_python(self):
        version = "%d.%d.%d" % sys.version_info[:3]
        if sys.version_info < (3, 9):
            self.add("python", FAIL, f"Python {version} 过低", "升级到 3.9+")
            return
        try:
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
            conn.close()
        except sqlite3.Error as exc:
            self.add("python", FAIL, f"Python {version}，但 SQLite 缺 FTS5: {exc}", "安装带 FTS5 的 SQLite")
            return
        self.add("python", PASS, f"Python {version}，SQLite {sqlite3.sqlite_version}，FTS5 可用")

    def check_layout(self):
        missing = [name for name in REQUIRED_MEMORY if not (self.root / "00_memory" / name).exists()]
        if missing:
            self.add("layout", FAIL, "缺少记忆文件: " + ", ".join(missing), "运行 one-click 初始化项目")
        else:
            self.add("layout", PASS, "00_memory 三件套齐全")
        if not (self.root / "03_manuscript").exists():
            self.add("manuscript", WARN, "03_manuscript/ 不存在（还没建章节目录）", "运行 one-click 或手动建目录")

    def check_scripts(self):
        missing = [name for name in REQUIRED_SCRIPTS if not (SCRIPT_DIR / name).exists()]
        if missing:
            self.add("scripts", FAIL, "缺脚本: " + ", ".join(missing), "重新安装 skill")
        else:
            self.add("scripts", PASS, f"{len(REQUIRED_SCRIPTS)} 个核心脚本齐全")

    def check_rag_db(self):
        db = self.root / ".novel_rag" / "novel_memory.db"
        if not db.exists():
            self.add("rag_db", WARN, "还没有 Novel-RAG 库（首次写入/开书时自动创建）", "运行 novel_rag_core.py ingest")
            return
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(fts_memories)").fetchall()]
            if "fts_text" not in cols:
                self.add("rag_db", FAIL, "FTS 表仍是旧结构（中文不可检索）", "升级脚本后重新打开一次库，会自动迁移")
                return
            mem = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            fts = conn.execute("SELECT COUNT(*) FROM fts_memories").fetchone()[0]
            ent = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            rel = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
            if mem != fts:
                self.add("rag_db", FAIL, f"memories={mem} 与 fts={fts} 不一致", "重跑 ingest 修复索引")
                return
            self.add("rag_db", PASS, f"memories={mem} entities={ent} relations={rel}，FTS 索引一致")
        finally:
            conn.close()

    def check_entity_quality(self):
        db = self.root / ".novel_rag" / "novel_memory.db"
        if not db.exists():
            return
        from novel_rag_core import TABLE_HEADER_WORDS

        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            names = [r[0] for r in conn.execute("SELECT name FROM entities").fetchall()]
            junk = sorted(set(names) & TABLE_HEADER_WORDS)
            null_rel = conn.execute("SELECT COUNT(*) FROM relations WHERE chunk_id IS NULL").fetchone()[0]
            if junk:
                self.add("entity_quality", FAIL, "表头被当成实体: " + ", ".join(junk), "升级 ingest 分类逻辑后重建库")
            elif null_rel:
                self.add("entity_quality", WARN, f"{null_rel} 条关系 chunk_id 为 NULL（旧数据）", "重新打开库会自动归一")
            else:
                self.add("entity_quality", PASS, f"{len(names)} 个实体，无表头污染")
        finally:
            conn.close()

    def check_recall_selftest(self):
        """用临时库跑一遍中文召回，验证引擎本身可用（与项目数据无关）。"""
        from novel_rag_core import NovelRAG

        tmp = Path(tempfile.mkdtemp(prefix="novel_doctor_"))
        try:
            rag = NovelRAG(tmp)
            rag.remember("后山禁地封印着太古凶兽", mtype="fact", tier=1, subject="plot")
            res = rag.query("后山禁地")
            rag.close()
            if res["memories"] and res["memories"][0]["claim"] == "后山禁地封印着太古凶兽":
                self.add("recall", PASS, "中文检索自测通过")
            else:
                self.add("recall", FAIL, "中文检索自测失败：查询不到已写入内容", "检查 novel_rag_core 的 fts_tokens/迁移逻辑")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def check_git(self):
        try:
            out = subprocess.run(
                ["git", "-C", str(self.root), "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True, timeout=10,
            )
            if out.returncode != 0:
                self.add("git", WARN, "项目不在 git 版本控制下", "git init 后提交一次，避免手稿无法回滚")
                return
            status = subprocess.run(
                ["git", "-C", str(self.root), "status", "--porcelain"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            last = subprocess.run(
                ["git", "-C", str(self.root), "log", "-1", "--pretty=%h %s"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            if status:
                changed = len(status.splitlines())
                self.add("git", WARN, f"有 {changed} 个未提交改动；最近提交 {last}", "提交一次快照")
            else:
                self.add("git", PASS, f"工作区干净；最近提交 {last}")
        except (OSError, subprocess.SubprocessError) as exc:
            self.add("git", WARN, f"git 检查失败: {exc}", "")

    def check_obsidian(self):
        entities_dir = self.root / "00_worldview" / "entities"
        canvas = self.root / "00_worldview" / "worldview_canvas.canvas"
        notes = len(list(entities_dir.glob("*.md"))) if entities_dir.exists() else 0
        if notes and canvas.exists():
            self.add("obsidian", PASS, f"{notes} 张实体笔记 + Canvas 画布")
        elif notes or canvas.exists():
            self.add("obsidian", WARN, "图谱产物不全", "运行 obsidian_graph_bridge.py export")
        else:
            self.add("obsidian", WARN, "还没有图谱产物", "写入后同步会自动生成，或手动 export")

    def check_manuscript(self):
        ms = self.root / "03_manuscript"
        if not ms.exists():
            return
        chapters = sorted(ms.glob("*.md"))
        if chapters:
            latest = max(chapters, key=lambda p: p.stat().st_mtime)
            self.add("manuscript", PASS, f"{len(chapters)} 章；最新 {latest.name}")
        else:
            self.add("manuscript", WARN, "还没有章节文件", "写第一章后自动生成")

    # ---- 汇总 ----
    def run(self) -> Dict[str, Any]:
        for check in (
            self.check_python, self.check_layout, self.check_scripts, self.check_rag_db,
            self.check_entity_quality, self.check_recall_selftest, self.check_git,
            self.check_obsidian, self.check_manuscript,
        ):
            try:
                check()
            except Exception as exc:  # noqa: BLE001 - 单项失败不能让自检崩掉
                self.add(check.__name__.replace("check_", ""), FAIL, f"检查异常: {exc}")

        failures = [c for c in self.checks if c["status"] == FAIL]
        warnings = [c for c in self.checks if c["status"] == WARN]
        return {
            "project_root": str(self.root),
            "ok": not failures,
            "checks": self.checks,
            "failures": len(failures),
            "warnings": len(warnings),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="小说工程开写前自检")
    parser.add_argument("--project-root", default=".", help="小说项目根目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    report = Doctor(Path(args.project_root)).run()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        icons = {PASS: "✅", WARN: "⚠️ ", FAIL: "❌"}
        print(f"\n小说工程自检：{report['project_root']}\n")
        for check in report["checks"]:
            print(f" {icons[check['status']]} {check['name']:<15} {check['detail']}")
            if check["status"] != PASS and check["fix"]:
                print(f"      → {check['fix']}")
        print()
        if report["ok"]:
            print(f"结论：可以开写（{report['warnings']} 个提示）")
        else:
            print(f"结论：有 {report['failures']} 项阻塞，先按上面的 → 修")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
