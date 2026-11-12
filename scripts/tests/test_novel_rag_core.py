#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Novel-RAG 核心引擎与 Obsidian 图谱桥接单元测试。"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from novel_rag_core import NovelRAG
from obsidian_graph_bridge import ObsidianBridge
from common import write_text, read_text


class TestNovelRAGCore(unittest.TestCase):
    """测试 Novel-RAG 独立数据库、认识论分类与取代链。"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="test_novel_rag_"))
        self.rag = NovelRAG(self.tmpdir)

    def tearDown(self):
        self.rag.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_db_isolation(self):
        """测试数据库隔离性：必须严格存放在项目根目录下的 .novel_rag/novel_memory.db。"""
        expected_db = self.tmpdir / ".novel_rag" / "novel_memory.db"
        self.assertTrue(expected_db.exists())
        self.assertEqual(self.rag.db_path, expected_db)

    def test_remember_and_mtypes(self):
        """测试认识论类型与记忆写入。"""
        cid1 = self.rag.remember(
            claim="天道在三百年前发生过一次灵气异变",
            mtype="fact",
            tier=1,
            subject="worldrule",
        )
        self.assertTrue(cid1.startswith("mem_fac_"))

        cid2 = self.rag.remember(
            claim="主角绝不圣母，对死敌必定斩草除根",
            mtype="preference",
            tier=0,
            subject="iron_law",
        )
        self.assertTrue(cid2.startswith("mem_pre_"))

        cid3 = self.rag.remember(
            claim="掌门师兄暗中投靠了极阴魔宗",
            mtype="inference",
            premise="曾在禁地密林发现其遗落的魔道信物",
            falsifier="如果掌门师兄是在卧底则作废",
            tier=2,
            subject="plot",
        )
        self.assertTrue(cid3.startswith("mem_inf_"))

        # 验证读取
        cur = self.rag.conn.cursor()
        cur.execute("SELECT * FROM memories WHERE chunk_id = ?", (cid3,))
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["mtype"], "inference")
        self.assertEqual(row["premise"], "曾在禁地密林发现其遗落的魔道信物")
        self.assertEqual(row["falsifier"], "如果掌门师兄是在卧底则作废")

    def test_superseded_chain(self):
        """测试单向取代链与检索压制。"""
        cid_old = self.rag.remember(
            claim="后山禁地内封印着一头太古凶兽",
            mtype="inference",
            tier=2,
            subject="plot",
        )

        # 检索时应可见
        res1 = self.rag.query("后山禁地封印")
        self.assertEqual(len(res1["memories"]), 1)
        self.assertEqual(res1["memories"][0]["chunk_id"], cid_old)

        # 推翻并挂载取代链
        cid_new = self.rag.supersede(
            old_chunk_id=cid_old,
            new_claim="后山禁地封印的其实是开山祖师的肉身炉鼎",
            reason="第三卷大纲修正，取消凶兽设定",
            tier=2,
        )
        self.assertIsNotNone(cid_new)

        # 再次检索，新结论排第一，旧结论被压制在末尾并标记 superseded
        res2 = self.rag.query("后山禁地封印")
        self.assertTrue(len(res2["memories"]) >= 1)
        self.assertEqual(res2["memories"][0]["chunk_id"], cid_new)
        self.assertIsNone(res2["memories"][0]["superseded_by"])

        # 验证旧结论带有取代指针
        cur = self.rag.conn.cursor()
        cur.execute("SELECT superseded_by, superseded_reason FROM memories WHERE chunk_id = ?", (cid_old,))
        row = cur.fetchone()
        self.assertEqual(row["superseded_by"], cid_new)
        self.assertEqual(row["superseded_reason"], "第三卷大纲修正，取消凶兽设定")

    def test_entities_and_relations(self):
        """测试实体与关系网络。"""
        eid1 = self.rag.add_entity("林尘", "character", aliases="尘哥,修罗剑圣", note="主角")
        eid2 = self.rag.add_entity("太玄剑宗", "faction", note="天下第一剑派")
        self.assertGreater(eid1, 0)
        self.assertGreater(eid2, 0)

        rid = self.rag.add_relation("林尘", "太玄剑宗", "外门弃徒", note="三年前被陷害逐出")
        self.assertGreater(rid, 0)

        # 检索验证实体与关系共现
        res = self.rag.query("林尘在太玄剑宗门前拔剑")
        names = [e["name"] for e in res["entities"]]
        self.assertIn("林尘", names)
        self.assertIn("太玄剑宗", names)

        rels = [f"{r['a']}--{r['rel']}-->{r['b']}" for r in res["relations"]]
        self.assertIn("林尘--外门弃徒-->太玄剑宗", rels)

    def test_iron_law_and_negresult_alerts(self):
        """测试铁律与已否证废案的警报提取机制。"""
        self.rag.remember("绝对禁止出现女主被反派绑架威胁主角吃瘪的情节", mtype="preference", tier=0)
        self.rag.remember("通过拍卖行洗白赃物这条路不可行已被黑市反杀证明走不通", mtype="negresult", tier=1)

        res = self.rag.query("主角准备去拍卖行出手脏物并寻找女主下落")
        alert_types = [a["type"] for a in res["alerts"]]
        self.assertIn("negresult", alert_types)

        brief = self.rag.generate_context_brief("拍卖行 出手 脏物 女主")
        self.assertIn("⚠️ 铁律红线与避坑警示", brief)
        self.assertIn("🚫 【已否证废案】", brief)


class TestObsidianBridge(unittest.TestCase):
    """测试 Obsidian 双链笔记导出、Canvas 画布生成与反向导入。"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="test_obsidian_"))
        self.bridge = ObsidianBridge(self.tmpdir)

    def tearDown(self):
        self.bridge.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_export_and_canvas(self):
        """测试将实体导出为 Obsidian 双链 Markdown 与 .canvas 白板。"""
        self.bridge.rag.add_entity("叶孤舟", "character", note="天生剑心")
        self.bridge.rag.add_entity("洗剑池", "location", note="铸剑古地")
        self.bridge.rag.add_relation("叶孤舟", "洗剑池", "闭关之地")

        cnt = self.bridge.export_entities_to_vault()
        self.assertEqual(cnt, 2)

        # 检查导出的 markdown 文件
        char_file = self.tmpdir / "00_worldview" / "entities" / "character_叶孤舟.md"
        self.assertTrue(char_file.exists())
        content = read_text(char_file)
        self.assertIn("name: \"叶孤舟\"", content)
        self.assertIn("[[洗剑池]]", content)

        # 检查 Canvas 画布
        canvas_file = self.bridge.export_canvas()
        self.assertTrue(canvas_file.exists())
        canvas_data = json.loads(read_text(canvas_file))
        self.assertIn("nodes", canvas_data)
        self.assertIn("edges", canvas_data)
        self.assertEqual(len(canvas_data["nodes"]), 2)
        self.assertEqual(len(canvas_data["edges"]), 1)
        self.assertEqual(canvas_data["edges"][0]["label"], "闭关之地")

    def test_import_from_vault(self):
        """测试从 Obsidian Markdown 提取 [[WikiLinks]] 双链并同步回 SQLite。"""
        # 手工创建一个 Obsidian 双链笔记
        note_path = self.tmpdir / "00_worldview" / "entities" / "faction_九黎神朝.md"
        raw_markdown = """---
name: "九黎神朝"
type: "faction"
tier: 1
aliases: ["九黎皇室"]
---

# 九黎神朝

> 南域第一不朽神朝

## 关系网络
- **死敌** ➔ [[大荒巫教]]
- **附属** ➔ [[灵宝商会]]
"""
        write_text(note_path, raw_markdown)

        counts = self.bridge.import_from_vault()
        self.assertGreaterEqual(counts["entities"], 1)
        self.assertGreaterEqual(counts["relations"], 2)

        # 检查 SQLite 中的数据
        cur = self.bridge.rag.conn.cursor()
        cur.execute("SELECT * FROM entities WHERE name = '九黎神朝'")
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["etype"], "faction")
        self.assertEqual(row["aliases"], "九黎皇室")

        cur.execute("SELECT * FROM relations WHERE a = '九黎神朝'")
        rels = cur.fetchall()
        targets = [r["b"] for r in rels]
        self.assertIn("大荒巫教", targets)
        self.assertIn("灵宝商会", targets)


if __name__ == "__main__":
    unittest.main()
