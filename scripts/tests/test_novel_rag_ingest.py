#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ingest 分类回归：表头不当实体、按小节映射 etype、括号注解剥离。"""

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


WORLD_STATE = """# 世界状态追踪

## 势力分布
| 势力名 | 实力等级 | 与主角关系 |
|--------|---------|-----------|
| 太虚门 | 二流 | 死敌 |

## 已揭示等级
| 等级名 | 描述 | 揭示章节 |
|--------|------|---------|
| 凡胎境 | 起点 | 第1章 |

## 已揭示规则
| 规则 | 描述 |
|------|------|
| 接地分流律 | 能量必须接地 |

## 重要物品/资源
| 物品名 | 持有者 |
|--------|--------|
| 引雷针 | 陈洛 |

## 地理位置
| 地点名 | 类型 |
|--------|------|
| 祭坛 | 圣地 |

## 主角行踪
| 章节范围 | 位置 |
|----------|------|
| 1-3 | 祭坛 |
"""

CHARACTERS = """# 角色状态追踪器

## 主角：苏凌霜（前期假女主 / 合作者）
- 当前境界/实力：金丹
- 当前目标：破局

## 核心配角

### 玄阳子
- 身份：太虚门掌门
- 与主角关系：死敌
"""


class TestIngestClassification(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rag_ingest_"))
        write_text(self.tmp / "00_memory" / "world_state.md", WORLD_STATE)
        write_text(self.tmp / "00_memory" / "character_tracker.md", CHARACTERS)
        self.rag = NovelRAG(self.tmp)

    def tearDown(self):
        self.rag.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _etypes(self):
        return {r["name"]: r["etype"] for r in self.rag.conn.execute("SELECT name, etype FROM entities")}

    def test_table_rows_are_typed_by_section(self):
        self.rag.ingest_from_workspace()
        etypes = self._etypes()
        self.assertEqual(etypes.get("太虚门"), "faction")
        self.assertEqual(etypes.get("凡胎境"), "power_system")
        self.assertEqual(etypes.get("接地分流律"), "worldrule")
        self.assertEqual(etypes.get("引雷针"), "item")
        self.assertEqual(etypes.get("祭坛"), "location")

    def test_table_headers_are_not_entities(self):
        self.rag.ingest_from_workspace()
        names = set(self._etypes())
        for junk in ("规则", "地点名", "物品名", "章节范围", "势力名", "等级名", "内容"):
            self.assertNotIn(junk, names, f"表头 {junk} 不应成为实体")

    def test_travel_table_is_skipped(self):
        self.rag.ingest_from_workspace()
        self.assertNotIn("1-3", self._etypes())

    def test_parenthetical_annotation_is_stripped(self):
        self.rag.ingest_from_workspace()
        names = self._etypes()
        self.assertIn("苏凌霜", names)
        self.assertNotIn("苏凌霜（前期假女主 / 合作者）", names)

    def test_section_labels_are_not_characters(self):
        self.rag.ingest_from_workspace()
        names = set(self._etypes())
        self.assertNotIn("核心配角", names, "小节标题不是人物")
        self.assertIn("玄阳子", names, "带身份字段的人物卡要入库")


if __name__ == "__main__":
    unittest.main()
