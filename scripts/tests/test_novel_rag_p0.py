#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Novel-RAG P0 回归：中文召回、写库幂等、关系去重、旧库迁移。

这些用例在修复前应当是红的：
- 中文 FTS 用 unicode61，整段中文是一个 token，任何中文子串都召回 0；
- chunk_id 掺时间戳，同一句话重复 ingest 会无限增殖；
- relations 的 UNIQUE(a,b,rel,chunk_id) 在 chunk_id 为 NULL 时失效。
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from novel_rag_core import NovelRAG
from common import write_text


class TestChineseRecall(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rag_p0_recall_"))
        self.rag = NovelRAG(self.tmp)

    def tearDown(self):
        self.rag.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_relevant_chinese_memory_beats_irrelevant_tier0(self):
        """tier-0 的无关事实不能压过 tier-2 的强相关内容。"""
        self.rag.remember("主角姓名是陈洛", mtype="fact", tier=0, subject="character")
        self.rag.remember("文风基调是冷幽默反套路", mtype="preference", tier=0, subject="style")
        self.rag.remember(
            "后山禁地深处封印着开山祖师的肉身炉鼎",
            mtype="inference",
            tier=2,
            subject="plot",
        )

        res = self.rag.query("后山禁地封印了什么")
        self.assertTrue(res["memories"], "中文查询必须能召回内容")
        self.assertEqual(res["memories"][0]["claim"], "后山禁地深处封印着开山祖师的肉身炉鼎")

    def test_chinese_entity_name_is_recalled(self):
        """实体名必须能命中相关记忆，而不是只靠 tier 排序。"""
        self.rag.remember("玄阳子把外门弟子当作活体避雷针", mtype="fact", tier=1, subject="plot")
        self.rag.remember("苏凌霜与主角在破局后各奔前程", mtype="fact", tier=1, subject="plot")

        res = self.rag.query("玄阳子的计划")
        claims = [m["claim"] for m in res["memories"]]
        self.assertIn("玄阳子把外门弟子当作活体避雷针", claims)


class TestIdempotency(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rag_p0_idem_"))
        self.rag = NovelRAG(self.tmp)

    def tearDown(self):
        self.rag.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_same_claim_twice_creates_one_row(self):
        self.rag.remember("天道在三百年前碎裂过一次", mtype="fact", tier=1)
        self.rag.remember("天道在三百年前碎裂过一次", mtype="fact", tier=1)

        count = self.rag.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        self.assertEqual(count, 1, "同一句话重复写入必须幂等")

    def test_ingest_twice_does_not_grow(self):
        write_text(self.tmp / "00_memory" / "novel_plan.md", "## 绝对规则（红线）\n1. 不许圣母\n2. 不许降智\n")
        self.rag.ingest_from_workspace()
        first = self.rag.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        self.rag.ingest_from_workspace()
        second = self.rag.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        self.assertEqual(first, second, "重复 ingest 不应增加记忆")
        self.assertGreater(first, 0)


class TestRelationDedup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rag_p0_rel_"))
        self.rag = NovelRAG(self.tmp)

    def tearDown(self):
        self.rag.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_same_relation_twice_creates_one_row(self):
        self.rag.add_entity("陈洛", "character")
        self.rag.add_entity("玄阳子", "character")
        self.rag.add_relation("陈洛", "玄阳子", "死敌")
        self.rag.add_relation("陈洛", "玄阳子", "死敌")

        count = self.rag.conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        self.assertEqual(count, 1, "同一关系重复写入必须去重")


class TestLegacyDbMigration(unittest.TestCase):
    """线上已有旧库（fts 表没有 bigram 列），打开时必须自动迁移。"""

    def test_old_schema_is_migrated_and_searchable(self):
        tmp = Path(tempfile.mkdtemp(prefix="rag_p0_mig_"))
        db_dir = tmp / ".novel_rag"
        db_dir.mkdir(parents=True)
        db = db_dir / "novel_memory.db"

        conn = sqlite3.connect(str(db))
        conn.executescript(
            """
            CREATE TABLE memories (
              chunk_id TEXT PRIMARY KEY, mtype TEXT NOT NULL DEFAULT 'fact', premise TEXT,
              claim TEXT NOT NULL, falsifier TEXT, decay_class TEXT NOT NULL DEFAULT 'permanent',
              tier INTEGER NOT NULL DEFAULT 1, subject TEXT, tags TEXT, chapter_no INTEGER DEFAULT 0,
              superseded_by TEXT, superseded_reason TEXT, superseded_at REAL,
              valid_count INTEGER DEFAULT 0, invalid_count INTEGER DEFAULT 0,
              created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE VIRTUAL TABLE fts_memories USING fts5(
              chunk_id UNINDEXED, claim, premise, falsifier, subject, tags, tokenize='unicode61'
            );
            """
        )
        conn.execute(
            "INSERT INTO memories (chunk_id, mtype, claim, tier, created_at, updated_at)"
            " VALUES ('mem_fac_legacy', 'fact', '后山禁地封印着太古凶兽', 1, 1, 1)"
        )
        conn.execute(
            "INSERT INTO fts_memories (chunk_id, claim) VALUES ('mem_fac_legacy', '后山禁地封印着太古凶兽')"
        )
        conn.commit()
        conn.close()

        rag = NovelRAG(tmp)
        try:
            res = rag.query("后山禁地")
            self.assertTrue(res["memories"], "旧库迁移后中文检索必须可用")
            self.assertEqual(res["memories"][0]["chunk_id"], "mem_fac_legacy")
        finally:
            rag.close()
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
