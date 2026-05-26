#!/usr/bin/env python3
"""
Push specific paragraph changes back to Notion by content-matching the
target block, not by position. Robust to TOC blocks, equations, etc.

Each edit is identified by a unique substring that appears in the
*current Notion* (pre-edit) plain_text of the paragraph. The script
finds that paragraph in Notion and PATCHes it with the new content
parsed from `parse_inline`.

Run with --apply to actually mutate Notion. Default is dry-run.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"

sys.path.insert(0, str(ROOT / "bin"))
from migrate_to_notion import parse_inline  # noqa: E402


def load_env(path):
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def notion_request(method, path, token, body=None):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode()[:500]
        raise RuntimeError(f"HTTP {e.code} for {method} {path}: {body_txt}")


def fetch_all_blocks(token, page_id):
    blocks, cursor = [], None
    while True:
        path = f"/blocks/{page_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        data = notion_request("GET", path, token)
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return blocks


def block_plain(b):
    t = b.get("type")
    if t != "paragraph":
        return ""
    return "".join(r.get("plain_text", "") for r in b.get("paragraph", {}).get("rich_text", []))


# Each post entry maps a substring-key (must uniquely identify a paragraph
# in the CURRENT Notion state) to the new markdown content for that paragraph.
EDITS = {
    # SVI / SABR
    "36358ac4-b0ac-810f-b7f0-e8946996fc11": [
        (
            "去年春天偶然对 stochastic volatility",
            "去年春天偶然对 stochastic volatility（波动率本身按一个随机过程在演化，不是常数）起了兴趣。option pricing（给 call/put 期权定价）教科书一上来就是 Black-Scholes 的 constant-vol 假设，但实际市场给的是一个 K（strike，行权价）和 T（到期时间）两个维度的 vol surface（波动率曲面），而且这个曲面还在动。底层是一组耦合的 SDE（stochastic differential equation），理论自洽性高，实际拟合一直 messy。",
        ),
        (
            "Last spring I picked up an interest in stochastic volatility",
            "Last spring I picked up an interest in stochastic volatility (vol itself evolving as its own random process, not a constant). Option-pricing textbooks open with Black-Scholes' constant-vol assumption, but the real market gives you a vol surface (implied vol as a function of both strike and time-to-expiry) that keeps moving. The system underneath is a coupled SDE (stochastic differential equation) — theoretically clean, practically a mess to fit.",
        ),
    ],
    # BPE → driving
    "36358ac4-b0ac-8119-b41f-cd0cf089ff31": [
        (
            "Tesla 是这条路上公开信息最完整的一家",
            "Tesla 是这条路上公开信息最完整的一家。下面是按时间顺序看 AI Day（Tesla 每年一次的公开技术分享）这几年披露的 stack（HydraNet 多任务感知 → BEV transformer 鸟瞰图融合 → Occupancy Network 3D 体素占据预测 → V12 端到端）演化，最后聊聊为什么 humanoid robot 那边 locomotion（行走/平衡控制）不是真正的瓶颈。",
        ),
        (
            "Tesla is the company with the cleanest public timeline",
            "Tesla is the company with the cleanest public timeline on this trajectory. What follows is a chronological read of the AI Day disclosures (Tesla's annual public engineering talk) — HydraNet (multi-task vision backbone) → BEV transformer (bird's-eye-view feature fusion) → Occupancy Network (3D voxel occupancy + flow) → V12 (end-to-end driving) — ending with why locomotion (walking / balance control) isn't the bottleneck for humanoid robots.",
        ),
    ],
    # Voice agent
    "36358ac4-b0ac-8198-b920-de4d2346d200": [
        (
            "一条 turn 端到端的延迟拆开大概是",
            "一条 turn 端到端的延迟拆开大概是 ~50 ms 网络 + ~30 ms WebRTC pickup + ~200 ms VAD/endpointing（voice activity detection,判断用户讲完了没）+ ~50 ms streaming ASR（automatic speech recognition,语音转文字）+ ~300 ms LLM TTFT（time-to-first-token,从 prompt 进去到第一个 token 出来）+ ~200 ms TTS（text-to-speech）first chunk，合计 ~830 ms。跟公开 benchmark 上做得最好的几套 730–750 ms（GPT-4 Nano + Cartesia Sonic-Turbo，[dev.to 30-stack benchmark](https://dev.to/cloudx/cracking-the-1-second-voice-loop-what-we-learned-after-30-stack-benchmarks-427)）相差不大。后面每一个工程决策都是奔着把这条 loop 压在 1 秒以内。",
        ),
        (
            "A single turn breaks down roughly as ~50 ms network",
            "A single turn breaks down roughly as ~50 ms network + ~30 ms WebRTC pickup + ~200 ms VAD/endpointing (voice activity detection + deciding when the user is done speaking) + ~50 ms streaming ASR (automatic speech recognition — speech to text) + ~300 ms LLM TTFT (time-to-first-token, prompt-in to first output token) + ~200 ms TTS (text-to-speech) first chunk, totaling ~830 ms — within range of the best published end-to-end numbers (730–750 ms for GPT-4 Nano + Cartesia Sonic-Turbo, [dev.to 30-stack benchmark](https://dev.to/cloudx/cracking-the-1-second-voice-loop-what-we-learned-after-30-stack-benchmarks-427)). Every engineering decision in the rest of this post is in service of that budget.",
        ),
    ],
    # RL training notes
    "36358ac4-b0ac-817e-9b9f-cf24d5abf14c": [
        (
            "表面看是不同 reward",
            "表面看是不同 reward、不同 objective，本质上每一版都在解同一个问题：把 reward signal（reward model 给一条 response 的打分）注入 policy（被训练的 LLM 自己），同时控制 **gradient variance**（梯度方差，太大就训不稳）和每步 **compute**（单步的计算和显存预算）。Variance 高就训不稳，需要更多 sample 平均、更小 learning rate、更多 KL 约束；compute 高就养不起几个模型、rollout（从当前 policy 采几条 response 拿来算 reward）贵、scale 不上去。PPO 这两条都拉满，后面每个新缩写都是在这两条轴上往左下挪——少一个模型、少一些 rollout、KL 估计更稳、importance ratio（新旧 policy 对同一 token 的概率比）不抖。",
        ),
        (
            "Strip the surface and every variant is the same problem",
            "Strip the surface and every variant is the same problem: inject a reward signal (the scalar score a reward model assigns to a response) into the policy (the LLM being trained) while keeping **gradient variance** and per-step **compute** under control. High variance means unstable training, smaller learning rate, more KL regularization. High compute means too many models in VRAM and rollouts (response samples drawn from the current policy to compute reward) you can't afford. PPO maxes out both, and every method after it is a step in the other direction — one fewer model, fewer rollouts, a lower-variance KL estimator, a steadier importance ratio (the new-vs-old policy probability ratio for the same token).",
        ),
    ],
    # KL estimators
    "36358ac4-b0ac-812c-990b-fc3b16df6c30": [
        (
            "作为 reference policy 的 anchor",
            "作为 reference policy（被冻结的初始 LLM，比如 SFT 完那个）的 anchor，防止训练把模型行为推得太远。这里 KL（Kullback-Leibler divergence，衡量两个概率分布有多不同的标准度量）越大越说明当前 policy 偏离了初始 policy。整个 vocab 上求和精确计算这个量太贵——一个 step 的 logits 张量已经吃掉一大块 VRAM，再叠一个 full-vocab KL summation 显存就不够——所以社区都用 **sample-based estimator**（用从 policy 采样的少量 token 去估这个期望，而不是穷举全 vocab）近似。",
        ),
        (
            "at every training step, as the reference-policy anchor",
            "at every training step, as the reference-policy anchor — π_ref is the frozen initial LLM (usually the post-SFT checkpoint) — that prevents the model from drifting too far. KL here is Kullback-Leibler divergence, the standard measure of how different two distributions are; a bigger KL means the current policy has drifted further from where it started. Computing this exactly by summing over the entire vocabulary isn't feasible — the logits tensor for a single step already eats a substantial fraction of VRAM, and a full-vocab KL summation pushes it over. So the community estimates it from a handful of sampled tokens instead.",
        ),
    ],
    # NVDA iron condor — 2 paragraphs each side
    "36958ac4-b0ac-81f2-85b4-ecf45ab97a9b": [
        (
            "跑完一系列 SPY 上的卖期权 backtest",
            "跑完一系列 SPY（S&P 500 指数 ETF）上的卖期权 backtest 之后基本是同一个结论：risk-adjusted（单位风险下的收益，比如 Sharpe）比纯持仓好，但**绝对收益**打不过 buy-and-hold（直接买入并长期持有）。NVDA 是整个 repo 里**唯一的反例**——单只股票上 sell options（卖期权收 premium 当 income）干净打赢底层，所以单独拎一篇出来讲，顺便把\"为什么是 NVDA、能不能复制到别的票\"这件事讲清楚。数据用的是 2023-06 到 2026-01 这 2.5 年的真实 NVDA 期权报价，正好 cover 了 AI 浪潮起来到上一轮调整。下面所有结论都是**最近 regime 的**，不是 30 年长期常量。",
        ),
        (
            "NVDA 从 2023 年中到 2026 年初翻了 3 倍",
            "NVDA 从 2023 年中到 2026 年初翻了 3 倍。直接持有股票年化 81%。同期每个月卖 covered call（持股 + 卖一个 call 期权,把超出某个 strike 的上涨封顶,换 premium 现金）反而**亏了 7 个点的 CAGR**（年化复合收益率）——cap on upside 在 NVDA 飞涨的时候咬得太狠。但是如果你**同时**卖 call **和** put（双向各 5% OTM 的 \"iron condor\"——OTM = out-of-the-money,strike 离现价 5% 远;iron condor = 同时卖一个高位 call 和一个低位 put,赌价格在两个 strike 之间），年化 **94%**，回撤还比纯持 NVDA 浅。原因是结构性的：NVDA 的期权市场对保险定价过高，即使每隔几个月被 NVDA 暴涨咬一口，累计 premium 也足够 compensate。",
        ),
        (
            "The SPY option-selling backtests in the rest of this repo",
            "The SPY (the S&P 500 index ETF) option-selling backtests in the rest of this repo all land on the same conclusion: risk-adjusted return (return per unit of risk, e.g. Sharpe) goes up, **absolute** return doesn't beat buy-and-hold. NVDA is the **one exception** — the single name where selling options (collecting premium as income from option buyers) cleanly beats holding the underlying — so it gets its own post, and a real look at *why it's NVDA* and whether the result transfers anywhere else. The data is 2.5 years of real NVDA option quotes from June 2023 to January 2026, which spans the run-up of the AI rally and the pullback that followed. Every finding below is a *recent-regime* result, not a long-run constant.",
        ),
        (
            "NVDA tripled between mid-2023 and early-2026",
            "NVDA tripled between mid-2023 and early-2026. Owning the shares earned about **81 % per year**. Selling a covered call (holding the shares plus selling a call option to cap the upside above some strike in exchange for cash premium) against those shares each month *lost you* 7 percentage points of CAGR (compound annual growth rate); the cap on upside bit hard when NVDA ripped. But if you sold a call AND a put each month — both 5 % away from the current price (out-of-the-money, OTM, in options jargon; selling both at once is an \"iron condor,\" betting price stays inside the two strikes) — you earned **94 % per year, with a shallower drawdown than just owning NVDA**. The reason is structural: NVDA's option market was systematically over-paying for protection, so even after eating big losses when NVDA ripped, the cumulative premium more than compensated.",
        ),
    ],
    # Leveraged ETF
    "36958ac4-b0ac-8199-905b-d64386f44d7f": [
        (
            "TQQQ 一直是雪球和 reddit 上",
            "TQQQ（3 倍杠杆 Nasdaq-100 ETF，标的指数涨 1% 它涨 3%，跌 1% 它跌 3%）一直是雪球和 reddit 上被讨论最多的杠杆产品之一——\"长期 Nasdaq 涨，3 倍杠杆就是 3 倍收益\"这套说法每隔几个月就被重新搬出来。一直觉得这话哪里不对，但具体哪里说不清，所以把 2010 年以来的数据全拉出来跑了一遍。",
        ),
        (
            "TQQQ is one of the most-pitched leveraged products",
            "TQQQ (a 3× leveraged Nasdaq-100 ETF — when the underlying index moves 1% it moves 3% in the same direction) is one of the most-pitched leveraged products on retail forums — \"Nasdaq goes up long-term, so 3× leverage is just 3× the return\" gets repeated every few months. Something about it always felt off without being able to pin down exactly what, so I pulled every day of data since 2010 and ran the numbers.",
        ),
    ],
    # Covered call
    "36958ac4-b0ac-8146-808d-e7688df0b84f": [
        (
            "上个月吃饭聊到一个朋友",
            "上个月吃饭聊到一个朋友——他从 2019 年开始一直在 SPY（S&P 500 指数 ETF）上写 covered call（持股的同时卖出一个 call 期权，把\"股价涨过某个 strike 之后\"的所有上涨封顶，换 premium 现金），每个月一套：挑一个 OTM 3% 的 strike（OTM = out-of-the-money，strike 比现价高 3%），把 call 卖掉，收 5-10 美元/股的 premium（期权买方付给卖方的钱），等到月底 expire。大多数月份合约归零，premium 揣兜里；有几个月 SPY 涨太凶，他得按 strike 把股票交出去，让出一截 upside。",
        ),
        (
            "Dinner last month with a friend who's been writing covered calls",
            "Dinner last month with a friend who's been writing covered calls on SPY (the S&P 500 index ETF) since 2019. A \"covered call\" is selling a call option against shares you already hold — you cap your upside above some strike in exchange for cash premium (the price the option buyer pays you). Same routine every month: pick a strike a few percent above spot (out-of-the-money, OTM), sell the call, collect $5–10 a share, wait for expiration. Most months the contract dies worthless and he keeps the cash. A few months SPY rips past the strike and he gives up some upside.",
        ),
    ],
    # Wheel strategy
    "36958ac4-b0ac-812d-9fd1-d62351e83bb4": [
        (
            "YouTube 上有个频道每周都教",
            "YouTube 上有个频道每周都教\"the wheel\"策略：在 SPY（S&P 500 指数 ETF）上卖 cash-secured put（卖出一个 put 期权,同时把 strike × 100 美元的现金锁住当抵押），赌它不会跌穿你的 strike（行权价）；万一跌穿了就被 assign（按 strike 强制买入股票），再卖 covered call（持股 + 卖个 call,把上涨封顶换 premium）,再赌它不会涨过你的 strike。**99% 的单子都是赚钱的**，主播每次都把这个数字打在缩略图上。看起来稳得不能再稳。",
        ),
        (
            "There's a YouTube channel that teaches",
            "There's a YouTube channel that teaches \"the wheel\" strategy every week: sell a cash-secured put on SPY (S&P 500 ETF — \"cash-secured\" means you lock up strike × 100 dollars as collateral, so if the put gets exercised you have the cash to buy the shares); hope it doesn't get assigned (assigned = forced to buy at the strike because price fell below it). If it does, you take the shares and sell a covered call against them (covered call = holding shares + selling a call to cap upside in exchange for premium). Cycle forever. **99 % of the individual trades are profitable**, and the host puts that number on every thumbnail. It looks unbeatable.",
        ),
    ],
    # BenchCAD
    "36358ac4-b0ac-817c-9ce5-d2e07d37246f": [
        (
            "这个题听起来非常适合 RLVR",
            "这个题听起来非常适合 RLVR（Reinforcement Learning with Verifiable Rewards，reward 来自一个能确定地判 \"对/不对\" 的程序而不是来自人类反馈或 reward model）：参数化建模的操作集合有限（sketch 画 2D 草图、extrude 拉伸成 3D、revolve 旋转成型、sweep 沿路径扫描、loft 在多个截面间放样、fillet 倒圆角、chamfer 倒直角——这些是 CAD 软件里最基础的 7 个操作），每个 part 都可以用代码精确表达，render、voxel IoU（把生成的几何和 ground truth 都体素化后算 3D 的 Intersection over Union）、几何检查全部能 100% 自动化 verify。比起 math reasoning 那种 reward 容易被 hack（钻规则空子拿分但答案其实不对）的领域，CAD 的 reward 看上去是干干净净的\"这块铁是不是符合规格\"。",
        ),
        (
            "Industrial CAD sounds like a clean RLVR target",
            "Industrial CAD sounds like a clean RLVR (Reinforcement Learning with Verifiable Rewards — the reward comes from a program that deterministically checks \"right / wrong\" rather than from human feedback or a learned reward model) target. The parametric op set is finite (sketch a 2D profile, extrude into 3D, revolve around an axis, sweep along a path, loft between cross-sections, fillet to round an edge, chamfer to bevel one — the seven basic operations in any CAD package), every part can be expressed exactly as code, and render, voxel IoU (Intersection over Union after voxelizing both the generated and ground-truth geometry), and geometric checks can be verified 100% automatically. Compared to math reasoning, where rewards are hackable (the model finds a way to score high without actually being right), the CAD reward looks like the cleanest \"is this piece of metal to spec.\"",
        ),
    ],
    # Diversifier matrix
    "36958ac4-b0ac-8128-a996-f9b1ba93fb25": [
        (
            "2022 年发生了一件理论上不该发生的事",
            "2022 年发生了一件理论上不该发生的事：标准 60/40（**60/40** 是过去几十年退休账户的默认资产配置——60% 股票 + 40% 债券；这里具体跑的是 60% SPY = S&P 500 指数 ETF + 40% 长期国债 TLT = iShares 20+ Year Treasury ETF）一年跌了 **23%**，比纯持 SPY 还多跌 2 个点。债券原本是放在那儿给股票崩盘兜底的\"保险腿\"，赔得比\"主险\"还狠。",
        ),
        (
            "In 2022 something happened that wasn't supposed to",
            "In 2022 something happened that wasn't supposed to: the textbook 60/40 (the default retirement allocation for decades — 60 % equities + 40 % bonds; here specifically 60 % SPY = S&P 500 index ETF + 40 % TLT = iShares 20+ Year Treasury ETF) lost **23 %** on the year — two percentage points worse than holding 100 % SPY. The bond leg was supposed to be there *because* stocks crash; it lost more than the thing it was insuring.",
        ),
    ],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    env = load_env(ENV_FILE)
    token = env.get("NOTION_TOKEN") or os.environ.get("NOTION_TOKEN")
    if not token:
        print("Missing NOTION_TOKEN", file=sys.stderr)
        sys.exit(1)

    for page_id, edits in EDITS.items():
        print(f"\n=== {page_id[:8]} ===")
        blocks = fetch_all_blocks(token, page_id)
        for old_key, new_text in edits:
            hits = [b for b in blocks if b.get("type") == "paragraph" and old_key in block_plain(b)]
            if not hits:
                print(f"  ✗ no paragraph matches: {old_key[:50]!r}")
                continue
            if len(hits) > 1:
                print(f"  ! multiple matches ({len(hits)}), skipping: {old_key[:50]!r}")
                continue
            block = hits[0]
            new_rich = parse_inline(new_text)
            payload = {"paragraph": {"rich_text": new_rich}}
            print(f"  PATCH {block['id'][:8]}  ← {old_key[:60]}")
            if args.apply:
                notion_request("PATCH", f"/blocks/{block['id']}", token, payload)


if __name__ == "__main__":
    main()
