#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Obsidian 动态知识图谱与双链桥接器。

功能：
1. 导出 (Export)：将 Novel-RAG SQLite 中的实体、关系导出为标准 Obsidian Markdown 双链笔记
   与 `.canvas` 无限白板画布文件，供 Obsidian Graph View 与 Canvas 直接可视化渲染。
2. 导入 (Import)：解析 Obsidian Vault 中的 Markdown 笔记，提取 YAML Frontmatter 和 `[[WikiLinks]]`，
   双向回写同步更新 Novel-RAG 的实体库与关系表。
"""

import argparse
import json
import math
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import ensure_dir, normalize_text, read_text, write_text
from novel_rag_core import NovelRAG

WIKILINK_RE = re.compile(r"\[\[([^\|\]\n]+)(?:\|([^\]\n]+))?\]\]")
FRONTMATTER_RE = re.compile(r"^---\s*\n([\s\S]*?)\n---\s*\n")


class ObsidianBridge:
    """Obsidian 双链与图谱桥接器。"""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.rag = NovelRAG(self.project_root)
        self.worldview_dir = self.project_root / "00_worldview"
        self.entities_dir = self.worldview_dir / "entities"
        ensure_dir(self.entities_dir)

    def close(self):
        self.rag.close()

    # ──────────────────────────────────────────────────────────
    # 导出到 Obsidian Vault
    # ──────────────────────────────────────────────────────────

    def export_entities_to_vault(self) -> int:
        """将 SQLite 实体与关系导出为 Obsidian 实体双链笔记。"""
        cur = self.rag.conn.cursor()
        cur.execute("SELECT * FROM entities")
        entities = cur.fetchall()

        cur.execute("SELECT * FROM relations WHERE status = 'active'")
        relations = cur.fetchall()

        # 构建关系索引: entity_name -> [(target, rel, note)]
        rel_map: Dict[str, List[Dict[str, str]]] = {}
        for r in relations:
            a, b, rel, note = r["a"], r["b"], r["rel"], r["note"] or ""
            rel_map.setdefault(a, []).append({"target": b, "rel": rel, "note": note})

        exported_count = 0
        for ent in entities:
            name = ent["name"]
            etype = ent["etype"]
            note = ent["note"] or ""
            aliases_str = ent["aliases"] or ""
            aliases_list = [a.strip() for a in aliases_str.split(",") if a.strip()]

            # 笔记文件名
            file_name = f"{etype}_{name}.md"
            target_path = self.entities_dir / file_name

            # 构建 YAML frontmatter
            frontmatter_lines = [
                "---",
                f"name: \"{name}\"",
                f"type: \"{etype}\"",
                f"tier: {ent['tier']}",
                f"status: \"{ent['status']}\"",
            ]
            if aliases_list:
                aliases_formatted = ", ".join(f'"{a}"' for a in aliases_list)
                frontmatter_lines.append(f"aliases: [{aliases_formatted}]")
            frontmatter_lines.append("---")

            # 构建 Markdown 正文
            body_lines = [
                f"# {name}",
                "",
                f"> **类别**: `{etype}` | **层级**: Tier {ent['tier']}",
            ]
            if note:
                body_lines.append(f"> **简介**: {note}")

            # 关系网络
            out_rels = rel_map.get(name, [])
            if out_rels:
                body_lines.append("\n## 🕸️ 关系网络")
                for rel_info in out_rels:
                    target = rel_info["target"]
                    rel_type = rel_info["rel"]
                    r_note = f" （{rel_info['note']}）" if rel_info["note"] else ""
                    body_lines.append(f"- **{rel_type}** ➔ [[{target}]]{r_note}")

            # 关联记忆
            cur.execute(
                """
                SELECT mtype, claim, superseded_by
                FROM memories
                WHERE claim LIKE ? AND superseded_by IS NULL
                LIMIT 10
                """,
                (f"%{name}%",),
            )
            mems = cur.fetchall()
            if mems:
                body_lines.append("\n## 📖 关联法则与设定")
                for m in mems:
                    body_lines.append(f"- `[{m['mtype']}]` {m['claim']}")

            full_content = "\n".join(frontmatter_lines) + "\n\n" + "\n".join(body_lines)
            write_text(target_path, full_content)
            exported_count += 1

        # 同时生成 Mermaid 关系图汇总页
        self._export_mermaid_summary(entities, relations)

        return exported_count

    def _export_mermaid_summary(self, entities: List[Any], relations: List[Any]):
        """生成支持 Obsidian 实时渲染的全局关系 Mermaid 汇总页。"""
        summary_path = self.worldview_dir / "00_全景关系图谱.md"
        lines = [
            "# 🌌 世界观全局关系图谱",
            "",
            "> 本图谱由 Novel-RAG 引擎自动生成，在 Obsidian 中支持直接交互预览与跳转。",
            "",
            "```mermaid",
            "graph TD",
        ]

        # 节点定义
        node_id_map = {}
        for idx, ent in enumerate(entities):
            node_id = f"N{idx+1}"
            node_id_map[ent["name"]] = node_id
            name = ent["name"]
            etype = ent["etype"]
            lines.append(f'  {node_id}["{name} ({etype})"]')

        # 连线定义
        for r in relations:
            a, b, rel = r["a"], r["b"], r["rel"]
            id_a = node_id_map.get(a)
            id_b = node_id_map.get(b)
            if id_a and id_b:
                lines.append(f'  {id_a} -->|"{rel}"| {id_b}')

        lines.extend([
            "```",
            "",
            "## 📌 实体索引速查",
        ])
        for ent in entities:
            lines.append(f"- [[{ent['name']}]] ({ent['etype']}): {ent['note'] or '无说明'}")

        write_text(summary_path, "\n".join(lines))

    def export_canvas(self) -> Path:
        """导出 Obsidian Canvas (.canvas) JSON 白板画布。"""
        canvas_path = self.worldview_dir / "worldview_canvas.canvas"

        cur = self.rag.conn.cursor()
        cur.execute("SELECT * FROM entities WHERE status = 'active'")
        entities = cur.fetchall()

        cur.execute("SELECT * FROM relations WHERE status = 'active'")
        relations = cur.fetchall()

        nodes = []
        edges = []
        node_id_map = {}

        # 布局算法：按实体类别分组或网格排布
        cols = 4
        node_w, node_h = 240, 120
        gap_x, gap_y = 60, 60

        type_colors = {
            "character": "1",    # 红色
            "faction": "2",      # 橙色
            "worldrule": "3",    # 黄色
            "item": "4",         # 绿色
            "location": "5",     # 青色
            "power_system": "6", # 紫色
        }

        for idx, ent in enumerate(entities):
            node_id = f"node_{uuid.uuid4().hex[:8]}"
            node_id_map[ent["name"]] = node_id

            col = idx % cols
            row = idx // cols
            x = col * (node_w + gap_x)
            y = row * (node_h + gap_y)

            color = type_colors.get(ent["etype"], "1")
            file_link = f"00_worldview/entities/{ent['etype']}_{ent['name']}.md"

            content = f"### [[{ent['name']}]]\n**类型**: {ent['etype']}\n{ent['note'] or ''}"

            nodes.append({
                "id": node_id,
                "x": x,
                "y": y,
                "width": node_w,
                "height": node_h,
                "type": "text",
                "text": content,
                "color": color,
            })

        for r in relations:
            a, b, rel = r["a"], r["b"], r["rel"]
            id_a = node_id_map.get(a)
            id_b = node_id_map.get(b)
            if id_a and id_b:
                edge_id = f"edge_{uuid.uuid4().hex[:8]}"
                edges.append({
                    "id": edge_id,
                    "fromNode": id_a,
                    "fromSide": "right",
                    "toNode": id_b,
                    "toSide": "left",
                    "label": rel,
                })

        canvas_data = {"nodes": nodes, "edges": edges}
        write_text(canvas_path, json.dumps(canvas_data, ensure_ascii=False, indent=2))
        return canvas_path

    # ──────────────────────────────────────────────────────────
    # 从 Obsidian Vault 导入回写 SQLite
    # ──────────────────────────────────────────────────────────

    def import_from_vault(self) -> Dict[str, int]:
        """解析 Vault 中所有的 Markdown 笔记，双向回写实体与双链关系。"""
        counts = {"entities": 0, "relations": 0}

        # 扫描整个项目的 md 文件
        md_files = list(self.project_root.glob("**/*.md"))
        for md_path in md_files:
            # 跳过缓存或归档
            if ".novel_rag" in str(md_path) or ".git" in str(md_path):
                continue

            content = read_text(md_path)
            if not content.strip():
                continue

            # 1. 解析 Frontmatter
            ent_name = md_path.stem
            if "_" in ent_name:
                # 可能是 etype_name
                parts = ent_name.split("_", 1)
                etype_guess = parts[0]
                pure_name = parts[1]
            else:
                etype_guess = "concept"
                pure_name = ent_name

            fm_match = FRONTMATTER_RE.match(content)
            etype = etype_guess
            aliases = ""
            note = ""
            tier = 1

            if fm_match:
                fm_text = fm_match.group(1)
                for line in fm_text.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k == "name":
                            pure_name = v
                        elif k == "type":
                            etype = v
                        elif k == "tier":
                            try:
                                tier = int(v)
                            except ValueError:
                                pass
                        elif k == "aliases":
                            aliases = v.strip("[]").replace('"', "").replace("'", "")

            # 提取正文简介
            note_match = re.search(r">\s*(?:\*\*[^\*]+\*\*\s*[:：]\s*)?([^\n]+)", content)
            if note_match:
                note = note_match.group(1).strip()

            if pure_name and etype in ["character", "faction", "location", "item", "worldrule", "power_system"]:
                self.rag.add_entity(
                    name=pure_name,
                    etype=etype,
                    aliases=aliases,
                    note=note,
                    tier=tier,
                )
                counts["entities"] += 1

            # 2. 提取 [[WikiLinks]] 双链作为关系
            links = WIKILINK_RE.findall(content)
            for link_target, _alias in links:
                target_clean = link_target.strip()
                if "_" in target_clean:
                    target_clean = target_clean.split("_", 1)[-1]

                if pure_name and target_clean and pure_name != target_clean:
                    # 记录单向关联
                    self.rag.add_relation(
                        a=pure_name,
                        b=target_clean,
                        rel="关联",
                        note=f"源自笔记 [[{md_path.name}]]",
                    )
                    counts["relations"] += 1

        return counts


# ──────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Obsidian 双链与图谱桥接器")
    subparsers = parser.add_subparsers(dest="cmd")

    export_p = subparsers.add_parser("export", help="导出实体与关系为 Obsidian 笔记")
    export_p.add_argument("--project-root", default=".", help="小说项目目录")

    canvas_p = subparsers.add_parser("canvas", help="导出 Obsidian Canvas 白板")
    canvas_p.add_argument("--project-root", default=".", help="小说项目目录")

    import_p = subparsers.add_parser("import", help="从 Obsidian 双链笔记解析并回写 SQLite")
    import_p.add_argument("--project-root", default=".", help="小说项目目录")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    project_root = Path(args.project_root)
    bridge = ObsidianBridge(project_root)

    if args.cmd == "export":
        cnt = bridge.export_entities_to_vault()
        canvas_path = bridge.export_canvas()
        print(f"[OK] 成功导出 {cnt} 个实体笔记至 00_worldview/entities/")
        print(f"[OK] 成功导出 Canvas 画布: {canvas_path}")
    elif args.cmd == "canvas":
        canvas_path = bridge.export_canvas()
        print(f"[OK] 成功生成 Canvas 画布: {canvas_path}")
    elif args.cmd == "import":
        counts = bridge.import_from_vault()
        print(f"[OK] 成功从 Vault 导入: {counts}")

    bridge.close()


if __name__ == "__main__":
    main()
