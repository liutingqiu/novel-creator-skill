#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写后同步钩子：章节落盘后 RAG 与 Obsidian 产物必须自动更新。"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from novel_flow_executor import _sync_novel_rag
from common import write_text

WORLD = """# 世界状态

## 势力分布
| 势力名 | 实力 |
|---|---|
| 太虚门 | 二流 |

## 已揭示规则
| 规则 | 描述 |
|---|---|
| 接地分流律 | 过载能量沿最低阻抗泄放 |
"""


class TestSyncHook(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="novel_sync_"))
        write_text(self.tmp / "00_memory" / "world_state.md", WORLD)
        write_text(self.tmp / "00_memory" / "novel_plan.md", "## 绝对规则（红线）\n1. 不许圣母\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sync_creates_rag_and_obsidian_artifacts(self):
        result = _sync_novel_rag(self.tmp)
        self.assertTrue(result.get("ok"), result)
        self.assertTrue((self.tmp / ".novel_rag" / "novel_memory.db").exists())
        notes = list((self.tmp / "00_worldview" / "entities").glob("*.md"))
        self.assertGreaterEqual(len(notes), 1, "应导出实体笔记")
        self.assertTrue((self.tmp / "00_worldview" / "worldview_canvas.canvas").exists())
        canvas = json.loads((self.tmp / "00_worldview" / "worldview_canvas.canvas").read_text(encoding="utf-8"))
        self.assertIn("nodes", canvas)

    def test_sync_is_repeatable(self):
        first = _sync_novel_rag(self.tmp)
        second = _sync_novel_rag(self.tmp)
        self.assertTrue(first.get("ok") and second.get("ok"))
        import sqlite3
        conn = sqlite3.connect(str(self.tmp / ".novel_rag" / "novel_memory.db"))
        count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        conn.close()
        self.assertEqual(count, 1, "重复同步不应增殖记忆")


if __name__ == "__main__":
    unittest.main()
