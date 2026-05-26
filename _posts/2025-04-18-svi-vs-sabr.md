---
layout: post
title: SVI vs SABR：短期合约 vol smile 上的差距 / SVI vs SABR, the gap on short-tenor smiles
date: 2025-04-18
description: 对 SDE 金融建模起了兴趣，跑了一下 AAPL vol surface 拟合——short tenor SVI 比 SABR 好 2–5×
tags: [vol-smile, sabr, svi, sde]
categories: [quant]
notion_id: 36358ac4-b0ac-810f-b7f0-e8946996fc11
last_updated: 2026-05-14
bilingual: true
---

## 中文 {#cn}

去年春天偶然对 stochastic volatility 起了兴趣。option pricing 教科书一上来就是 Black-Scholes 的 constant-vol 假设，但实际市场给的是一个 K 和 T 两个维度的曲面，而且这个曲面还在动。底层是一组耦合的 SDE，理论自洽性高，实际拟合一直 messy。

vol surface fitting 这件事，[Gatheral & Jacquier 2014](https://arxiv.org/abs/1204.0646) 把 SVI 这一支推到 SSVI / no-butterfly 的完整框架后基本定型；SABR 自 [Hagan 2002](https://www.researchgate.net/publication/235622441_Managing_Smile_Risk) 之后也有大量改进（[Hagan et al. 2014 "Arbitrage-Free SABR"](https://www.researchgate.net/publication/265252097_Arbitrage-Free_SABR) 用 PDE 替掉 asymptotic 是其中一个代表）。但 desk 上谁该用哪个，文献里的回答比想象中模糊。挑了 vanilla SVI 和 vanilla Hagan-SABR——工业上最常用的两个 baseline——在 AAPL 真实数据上跑了一次对比，记一下。

选哪一个本质上是两件事在打架：参数有没有金融意义、跟数据贴得有多紧。SABR 是参数派的极致——4 个参数全部有意义、能 stress test 也能外推——但 Hagan asymptotic 大 T 还行、小 T 上拉不动曲率。SVI 反过来：fit 起来能贴任何 smile 形状，但参数跟 SDE 切断，看不出"市场在想什么"。

### 两个模型的设计选择

[SABR](https://www.researchgate.net/publication/235622441_Managing_Smile_Risk) 是真正意义上的 stochastic-vol model：vol 服从一个独立的扩散过程，跟价格扩散通过 correlation `ρ` 耦合。它的 4 个参数 `α, β, ρ, ν` 都有金融意义——`α` 是 ATM vol，`β` 决定 stickiness（lognormal vs normal），`ν` 是 vol-of-vol，`ρ` 是 spot-vol 相关性。卖点是参数可解释、可外推；缺点是它给出的 implied vol 公式（Hagan asymptotic expansion）是大 T 近似，短期、深 OTM 时假设 break down。

[SVI](https://www.researchgate.net/publication/265252297_A_Parsimonious_Arbitrage-Free_Implied_Volatility_Parameterization_with_Application_to_the_Valuation_of_Volatility_Derivatives) 走另一条路：直接 parameterize implied total variance

```plain text
w(k) = a + b · (ρ · (k − m) + √((k − m)² + σ²))
```

5 个参数纯 descriptive。它不来自任何 SDE，所以拿到 SVI 参数后说不出市场在想什么；但作为 fitter 它极其灵活，可以贴合任何形状的 smile。SABR 解释市场，SVI 只负责把曲线弯过去。

### 实验：AAPL 跨十个 expiry

AAPL 2024-09-13 snapshot，10 个 expiry 从 13 天到 6 个月。每个 expiry 的流程是 pull call mid quote → solve BS implied vol → 同时用 SVI 和 SABR 拟合 → 算 per-strike RMSE。SVI 还要做一个 butterfly-arbitrage diagnostic：implied density `g(k) = ∂²C/∂K²` 处处 ≥ 0 等价于该 slice 无 butterfly 套利。

| Expiry | T (y) | SVI RMSE (bps) | SABR RMSE (bps) | |---|---:|---:|---:| | 2024-09-27 | 0.04 | **121** | 577 | | 2024-10-18 | 0.10 | **40** | 287 | | 2024-11-15 | 0.17 | **18** | 97 | | 2024-12-20 | 0.27 | **14** | 40 | | 2025-01-17 | 0.35 | 10 | **13** | | 2025-03-21 | 0.52 | 7 | **5** |

### 结果是一个干净的 regime split

T ≤ 0.13y（六周以内）SVI 比 SABR 好 2-5×，13 天合约上 SVI 121 bps 对 SABR 577 bps，差不多 5 倍。直观解释是短期 smile 是 deeply U 形，两翼都很陡，SVI 的 5 个参数可以弯过去，SABR 的 Hagan 近似公式在这种 regime 下根本拉不出那么大的曲率。

T ≥ 0.35y 两者基本打平，SABR 反而略好。smile flatten，曲线接近线性，谁拟合都行——SABR 在长端略胜，可能是因为它的 lognormal-plus-vol-of-vol 设定本来就匹配长期 smile 的轻微 skew。所以"哪个模型更好"这个问题本身没有 standalone 答案，要看 tenor。

### Butterfly arbitrage 是 SVI 必须自己监控的一步

SVI 灵活，理论上能把曲线弯到 implied density 局部为负，产生 butterfly 套利。所以每次拟合完都要算一下 `g(k)` 的正性。这个 snapshot 10 个 slice 全部 `g_min > 0`，最紧的是 13 天那一个 `g_min = 0.03`——离 arb-free 边界很近但还在内侧。短期 SVI 是要监控的。SABR 反过来 SDE-grounded，butterfly arb 默认不会违反（Hagan expansion 在 deep OTM 可能违反 wing 单调性，但 butterfly 不会）。"贴得紧"的代价就是要自己盯套利。

### 实际 desk 上的用法

实际生产里这两个模型都用，分工不同。短期 vol slice 用 SVI 拟合，差距大到不是 SABR 调一调参数能补回来的；长期那一段 SABR 也行，而且参数有 financial meaning，方便 risk management 和 stress test。一种比较常见的混合方案是 SVI 负责 marking（精度优先），完了再 fit 一组 SABR 在 SVI 出来的 surface 上提取 `ρ` / `ν` 等可解释量。底层 SDE 理论很漂亮，但工业实践里需要的常常是一个能精确弯到市场形状、且 numerically 无套利的 fitter，SVI 在这个位置上几乎没有竞争对手。

### 这次实验留下的几个坑

最该补的是 PDE-SABR。这套对比只跑了 vanilla Hagan，"Arbitrage-Free SABR"（PDE 方法）按理应该能在短期 smile 上把 SABR 拉回来，代价是 closed-form 公式换成数值求解，calibration 慢一个数量级。下一次做这件事的正确姿势是 SVI vs Hagan SABR vs PDE SABR 三方对比，集中在 T ≤ 0.13y。

第二个是只跑了 AAPL。在 large-cap、liquidity 中等、event-driven 程度也中等的标的上结果应该普适，但 index option（SPX 长 tenor 几乎没有 skew kink）和 single-name 高 leverage 标的的 regime split 位置可能完全不一样。

剩下几件比较细。Butterfly 检查只看了离散网格，`g(k) > 0` 是逐点条件，离散采样会漏掉 narrow region 的负密度，生产里要走 SVI raw-form constraint（[Gatheral & Jacquier 2014](https://arxiv.org/abs/1204.0646) Theorem 4.2）或者直接 SSVI no-butterfly 参数化。这次也没碰 SABR 的 vol-of-vol 跨 tenor 稳定性——`ν` 在长 tenor fit 出来能不能用来推短 tenor 的 smile shape，是 SABR 真正区别于 SVI 的地方，per-slice fitting 没用到，所以这套对比里 SABR 大概被低估。fit metric 是 implied vol RMSE 不是 PnL，bps 上"差 5×"在 hedging error 上可能根本看不到，desk 上真正决定用哪个模型的是后者。

---

## English {#en}

Last spring I picked up an interest in stochastic volatility. Option-pricing textbooks open with Black-Scholes' constant-vol assumption, but the real market gives you a surface over strikes and tenors that keeps moving. The system underneath is a coupled SDE — theoretically clean, practically a mess to fit.

The SVI lineage was closed out by [Gatheral and Jacquier 2014](https://arxiv.org/abs/1204.0646) into SSVI with no-butterfly conditions; SABR has had its share of upgrades since [Hagan 2002](https://www.researchgate.net/publication/235622441_Managing_Smile_Risk), notably [Hagan et al. 2014 "Arbitrage-Free SABR"](https://www.researchgate.net/publication/265252097_Arbitrage-Free_SABR), which replaces the asymptotic expansion with a PDE solve. But which model a desk should actually use is less clear in the literature than you'd expect. So I ran vanilla SVI against vanilla Hagan-SABR — the two textbook baselines — on real AAPL data.

The choice between the two reduces to a fight between two properties: whether the parameters carry financial meaning, and how tightly the curve fits the market. SABR sits at the parameter end — all four parameters are quantities someone on a desk can stress-test or extrapolate — but Hagan's asymptotic expansion runs out of curvature at short tenors. SVI sits at the fit end: it bends to any smile shape, but the parameters carry no information about the underlying SDE.

### The design choices in each model

[SABR](https://www.researchgate.net/publication/235622441_Managing_Smile_Risk) is a genuine stochastic-vol model: volatility follows its own diffusion, coupled to the price diffusion via a correlation `ρ`. Its four parameters `α, β, ρ, ν` all carry financial meaning — `α` is ATM vol, `β` controls stickiness (lognormal vs normal), `ν` is vol-of-vol, `ρ` is spot–vol correlation. The selling point is interpretable, extrapolable parameters. The cost is that the implied-vol formula SABR ships with (Hagan's asymptotic expansion) is a long-tenor approximation, and its assumptions break down in short, deeply-OTM regimes.

[SVI](https://www.researchgate.net/publication/265252297_A_Parsimonious_Arbitrage-Free_Implied_Volatility_Parameterization_with_Application_to_the_Valuation_of_Volatility_Derivatives) takes the other path. It directly parameterizes implied total variance:

```plain text
w(k) = a + b · (ρ · (k − m) + √((k − m)² + σ²))
```

Five purely descriptive parameters, none traceable to an SDE. Without an SDE, SVI parameters don't tell you what the market is thinking. As a fitter, it bends to whatever the smile is doing. The cleanest framing is that SABR is in the business of explaining the market, and SVI is in the business of matching the curve.

### The experiment: AAPL across ten expiries

AAPL on 2024-09-13, ten expiries from 13 days to six months. For each expiry: pull call mids → solve BS implied vol → fit both SVI and SABR → compute per-strike RMSE. SVI additionally gets a butterfly-arbitrage diagnostic — the implied density `g(k) = ∂²C/∂K²` must stay ≥ 0 everywhere, otherwise the slice contains a butterfly arb.

| Expiry | T (y) | SVI RMSE (bps) | SABR RMSE (bps) | |---|---:|---:|---:| | 2024-09-27 | 0.04 | **121** | 577 | | 2024-10-18 | 0.10 | **40** | 287 | | 2024-11-15 | 0.17 | **18** | 97 | | 2024-12-20 | 0.27 | **14** | 40 | | 2025-01-17 | 0.35 | 10 | **13** | | 2025-03-21 | 0.52 | 7 | **5** |

### The result is a clean regime split

At short tenors (T ≤ 0.13y, roughly six weeks and in) SVI beats SABR by 2–5×. At 13 days SVI sits at 121 bps and SABR at 577 bps — almost 5×. Short-tenor smiles are deeply U-shaped with both wings steep, and SVI's five parameters can bend to that. SABR's lognormal asymptotic expansion can't generate enough curvature in this regime.

At long tenors (T ≥ 0.35y) the two essentially tie, and SABR slightly pulls ahead. Smiles flatten, the curve approaches linear, both models fit. SABR's edge at the long end probably comes from its lognormal-plus-vol-of-vol structure matching the gentle long-tenor skew shape natively. "Which model is better" has no standalone answer — it depends on the tenor.

### SVI's flexibility costs an explicit arbitrage check

Because SVI can bend a curve into a negative implied density in principle, butterfly arbitrage is something the fitter can produce without warning. So every fit needs `g(k) = ∂²C/∂K²` checked for non-negativity. On this snapshot all ten slices stay strictly positive; the tightest is the 13-day expiry at `g_min = 0.03` — close to the arb-free boundary but still inside. Short-tenor SVI needs monitoring. SABR is the opposite — SDE-grounded, butterfly arbitrage is precluded by construction (Hagan can violate wing monotonicity in deep OTM, but not butterfly). The price of bending tighter is having to police your own arbitrage.

### What this actually looks like on a desk

In production both models tend to get used, with different roles. Short-tenor slices are fit by SVI — the gap is too large to close by retuning SABR. The long end is fine with SABR, and the interpretable parameters get used downstream for risk management and stress tests. A common hybrid is SVI marking the surface for accuracy, with SABR then fit *to* the calibrated SVI surface to extract interpretable quantities (`ρ`, `ν`). The SDE-grounded theory is beautiful, but day-to-day what production needs is a fitter that bends accurately to whatever shape the market is in and stays numerically arbitrage-free. SVI occupies that role with essentially no competition.

### What this experiment leaves on the table

The most obvious follow-up is PDE-SABR. I only tested vanilla Hagan; the PDE variant (Arbitrage-Free SABR) should pull SABR back at short tenors, at the cost of swapping a closed-form formula for a numerical solve and slowing calibration by an order of magnitude. The right next round is SVI vs Hagan SABR vs PDE SABR specifically in T ≤ 0.13y.

AAPL is one underlying. The pattern probably generalizes across large-cap, liquid, moderately event-driven names, but index options (SPX, almost no skew kink at the long end) and high-leverage single names will probably sit at a different regime-split point.

A few smaller items. The butterfly check was a discrete grid: `g(k) > 0` is pointwise, and sparse sampling can miss a narrow negative-density region — production code should use SVI raw-form constraints from [Gatheral and Jacquier 2014](https://arxiv.org/abs/1204.0646) Theorem 4.2, or adopt SSVI's no-butterfly parameterization directly. I also didn't exercise SABR's vol-of-vol stability across tenors, which is exactly where SABR's parameters earn their keep; per-slice fitting underuses that, so this comparison probably understates SABR. The metric throughout is implied-vol RMSE, not PnL — a 5× gap in bps may not show up in hedging error at all, and a desk deciding which model to use cares about hedging error first.
