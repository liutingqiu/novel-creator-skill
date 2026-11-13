#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""正文物理一致性检查（Worldview Lint）。

世界观审查做得再细，正文一句"太阳正在死去"就能把它推翻。
这个脚本给写作线一个可执行的护栏：扫正文，命中即报。

规则三族：
  L001 现代词直出      —— 冰山法则红线：正文不许出现物理/信息学术语
  L002 与宇宙设定冲突  —— 例如"恒星在衰亡""把太阳抽干"，物理上已被否掉
  L003 数值越界        —— 例如遮挡率超过 5%，与账本结论冲突

用法：
    python3 scripts/worldview_lint.py                # 扫 03_manuscript
    python3 scripts/worldview_lint.py --path SOME.md
    python3 scripts/worldview_lint.py --strict       # 有命中则退出码 1

行尾写 <!-- nolint --> 可豁免该行（仅用于有意的例外，如天道的报错台词）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RULES = {
    "L001": "现代词直出",
    "L002": "与宇宙设定冲突",
    "L003": "数值越界",
}

# L001：正文禁用词（技术线术语表 05 的镜像）
FORBIDDEN_TERMS = [
    "熵", "量子", "热力学", "负熵", "焦耳", "瓦特", "能量守恒", "麦克斯韦",
    "电磁波", "折射率", "概率云", "分子", "原子", "细胞", "辐射", "电离",
    "戴森", "轨道", "卫星", "算法", "程序", "系统日志", "校验码", "信噪比",
]

# L002：已被设定否掉的说法（正则）
FORBIDDEN_CLAIMS = [
    (r"(太阳|日头|恒星)[^。！？]{0,8}(正在|将要|一年年|逐渐)?(变暗|衰亡|死去|熄灭|老去)", "恒星不会因修仙而变暗，只会被遮挡"),
    (r"抽干[^。！？]{0,6}(恒星|太阳)", "恒星光度与修仙耗能差 16 个数量级"),
    (r"(吸收|抽取)[^。！？]{0,6}(恒星的?)?(自由能|寿命)", "恒星能量不可被抽取"),
]

# L003：数值边界
MAX_OCCLUSION = 5.0  # 百分比；超过即农业崩溃线


def strip_code_fences(text):
    """把 ``` 围栏内的内容替换成等长空行，保持行号不变。"""
    out = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return out


def check_line(line):
    """对单行做检查，返回 [(rule, message)]。"""
    hits = []
    if "nolint" in line:
        return hits
    for term in FORBIDDEN_TERMS:
        if term in line:
            hits.append(("L001", "出现现代词「{}」".format(term)))
    for pattern, why in FORBIDDEN_CLAIMS:
        if re.search(pattern, line):
            hits.append(("L002", why))
    for match in re.finditer(r"遮挡[^0-9%]{0,4}([0-9]+(?:\.[0-9]+)?)\s*%", line):
        value = float(match.group(1))
        if value > MAX_OCCLUSION:
            hits.append(("L003", "遮挡率 {:.1f}% 超过崩溃线 {:g}%".format(value, MAX_OCCLUSION)))
    return hits


def lint_text(text):
    """返回 [(lineno, rule, message, line)]。"""
    results = []
    lines = strip_code_fences(text)
    for index, line in enumerate(lines, start=1):
        for rule, message in check_line(line):
            results.append((index, rule, message, line.strip()))
    return results


def lint_file(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return lint_text(text)


def collect_targets(root):
    root = Path(root)
    if root.is_file():
        return [root]
    return sorted(p for p in root.rglob("*.md") if p.is_file())


def render(results, target):
    lines = []
    for lineno, rule, message, source in results:
        lines.append("{}:{}: [{}] {} | {}".format(target, lineno, rule, RULES[rule], message))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="正文物理一致性检查")
    parser.add_argument("--path", default="03_manuscript", help="要检查的目录或文件")
    parser.add_argument("--strict", action="store_true", help="有命中则退出码 1")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    args = parser.parse_args(argv)

    targets = collect_targets(args.path)
    if not targets:
        print("no markdown found in " + args.path)
        return 0

    total = 0
    payload = []
    for target in targets:
        results = lint_file(target)
        total += len(results)
        if results and not args.json:
            print(render(results, target))
        for lineno, rule, message, source in results:
            payload.append({"file": str(target), "line": lineno, "rule": rule,
                            "message": message, "text": source})

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("checked {} file(s), {} hit(s)".format(len(targets), total))

    if args.strict and total:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
