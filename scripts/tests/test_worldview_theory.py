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



class TestInformationBudget(unittest.TestCase):
    def test_telemetry_over_two_centuries(self):
        self.assertAlmostEqual(wt.telemetry_bits() / 6.31e21, 1.0, places=2)

    def test_observation_deficit_is_order_hundred(self):
        # 赤字必须大于 1：否则"全知"就成立了，整个设定塌掉
        self.assertGreater(wt.observation_deficit(), 10.0)
        self.assertLess(wt.observation_deficit(), 1e4)

    def test_per_person_bandwidth_is_kilobit(self):
        self.assertAlmostEqual(wt.per_person_bandwidth() / 1e3, 1.0, places=6)

    def test_probe_duration_is_quarter_hour(self):
        # 天劫 = 独占全站带宽约 1000 秒
        self.assertTrue(600 <= wt.probe_duration() <= 1800)



class TestTransportAndInstitutions(unittest.TestCase):
    def test_peclet_is_advection_dominated(self):
        # 河流与大气都必须 Pe >> 1，否则"毒地成廊道"不成立
        self.assertGreater(wt.peclet(1.0, 1e4, 0.1), 1e3)
        self.assertGreater(wt.peclet(5.0, 1e4, 10.0), 1e3)

    def test_river_concentration_is_mg_per_litre(self):
        # 1e6 kg/年 排入 100 m3/s 的河，浓度应在 0.3 mg/L 量级
        mg_per_l = wt.river_concentration(1e6, 100.0) * 1e6
        self.assertTrue(0.1 < mg_per_l < 1.0)

    def test_water_demand_for_gigawatt(self):
        # 1e9 W 全蒸发散热约 3.6e4 吨/天
        self.assertAlmostEqual(wt.water_per_day(1e9) / 36000.0, 1.0, places=2)

    def test_water_demand_scales_linearly(self):
        self.assertAlmostEqual(wt.water_per_day(1e8) / wt.water_per_day(1e7), 10.0, places=6)

    def test_evaporative_share_reduces_demand(self):
        self.assertLess(wt.water_per_day(1e8, 0.3), wt.water_per_day(1e8, 1.0))



class TestDynamics(unittest.TestCase):
    def test_leyline_intake_is_kilowatt(self):
        self.assertAlmostEqual(wt.intake_rate(1e4) / 1.8e3, 1.0, places=2)

    def test_ambient_intake_is_watts(self):
        self.assertTrue(1.0 < wt.intake_rate(13.7) < 10.0)

    def test_speed_scales_as_cube_root(self):
        # 功率涨 1000 倍，速度只涨 10 倍
        ratio = wt.travel_speed(1e8) / wt.travel_speed(1e5)
        self.assertAlmostEqual(ratio, 10.0, places=1)

    def test_speed_at_1e5_is_about_87(self):
        self.assertAlmostEqual(wt.travel_speed(1e5), 87.0, delta=2.0)

    def test_reserve_time_is_hours(self):
        hours = 1e9 / 1e5 / 3600.0
        self.assertTrue(2.0 < hours < 4.0)

    def test_growth_requires_century(self):
        years = wt.years_to_power(1e8)
        self.assertTrue(80 < years < 200)

    def test_siege_is_about_two_weeks(self):
        self.assertAlmostEqual(wt.siege_days(1e6, 1e9), 11.6, delta=0.5)

    def test_logistic_starts_at_p0_and_saturates(self):
        self.assertAlmostEqual(wt.logistic_power(0) / 1e3, 1.0, places=6)
        # 长时间后贴近上限（浮点下可能相等，按相对误差判）
        self.assertAlmostEqual(wt.logistic_power(2000) / wt.max_power(), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()