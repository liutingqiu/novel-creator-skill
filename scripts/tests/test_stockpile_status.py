#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""存稿看板的回归用例。"""

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import stockpile_status as ss


class TestStockpile(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stockpile_"))

    def write(self, name, text):
        (self.tmp / name).write_text(text, encoding="utf-8")

    def test_count_chars_ignores_whitespace(self):
        self.assertEqual(ss.count_chars("一二 三\n四"), 4)

    def test_parse_chapter_number(self):
        self.assertEqual(ss.parse_chapter(Path("第007章-废坑.md")), 7)
        self.assertIsNone(ss.parse_chapter(Path("说明.md")))

    def test_summarize_detects_duplicates(self):
        self.write("第001章-a.md", "甲" * 1200)
        self.write("第001章-b.md", "乙" * 800)
        groups = ss.scan(self.tmp)
        summary = ss.summarize(groups, 7000)
        self.assertEqual(summary["chapters"], 1)
        self.assertEqual(len(summary["duplicates"]), 1)

    def test_summarize_detects_missing(self):
        self.write("第001章-a.md", "甲" * 1200)
        self.write("第003章-c.md", "丙" * 1200)
        summary = ss.summarize(ss.scan(self.tmp), 7000)
        self.assertEqual(summary["missing"], [2])

    def test_stub_detection(self):
        self.write("第001章-a.md", "短")
        summary = ss.summarize(ss.scan(self.tmp), 7000)
        self.assertEqual(summary["stubs"], [1])

    def test_buffer_days(self):
        self.write("第001章-a.md", "字" * 14000)
        summary = ss.summarize(ss.scan(self.tmp), 7000)
        self.assertAlmostEqual(summary["buffer_days"], 2.0, places=3)

    def test_check_flags_traditional(self):
        problems = ss.check_text("他們說這本書很好看")
        self.assertTrue(any("繁体" in p for p in problems))

    def test_check_flags_external_link(self):
        problems = ss.check_text("详见 https://example.com")
        self.assertTrue(any("外链" in p for p in problems))

    def test_check_clean_text(self):
        self.assertEqual(ss.check_text("他挪了半尺，雷从后山走了。"), [])


if __name__ == "__main__":
    unittest.main()
