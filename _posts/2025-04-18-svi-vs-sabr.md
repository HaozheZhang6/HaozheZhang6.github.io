---
layout: post
title: SVI vs SABR：短期合约 vol smile 上的差距
date: 2025-04-18 16:00:00 -0700
description: 对 SDE 金融建模起了兴趣，跑了一下 AAPL vol surface 拟合——short tenor SVI 比 SABR 好 2–5×
tags: finance volatility quant
categories: research
---

## 中文

去年春天偶然对 stochastic volatility 起了兴趣。option pricing 教科书一上来就是 Black-Scholes 的 constant-vol 假设，但实际市场给你的是一个 K 和 T 两个维度的曲面，而且这个曲面还在动。底层是一组耦合的 SDE，理论自洽性很高，但实际拟合一直是 messy business。趁着兴起挑了 SVI 和 SABR——工业上最常用的两个 model——在 AAPL 真实数据上跑了一次对比，记一下。

### 两个模型在做什么不一样

**SABR**（[Hagan 2002](https://www.researchgate.net/publication/235622441_Managing_Smile_Risk)）是真正意义上的 stochastic-vol model：vol 服从一个独立的扩散过程，跟价格扩散通过 correlation `ρ` 耦合。它的 4 个参数 `α, β, ρ, ν` 都有金融意义——`α` 是 ATM vol，`β` 决定 stickiness（lognormal vs normal），`ν` 是 vol-of-vol，`ρ` 是 spot-vol 相关性。SABR 的卖点是**参数可解释、可外推**；缺点是它给出的 implied vol 公式（Hagan asymptotic expansion）是大 T 的近似，在短期、深 OTM 时假设 break down。

**SVI**（[Gatheral 2004](https://www.researchgate.net/publication/265252297_A_Parsimonious_Arbitrage-Free_Implied_Volatility_Parameterization_with_Application_to_the_Valuation_of_Volatility_Derivatives)）走另一条路：直接 parameterize implied total variance

```
w(k) = a + b · (ρ · (k − m) + √((k − m)² + σ²))
```

5 个参数纯 descriptive。它不来自任何 SDE，所以拿到 SVI 参数后说不出"市场在想什么"；但作为 fitter 它极其灵活，可以贴合任何形状的 smile。

**核心 trade-off：SABR 给你"为什么"，SVI 给你"贴得多紧"。**

### 实验

AAPL 2024-09-13 snapshot，10 个 expiry 从 13 天到 6 个月。每个 expiry 拉 call mid quote → solve BS implied vol → 同时用 SVI 和 SABR 拟合 → 算 per-strike RMSE。SVI 额外做一个 butterfly-arbitrage diagnostic：implied density `g(k) = ∂²C/∂K²` 处处 ≥ 0 = 该 slice 无 butterfly 套利。

完整数据和图在 [`option_analysis_system`](https://github.com/HaozheZhang6/option_analysis_system) repo 的 `docs/analysis/06_svi_vs_sabr/`。

### 结果有一个明显的 regime split

| Expiry | T (y) | SVI RMSE (bps) | SABR RMSE (bps) |
|---|---:|---:|---:|
| 2024-09-27 | 0.04 | **121** | 577 |
| 2024-10-18 | 0.10 | **40** | 287 |
| 2024-11-15 | 0.17 | **18** | 97 |
| 2024-12-20 | 0.27 | **14** | 40 |
| 2025-01-17 | 0.35 | 10 | **13** |
| 2025-03-21 | 0.52 | 7 | **5** |

**T ≤ 0.13y（约 6 周以内）：SVI 比 SABR 好 2–5×。** 13 天合约上 SVI 121 bps 对 SABR 577 bps——差不多 5 倍。直观解释：短期 smile 是 deeply U 形，两翼都很陡；SVI 的 5 个参数可以弯过去，SABR 的 Hagan 近似公式在这种 regime 下根本拉不出那么大的曲率。

**T ≥ 0.35y：两者基本打平，SABR 反而略好。** smile flatten，曲线接近线性，谁拟合都行——SABR 在长端略胜，可能是因为它的 lognormal-plus-vol-of-vol 设定本来就匹配长期 smile 的轻微 skew。

### Butterfly arbitrage 检查

SVI 灵活，理论上能把曲线弯到 implied density 局部为负，产生 butterfly 套利。所以拟合完要算一下 `g(k)` 的正性。这个 snapshot 10 个 slice 全部 `g_min > 0`，最紧的是 13 天那一个 (`g_min = 0.03`)——离 arb-free 边界很近但还在内侧。短期 SVI 是要监控的。

### 实践 take-away

- **短期 vol slice 用 SVI 拟合**，差距大到不是 SABR 调一调参数能补回来的。
- **长期 SABR 也行**，而且参数有 financial meaning，便于 risk management 和 stress test。
- **生产里两者并用**：SVI 负责 marking（精度优先），完了再 fit 一组 SABR 在 SVI 出来的 surface 上提取 `ρ` / `ν` 等可解释量。这套 "best-of-both" 在很多 trading desk 是标配。

底层 SDE 那套理论很漂亮，但工业实践里你真正需要的常常是**一个能精确弯到市场形状、且 numerically 无套利的 fitter**。SVI 在那个位置上几乎没有竞争对手。

---

## English

Last spring I picked up an interest in stochastic volatility. Option-pricing textbooks open with Black-Scholes' constant-vol assumption, but the real market gives you a surface over strikes and tenors that keeps moving. Underneath the surface is a coupled SDE system — theoretically clean, practically a mess to fit. I went and ran a small experiment comparing the two industry-standard models, SVI and SABR, on real AAPL data. Writing it down.

### What separates the two models

**SABR** ([Hagan 2002](https://www.researchgate.net/publication/235622441_Managing_Smile_Risk)) is a genuine stochastic-vol model: vol follows its own diffusion, coupled to the price diffusion through a correlation `ρ`. Its four parameters `α, β, ρ, ν` all carry financial meaning — `α` is ATM vol, `β` sets the stickiness (lognormal vs normal), `ν` is vol-of-vol, `ρ` is spot–vol correlation. The selling point is **interpretable, extrapolable parameters**. The cost is that the implied-vol formula SABR ships with (Hagan's asymptotic expansion) is a long-tenor approximation, and it breaks down in short, deeply-OTM regimes.

**SVI** ([Gatheral 2004](https://www.researchgate.net/publication/265252297_A_Parsimonious_Arbitrage-Free_Implied_Volatility_Parameterization_with_Application_to_the_Valuation_of_Volatility_Derivatives)) takes the other path. It directly parameterizes implied total variance

```
w(k) = a + b · (ρ · (k − m) + √((k − m)² + σ²))
```

with five purely descriptive parameters. It comes from no SDE, so SVI parameters don't tell you what the market is *thinking*. But as a fitter it bends to whatever the smile is doing.

**The core trade-off: SABR gives you a "why," SVI gives you "how tight."**

### The experiment

AAPL on 2024-09-13, ten expiries from 13 days to six months. For each expiry: pull call mids → solve BS implied vol → fit both SVI and SABR → compute per-strike RMSE. SVI additionally gets a butterfly-arbitrage diagnostic — the implied density `g(k) = ∂²C/∂K²` must stay ≥ 0 everywhere, otherwise the slice contains a butterfly arb.

Full data and plots are in [`option_analysis_system`](https://github.com/HaozheZhang6/option_analysis_system) under `docs/analysis/06_svi_vs_sabr/`.

### The result is a clean regime split

| Expiry | T (y) | SVI RMSE (bps) | SABR RMSE (bps) |
|---|---:|---:|---:|
| 2024-09-27 | 0.04 | **121** | 577 |
| 2024-10-18 | 0.10 | **40** | 287 |
| 2024-11-15 | 0.17 | **18** | 97 |
| 2024-12-20 | 0.27 | **14** | 40 |
| 2025-01-17 | 0.35 | 10 | **13** |
| 2025-03-21 | 0.52 | 7 | **5** |

**Short tenors (T ≤ 0.13y, roughly six weeks and in): SVI beats SABR by 2–5×.** At 13 days SVI sits at 121 bps and SABR at 577 bps — almost 5×. The picture explains it: short-tenor smiles are deeply U-shaped with both wings steep; SVI's five parameters can bend to that, while SABR's lognormal asymptotic expansion can't generate the curvature.

**Long tenors (T ≥ 0.35y): essentially tied, and SABR even pulls slightly ahead.** Smiles flatten and the curve goes nearly linear. SABR's edge at the long end probably comes from its lognormal-plus-vol-of-vol structure matching the gentle long-tenor skew shape natively.

### Butterfly arbitrage check

SVI's flexibility means it can in principle bend a curve into a negative implied density and create butterfly arbitrage. So after fitting you have to check `g(k) = ∂²C/∂K²` stays non-negative everywhere. On this snapshot all ten slices stay strictly positive; the tightest is the 13-day expiry at `g_min = 0.03` — close to the arb-free boundary but still inside. Short-tenor SVI is worth keeping an eye on.

### Practical take-aways

- **Use SVI for short-tenor slices.** The gap is too large to close by retuning SABR.
- **SABR is fine at the long end**, and it gives you interpretable parameters for risk management and stress tests.
- **Production uses both.** SVI marks the surface (accuracy first), then SABR is fit *to* the calibrated SVI surface to extract interpretable quantities (`ρ`, `ν`). That "best-of-both" stack is standard on most trading desks.

The SDE-grounded theory is beautiful, but what production usually needs is **a fitter that bends accurately to whatever shape the market gives you, and is numerically arbitrage-free.** SVI sits in that role with very little real competition.
