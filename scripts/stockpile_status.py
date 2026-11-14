#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""存稿看板：统计正文章节、字数、重复与缺口，并换算成日更能撑几天。

用法：
    python3 scripts/stockpile_status.py                  # 看板
    python3 scripts/stockpile_status.py --daily 7000     # 按日更字数算缓冲
    python3 scripts/stockpile_status.py --check          # 上架前体检（繁体外链空章乱序）
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

CHAPTER_RE = re.compile(r"第\s*(\d+)\s*章")
STUB_CHARS = 500
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
TRAD_ONLY = set("們這個來時說會發現實現點緣體認識讓與為對開關東車書長門問間頭")
EXTERNAL = ("http://", "https://", "www.", "番茄", "作家助手", "公众号", "微信")


def count_chars(text):
    """按番茄口径：计非空白字符数。"""
    return len(re.sub(r"\s", "", text))


def parse_chapter(path):
    m = CHAPTER_RE.search(path.name)
    return int(m.group(1)) if m else None


def scan(root):
    root = Path(root)
    groups = defaultdict(list)
    for path in sorted(root.glob("*.md")):
        num = parse_chapter(path)
        if num is None:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        groups[num].append({"path": path, "chars": count_chars(text), "text": text})
    return groups


def summarize(groups, daily):
    chapters = sorted(groups)
    best = {}
    duplicates = []
    for num in chapters:
        versions = groups[num]
        # 规则：有 manifest 用 manifest；否则取最新修改的版本（重写后的通常是最新）
        versions.sort(key=lambda v: (v["path"].stat().st_mtime, v["chars"]), reverse=True)
        best[num] = versions[0]
        if len(versions) > 1:
            duplicates.append((num, [v["path"].name for v in versions]))
    stubs = [n for n, v in best.items() if v["chars"] < STUB_CHARS]
    total = sum(v["chars"] for v in best.values())
    missing = []
    if chapters:
        missing = [n for n in range(min(chapters), max(chapters) + 1) if n not in best]
    days = total / daily if daily else 0
    return {
        "chapters": len(best),
        "total_chars": total,
        "avg_chars": total / len(best) if best else 0,
        "duplicates": duplicates,
        "stubs": stubs,
        "missing": missing,
        "buffer_days": days,
        "daily": daily,
    }


def check_text(text):
    problems = []
    trad = sorted({c for c in text if c in TRAD_ONLY})
    if trad:
        problems.append("疑似繁体/异体字：" + "".join(trad[:8]))
    for token in EXTERNAL:
        if token in text:
            problems.append("含外链或平台名：" + token)
    return problems


def render(summary, groups):
    lines = ["# 存稿看板", ""]
    lines.append("| 指标 | 值 |")
    lines.append("| :--- | ---: |")
    lines.append("| 去重后章节数 | {} |".format(summary["chapters"]))
    lines.append("| 总字数 | {:,} |".format(summary["total_chars"]))
    lines.append("| 单章均字数 | {:.0f} |".format(summary["avg_chars"]))
    lines.append("| 日更 {} 字可撑 | {:.1f} 天 |".format(summary["daily"], summary["buffer_days"]))
    lines.append("")
    if summary["duplicates"]:
        lines.append("## 重复章节（同一章号多个文件）")
        for num, names in summary["duplicates"]:
            lines.append("- 第{:03d}章：{}".format(num, " / ".join(names)))
        lines.append("")
    if summary["missing"]:
        lines.append("## 缺章")
        lines.append("- " + ", ".join("第{:03d}章".format(n) for n in summary["missing"]))
        lines.append("")
    if summary["stubs"]:
        lines.append("## 疑似占位章（<{} 字）".format(STUB_CHARS))
        lines.append("- " + ", ".join("第{:03d}章".format(n) for n in summary["stubs"]))
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="存稿看板")
    parser.add_argument("--root", default="03_manuscript")
    parser.add_argument("--daily", type=int, default=7000)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    groups = scan(args.root)
    if not groups:
        print("no chapters found in " + args.root)
        return 0

    summary = summarize(groups, args.daily)
    print(render(summary, groups))

    if args.check:
        bad = 0
        for num in sorted(groups):
            for version in groups[num]:
                for problem in check_text(version["text"]):
                    print("第{:03d}章 {}: {}".format(num, version["path"].name, problem))
                    bad += 1
        print("\n体检完成，问题 {} 处".format(bad))
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
