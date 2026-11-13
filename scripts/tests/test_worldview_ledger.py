#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""世界观账本回归：数量级结论必须稳定，不能被随手改坏。"""

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import worldview_ledger as wl


class TestLedger(unittest.TestCase):
    def test_solar_budget_order(self):
        self.assertTrue(1e17 < wl.absorbed_solar_power() < 2e17)

    def test_landauer_is_tiny_bound(self):
        # 朗道尔极限是下界：室温下必须是 1e-21 J 量级，不是"高热"
        self.assertTrue(1e-22 < wl.landauer_energy(300.0) < 1e-20)

    def test_cultivation_cannot_drive_global_climate(self):
        self.assertLess(wl.cultivation_power_share(), 1e-3)

    def test_local_pollution_is_severe(self):
        # 排污带必须真的毒：热流高于地表平均 240 W/m2 的量级
        self.assertGreater(wl.local_excess_flux(), 100.0)

    def test_star_cannot_be_drained(self):
        # 修仙总耗能 / 恒星总输出 必须小到"抽干恒星"不成立
        self.assertLess(wl.stellar_energy_ratio(), 1e-12)

    def test_occlusion_is_a_countdown(self):
        # 当前遮挡必须小到人类还能活，但 5% 崩溃线要在几百年内
        self.assertLess(wl.occlusion_now(), 0.03)
        years = wl.years_until_target_occlusion(0.05)
        self.assertTrue(50 < years < 400)

    def test_planet_heat_quota_is_survivable(self):
        self.assertLess(wl.planet_heat_budget()["warming_k"], 3.0)

    def test_radiator_is_megastructure_scale(self):
        rad = wl.world_radiators()
        self.assertGreater(rad["square_side_km"], 100.0)
        self.assertLess(rad["earth_surface_ratio"], 0.05)

    def test_check_passes_on_default_assumptions(self):
        self.assertEqual(wl.check(wl.build_facts()), [])

    def test_markdown_contains_key_sections(self):
        text = wl.build_markdown(wl.build_facts())
        for section in ["行星能量收支", "天在关帘", "朗道尔", "散热账"]:
            self.assertIn(section, text)


if __name__ == "__main__":
    unittest.main()
