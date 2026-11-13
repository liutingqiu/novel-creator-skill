#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""力量标度定律的回归用例：这些数一旦变了，世界观就变了。"""

import math
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import worldview_theory as wt


class TestPowerScaling(unittest.TestCase):
    def test_body_limit_is_physiological(self):
        # 裸身持续散热必须在百瓦量级：大了就不是人，小了就活不下去
        self.assertTrue(150 <= wt.body_limit() <= 250)

    def test_sweat_peak_is_kilowatt(self):
        self.assertTrue(500 <= wt.sweat_boost() <= 2000)

    def test_net_power_starts_at_zero(self):
        self.assertAlmostEqual(wt.net_power(0.0), 0.0)

    def test_optimum_is_a_maximum(self):
        a = wt.optimal_area()
        peak = wt.net_power(a)
        self.assertGreater(peak, wt.net_power(a * 0.5))
        self.assertGreater(peak, wt.net_power(a * 2.0))
        self.assertAlmostEqual(peak / wt.max_power(), 1.0, places=6)

    def test_max_power_is_finite_and_sane(self):
        pmax = wt.max_power()
        self.assertTrue(1e8 <= pmax <= 1e10)

    def test_stone_rate_matches_definition(self):
        # 1 kW 一天 = 86400 kJ = 0.0864 块（1 块 = 1e9 J）
        self.assertAlmostEqual(wt.stone_rate(1e3), 0.0864, places=6)

    def test_stone_rate_is_linear(self):
        self.assertAlmostEqual(wt.stone_rate(1e6) / wt.stone_rate(1e5), 10.0, places=6)

    def test_ladder_respects_ceiling(self):
        rows = wt.ladder()
        for row in rows:
            self.assertEqual(row["feasible"], row["power_w"] <= wt.max_power())

    def test_qi_budget_closes(self):
        qi = wt.qi_budget_closure()
        self.assertAlmostEqual(qi["utilization"], 1e-3, places=9)
        self.assertGreater(qi["rest_w"], 0)

    def test_dongtian_capacity_is_finite(self):
        cap = wt.dongtian_capacity(1e5)
        self.assertTrue(math.isfinite(cap["capacity"]))
        self.assertGreater(cap["capacity"], 1e6)


if __name__ == "__main__":
    unittest.main()
