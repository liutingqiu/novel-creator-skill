#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""正文物理一致性检查的回归用例。"""

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import worldview_lint as wl


class TestWorldviewLint(unittest.TestCase):
    def test_clean_text_has_no_hits(self):
        text = "他挪了半尺，雷从后山走了。霜期又长了十天。"
        self.assertEqual(wl.lint_text(text), [])

    def test_forbidden_term_detected(self):
        hits = wl.lint_text("这一炉丹的熵在上升。")
        self.assertEqual(hits[0][1], "L001")

    def test_code_fence_is_skipped(self):
        text = "正文很干净。\n```\n量子力学\n```\n还是干净的。"
        self.assertEqual(wl.lint_text(text), [])

    def test_nolint_escape_hatch(self):
        text = "【系统日志 0x7F9B】校验失败 <!-- nolint -->"
        self.assertEqual(wl.lint_text(text), [])

    def test_forbidden_claim_detected(self):
        hits = wl.lint_text("太阳正在变暗，一年不如一年。")
        self.assertEqual(hits[0][1], "L002")

    def test_occlusion_over_limit(self):
        hits = wl.lint_text("遮挡 8%，粮价翻了三倍。")
        self.assertEqual(hits[0][1], "L003")

    def test_occlusion_at_limit_is_ok(self):
        self.assertEqual(wl.lint_text("遮挡 5%，已经到线了。"), [])

    def test_strict_mode_exit_code(self):
        demo = Path("/tmp/_wl_strict.md")
        demo.write_text("熵\n", encoding="utf-8")
        self.assertEqual(wl.main(["--path", str(demo), "--strict"]), 1)
        self.assertEqual(wl.main(["--path", str(demo)]), 0)

    def test_collect_targets_directory(self):
        root = Path("/tmp/_wl_dir")
        root.mkdir(exist_ok=True)
        (root / "a.md").write_text("干净\n", encoding="utf-8")
        self.assertEqual(len(wl.collect_targets(root)), 1)


if __name__ == "__main__":
    unittest.main()
