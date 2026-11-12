#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Novel-RAG 核心模块：长篇小说专属结构化记忆、认识论分级、单向取代链与图谱检索。

设计定位：
1. 项目级物理隔离：每个小说项目拥有专属数据库 `<project_root>/.novel_rag/novel_memory.db`，
   绝不向全局或个人日常记忆库写入任何内容。
2. 认识论分类 (mtypes)：
   - `fact`: 世界观硬设定、角色已知境界、宗门地理、法则限制（永久置信）
   - `inference`: 剧情推测、伏笔预设（必须携带 premise 前提和 falsifier 反证条件）
   - `preference`: 作者铁律、核心红线、写作避雷（最高权重置顶，防剧情崩坏）
   - `negresult`: 已否证的路线/废案（最高防雷警示，避免炒冷饭与重蹈覆辙）
   - `method`: 写作技巧、特定门派招式心法推演逻辑
   - `task`: 未收束伏笔、下一章推进任务
3. 单向取代链 (Superseded Chain)：
   中途改纲时旧设定不物理删除，标记 `superseded_by = new_id` 与推翻原因。
   检索时压制旧设定，但完整保留决策证据链。
4. 知识图谱 (Entities / Relations / Events)：
   结构化追踪实体与网状因果，天然适配 Obsidian 双向链接与 Graph View。
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import ensure_dir, normalize_text, read_text, save_json, slugify

# ---- 认识论类型定义 ----
MTYPES = ("fact", "inference", "preference", "method", "negresult", "task")

DECAY_CLASSES = {
    "permanent": None,   # 铁律、核心世界观法则、核心设定
    "long": 365.0,       # 势力关系、长期未解伏笔
    "medium": 90.0,      # 一般剧情推断、章节局部设定
    "short": 14.0,       # 短期任务、即时状态
    "ephemeral": 3.0,    # 临时的数值、即时伤势、短期物品持有
}

DEFAULT_DECAY = {
    "preference": "permanent",
    "method": "permanent",
    "fact": "permanent",
    "negresult": "long",
    "inference": "medium",
    "task": "short",
}

# 权威层级
TIERS = {
    0: "作者铁律/绝对红线",
    1: "世界观定稿法则",
    2: "大纲与分卷草案",
    3: "正文章节已揭露事实",
    4: "背景素材与归档",
}

SCHEMA_SQL = """
-- 结构化记忆表
CREATE TABLE IF NOT EXISTS memories (
  chunk_id           TEXT PRIMARY KEY,
  mtype              TEXT NOT NULL DEFAULT 'fact',
  premise            TEXT,            -- 前提假设（在什么条件下成立）
  claim              TEXT NOT NULL,   -- 核心论断/设定内容
  falsifier          TEXT,            -- 反证条件（什么剧情发生即失效）
  decay_class        TEXT NOT NULL DEFAULT 'permanent',
  tier               INTEGER NOT NULL DEFAULT 1, -- 0=铁律, 1=定稿, 2=草案, 3=正文已写, 4=归档
  subject            TEXT,            -- 主题分类，如 worldview / character / plot / magic_system
  tags               TEXT,            -- 逗号分隔的标签
  chapter_no         INTEGER DEFAULT 0,
  superseded_by      TEXT,            -- 被哪个 chunk_id 取代
  superseded_reason  TEXT,            -- 为什么推翻/取代
  superseded_at      REAL,
  valid_count        INTEGER DEFAULT 0,
  invalid_count      INTEGER DEFAULT 0,
  created_at         REAL NOT NULL,
  updated_at         REAL NOT NULL
);

-- 全文检索虚表
CREATE VIRTUAL TABLE IF NOT EXISTS fts_memories USING fts5(
  chunk_id UNINDEXED,
  claim,
  premise,
  falsifier,
  subject,
  tags,
  tokenize='unicode61'
);

-- 实体表 (人物/地点/门派/物品/法则/事件)
CREATE TABLE IF NOT EXISTS entities (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  name               TEXT NOT NULL UNIQUE,
  etype              TEXT NOT NULL,   -- character / location / faction / item / worldrule / power_system
  aliases            TEXT,            -- 逗号分隔别名
  note               TEXT,            -- 一句话简介
  tier               INTEGER DEFAULT 1,
  attributes_json    TEXT,            -- 结构化属性 (JSON)
  first_seen_chapter INTEGER DEFAULT 0,
  last_seen_chapter  INTEGER DEFAULT 0,
  status             TEXT DEFAULT 'active',
  created_at         REAL NOT NULL,
  updated_at         REAL NOT NULL
);

-- 实体关系表 (A --rel--> B)
CREATE TABLE IF NOT EXISTS relations (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  a                  TEXT NOT NULL,
  b                  TEXT NOT NULL,
  rel                TEXT NOT NULL,   -- 关系类型，如 盟友/敌对/门徒/持有/从属
  note               TEXT,
  chapter_no         INTEGER DEFAULT 0,
  chunk_id           TEXT,
  status             TEXT DEFAULT 'active',
  created_at         REAL NOT NULL,
  UNIQUE(a, b, rel, chunk_id)
);

-- 剧情重大事件因果表
CREATE TABLE IF NOT EXISTS events (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  chapter_no         INTEGER DEFAULT 0,
  actor              TEXT,
  action             TEXT,
  obj                TEXT,
  outcome            TEXT,
  topic              TEXT,
  raw                TEXT,
  chunk_id           TEXT,
  created_at         REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_mtype ON memories(mtype);
CREATE INDEX IF NOT EXISTS idx_memories_subject ON memories(subject);
CREATE INDEX IF NOT EXISTS idx_memories_superseded ON memories(superseded_by);
CREATE INDEX IF NOT EXISTS idx_entities_etype ON entities(etype);
CREATE INDEX IF NOT EXISTS idx_relations_a ON relations(a);
CREATE INDEX IF NOT EXISTS idx_relations_b ON relations(b);
"""


class NovelRAG:
    """小说专属定制 RAG 引擎。"""

    def __init__(self, project_root: Path, db_name: str = "novel_memory.db"):
        self.project_root = Path(project_root).resolve()
        self.rag_dir = self.project_root / ".novel_rag"
        ensure_dir(self.rag_dir)
        self.db_path = self.rag_dir / db_name
        self.conn = self._init_db()

    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        with conn:
            conn.executescript(SCHEMA_SQL)
        return conn

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    # ──────────────────────────────────────────────────────────
    # 记忆操作（写入 / 取代 / 反馈）
    # ──────────────────────────────────────────────────────────

    def remember(
        self,
        claim: str,
        mtype: str = "fact",
        premise: Optional[str] = None,
        falsifier: Optional[str] = None,
        decay_class: Optional[str] = None,
        tier: int = 1,
        subject: Optional[str] = None,
        tags: str = "",
        chapter_no: int = 0,
        chunk_id: Optional[str] = None,
    ) -> str:
        """写入一条结构化小说记忆。"""
        claim = normalize_text(claim)
        if not claim:
            raise ValueError("claim 不能为空")

        if mtype not in MTYPES:
            mtype = "fact"

        if not decay_class:
            decay_class = DEFAULT_DECAY.get(mtype, "permanent")

        now = time.time()
        if not chunk_id:
            raw_hash = hashlib.sha256(f"{claim}:{now}".encode("utf-8")).hexdigest()[:12]
            chunk_id = f"mem_{mtype[:3]}_{raw_hash}"

        with self.conn:
            # 插入或替换
            self.conn.execute(
                """
                INSERT OR REPLACE INTO memories (
                    chunk_id, mtype, premise, claim, falsifier,
                    decay_class, tier, subject, tags, chapter_no,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id, mtype, premise, claim, falsifier,
                    decay_class, tier, subject, tags, chapter_no,
                    now, now,
                ),
            )
            # 更新 FTS
            self.conn.execute("DELETE FROM fts_memories WHERE chunk_id = ?", (chunk_id,))
            self.conn.execute(
                """
                INSERT INTO fts_memories (chunk_id, claim, premise, falsifier, subject, tags)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chunk_id, claim, premise or "", falsifier or "", subject or "", tags or ""),
            )

        return chunk_id

    def supersede(
        self,
        old_chunk_id: str,
        new_claim: Optional[str] = None,
        reason: str = "设定或大纲调整",
        new_mtype: Optional[str] = None,
        tier: int = 1,
        chapter_no: int = 0,
    ) -> Optional[str]:
        """推翻并挂载取代链。原设定不物理删除，以供证据追溯。"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM memories WHERE chunk_id = ?", (old_chunk_id,))
        old = cur.fetchone()
        if not old:
            return None

        now = time.time()
        new_id = None
        if new_claim:
            mtype = new_mtype or old["mtype"]
            new_id = self.remember(
                claim=new_claim,
                mtype=mtype,
                tier=tier,
                subject=old["subject"],
                tags=old["tags"],
                chapter_no=chapter_no,
            )

        with self.conn:
            self.conn.execute(
                """
                UPDATE memories
                SET superseded_by = ?, superseded_reason = ?, superseded_at = ?, updated_at = ?
                WHERE chunk_id = ?
                """,
                (new_id or "REMOVED_WITHOUT_REPLACEMENT", reason, now, now, old_chunk_id),
            )

        return new_id

    def record_feedback(self, chunk_id: str, useful: bool = True, note: str = ""):
        """记录该设定是否在实际写作中被证实或发挥价值。"""
        with self.conn:
            if useful:
                self.conn.execute(
                    "UPDATE memories SET valid_count = valid_count + 1, updated_at = ? WHERE chunk_id = ?",
                    (time.time(), chunk_id),
                )
            else:
                self.conn.execute(
                    "UPDATE memories SET invalid_count = invalid_count + 1, updated_at = ? WHERE chunk_id = ?",
                    (time.time(), chunk_id),
                )

    # ──────────────────────────────────────────────────────────
    # 图谱操作（实体 / 关系 / 事件）
    # ──────────────────────────────────────────────────────────

    def add_entity(
        self,
        name: str,
        etype: str,
        aliases: str = "",
        note: str = "",
        tier: int = 1,
        attributes: Optional[Dict[str, Any]] = None,
        chapter_no: int = 0,
    ) -> int:
        """添加或更新实体 (人物/宗门/地点/法宝/规则)。"""
        now = time.time()
        attr_json = json.dumps(attributes or {}, ensure_ascii=False)
        with self.conn:
            cur = self.conn.cursor()
            cur.execute("SELECT id, first_seen_chapter, attributes_json FROM entities WHERE name = ?", (name,))
            row = cur.fetchone()
            if row:
                first_seen = row["first_seen_chapter"]
                if first_seen == 0 or (chapter_no > 0 and chapter_no < first_seen):
                    first_seen = chapter_no
                self.conn.execute(
                    """
                    UPDATE entities
                    SET etype = ?, aliases = ?, note = ?, tier = ?, attributes_json = ?,
                        last_seen_chapter = MAX(last_seen_chapter, ?), first_seen_chapter = ?, updated_at = ?
                    WHERE name = ?
                    """,
                    (etype, aliases, note, tier, attr_json, chapter_no, first_seen, now, name),
                )
                return row["id"]
            else:
                cur.execute(
                    """
                    INSERT INTO entities (
                        name, etype, aliases, note, tier, attributes_json,
                        first_seen_chapter, last_seen_chapter, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (name, etype, aliases, note, tier, attr_json, chapter_no, chapter_no, now, now),
                )
                return cur.lastrowid

    def add_relation(
        self,
        a: str,
        b: str,
        rel: str,
        note: str = "",
        chapter_no: int = 0,
        chunk_id: Optional[str] = None,
    ) -> int:
        """记录实体间的单向/双向关系。"""
        now = time.time()
        with self.conn:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO relations (a, b, rel, note, chapter_no, chunk_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (a, b, rel, note, chapter_no, chunk_id, now),
            )
            return cur.lastrowid

    def record_event(
        self,
        actor: str,
        action: str,
        obj: str,
        outcome: str = "",
        topic: str = "",
        raw: str = "",
        chapter_no: int = 0,
        chunk_id: Optional[str] = None,
    ) -> int:
        """记录大事件。"""
        now = time.time()
        with self.conn:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO events (chapter_no, actor, action, obj, outcome, topic, raw, chunk_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (chapter_no, actor, action, obj, outcome, topic, raw, chunk_id, now),
            )
            return cur.lastrowid

    # ──────────────────────────────────────────────────────────
    # 混合检索与上下文提取 (Hybrid Retrieval)
    # ──────────────────────────────────────────────────────────

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        mtypes: Optional[List[str]] = None,
        tiers: Optional[List[int]] = None,
        include_superseded: bool = False,
    ) -> Dict[str, Any]:
        """混合检索：全文 FTS5 + 实体共现 + 认识论加权 + 取代链压制。"""
        q = normalize_text(query_text)
        if not q:
            return {"memories": [], "entities": [], "relations": [], "alerts": []}

        cur = self.conn.cursor()

        # 1. 实体识别 (从 query 中找到已注册实体)
        cur.execute("SELECT name, etype, note, aliases FROM entities")
        all_entities = cur.fetchall()
        matched_entities = []
        for ent in all_entities:
            name = ent["name"]
            aliases = [a.strip() for a in (ent["aliases"] or "").split(",") if a.strip()]
            if name in q or any(a in q for a in aliases):
                matched_entities.append(ent)

        matched_names = [e["name"] for e in matched_entities]

        # 2. 关系检索
        matched_relations = []
        if matched_names:
            placeholders = ",".join("?" for _ in matched_names)
            cur.execute(
                f"""
                SELECT a, b, rel, note FROM relations
                WHERE status = 'active' AND (a IN ({placeholders}) OR b IN ({placeholders}))
                LIMIT 15
                """,
                matched_names * 2,
            )
            matched_relations = [dict(r) for r in cur.fetchall()]

        # 3. 全文与语义关键词构建（2~3 元重叠 n-gram + 英文单词）
        en_words = re.findall(r'[A-Za-z0-9_]{2,}', q)
        cn_chars = re.sub(r'[^\u4e00-\u9fff]', '', q)
        ngram_set = set(en_words)
        for n in (2, 3):
            for i in range(len(cn_chars) - n + 1):
                ngram_set.add(cn_chars[i : i + n])
        tokens = sorted(list(ngram_set), key=lambda x: len(x), reverse=True)
        fts_query = ' OR '.join(f'"{t}"' for t in tokens[:8]) if tokens else f'"{q[:8]}"'
        fts_hits: Dict[str, float] = {}
        if fts_query.strip():
            try:
                cur.execute(
                    """
                    SELECT chunk_id, bm25(fts_memories) as rank_score
                    FROM fts_memories
                    WHERE fts_memories MATCH ?
                    LIMIT 40
                    """,
                    (fts_query,),
                )
                for row in cur.fetchall():
                    # bm25 分数越负越相关，取反变正
                    fts_hits[row["chunk_id"]] = max(0.1, -row["rank_score"])
            except sqlite3.OperationalError:
                # 容错：FTS 语法异常时降级
                pass

        # 4. 加载所有候选记忆进行加权排序
        cur.execute("SELECT * FROM memories")
        all_mems = cur.fetchall()

        scored_mems = []
        alerts = []

        for m in all_mems:
            cid = m["chunk_id"]
            claim = m["claim"]
            mtype = m["mtype"]
            tier = m["tier"]
            is_superseded = bool(m["superseded_by"])

            # 过滤
            if mtypes and mtype not in mtypes:
                continue
            if tiers and tier not in tiers:
                continue

            # 基础分
            base_score = fts_hits.get(cid, 0.0)

            # 实体命中加分
            for ename in matched_names:
                if ename in claim:
                    base_score += 2.5

            # 认识论加权
            weight = 1.0
            if mtype == "preference":
                weight = 3.0  # 铁律必须优先浮现
                # 如果包含警示词，作为警报直接提取
                if any(t in claim for t in tokens):
                    alerts.append({"type": "iron_law", "content": claim})
            elif mtype == "negresult":
                weight = 2.5  # 否证路线高权防雷
                if any(t in claim for t in tokens):
                    alerts.append({"type": "negresult", "content": claim})
            elif mtype == "fact":
                weight = 1.8
            elif mtype == "inference":
                # 反馈修正
                val = m["valid_count"]
                inval = m["invalid_count"]
                weight = 1.2 + (val * 0.2) - (inval * 0.4)

            # 层级修正
            tier_bonus = max(0, (4 - tier) * 0.3)

            final_score = (base_score + tier_bonus) * weight

            # 取代链压制
            if is_superseded:
                if not include_superseded:
                    final_score *= 0.05  # 几乎压到最底
                else:
                    final_score *= 0.4

            if final_score > 0.05:
                scored_mems.append({
                    "chunk_id": cid,
                    "mtype": mtype,
                    "claim": claim,
                    "premise": m["premise"],
                    "falsifier": m["falsifier"],
                    "tier": tier,
                    "subject": m["subject"],
                    "superseded_by": m["superseded_by"],
                    "superseded_reason": m["superseded_reason"],
                    "score": round(final_score, 3),
                })

        scored_mems.sort(key=lambda x: x["score"], reverse=True)

        return {
            "memories": scored_mems[:top_k],
            "entities": [dict(e) for e in matched_entities[:6]],
            "relations": matched_relations[:8],
            "alerts": alerts[:4],
        }

    def generate_context_brief(self, query_text: str) -> str:
        """为当前章节写作生成高密度上下文提示块（Markdown 格式）。"""
        res = self.query(query_text, top_k=6)
        lines = ["<!-- NOVEL_RAG_CONTEXT_START -->", "### 📚 本章关联高维记忆与设定约束"]

        if res["alerts"]:
            lines.append("\n#### ⚠️ 铁律红线与避坑警示")
            for a in res["alerts"]:
                prefix = "⛔ 【铁律】" if a["type"] == "iron_law" else "🚫 【已否证废案】"
                lines.append(f"- {prefix} {a['content']}")

        if res["entities"]:
            lines.append("\n#### 👥 关联实体与状态")
            for e in res["entities"]:
                note = f"（{e['note']}）" if e["note"] else ""
                lines.append(f"- `[[{e['name']}]]` [{e['etype']}]{note}")

        if res["relations"]:
            lines.append("\n#### 🕸️ 实体关系网络")
            for r in res["relations"]:
                note = f" : {r['note']}" if r.get("note") else ""
                lines.append(f"- `[[{r['a']}]]` --**{r['rel']}**--> `[[{r['b']}]]`{note}")

        if res["memories"]:
            lines.append("\n#### 📖 核心事实与有效推论")
            for m in res["memories"]:
                status = " [已废弃]" if m["superseded_by"] else ""
                premise_str = f" [前提: {m['premise']}]" if m.get("premise") else ""
                lines.append(f"- [{m['mtype']}]{status} {m['claim']}{premise_str}")

        lines.append("<!-- NOVEL_RAG_CONTEXT_END -->")
        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────
    # 从传统 Markdown 文件导入 (种子构建)
    # ──────────────────────────────────────────────────────────

    def ingest_from_workspace(self) -> Dict[str, int]:
        """将 00_memory/ 下的现有世界观、人物卡解析并录入到 SQLite 中。"""
        counts = {"entities": 0, "relations": 0, "memories": 0}

        # 1. 角色追踪器 character_tracker.md
        char_file = self.project_root / "00_memory" / "character_tracker.md"
        if char_file.exists():
            text = read_text(char_file)
            # 提取主角
            prot_m = re.search(r"##\s*主角[：:]\s*([^\n]+)", text)
            if prot_m:
                pname = prot_m.group(1).strip()
                self.add_entity(name=pname, etype="character", note="主角", tier=0)
                counts["entities"] += 1
                self.remember(claim=f"主角姓名是{pname}", mtype="fact", tier=0, subject="character")
                counts["memories"] += 1

            # 提取核心配角
            sub_matches = re.finditer(r"###\s*([^\n]+)", text)
            for sm in sub_matches:
                cname = sm.group(1).strip()
                if cname and not cname.startswith("{"):
                    self.add_entity(name=cname, etype="character", note="配角", tier=1)
                    counts["entities"] += 1

        # 2. 世界状态 world_state.md
        world_file = self.project_root / "00_memory" / "world_state.md"
        if world_file.exists():
            wtext = read_text(world_file)
            lines = wtext.splitlines()
            for line in lines:
                if line.strip().startswith("|") and not line.startswith("|-"):
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 2 and parts[0] != "势力名" and parts[0] != "等级名" and not parts[0].startswith("{"):
                        self.add_entity(name=parts[0], etype="faction", note=parts[1] if len(parts) > 1 else "", tier=1)
                        counts["entities"] += 1

        # 3. 主线计划 novel_plan.md 提取绝对规则
        plan_file = self.project_root / "00_memory" / "novel_plan.md"
        if plan_file.exists():
            ptext = read_text(plan_file)
            rules_block = re.search(r"##\s*绝对规则[^\n]*\n([\s\S]*?)(?=\n##|\Z)", ptext)
            if rules_block:
                for line in rules_block.group(1).splitlines():
                    clean_line = re.sub(r"^\d+[\.\、]\s*", "", line).strip()
                    if clean_line and not clean_line.startswith("<!--") and not clean_line.startswith("{"):
                        self.remember(claim=clean_line, mtype="preference", tier=0, subject="iron_law")
                        counts["memories"] += 1

        return counts


# ──────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Novel-RAG 独立记忆引擎")
    subparsers = parser.add_subparsers(dest="cmd")

    init_p = subparsers.add_parser("init", help="初始化小说 RAG 数据库")
    init_p.add_argument("--project-root", default=".", help="小说项目根目录")

    rem_p = subparsers.add_parser("remember", help="写入记忆")
    rem_p.add_argument("--project-root", default=".", help="小说项目根目录")
    rem_p.add_argument("--claim", required=True, help="论断内容")
    rem_p.add_argument("--mtype", default="fact", choices=MTYPES, help="认识论类型")
    rem_p.add_argument("--premise", help="前提条件")
    rem_p.add_argument("--falsifier", help="反证条件")
    rem_p.add_argument("--tier", type=int, default=1, help="权威层级(0-4)")
    rem_p.add_argument("--subject", help="主题分类")

    query_p = subparsers.add_parser("query", help="检索记忆")
    query_p.add_argument("--project-root", default=".", help="小说项目根目录")
    query_p.add_argument("--query", required=True, help="检索语句")
    query_p.add_argument("--top-k", type=int, default=5, help="返回条数")

    brief_p = subparsers.add_parser("brief", help="生成章节前置 Markdown 提示块")
    brief_p.add_argument("--project-root", default=".", help="小说项目根目录")
    brief_p.add_argument("--query", required=True, help="当前章节剧情大纲")

    ingest_p = subparsers.add_parser("ingest", help="从现有 Markdown 文件导入")
    ingest_p.add_argument("--project-root", default=".", help="小说项目根目录")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    project_root = Path(args.project_root)
    rag = NovelRAG(project_root)

    if args.cmd == "init":
        print(f"[OK] Novel-RAG 数据库已就绪: {rag.db_path}")
    elif args.cmd == "remember":
        cid = rag.remember(
            claim=args.claim,
            mtype=args.mtype,
            premise=args.premise,
            falsifier=args.falsifier,
            tier=args.tier,
            subject=args.subject,
        )
        print(f"[OK] 记忆已记录: {cid}")
    elif args.cmd == "query":
        res = rag.query(args.query, top_k=args.top_k)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.cmd == "brief":
        print(rag.generate_context_brief(args.query))
    elif args.cmd == "ingest":
        counts = rag.ingest_from_workspace()
        print(f"[OK] 导入完成: {counts}")

    rag.close()


if __name__ == "__main__":
    main()
