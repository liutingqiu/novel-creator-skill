#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""占位符过滤：专有名词未定稿时，[待定]/[暂代] 不应进入图谱。"""

import shutil
import tempfile
import unittest
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from novel_rag_core import NovelRAG
from common import write_text


WORLD = """# 世界状态

## 势力分布
| 势力代号 | 层级定位 |
|---|---|
| [初期宗门] | 底层牢笼 |
| [待定宗门] | 占位 |
| [暂定代号：激进教派] | 地下反抗 |
"""

TRACKER = """# 角色

## 主角：`[主角 - 暂代名：陈洛/待定]`
- 当前状态：待写

### 玄阳子
- 身份：掌门
- 与主角关系：死敌
"""


class TestPlaceholderFilter(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rag_placeholder_"))
        write_text(self.tmp / "00_memory" / "world_state.md", WORLD)
        write_text(self.tmp / "00_memory" / "character_tracker.md", TRACKER)
        self.rag = NovelRAG(self.tmp)
        self.rag.ingest_from_workspace()
        self.names = {r[0] for r in self.rag.conn.execute("SELECT name FROM entities")}

    def tearDown(self):
        self.rag.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_placeholder_rows_skipped(self):
        self.assertNotIn("待定宗门", self.names)
        self.assertNotIn("暂定代号：激进教派", self.names)

    def test_real_row_kept(self):
        self.assertIn("初期宗门", self.names)

    def test_placeholder_protagonist_skipped(self):
        self.assertFalse(any("待定" in n for n in self.names), self.names)
        self.assertFalse(any("暂代" in n for n in self.names), self.names)

    def test_named_character_kept(self):
        self.assertIn("玄阳子", self.names)

    def test_bracket_heading_with_pending_annotation_is_skipped(self):
        """### `[初期Boss - 宗门掌门]`（名字待定） 这类标题不应入库。"""
        write_text(
            self.tmp / "00_memory" / "character_tracker.md",
            "# 角色\n\n## 主角：陈洛\n- 当前状态：待写\n\n"
            "### `[初期Boss - 宗门掌门]`（名字待定）\n- 身份：掌门\n- 与主角关系：死敌\n",
        )
        self.rag.ingest_from_workspace()
        names = {r[0] for r in self.rag.conn.execute("SELECT name FROM entities")}
        self.assertFalse(any("初期Boss" in n for n in names), names)
        self.assertFalse(any("`" in n or n.startswith("[") for n in names), names)


class TestPrune(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rag_prune_"))
        self.rag = NovelRAG(self.tmp)

    def tearDown(self):
        self.rag.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_prune_removes_legacy_junk_only(self):
        self.rag.add_entity("初期宗门_待定", "faction")
        self.rag.add_entity("规则", "faction")
        self.rag.add_entity("`[初期Boss - 掌门]`", "character")
        self.rag.add_entity("陈洛", "character")
        self.rag.add_relation("陈洛", "初期宗门_待定", "敌对")

        result = self.rag.prune_placeholder_entities()
        self.assertEqual(result["entities"], 3)

        names = {r[0] for r in self.rag.conn.execute("SELECT name FROM entities")}
        self.assertEqual(names, {"陈洛"})
        rels = self.rag.conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        self.assertEqual(rels, 0, "被清理实体的关系也要一并删除")


if __name__ == "__main__":
    unittest.main()
