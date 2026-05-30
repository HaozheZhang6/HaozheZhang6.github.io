#!/usr/bin/env python3
"""Insert external image blocks into Notion quant posts so they (a) render in
Notion and (b) survive the Notion->_posts sync. Images point to stable
github.io asset URLs. Placement rule: insert after the LAST table in the named
section; if the section has no table, at the end of the section.

Run dry (default) to preview; pass --apply to write.
"""
import json, sys, urllib.request, urllib.error
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"
TOKEN = [l.strip().split("=", 1)[1] for l in ENV.read_text().splitlines() if l.startswith("NOTION_TOKEN")][0]
BASE = "https://haozhezhang6.github.io/assets/img/blog"
HDRS = {"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}

CAP = {
    # nvda
    "equity_curves.png": "Daily equity curves, all five strategies",
    "real_vs_bs_premium.png": "Real option premium vs Black-Scholes+VIX estimate, per trade",
    "strategy_pnl_per_trade.png": "Per-trade P&L by month",
    # lev-etf
    "equity_SH.png": "SH (-1x S&P 500) equity vs benchmark",
    "equity_SSO.png": "SSO (2x S&P 500) equity vs benchmark",
    "equity_UPRO.png": "UPRO (3x S&P 500) equity vs benchmark",
    "equity_TQQQ.png": "TQQQ (3x Nasdaq-100) equity vs benchmark",
    "equity_SQQQ.png": "SQQQ (-3x Nasdaq-100) equity vs benchmark",
    "cagr_by_start_year.png": "CAGR by start year",
    "decay_SQQQ.png": "SQQQ rolling 1-year volatility decay",
    "decay_SH.png": "SH rolling 1-year volatility decay",
    "decay_SSO.png": "SSO rolling 1-year volatility decay",
    "decay_UPRO.png": "UPRO rolling 1-year volatility decay",
    "decay_TQQQ.png": "TQQQ rolling 1-year volatility decay",
    "breakeven_heatmap.png": "Share of N-year windows the leveraged ETF beats its benchmark",
    # covered-call
    "best_curves.png": "Equity curves of the best covered-call variants vs SPY",
    "drawdown_by_event.png": "Drawdown by event: SPY vs covered call",
    "drawdown_comparison.png": "33-year drawdown curves overlaid",
    "pareto_sharpe_cagr.png": "Sharpe vs CAGR across rolling windows",
    "heatmap_otm_vs_dte_sharpe.png": "Sharpe ablation: OTM distance vs DTE",
    "heatmap_otm_vs_vix_sharpe.png": "Sharpe ablation: OTM distance vs VIX regime",
    # wheel
    "win_rate_vs_wealth.png": "Per-trade win rate vs final wealth (the vanity-metric chart)",
    "phase_split.png": "Time spent holding shares vs sitting in cash",
    # diversifier
    "sharpe_vs_maxdd.png": "Sharpe vs max drawdown (Pareto scatter)",
    "drawdown_2022.png": "2022 max drawdown by defender",
}

# slug -> list of (section_heading_exact_text, [image_filenames...])
PLAN = {
    "nvda-iron-condor": {
        "id": "36958ac4-b0ac-81f2-85b4-ecf45ab97a9b",
        "secs": [
            ("短答", ["equity_curves.png"]),
            ("The short version", ["equity_curves.png"]),
            ("为啥卖 NVDA option 真的能赚钱", ["real_vs_bs_premium.png"]),
            ("Why selling NVDA options actually works", ["real_vs_bs_premium.png"]),
            ("哪些月份亏了", ["strategy_pnl_per_trade.png"]),
            ("Which months lost money", ["strategy_pnl_per_trade.png"]),
        ],
    },
    "leveraged-etf-decay": {
        "id": "36958ac4-b0ac-8199-905b-d64386f44d7f",
        "secs": [
            ("四个产品到底是啥", ["equity_SH.png", "equity_SSO.png", "equity_UPRO.png", "equity_TQQQ.png", "equity_SQQQ.png"]),
            ("The four products explained", ["equity_SH.png", "equity_SSO.png", "equity_UPRO.png", "equity_TQQQ.png", "equity_SQQQ.png"]),
            ("起始年份 dominate 一切——这张图", ["cagr_by_start_year.png"]),
            ("The start year dominates everything", ["cagr_by_start_year.png"]),
            ("SQQQ 的死亡螺旋", ["decay_SQQQ.png"]),
            ("SQQQ's death spiral", ["decay_SQQQ.png"]),
            ("全分布——滚动窗口看清楚", ["breakeven_heatmap.png", "decay_SH.png", "decay_SSO.png", "decay_UPRO.png", "decay_TQQQ.png"]),
            ("Full distributions across rolling windows", ["breakeven_heatmap.png", "decay_SH.png", "decay_SSO.png", "decay_UPRO.png", "decay_TQQQ.png"]),
        ],
    },
    "covered-call-ablation": {
        "id": "36958ac4-b0ac-8146-808d-e7688df0b84f",
        "secs": [
            ("最近 1-5 年实际赚了多少", ["best_curves.png", "drawdown_by_event.png", "drawdown_comparison.png"]),
            ("What the last 1-5 years actually paid", ["best_curves.png", "drawdown_by_event.png", "drawdown_comparison.png"]),
            ("把所有 rolling window 拿出来看", ["pareto_sharpe_cagr.png"]),
            ("The rolling-window picture", ["pareto_sharpe_cagr.png"]),
            ("三个看着聪明、实际无效的改良", ["heatmap_otm_vs_dte_sharpe.png", "heatmap_otm_vs_vix_sharpe.png"]),
            ("Three things I tried that didn't help", ["heatmap_otm_vs_dte_sharpe.png", "heatmap_otm_vs_vix_sharpe.png"]),
        ],
    },
    "wheel-strategy": {
        "id": "36958ac4-b0ac-812d-9fd1-d62351e83bb4",
        "secs": [
            ("最近 1-5 年实际赚了多少", ["equity_curves.png"]),
            ("What the last 1-5 years actually paid", ["equity_curves.png"]),
            ("Vanity metric 陷阱——这一张图说完", ["win_rate_vs_wealth.png"]),
            ("The vanity-metric trap — one chart to end the debate", ["win_rate_vs_wealth.png"]),
            ("Wheel 到底花了多少时间在等", ["phase_split.png"]),
            ("How much time the wheel actually spends doing nothing", ["phase_split.png"]),
        ],
    },
    "diversifier-matrix": {
        "id": "36958ac4-b0ac-8128-a996-f9b1ba93fb25",
        "secs": [
            ("17 年总排名（按 Sharpe）", ["sharpe_vs_maxdd.png", "equity_curves.png"]),
            ("17-year ranking (sorted by Sharpe)", ["sharpe_vs_maxdd.png", "equity_curves.png"]),
            ("最近 1-5 年实际赚了多少——关键的一张图", ["cagr_by_start_year.png"]),
            ("Recent 1-5 year reality — the chart that matters", ["cagr_by_start_year.png"]),
            ("2022 — 诊断年", ["drawdown_2022.png"]),
            ("2022 — the diagnostic year", ["drawdown_2022.png"]),
        ],
    },
}


def api(method, url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=HDRS, method=method)
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode()[:300]); raise


def all_blocks(pid):
    out, cur = [], None
    while True:
        u = f"https://api.notion.com/v1/blocks/{pid}/children?page_size=100" + (f"&start_cursor={cur}" if cur else "")
        d = api("GET", u)
        out += d["results"]
        if not d.get("has_more"):
            return out
        cur = d["next_cursor"]


def btxt(b):
    body = b.get(b["type"], {})
    if isinstance(body, dict) and "rich_text" in body:
        return "".join(r["plain_text"] for r in body["rich_text"]).strip()
    return ""


def img_block(url, cap):
    return {"object": "block", "type": "image",
            "image": {"type": "external", "external": {"url": url},
                      "caption": [{"type": "text", "text": {"content": cap}}]}}


def resolve_anchor(blocks, heading):
    """Return block id to insert after for the given section heading."""
    idx = None
    for i, b in enumerate(blocks):
        if b["type"] in ("heading_2", "heading_3") and btxt(b) == heading:
            idx = i; break
    if idx is None:
        return None, "HEADING NOT FOUND", set()
    # section = blocks (idx+1 .. next heading)
    end = len(blocks)
    for j in range(idx + 1, len(blocks)):
        if blocks[j]["type"] in ("heading_2", "heading_3"):
            end = j; break
    section = blocks[idx + 1:end]
    sec_urls = {(b["image"].get("external") or b["image"].get("file") or {}).get("url", "")
                for b in section if b["type"] == "image"}
    # anchor: last table in section, else last non-image block, else heading
    last_table = None
    for b in section:
        if b["type"] == "table":
            last_table = b
    if last_table:
        return last_table["id"], f"after table (section '{heading}', {len(section)} blocks)", sec_urls
    if section:
        non_img = [b for b in section if b["type"] != "image"]
        anchor = non_img[-1] if non_img else section[-1]
        return anchor["id"], f"after last block (section '{heading}')", sec_urls
    return blocks[idx]["id"], f"after heading itself (empty section '{heading}')", sec_urls


def existing_image_urls(blocks):
    urls = set()
    for b in blocks:
        if b["type"] == "image":
            i = b["image"]
            urls.add((i.get("external") or i.get("file") or {}).get("url", ""))
    return urls


def main():
    apply = "--apply" in sys.argv
    for slug, cfg in PLAN.items():
        pid = cfg["id"]
        blocks = all_blocks(pid)
        print(f"\n===== {slug} ({len(blocks)} blocks, {len(existing_image_urls(blocks))} existing images) =====")
        for heading, files in cfg["secs"]:
            anchor, how, sec_urls = resolve_anchor(blocks, heading)
            if anchor is None:
                print(f"  !! {heading}: {how}"); continue
            children, urls = [], []
            for f in files:
                url = f"{BASE}/{slug}/{f}"
                if url in sec_urls:
                    continue
                children.append(img_block(url, CAP.get(f, f)))
                urls.append(f)
            if not children:
                print(f"  -- {heading}: all present in section, skip"); continue
            print(f"  + {heading}: insert {urls} {how}")
            if apply:
                api("PATCH", f"https://api.notion.com/v1/blocks/{pid}/children",
                    {"children": children, "after": anchor})
                blocks = all_blocks(pid)  # refresh so later anchors/dedup stay valid
    print("\nDRY RUN — pass --apply to write" if not apply else "\nAPPLIED")


if __name__ == "__main__":
    main()
