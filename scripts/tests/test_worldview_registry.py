#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""依赖登记的回归用例：改一条公理必须能查出影响面。"""

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import worldview_registry as wr


class TestRegistry(unittest.TestCase):
    def test_dependencies_are_complete_and_acyclic(self):
        self.assertEqual(wr.check(), [])

    def test_impact_of_structure_cost(self):
        hits = wr.impact("k_structure")
        self.assertIn("T3.3", hits)
        self.assertIn("T6.4", hits)

    def test_impact_of_thermodynamics_is_broad(self):
        hits = wr.impact("A2")
        self.assertIn("T2.1", hits)
        self.assertGreater(len(hits), 5)

    def test_impact_prefers_downstream_only(self):
        # 上游不应出现在下游列表里
        self.assertNotIn("A2", wr.impact("k_structure"))

    def test_every_prediction_has_source_theorem(self):
        ids = {t["id"] for t in wr.THEOREMS}
        for p in wr.PREDICTIONS:
            self.assertIn(p["from"], ids)

    def test_every_theorem_cites_something(self):
        for t in wr.THEOREMS:
            self.assertTrue(t["up"], t["id"])

    def test_graph_renders(self):
        text = wr.render_graph()
        self.assertIn("graph LR", text)
        self.assertIn("T3.3", text)

    def test_constants_table_renders(self):
        text = wr.render_constants()
        self.assertIn("k_structure", text)
        self.assertIn("W/m^1.5", text)


if __name__ == "__main__":
    unittest.main()
