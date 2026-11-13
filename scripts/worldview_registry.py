#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""世界观依赖登记（Worldview Registry）。

论文体的价值在于：改一条公理，能立刻知道会推翻哪些结论。
本模块把 公理/初始条件/参数/定理/预言 及其依赖关系登记下来，
并提供 impact 查询与 Mermaid 依赖图输出。

用法：
    python3 scripts/worldview_registry.py --constants
    python3 scripts/worldview_registry.py --graph
    python3 scripts/worldview_registry.py --impact k_structure
    python3 scripts/worldview_registry.py --check
"""

from __future__ import annotations

import argparse
import json
import sys

AXIOMS = {
    "A1": "因果局域性：信息与影响不超光速",
    "A2": "热力学：能量守恒，孤立系统熵不减",
    "A3": "量子：幺正演化、退相干、不可克隆",
    "A4": "生命：维持低熵必须持续耗散",
    "A5": "计算：擦除一位至少耗散 kT ln2",
    "A6": "单一舞台：一颗行星 + 一套轨道巨构",
}

INITIAL = {
    "I1": "恒星 G 型，L=3.83e26 W，光度稳定",
    "I2": "行星 R=6.371e6 m，反照率 0.29",
    "I3": "轨道巨构三群，已退化",
    "I4": "生物圈碳基，人口 1e9 量级",
    "I5": "遗留指令未完成、未撤销",
    "I6": "遮挡已 40 年，当前 1.19%",
    "I7": "无外来干预",
}

PARAMS = {
    "h_forced": ("50 W/m2K", "强对流换热系数"),
    "dT_fa": ("100 K", "外置结构容许温差"),
    "k_structure": ("4.3 W/m^1.5", "单位体积的结构维持代价"),
    "Q_quota": ("1e15 W", "清气地表配额"),
    "lambda_climate": ("0.75 K/(W/m2)", "气候敏感度"),
    "R_telemetry": ("1e12 bit/s", "巨构遥测带宽"),
    "stone_joule": ("1e9 J", "一块标准灵石"),
    "gamma_degrade": ("3e-4 /yr", "集能群退化率"),
}

# 定理登记：up 是依赖，paper 是出处
THEOREMS = [
    {"id": "T2.1", "paper": "II", "title": "行星能量收支闭合", "up": ["A2", "I1", "I2"]},
    {"id": "T2.2", "paper": "II", "title": "清气配额上界 1.02e15 W", "up": ["A2", "I2", "lambda_climate"]},
    {"id": "T2.3", "paper": "II", "title": "洞天增温 +10.3 K", "up": ["T2.2", "Q_quota", "lambda_climate"]},
    {"id": "T2.4", "paper": "II", "title": "关帘速率由退化率锁定", "up": ["I3", "gamma_degrade"]},
    {"id": "T2.5", "paper": "II", "title": "排污只能是局地", "up": ["T2.1", "A2"]},
    {"id": "T2.6", "paper": "II", "title": "倒热与关帘是同一次恒温控制", "up": ["T2.2", "T2.3", "T2.4"]},
    {"id": "T3.1", "paper": "III", "title": "裸身散热上限 180 W", "up": ["I2", "h_forced"]},
    {"id": "T3.2", "paper": "III", "title": "外置结构定律 P=h dT A - k A^1.5", "up": ["A2", "h_forced", "dT_fa", "k_structure"]},
    {"id": "T3.3", "paper": "III", "title": "功率上限 1e9 W 与最优面积 6e5 m2", "up": ["T3.2"]},
    {"id": "T3.4", "paper": "III", "title": "力量是连续量、比较是偏序", "up": ["T3.3"]},
    {"id": "T3.5", "paper": "III", "title": "灵石消耗率 n = P*86400/1e9", "up": ["stone_joule", "T3.3"]},
    {"id": "T4.1", "paper": "IV", "title": "观测赤字 158 倍", "up": ["A5", "I4", "R_telemetry"]},
    {"id": "T4.2", "paper": "IV", "title": "判定必为统计", "up": ["T4.1"]},
    {"id": "T4.3", "paper": "IV", "title": "天劫=1000 秒独占窗口", "up": ["T4.1"]},
    {"id": "T4.4", "paper": "IV", "title": "补丁周期约 200 年", "up": ["T4.3"]},
    {"id": "T4.5", "paper": "IV", "title": "只能收货不能生产", "up": ["T4.1", "A3"]},
    {"id": "T5.1", "paper": "V", "title": "污染输运由对流主导", "up": ["A2", "I2"]},
    {"id": "T5.2", "paper": "V", "title": "毒地横向陡、纵向长", "up": ["T5.1"]},
    {"id": "T5.3", "paper": "V", "title": "河流浓度 0.3 mg/L 量级", "up": ["T5.1", "A2"]},
    {"id": "T6.1", "paper": "VI", "title": "分配制度必然存在", "up": ["T2.2"]},
    {"id": "T6.2", "paper": "VI", "title": "1e9 W 阵地需 3.6e4 吨水/天", "up": ["T3.2"]},
    {"id": "T6.3", "paper": "VI", "title": "计量垄断生成铸币权", "up": ["stone_joule", "T2.2"]},
    {"id": "T6.4", "paper": "VI", "title": "阶级=可控散热面积", "up": ["T3.3", "T6.2"]},
    {"id": "T6.5", "paper": "VI", "title": "战争目标是水与节点", "up": ["T6.2", "T6.4", "T4.2"]},
]

PREDICTIONS = [
    {"id": "F3.1", "from": "T3.3", "text": "不存在不借系统的 1e12 W 持续输出"},
    {"id": "F3.5", "from": "T3.2", "text": "环境（水域/高空/冬季）显著改变可持续功率"},
    {"id": "F4.1", "from": "T4.2", "text": "天道不能看穿个体心思"},
    {"id": "F4.3", "from": "T4.3", "text": "天劫必伴随全行星天象异常"},
    {"id": "F5.1", "from": "T5.2", "text": "毒地沿水系与风带延伸，不是孤立圆斑"},
    {"id": "F6.1", "from": "T6.2", "text": "1e8 W 以上势力必临水"},
    {"id": "F6.5", "from": "T6.1", "text": "不存在增产型灵气政策"},
]


def all_nodes():
    nodes = {}
    nodes.update({k: "axiom" for k in AXIOMS})
    nodes.update({k: "initial" for k in INITIAL})
    nodes.update({k: "param" for k in PARAMS})
    nodes.update({t["id"]: "theorem" for t in THEOREMS})
    nodes.update({p["id"]: "prediction" for p in PREDICTIONS})
    return nodes


def edges():
    out = []
    for t in THEOREMS:
        for up in t["up"]:
            out.append((up, t["id"]))
    for p in PREDICTIONS:
        out.append((p["from"], p["id"]))
    return out


def impact(node):
    """改掉 node 会影响到的所有下游节点（含预言）。"""
    adj = {}
    for src, dst in edges():
        adj.setdefault(src, []).append(dst)
    seen = set()
    stack = list(adj.get(node, []))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(adj.get(cur, []))
    return sorted(seen)


def check():
    """完整性检查：依赖必须存在，图必须无环。"""
    nodes = all_nodes()
    problems = []
    for src, dst in edges():
        if src not in nodes:
            problems.append("未知依赖: " + src)
        if dst not in nodes:
            problems.append("未知节点: " + dst)
    # 环检测
    adj = {}
    for src, dst in edges():
        adj.setdefault(src, []).append(dst)
    state = {}

    def visit(n, path):
        if state.get(n) == 1:
            problems.append("存在环: " + " -> ".join(path + [n]))
            return
        if state.get(n) == 2:
            return
        state[n] = 1
        for m in adj.get(n, []):
            visit(m, path + [n])
        state[n] = 2

    for n in nodes:
        visit(n, [])
    return problems


def render_constants():
    lines = ["| 参数 | 值 | 含义 |", "| :--- | ---: | :--- |"]
    for key in sorted(PARAMS):
        value, desc = PARAMS[key]
        lines.append("| " + key + " | " + value + " | " + desc + " |")
    return "\n".join(lines)


def render_graph():
    lines = ["```mermaid", "graph LR"]
    for src, dst in edges():
        lines.append("  " + src + " --> " + dst)
    lines.append("```")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="世界观依赖登记")
    parser.add_argument("--constants", action="store_true")
    parser.add_argument("--graph", action="store_true")
    parser.add_argument("--impact", default="")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        problems = check()
        for p in problems:
            print("[FAIL] " + p, file=sys.stderr)
        if problems:
            return 1
        print("[OK] 依赖登记完整，无环：{} 定理 / {} 预言".format(len(THEOREMS), len(PREDICTIONS)))
        return 0
    if args.constants:
        print(render_constants())
        return 0
    if args.graph:
        print(render_graph())
        return 0
    if args.impact:
        hits = impact(args.impact)
        print(json.dumps({"node": args.impact, "affected": hits, "count": len(hits)}, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps({"axioms": len(AXIOMS), "initial": len(INITIAL), "params": len(PARAMS),
                      "theorems": len(THEOREMS), "predictions": len(PREDICTIONS)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
