#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""世界观能量与尺度账本（Worldview Energy & Scale Ledger）。

"理论现实修仙"最容易被读者击穿的地方不是设定够不够炫，而是数量级。
本模块把世界观里所有会被追问的宏观量算一遍，用真实物理常数给出上下界，
让审查结论可复算、可回归，而不是靠感觉。

用法：
    python scripts/worldview_ledger.py                # 打印 Markdown 账本
    python scripts/worldview_ledger.py --format json  # 机器可读
    python scripts/worldview_ledger.py --check        # 只做断言，违反则退出码 1
    python scripts/worldview_ledger.py --out FILE     # 写入文件

注意：本文件只做物理核算，不修改任何设定文本。
"""

from __future__ import annotations

import argparse
import json
import math
import sys

# ---------------------------------------------------------------- 物理常数
K_B = 1.380649e-23          # J/K
SIGMA_SB = 5.670374419e-8   # W/(m^2 K^4)
AU = 1.495978707e11         # m
R_EARTH = 6.371e6           # m
L_SUN = 3.828e26            # W
SOLAR_CONSTANT = 1360.8     # W/m^2 @1AU
EARTH_ALBEDO = 0.29
GEOTHERMAL_HEAT = 4.7e13    # W，地球总热流
YEAR = 3.15576e7            # s

# ---------------------------------------------------------------- 设定假设
# 这些是"设定参数"，不是物理常数；改设定就改这里，账本自动重算。
ASSUMPTIONS = {
    "修士总数": 1.0e6,             # 一颗类地行星上的修士存量（含低阶）
    "修士平均耗散功率_W": 1.0e6,    # 幂律分布下的均值：少数高阶贡献绝大部分
    "修仙文明存续年数": 1.0e4,      # 一万年
    "凡人总数": 1.0e9,
    "排污带面积_m2": 2.0e9,         # 约 100km x 20km
    "天道常驻算力功耗_W": 1.0e16,   # 行星级治理系统的功率量级
    "天道散热器温度_K": 600.0,      # 深空辐射散热的工作温度
    "天道地表散热配额_W": 1.0e15,   # 它敢往地表倒的最大功率（超过就把宿主烤熟）
    "遮挡年增速": 3.0e-4,           # 集能群每年多挡掉的比例
    "已遮挡年数": 40.0,             # 从哪一年开始关帘
    "气候敏感度_K_per_W": 0.75,     # 每 W/m2 辐射强迫对应的平衡温度变化
}


def absorbed_solar_power():
    """地球吸收的太阳辐射功率（W）。"""
    intercepted = math.pi * R_EARTH ** 2 * SOLAR_CONSTANT
    return intercepted * (1.0 - EARTH_ALBEDO)


def landauer_energy(temperature=300.0):
    """朗道尔极限：擦除 1 bit 的最小耗散（J）。这是下界，不是上界。"""
    return K_B * temperature * math.log(2.0)


def radiator_area(power, temperature):
    """黑体辐射散热所需面积（m^2）。"""
    return power / (SIGMA_SB * temperature ** 4)


def cultivation_power_share():
    """修仙文明的持续排废功率占地球吸收太阳辐射的比例。"""
    return (ASSUMPTIONS["修士总数"] * ASSUMPTIONS["修士平均耗散功率_W"]) / absorbed_solar_power()


def local_excess_flux():
    """排污带内的额外热流密度（W/m^2）。"""
    power = ASSUMPTIONS["修士总数"] * ASSUMPTIONS["修士平均耗散功率_W"]
    return power / ASSUMPTIONS["排污带面积_m2"]


def historical_cultivation_energy():
    """一万年修仙文明累计抽取/耗散的能量（J）。"""
    return (ASSUMPTIONS["修士总数"]
            * ASSUMPTIONS["修士平均耗散功率_W"]
            * ASSUMPTIONS["修仙文明存续年数"]
            * YEAR)


def stellar_output_over_history():
    return L_SUN * ASSUMPTIONS["修仙文明存续年数"] * YEAR


def stellar_energy_ratio():
    """修仙总耗能 / 恒星同期总输出：判断"抽干恒星"是否可能。"""
    return historical_cultivation_energy() / stellar_output_over_history()


def natural_stellar_dimming_per_year():
    """主序星自然光度变化率（每年）：太阳约每 1e8 年增亮 1%。"""
    return 0.01 / 1e8


def occlusion_fraction(years, annual_growth):
    """天穹集能群按年扩张时的累计遮挡比例：1-(1-g)^n。"""
    return 1.0 - (1.0 - annual_growth) ** years


def world_radiators():
    power = ASSUMPTIONS["天道常驻算力功耗_W"]
    area = radiator_area(power, ASSUMPTIONS["天道散热器温度_K"])
    return {
        "power_w": power,
        "area_m2": area,
        "earth_surface_ratio": area / (4.0 * math.pi * R_EARTH ** 2),
        "square_side_km": math.sqrt(area) / 1000.0,
    }


def occlusion_now():
    years = ASSUMPTIONS["已遮挡年数"]
    return occlusion_fraction(years, ASSUMPTIONS["遮挡年增速"])


def occlusion_dimming_kelvin():
    """遮挡造成的辐射强迫与平衡降温（K）。地表吸收按 240 W/m2 计。"""
    forcing = -occlusion_now() * 240.0
    return forcing, forcing * ASSUMPTIONS["气候敏感度_K_per_W"]


def years_until_target_occlusion(target=0.05):
    g = ASSUMPTIONS["遮挡年增速"]
    return math.log(1.0 - target) / math.log(1.0 - g)


def planet_heat_budget():
    """天道倒到地表的散热功率，折算成全球热流与升温。"""
    power = ASSUMPTIONS["天道地表散热配额_W"]
    flux = power / (4.0 * math.pi * R_EARTH ** 2)
    return {
        "power_w": power,
        "flux_w_m2": flux,
        "warming_k": flux * ASSUMPTIONS["气候敏感度_K_per_W"],
    }


def build_facts():
    """所有核算结果，供 JSON / 断言 / Markdown 共用。"""
    earth_surface = 4.0 * math.pi * R_EARTH ** 2
    facts = {
        "solar_absorbed_w": absorbed_solar_power(),
        "earth_surface_m2": earth_surface,
        "landauer_j_per_bit_300k": landauer_energy(300.0),
        "cultivation_power_share": cultivation_power_share(),
        "local_excess_flux_w_m2": local_excess_flux(),
        "historical_cultivation_energy_j": historical_cultivation_energy(),
        "stellar_output_over_history_j": stellar_output_over_history(),
        "stellar_energy_ratio": stellar_energy_ratio(),
        "natural_stellar_dimming_per_year": natural_stellar_dimming_per_year(),
        "occlusion_now": occlusion_now(),
        "occlusion_forcing_w_m2": occlusion_dimming_kelvin()[0],
        "occlusion_cooling_k": occlusion_dimming_kelvin()[1],
        "years_until_5pct": years_until_target_occlusion(0.05),
        "planet_heat": planet_heat_budget(),
        "occlusion_100y": occlusion_fraction(100.0, 0.003),
        "occlusion_300y": occlusion_fraction(300.0, 0.003),
        "occlusion_1000y": occlusion_fraction(1000.0, 0.003),
        "world_radiators": world_radiators(),
        "assumptions": dict(ASSUMPTIONS),
    }
    return facts


def fmt(value):
    """科学计数法，保留两位有效数字，便于人眼比较数量级。"""
    if value == 0:
        return "0"
    if 1e-3 <= abs(value) < 1e4:
        return "{:.3g}".format(value)
    exp = int(math.floor(math.log10(abs(value))))
    mant = value / (10.0 ** exp)
    return "{:.2f}e{:+d}".format(mant, exp)


def build_markdown(facts):
    rad = facts["world_radiators"]
    lines = [
        "# 世界观能量与尺度账本",
        "",
        "> **自动生成文件，请勿手改。** 由 scripts/worldview_ledger.py 计算；",
        "> 改设定参数请改脚本顶部的 ASSUMPTIONS，然后重跑。",
        "",
        "这份账本只回答一个问题：**设定里的数，能不能过数量级这一关。**",
        "凡是被读者用计算器一按就塌的设定，都写不进正文。",
        "",
        "## 一、行星能量收支",
        "",
        "| 项目 | 数值 | 说明 |",
        "| :--- | ---: | :--- |",
        "| 大气顶太阳辐射截获 | {} W | 太阳常数 1360.8 W/m2 x 地球截面 |".format(
            fmt(math.pi * R_EARTH ** 2 * SOLAR_CONSTANT)),
        "| 地表实际吸收 | {} W | 扣除反照率 0.29 |".format(fmt(facts["solar_absorbed_w"])),
        "| 地球内部热流 | {} W | 地幔对流+放射性衰变，占比可忽略 |".format(fmt(GEOTHERMAL_HEAT)),
        "| 地球表面积 | {} m2 | 全部排污与散热的物理上限 |".format(fmt(facts["earth_surface_m2"])),
        "",
        "## 二、修仙文明的功率占比（决定浊煞能有多大影响）",
        "",
        "| 项目 | 数值 | 结论 |",
        "| :--- | ---: | :--- |",
        "| 修士总数假设 | {} | 设定参数 |".format(fmt(ASSUMPTIONS["修士总数"])),
        "| 单人平均排废功率 | {} W | 金丹级持续耗散 |".format(fmt(ASSUMPTIONS["修士平均耗散功率_W"])),
        "| 修仙文明总排废 | {} W | 人数 x 单人功率 |".format(
            fmt(ASSUMPTIONS["修士总数"] * ASSUMPTIONS["修士平均耗散功率_W"])),
        "| 占地表吸收比例 | {:.3g} | **不可能驱动全球气候** |".format(facts["cultivation_power_share"]),
        "| 排污带内额外热流 | {} W/m2 | 对比地表平均 240 W/m2，**局地灾变成立** |".format(
            fmt(facts["local_excess_flux_w_m2"])),
        "",
        "**硬结论**：浊煞只能是局地生态灾难，不能是全球变暖。",
        "要写整个凡间都在腐烂，就必须写成：凡间的好地都被仙门占了，只剩排污带能活。",
        "这是政治地理，不是热力学。这条限制反而更黑暗、更好写。",
        "",
        "## 三、抽干恒星能不能成立",
        "",
        "| 项目 | 数值 |",
        "| :--- | ---: |",
        "| 一万年修仙累计耗能 | {} J |".format(fmt(facts["historical_cultivation_energy_j"])),
        "| 恒星同期总输出 | {} J |".format(fmt(facts["stellar_output_over_history_j"])),
        "| 比值 | {} |".format(fmt(facts["stellar_energy_ratio"])),
        "| 主序星自然光度变化 | {}/年 |".format(fmt(facts["natural_stellar_dimming_per_year"])),
        "",
        "**硬结论**：修仙文明的全部能耗比恒星一万年的输出小十几个数量级。",
        "要让主序星在千年尺度上肉眼可见地变暗，需要的不是抽能量，是改质量。",
        "所以太阳快死了必须另有解释。",
        "",
        "## 四、替代方案：天穹闭合（遮挡）",
        "",
        "天道不是把恒星抽干，而是逐年扩大轨道集能群的遮挡面积来补自己的功率缺口。",
        "",
        "| 年扩张率 | 100 年 | 300 年 | 1000 年 | 观感 |",
        "| ---: | ---: | ---: | ---: | :--- |",
        "| 0.3% | {:.1%} | {:.1%} | {:.1%} | 每代人都能察觉，但不会活不过一代 |".format(
            facts["occlusion_100y"], facts["occlusion_300y"], facts["occlusion_1000y"]),
        "",
        "这个方案同时解决四件事：恒星光度不需要变；逐年变暗有了物理机制；",
        "太阳发红是低角度光穿过厚大气与气溶胶的光学效果，不用改恒星；",
        "第二卷名场面的攻击目标从恒星核心变成遮挡控制，更可打、更可信。",
        "",
        "## 五、天道的散热账（它为什么要地表）",
        "",
        "| 项目 | 数值 |",
        "| :--- | ---: |",
        "| 常驻算力功耗 | {} W |".format(fmt(rad["power_w"])),
        "| 600 K 散热所需面积 | {} m2 |".format(fmt(rad["area_m2"])),
        "| 相当于地球表面积 | {:.3g} |".format(rad["earth_surface_ratio"]),
        "| 等效方形散热阵边长 | {:.0f} km |".format(rad["square_side_km"]),
        "",
        "**硬结论**：轨道散热阵是千公里级巨构，完全暴露在微流星与热循环里，会坏、且修不起。",
        "把计算搬到有大气、有水循环、有生物圈的行星表面，等于用对流和蒸发潜热替它散热。",
        "这就是把修士当电池的真正底层动机：不是缺电，是缺散热面积和备件。",
        "",
        "## 六、地表热预算：它敢往地上倒多少热",
        "",
        "| 项目 | 数值 |",
        "| :--- | ---: |",
        "| 地表散热配额 | {} W |".format(fmt(facts["planet_heat"]["power_w"])),
        "| 折算全球额外热流 | {:.2f} W/m2 |".format(facts["planet_heat"]["flux_w_m2"]),
        "| 对应平衡升温 | {:+.2f} K |".format(facts["planet_heat"]["warming_k"]),
        "",
        "**硬结论**：把 1e16 W 全倒到地上会烤熟行星（+15 K 量级），所以它只能倒一小部分。",
        "这条配额就是灵气总量的物理上限，也是神朝收税、宗门争配额的物质基础。",
        "",
        "## 七、天在关帘：遮挡的进度表",
        "",
        "| 项目 | 数值 |",
        "| :--- | ---: |",
        "| 当前遮挡比例（已关 {:g} 年） | {:.2%} |".format(ASSUMPTIONS["已遮挡年数"], facts["occlusion_now"]),
        "| 辐射强迫 | {:.1f} W/m2 |".format(facts["occlusion_forcing_w_m2"]),
        "| 对应平衡降温 | {:.1f} K |".format(facts["occlusion_cooling_k"]),
        "| 遮挡到 5%（农业崩溃线）还需 | {:.0f} 年 |".format(facts["years_until_5pct"]),
        "",
        "**硬结论**：遮挡不是背景装饰，它是一条**倒计时**。",
        "关得太快，生物圈先死（它自己也需要生物圈散热）；关得太慢，它的功率缺口补不上。",
        "两头都是死线，这就是全书的时间压力。",
        "",
        "## 八、朗道尔极限的正确用法",
        "",
        "| 项目 | 数值 |",
        "| :--- | ---: |",
        "| 300 K 下擦除 1 bit 的最小耗散 | {} J |".format(fmt(facts["landauer_j_per_bit_300k"])),
        "| 每秒擦除 1e20 bit 的最小耗散 | {} W |".format(
            fmt(facts["landauer_j_per_bit_300k"] * 1e20)),
        "",
        "**硬结论**：朗道尔极限是下界，数值极小，它永远不是危机的直接原因。",
        "它是为什么不能靠无限算力硬解的理由：算得越多，下限散热越大，而散热面积有限。",
        "危机在散热瓶颈，不在极限本身。草案 v1.0 写成擦除信息产生极限高热，方向反了。",
        "",
        "---",
        "",
        "## 附：设定参数（改这里，全表重算）",
        "",
        "```json",
        json.dumps(ASSUMPTIONS, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)


def check(facts):
    """硬性断言。返回失败项列表；空列表表示通过。"""
    failures = []

    if not (1e17 < facts["solar_absorbed_w"] < 2e17):
        failures.append("地表吸收太阳辐射应在 1.2e17 W 量级，实得 {}".format(fmt(facts["solar_absorbed_w"])))

    if facts["cultivation_power_share"] > 1e-3:
        failures.append("修仙排废占比 {} 过高：设定已滑向全球气候灾变，与账本结论冲突".format(
            fmt(facts["cultivation_power_share"])))

    if facts["local_excess_flux_w_m2"] < 10.0:
        failures.append("排污带额外热流过小，局地灾变不成立")

    if facts["stellar_energy_ratio"] > 1e-12:
        failures.append("修仙耗能与恒星光度同量级，物理上不成立：必须改用遮挡方案")

    if facts["landauer_j_per_bit_300k"] > 1e-20:
        failures.append("朗道尔极限数量级异常")

    rad = facts["world_radiators"]
    if rad["area_m2"] > facts["earth_surface_m2"] * 0.05:
        failures.append("散热阵面积超过地球表面积 5%，巨构尺度失衡")

    if facts["planet_heat"]["warming_k"] > 3.0:
        failures.append("天道地表散热配额会把行星烤熟（+{:.1f} K），宿主不可生存".format(
            facts["planet_heat"]["warming_k"]))

    if facts["occlusion_now"] > 0.03:
        failures.append("当前遮挡已达 {:.1%}，全球降温超过 5 K，文明无法维持".format(
            facts["occlusion_now"]))

    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description="世界观能量与尺度账本")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--out", default="", help="写入文件（默认 stdout）")
    parser.add_argument("--check", action="store_true", help="只做断言")
    args = parser.parse_args(argv)

    facts = build_facts()

    if args.check:
        failures = check(facts)
        if failures:
            for item in failures:
                print("[FAIL] " + item, file=sys.stderr)
            return 1
        print("[OK] 世界观账本 6 项断言全部通过")
        return 0

    if args.format == "json":
        text = json.dumps(facts, ensure_ascii=False, indent=2)
    else:
        text = build_markdown(facts)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("written: " + args.out)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
