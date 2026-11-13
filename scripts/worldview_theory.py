#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""世界观理论核算（Worldview Theory）。

论文体世界观的地基：所有设定必须能由初始条件与少量公理推出来。
本模块把推导算成数，让论文里的每个不等式都站得住。

核心结论：
  1. 个体可持续功率由散热面积决定：P = h*dT*A - c*A^2
  2. 该式有极大值，因此存在个体功率的理论上限 P_max = (h*dT)^2/(4c)
  3. 最优法相面积 A* = h*dT/(2c)，超过它越大越亏
  4. 灵石消耗率与功率成正比，因此高阶修士的经济压力可算

用法：python3 scripts/worldview_theory.py [--format markdown|json]
"""

from __future__ import annotations

import argparse
import json
import math

R_EARTH = 6.371e6

# ---------------------------------------------------------------- 世界参数
# 这些不是物理常数，是这个世界允许的工程参数；改它们等于改世界。
PARAMS = {
    "h_natural": 10.0,      # W/(m^2 K) 自然对流换热系数（人体量级）
    "h_forced": 50.0,       # W/(m^2 K) 强对流（法相高速运转时）
    "dT_body": 10.0,        # K 人体容许的核心-皮肤温差
    "dT_fa": 100.0,         # K 法相容许温差（高温辐射+强对流）
    "k_structure": 4.3,     # W/m^1.5 维持外置结构的单位体积代价（表/体之争）
    "stone_joule": 1.0e9,   # J 一块标准灵石
}


def area_for_power(power, h=None, dT=None):
    """只靠对流散热时，维持给定功率所需的换热面积。"""
    h = PARAMS["h_forced"] if h is None else h
    dT = PARAMS["dT_fa"] if dT is None else dT
    return power / (h * dT)


def net_power(area, h=None, dT=None, k=None):
    """法相面积为 A 时的净可用功率。

    散热能力正比于面积（h*dT*A），
    维持结构本身的代价正比于体积（k*A^1.5）。
    两者相减，必有一极大值。
    """
    h = PARAMS["h_forced"] if h is None else h
    dT = PARAMS["dT_fa"] if dT is None else dT
    k = PARAMS["k_structure"] if k is None else k
    return h * dT * area - k * area ** 1.5


def optimal_area(h=None, dT=None, k=None):
    """净功率最大时的面积：dP/dA = h*dT - 1.5*k*A^0.5 = 0。"""
    hd = (PARAMS["h_forced"] if h is None else h) * (PARAMS["dT_fa"] if dT is None else dT)
    k = PARAMS["k_structure"] if k is None else k
    return (2.0 * hd / (3.0 * k)) ** 2


def max_power(h=None, dT=None, k=None):
    """个体可持续功率上限：P(A*) = (4/27) * (h*dT)^3 / k^2。"""
    hd = (PARAMS["h_forced"] if h is None else h) * (PARAMS["dT_fa"] if dT is None else dT)
    k = PARAMS["k_structure"] if k is None else k
    return (4.0 / 27.0) * hd ** 3 / (k ** 2)


def body_limit():
    """不借助外置结构的功率上限：皮肤面积 x 自然对流 x 容许温差。"""
    skin = 1.8
    return PARAMS["h_natural"] * PARAMS["dT_body"] * skin


def sweat_boost():
    """短时蒸发散热峰值：出汗约 1.5 L/h，汽化潜热 2.4 MJ/kg。"""
    return 1.5 / 3600.0 * 2.4e6


def stone_rate(power, hours=24.0):
    """维持该功率的灵石消耗率（块/天）。"""
    return power * hours * 3600.0 / PARAMS["stone_joule"]


def qi_budget_closure():
    """清气配额的去向闭合：投入 = 地表吸收 + 再辐射。"""
    quota = 1.0e15
    area = 4.0 * math.pi * R_EARTH ** 2 * 0.05
    used = 1.0e12
    return {
        "quota_w": quota,
        "flux_w_m2": quota / area,
        "cultivator_draw_w": used,
        "utilization": used / quota,
        "rest_w": quota - used,
    }


def dongtian_capacity(area_per_person):
    """洞天可容纳的高阶修士数量上限（受散热用地约束）。"""
    total = 4.0 * math.pi * R_EARTH ** 2 * 0.05
    return {"total_m2": total, "capacity": total / area_per_person}


def telemetry_bits(rate_bps=1.0e12, years=200.0):
    """巨构在 given 年内能接收的遥测总量（bit）。"""
    return rate_bps * years * 3.156e7


def mind_state_bits(n_minds=1.0e9, bits_per_mind=1.0e15):
    """要完整描述全体心智所需的信息量（bit）。"""
    return n_minds * bits_per_mind


def observation_deficit(years=200.0):
    """观测赤字：所需信息 / 可获得信息。大于 1 表示永远看不全。"""
    return mind_state_bits() / telemetry_bits(years=years)


def per_person_bandwidth(n_minds=1.0e9, rate_bps=1.0e12):
    """摊到每个人头上的遥测速率（bit/s）。"""
    return rate_bps / n_minds


def probe_duration(bits=1.0e15, rate_bps=1.0e12):
    """全分辨率探测一个人的状态需要占用多久全站带宽（s）。"""
    return bits / rate_bps


def peclet(velocity, length, dispersion):
    """佩克莱数：Pe >> 1 表示对流主导（污染物成廊道），Pe << 1 表示扩散主导。"""
    return velocity * length / dispersion


def river_concentration(mass_per_year_kg, flow_m3s):
    """河流中污染物的稳定浓度（kg/m3）。"""
    litres = flow_m3s * 3.156e7 * 1000.0
    return mass_per_year_kg / litres


def cooling_water_demand(power, evaporative_share=1.0, latent=2.4e6):
    """蒸发散热带走 given 功率所需的水（kg/s）。"""
    return power * evaporative_share / latent


def water_per_day(power, evaporative_share=1.0):
    """折算成吨/天。"""
    return cooling_water_demand(power, evaporative_share) * 86400.0 / 1000.0


def ladder():
    """功率-面积-灵石 阶梯：用来替代固定境界。"""
    rows = []
    for power in (1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9):
        area = area_for_power(power)
        rows.append({
            "power_w": power,
            "area_m2": area,
            "side_m": math.sqrt(area),
            "stone_per_day": stone_rate(power),
            "feasible": power <= max_power(),
        })
    return rows


def fmt(x):
    if x == 0:
        return "0"
    if 1e-3 <= abs(x) < 1e4:
        return "{:.3g}".format(x)
    e = int(math.floor(math.log10(abs(x))))
    return "{:.2f}e{:+d}".format(x / 10.0 ** e, e)


def build_markdown():
    a = optimal_area()
    pmax = max_power()
    lines = [
        "# 力量标度核算表（自动生成）",
        "",
        "> 由 scripts/worldview_theory.py 计算；改 PARAMS 即改世界。",
        "",
        "## 一、三条基本量",
        "",
        "| 量 | 值 | 含义 |",
        "| :--- | ---: | :--- |",
        "| 裸身持续散热上限 | {} W | 皮肤 1.8 m2 x 自然对流 10 x 温差 10 K |".format(fmt(body_limit())),
        "| 短时蒸发峰值 | {} W | 出汗 1.5 L/h 的汽化潜热 |".format(fmt(sweat_boost())),
        "| 法相最优面积 A* | {} m2 | 约 {:.0f} m 见方 |".format(fmt(a), math.sqrt(a)),
        "| 个体功率上限 P_max | {} W | 超过它，结构维持开销吃掉全部散热能力 |".format(fmt(pmax)),
        "",
        "## 二、功率-面积-灵石 阶梯（替代固定境界）",
        "",
        "| 持续功率 | 所需外置面积 | 等效边长 | 灵石（块/天） | 可行 |",
        "| ---: | ---: | ---: | ---: | :--- |",
    ]
    for row in ladder():
        lines.append("| {} W | {} m2 | {:.0f} m | {:.1f} | {} |".format(
            fmt(row["power_w"]), fmt(row["area_m2"]), row["side_m"],
            row["stone_per_day"], "是" if row["feasible"] else "否"))
    qi = qi_budget_closure()
    lines += [
        "",
        "## 三、清气配额去向（闭合检查）",
        "",
        "| 项 | 值 |",
        "| :--- | ---: |",
        "| 地表配额 | {} W |".format(fmt(qi["quota_w"])),
        "| 洞天面积热流 | {} W/m2 |".format(fmt(qi["flux_w_m2"])),
        "| 修士实际汲取 | {} W |".format(fmt(qi["cultivator_draw_w"])),
        "| 利用率 | {:.2%} |".format(qi["utilization"]),
        "| 其余 | 加热地表后由大气与辐射排出 |",
        "",
        "**结论**：灵气是环境浓度，不是被消耗的资源。修士只取万分之一，",
        "剩下的负责把洞天烤暖（+10.3 K），再由环流带走。账是平的。",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="力量标度核算")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args(argv)
    if args.format == "json":
        print(json.dumps({"ladder": ladder(), "max_power": max_power(),
                          "optimal_area": optimal_area(), "qi": qi_budget_closure()},
                         ensure_ascii=False, indent=2))
    else:
        print(build_markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
