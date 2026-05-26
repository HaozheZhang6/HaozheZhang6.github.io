#!/usr/bin/env python3
"""
One-shot: push selected option_analysis_system report.md files into the
Notion 'Blog Posts' DB as standalone bilingual posts.

Each entry below maps an experiment directory to its (slug, publish_date,
title, description, tags) metadata. The script:
  - reads report.md
  - strips the first heading (becomes Title property) and the date/code line
  - rewrites `## 中文版` → `## 中文 {#cn}` and `## English version` → `## English {#en}`
    so sync_notion.py's detect_bilingual matches
  - rewrites `./plots/foo.png` → absolute github.io URL (assets must be
    deployed for Notion to render them)
  - creates the Notion page with Status=Published

Skips if the slug already exists.

Usage: uv run python bin/migrate_option_reports.py
"""

import os
import re
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))

from migrate_to_notion import (  # noqa: E402
    create_page,
    existing_slugs,
    load_env,
    parse_markdown,
    rt_text,
)

ENV_FILE = ROOT / ".env"
OPTION_REPO = Path.home() / "Documents" / "Projects_code" / "option_analysis_system"
GITHUB_PAGES_BASE = "https://haozhezhang6.github.io"

ENTRIES = [
    {
        "exp_dir": "33_real_nvda_strategies",
        "slug": "nvda-iron-condor",
        "date": "2026-03-26",
        "title": "NVDA 上卖期权能跑赢直接持有吗 / Can selling NVDA options beat just holding the stock?",
        "description": "30 个月真实 NVDA 期权数据:卖 5% OTM call+put 年化 94% 干净打赢 buy-and-hold,但只在 NVDA 上有效,且 BS+VIX 估的 premium 比真实低 10 倍。",
        "categories": ["quant"],
        "tags": ["options", "iron-condor", "nvda", "covered-call", "wheel"],
    },
    {
        "exp_dir": "36_leveraged_etf_decay",
        "slug": "leveraged-etf-decay",
        "date": "2026-04-09",
        "title": "3 倍 ETF 真的能让你发财吗 / Will leveraged ETFs actually make you rich?",
        "description": "TQQQ 同一个产品,2024 起步年化 66%,2021 起步年化 28% 还吃了 −82% drawdown。SQQQ 所有 3 年以上窗口都亏钱。",
        "categories": ["quant"],
        "tags": ["leveraged-etf", "tqqq", "vol-drag", "leaps"],
    },
    {
        "exp_dir": "37_covered_call_ablation",
        "slug": "covered-call-ablation",
        "date": "2026-04-23",
        "title": "SPY 上写 covered call 到底赚不赚钱 / Are covered calls actually paying you?",
        "description": "33 年 SPY 数据:3% OTM covered call 每年比纯持 SPY 少赚 4 个点 CAGR,但 drawdown 砍半。是 Sharpe 交易,不是 return 交易。",
        "categories": ["quant"],
        "tags": ["covered-call", "spy", "jepi", "options"],
    },
    {
        "exp_dir": "38_long_history_wheel",
        "slug": "wheel-strategy",
        "date": "2026-05-07",
        "title": "The wheel 策略到底赚不赚 / Does the wheel strategy actually make money?",
        "description": "Wheel 99% 胜率但 33 年下来比纯持 SPY 少 14 倍财富。胜率是 vanity metric,总财富才是衡量标准。",
        "categories": ["quant"],
        "tags": ["wheel", "spy", "options", "cash-secured-put"],
    },
    {
        "exp_dir": "39_diversifier_matrix",
        "slug": "diversifier-matrix",
        "date": "2026-05-21",
        "title": "你的 60/40 应该用什么资产 / What should the 40% in 60/40 actually be?",
        "description": "60/40 + 黄金每个最近窗口都打赢 100% SPY,60/40 + 长债在 2022 跌得比纯 SPY 还多。教科书 60/40 已经过时。",
        "categories": ["quant"],
        "tags": ["asset-allocation", "60-40", "gold", "bonds"],
    },
]


def transform_body(raw, slug):
    """Strip preamble, swap bilingual heading style, rewrite image paths."""
    lines = raw.splitlines()

    # Drop lines until we hit the post-preamble divider.
    # Preamble is: `# Title`, blank, `**Date**: ... · **Code**: ...`, blank, `---`
    body_start = 0
    for i, ln in enumerate(lines):
        if ln.strip() == "---" and i > 0:
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:]).lstrip("\n")

    # Bilingual headings
    body = re.sub(r"^##\s+中文版\s*$", "## 中文 {#cn}", body, flags=re.MULTILINE)
    body = re.sub(r"^##\s+English version\s*$", "## English {#en}", body, flags=re.MULTILINE)

    # Image paths: ./plots/foo.png → absolute URL
    pages_url = f"{GITHUB_PAGES_BASE}/assets/img/blog/{slug}"
    body = re.sub(
        r"!\[([^\]]*)\]\(\./plots/([^)]+)\)",
        lambda m: f"![{m.group(1)}]({pages_url}/{m.group(2)})",
        body,
    )

    return body


def build_props(entry):
    last_updated = "2026-05-22"
    return {
        "Title": {"title": [rt_text(entry["title"])]},
        "Status": {"status": {"name": "Published"}},
        "Publish Date": {"date": {"start": entry["date"]}},
        "Slug": {"rich_text": [rt_text(entry["slug"])]},
        "Description": {"rich_text": [rt_text(entry["description"])]},
        "Categories": {"multi_select": [{"name": c} for c in entry["categories"]]},
        "Tags": {"multi_select": [{"name": t} for t in entry["tags"]]},
        "Last Edited": {"date": {"start": last_updated}},
    }


def migrate_entry(token, db_id, entry, taken_slugs):
    slug = entry["slug"]
    if slug in taken_slugs:
        return False, f"already in Notion ({slug})"
    src = OPTION_REPO / "docs" / "analysis" / entry["exp_dir"] / "report.md"
    if not src.exists():
        return False, f"source missing: {src}"
    raw = src.read_text()
    body = transform_body(raw, slug)
    children = parse_markdown(body)
    props = build_props(entry)
    page = create_page(token, db_id, props, children)
    return True, page["id"]


def main():
    env = load_env(ENV_FILE)
    token = env.get("NOTION_TOKEN") or os.environ.get("NOTION_TOKEN")
    db_id = env.get("NOTION_DB_ID") or os.environ.get("NOTION_DB_ID")
    if not token or not db_id:
        print("Missing NOTION_TOKEN or NOTION_DB_ID", file=sys.stderr)
        sys.exit(1)

    taken = existing_slugs(token, db_id)
    print(f"Existing slugs in Notion: {sorted(taken.keys())}\n")

    for entry in ENTRIES:
        try:
            ok, info = migrate_entry(token, db_id, entry, taken)
            tag = "OK  " if ok else "SKIP"
            print(f"[{tag}] {entry['exp_dir']} → {info}")
            if ok:
                taken[entry["slug"]] = info
        except urllib.error.HTTPError as e:
            print(f"[FAIL] {entry['exp_dir']}: HTTP {e.code} {e.read().decode()[:400]}")
        except Exception as e:
            print(f"[FAIL] {entry['exp_dir']}: {e}")


if __name__ == "__main__":
    main()
