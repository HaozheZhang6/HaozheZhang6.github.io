---
layout: post
title: 估 KL penalty 的三个 estimator / Three ways to estimate the KL penalty
date: 2026-03-22
description: K1 / K2 / K3 三个 sample-based KL estimator 的 bias / variance 推导和实际选哪一个
tags: [kl-divergence, estimator, control-variate]
categories: [rl]
notion_id: 36358ac4-b0ac-812c-990b-fc3b16df6c30
last_updated: 2026-05-16
bilingual: true
---

## 中文 {#cn}

**目录**

- [Notation](#cn-notation)
- [K1：plug-in estimator](#cn-k1)
- [K2：用 bias 换 variance](#cn-k2)
- [K3：control variate 救场](#cn-k3)
- [三个 estimator 的实际差距](#cn-impact)
- [References](#cn-refs)

PPO 和 GRPO 这套 RL 框架每一步都要算一个

$$\mathrm{KL}(\pi \,\|\, \pi_{\text{ref}}) = \mathbb{E}_{x \sim \pi}\!\left[\log \frac{\pi(x)}{\pi_{\text{ref}}(x)}\right]$$

作为 reference policy（被冻结的初始 LLM，比如 SFT 完那个）的 anchor，防止训练把模型行为推得太远。这里 KL（Kullback-Leibler divergence，衡量两个概率分布有多不同的标准度量）越大越说明当前 policy 偏离了初始 policy。整个 vocab 上求和精确计算这个量太贵——一个 step 的 logits 张量已经吃掉一大块 VRAM，再叠一个 full-vocab KL summation 显存就不够——所以社区都用 **sample-based estimator**（用从 policy 采样的少量 token 去估这个期望，而不是穷举全 vocab）近似。

Schulman (2020) 那篇 [Approximating KL Divergence](http://joschu.net/blog/kl-approx.html) blog 整理了三个 estimator，社区一般叫 **K1**、**K2**、**K3**。Paper 里几乎不写为什么选了哪一个，但同一份 RL 配方换一个 estimator，最终 reward 能差到 single-digit 百分点。这篇是把三个 estimator 的推导、bias / variance 分析、和实际选哪一个放在一起。

### Notation {#cn-notation}

- $$x \sim \pi$$：从当前 policy $$\pi$$ 采的一条 sample
- $$r = \pi_{\text{ref}}(x) / \pi(x)$$：reference 和当前 policy 的 **likelihood ratio**
- $$\mathbb{E}_{x \sim \pi}[\,\cdot\,]$$：在 $$\pi$$ 下取期望
- $$\mathrm{KL}(\pi \,\|\, \pi_{\text{ref}})$$：要估计的目标量

### K1：plug-in estimator {#cn-k1}

$$K_1 = -\log r = \log \frac{\pi}{\pi_{\text{ref}}}$$

直接根据 KL 的定义就是 **unbiased**：

$$\mathbb{E}_{x \sim \pi}[-\log r] = \mathbb{E}_{x \sim \pi}\!\left[\log \frac{\pi(x)}{\pi_{\text{ref}}(x)}\right] = \mathrm{KL}(\pi \,\|\, \pi_{\text{ref}}).$$

但 K1 单条 sample 没有符号约束——$$r > 1$$ 时 $$-\log r$$ 为负，$$r < 1$$ 时为正。Policy 一漂移 $$r$$ 的分布两边都拖很远，单 sample 估计噪声极大。三个里 variance 最高。

直接用 K1 训练的实际问题是：KL 在 batch 上估出来有时为负——这跟 $$\mathrm{KL} \ge 0$$ 的定义矛盾，体现在训练里就是 KL penalty 偶尔贡献一个负的 loss，等同于鼓励 policy 偏离 ref。看起来荒谬，但低 sample-size 的 batch 上 K1 确实允许这件事发生。

### K2：用 bias 换 variance {#cn-k2}

$$K_2 = \tfrac{1}{2}(\log r)^2$$

K2 永远非负（一个平方），单 sample variance 比 K1 低一个量级——直觉上是因为 K2 把符号信息丢了、只保留幅度。

代价是 **biased**。K2 估的是 $$\tfrac{1}{2}\mathbb{E}[(\log r)^2]$$，**不是 KL 本身**。两者只在 $$\pi \approx \pi_{\text{ref}}$$ 时由 Taylor 展开重合：

$$\log r = (r - 1) - \tfrac{1}{2}(r - 1)^2 + O\!\left((r-1)^3\right),$$

平方一下到 leading order $$(\log r)^2 \approx (r-1)^2$$，同时 KL 本身在该 limit 下展开

$$\mathrm{KL} \approx \tfrac{1}{2}\mathbb{E}[(r-1)^2].$$

所以 $$K_2 \approx \mathrm{KL}$$ 只在 $$\pi$$ 跟 $$\pi_{\text{ref}}$$ 距离很小时成立；policy 漂得越远，K2 偏差越大。

实践上 K2 的风险是它在训练过程中"看起来"很稳——非负、variance 低——但监控的不是想 penalize 的那个 KL。Policy 大幅偏离 ref 的时候，K2 给的数字可能远低于真实 KL，模型已经漂飞但监控看不到，penalty 也压不回来。

### K3：control variate 救场 {#cn-k3}

$$K_3 = (r - 1) - \log r$$

K3 是 K1 加一个零均值 **control variate** $$(r - 1)$$。算 $$(r - 1)$$ 在 $$\pi$$ 下的期望：

$$\begin{aligned}
\mathbb{E}_{x \sim \pi}[r - 1] &= \mathbb{E}_{x \sim \pi}\!\left[\frac{\pi_{\text{ref}}(x)}{\pi(x)}\right] - 1 \\
&= \sum_{x} \pi(x) \cdot \frac{\pi_{\text{ref}}(x)}{\pi(x)} - 1 \\
&= \sum_{x} \pi_{\text{ref}}(x) - 1 = 0.
\end{aligned}$$

$$(r-1)$$ 期望为 0，加到 K1 上不改变期望——$$\mathbb{E}[K_3] = \mathbb{E}[K_1] + \mathbb{E}[r-1] = \mathrm{KL} + 0 = \mathrm{KL}$$——所以 K3 仍然 **unbiased**。

为什么 variance 比 K1 低？control variate 这个 trick 的关键是被加的那一项跟原 estimator **同向相关**：$$r$$ 大的时候 $$(r-1)$$ 大、$$-\log r$$ 小（甚至为负）；$$r$$ 小的时候反过来——两者的噪声部分相互抵消，加起来 variance 下降。

K3 还有个意外的好处：永远 **non-negative**。在 $$r = 1$$ 附近 Taylor 展开

$$-\log r = -(r-1) + \tfrac{1}{2}(r-1)^2 - \tfrac{1}{3}(r-1)^3 + \cdots,$$

代回得

$$K_3 = (r-1) + (-\log r) = \tfrac{1}{2}(r-1)^2 + O\!\left((r-1)^3\right),$$

leading term $$\tfrac{1}{2}(r-1)^2 \ge 0$$。更严格地：$$K_3(1) = 0$$、$$K_3'(r) = 1 - 1/r$$ 在 $$r=1$$ 处也为 0、$$K_3''(r) = 1/r^2 > 0$$——K3 是 $$r$$ 的凸函数，全局最小值 0 在 $$r=1$$ 处取到。

总结：K3 同时拿到了 K1 的 unbiased、K2 的 non-negative、以及比 K1 低的 variance。Schulman 推荐这个，DeepSeek 和 R1 系默认用的也是它。

### 三个 estimator 的实际差距 {#cn-impact}

不同 estimator 在同一份 RL 配方上的影响并不小。Schulman (2020) 的 blog 和后续社区复现都给出过 single-digit 百分点级别的 final reward 差距，具体大小看任务。Paper 里几乎不写自己用了哪一个 estimator，意味着 published 的"算法提升"里有一部分实际上是 estimator 差异，不是算法差异。

实践上默认用 K3。K2 有人用，但要意识到它在大 policy drift 下估的根本不是想要的 KL；K1 主要出现在教学代码或 sanity check 里——variance 高到训练根本起不来。

Control variate 这个 trick 不是 RL 独有的。REINFORCE (Williams, 1992) 里的 baseline subtraction（advantage = reward − baseline）本质上也是 control variate，目的一样：减一个零均值量来降 variance，不动期望。K3 是同一套思路在 KL 估计上的一个特别整洁的应用。

### References {#cn-refs}

- Schulman, J. (2020). Approximating KL Divergence. [joschu.net/blog/kl-approx](http://joschu.net/blog/kl-approx.html)
- Schulman et al. (2017). Proximal Policy Optimization Algorithms. [arXiv:1707.06347](https://arxiv.org/abs/1707.06347)
- Shao et al., DeepSeek (2024). DeepSeekMath / GRPO. [arXiv:2402.03300](https://arxiv.org/abs/2402.03300)
- Williams, R. J. (1992). Simple Statistical Gradient-Following Algorithms for Connectionist Reinforcement Learning (REINFORCE). *Machine Learning* 8.

---

## English {#en}

**Contents**

- [Notation](#en-notation)
- [K1: the plug-in estimator](#en-k1)
- [K2: variance for bias](#en-k2)
- [K3: a control variate gets you both](#en-k3)
- [What the difference looks like in practice](#en-impact)
- [References](#en-refs)

PPO and GRPO both need to compute

$$\mathrm{KL}(\pi \,\|\, \pi_{\text{ref}}) = \mathbb{E}_{x \sim \pi}\!\left[\log \frac{\pi(x)}{\pi_{\text{ref}}(x)}\right]$$

at every training step, as the reference-policy anchor — π_ref is the frozen initial LLM (usually the post-SFT checkpoint) — that prevents the model from drifting too far. KL here is Kullback-Leibler divergence, the standard measure of how different two distributions are; a bigger KL means the current policy has drifted further from where it started. Computing this exactly by summing over the entire vocabulary isn't feasible — the logits tensor for a single step already eats a substantial fraction of VRAM, and a full-vocab KL summation pushes it over. So the community estimates it from a handful of sampled tokens instead.

Schulman (2020), [Approximating KL Divergence](http://joschu.net/blog/kl-approx.html), lays out three **sample-based estimators**, conventionally called **K1**, **K2**, and **K3**. Papers almost never document which one they used, but swapping K1 for K3 inside the same RL recipe moves the final reward by single-digit percentage points. This post walks through the derivations, the bias / variance trade-offs, and which one to actually use.

### Notation {#en-notation}

- $$x \sim \pi$$ — one sample drawn from the current policy $$\pi$$
- $$r = \pi_{\text{ref}}(x) / \pi(x)$$ — **likelihood ratio** of reference to current policy
- $$\mathbb{E}_{x \sim \pi}[\,\cdot\,]$$ — expectation under $$\pi$$
- $$\mathrm{KL}(\pi \,\|\, \pi_{\text{ref}})$$ — the target quantity to estimate

### K1: the plug-in estimator {#en-k1}

$$K_1 = -\log r = \log \frac{\pi}{\pi_{\text{ref}}}$$

By definition K1 is **unbiased**:

$$\mathbb{E}_{x \sim \pi}[-\log r] = \mathbb{E}_{x \sim \pi}\!\left[\log \frac{\pi(x)}{\pi_{\text{ref}}(x)}\right] = \mathrm{KL}(\pi \,\|\, \pi_{\text{ref}}).$$

K1 has no sign constraint at the single-sample level. When $$r > 1$$ (the reference assigns this sample more mass than the current policy does), $$-\log r$$ is negative; when $$r < 1$$, it's positive. Under any real policy drift, $$r$$ has heavy tails on both sides, and the per-sample estimate can be a large positive or large negative number. K1 has the highest variance of the three.

A practical consequence: KL estimated with K1 on a small batch can come out negative on average — mathematically impossible for the true KL. In training, this shows up as a negative KL-penalty contribution to the loss, briefly rewarding the model for moving away from the reference. It looks absurd, but on a small enough batch K1 actually allows it.

### K2: variance for bias {#en-k2}

$$K_2 = \tfrac{1}{2}(\log r)^2$$

K2 is always **non-negative** (a square), and its single-sample variance is about an order of magnitude lower than K1's. Intuitively, K2 throws away the sign of $$\log r$$ and keeps only magnitude.

The cost is **bias**. K2 estimates $$\tfrac{1}{2}\mathbb{E}[(\log r)^2]$$, **not KL**. The two coincide only when $$\pi \approx \pi_{\text{ref}}$$, via Taylor expansion:

$$\log r = (r - 1) - \tfrac{1}{2}(r-1)^2 + O\!\left((r-1)^3\right),$$

so $$(\log r)^2 \approx (r-1)^2$$ to leading order, and KL in the same limit expands to

$$\mathrm{KL} \approx \tfrac{1}{2}\mathbb{E}[(r-1)^2].$$

So $$K_2 \approx \mathrm{KL}$$ holds only when $$\pi$$ and $$\pi_{\text{ref}}$$ are close; once the policy drifts meaningfully, K2 starts undershooting the true KL — the screen shows small, well-behaved values while the quantity being measured has detached from the KL the penalty was supposed to enforce.

The practical risk is that the training curve looks healthy — non-negative KL, low variance — while the actual policy is drifting more than the loss reports. The penalty stops doing its job before you notice.

### K3: a control variate gets you both {#en-k3}

$$K_3 = (r-1) - \log r$$

K3 is K1 plus a zero-mean **control variate** $$(r-1)$$. The expectation of $$(r-1)$$ under $$\pi$$ is zero:

$$\begin{aligned}
\mathbb{E}_{x \sim \pi}[r - 1] &= \mathbb{E}_{x \sim \pi}\!\left[\frac{\pi_{\text{ref}}(x)}{\pi(x)}\right] - 1 \\
&= \sum_x \pi(x) \cdot \frac{\pi_{\text{ref}}(x)}{\pi(x)} - 1 \\
&= \sum_x \pi_{\text{ref}}(x) - 1 = 0.
\end{aligned}$$

Adding it to K1 leaves the expectation untouched ($$\mathbb{E}[K_3] = \mathbb{E}[K_1] + \mathbb{E}[r-1] = \mathrm{KL} + 0 = \mathrm{KL}$$), but variance drops because $$(r-1)$$ and $$-\log r$$ are **positively correlated** — when one is high the other is also high, and adding them cancels part of their shared noise.

K3 is also always non-negative. Taylor-expanding $$-\log r$$ around $$r = 1$$:

$$-\log r = -(r-1) + \tfrac{1}{2}(r-1)^2 - \tfrac{1}{3}(r-1)^3 + \cdots,$$

substituting back:

$$K_3 = (r-1) + (-\log r) = \tfrac{1}{2}(r-1)^2 + O\!\left((r-1)^3\right).$$

The leading term $$\tfrac{1}{2}(r-1)^2 \ge 0$$. More rigorously: $$K_3(1) = 0$$, the first derivative $$K_3'(r) = 1 - 1/r$$ also vanishes at $$r=1$$, and the second derivative $$K_3''(r) = 1/r^2 > 0$$ is strictly positive — K3 is **convex** in $$r$$ with global minimum 0 at $$r = 1$$.

So K3 collects all three properties at once: unbiased (like K1), non-negative (like K2), and lower variance than K1. Schulman recommends K3; DeepSeek and the R1-lineage code use it by default.

### What the difference looks like in practice {#en-impact}

The gap between estimators matters more than the literature suggests. Schulman (2020) and subsequent community reproductions report single-digit percentage-point differences in final reward when swapping K1 for K3 inside the same recipe, with the exact magnitude task-dependent. Most papers don't state which estimator they used, which means published "algorithm improvements" can be partially or entirely attributable to estimator choice across the comparison.

The practical default is K3. K2 has its users, but anyone reaching for it should know that under real policy drift the quantity being measured isn't the KL anymore. K1 mostly appears in pedagogical contexts or sanity checks — its variance makes training too unstable to actually use.

The control-variate trick isn't specific to KL estimation. REINFORCE's baseline subtraction (Williams, 1992) — advantage = reward − baseline — is the same idea: subtract a zero-mean quantity to reduce variance without moving the expectation. K3 is that pattern applied very neatly to KL.

### References {#en-refs}

- Schulman, J. (2020). Approximating KL Divergence. [joschu.net/blog/kl-approx](http://joschu.net/blog/kl-approx.html)
- Schulman et al. (2017). Proximal Policy Optimization Algorithms. [arXiv:1707.06347](https://arxiv.org/abs/1707.06347)
- Shao et al., DeepSeek (2024). DeepSeekMath / GRPO. [arXiv:2402.03300](https://arxiv.org/abs/2402.03300)
- Williams, R. J. (1992). Simple Statistical Gradient-Following Algorithms for Connectionist Reinforcement Learning (REINFORCE). *Machine Learning* 8.
