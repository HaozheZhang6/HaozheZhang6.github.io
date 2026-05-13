---
layout: post
title: PPO 到 GSPO 究竟在改什么
date: 2026-03-15 14:00:00 -0700
description: PPO/DPO/GRPO/GSPO 的 anatomy、K1/K2/K3 KL 近似、sync vs async 一次过梳理
tags: llm rl training
categories: engineering
---

## 中文

### RL 在 LLM 上要解决什么

SFT 完之后你有一个 baseline policy π_0，它在 corpus 上拟合得差不多了。但 SFT 没有"偏好"这个概念——它对所有训练样本一视同仁。RL 这一层做的事，本质上是"用一个 reward signal 把 π_0 推到一个更偏好的方向"。reward 可以是 preference（人或 RM 投票），也可以是 verifier（math 对错、code 能不能跑、format 对不对）。

难点在哪？reward 是 sparse 的、noisy 的、可能 hackable 的；policy 更新一定要保守，否则会 catastrophic forgetting 把 SFT 学到的能力洗掉；RL 又特别吃算力，rollout 一次比 forward 贵几个数量级。所有 PPO / DPO / GRPO / GSPO 的差异，归根结底都在"如何用更少的算力、更稳定的方式施加这股推力"。

### PPO 的 anatomy

PPO 是经典版。每一个 training step 你要做这几件事：

1. **Rollout**：用当前 policy π 对一个 batch 的 prompt 各采 K 条 response（K 一般 1–16）。
2. **Reward**：用 reward model 给每条 response 打分，拿到 R_i。
3. **Value baseline**：另一个独立的 critic 模型 V(s)，估算每条 response 在每个 token 位置的 baseline value。
4. **Advantage**：A = R − V，"这条 sample 比 baseline 好多少"。一般做 GAE 把这个量在 token 级别 smooth 一下。
5. **Importance ratio**：r_t = π(a_t∣s_t) / π_old(a_t∣s_t)，"现在的 policy 比 rollout 时的 policy 在这个 token 上 likelihood 增加了多少"。
6. **Clipped surrogate objective**：min(r·A, clip(r, 1−ε, 1+ε)·A)。这是 PPO 的 signature 招——通过 clip ratio 防止 policy 在一个 step 内偏离 rollout 分布太远。
7. **KL penalty**：再加一个 β · KL(π ‖ π_ref) 把当前 policy 往 reference model（一般是 SFT 之后那个）拉，防止行为漂移。

光这一套，你显存里要养四个模型：policy、ref（算 KL）、critic（算 V）、reward model（算 R）。一个 token 要过四次 forward 才能出 loss。重、挑剔、慢。InstructGPT 当年用的就是它，能跑出来是因为 OpenAI 有那个 budget。

### DPO 偷掉的那一步

DPO 的洞察一行讲完：把 KL-constrained reward maximization 的 closed-form 解代回 likelihood 框架里，你会发现整个"RM + PPO"流水线，数学上等价于一个在 preference pair 上的二分类问题。

换句话说：你给我 `(prompt, chosen, rejected)`，我直接 supervised 学一个 likelihood ratio 的 sigmoid，就拿到了"在隐含 reward 下做 RL 的最优解"。RM 不要了、rollout 不要了、critic 不要了——显存里只剩 policy 和 ref。便宜、稳定、好 debug。

但它有一个不可逆的上限：DPO 只用 preference data，preference data 只覆盖你"已经能写出两个候选答案让人选一个"的那部分能力。reasoning 那种"需要先采几十条 rollout、靠 verifier 筛出对的"的题，DPO 学不到。这是为什么 DPO 改 tone / persona / refusal 都很好，但 DPO 不出 R1。

### GRPO：把 critic 也省了

GRPO 是 DeepSeek 那一篇。critic 模型本来是为了给 advantage 一个 baseline，GRPO 的观察是：如果我对同一个 prompt 采 K 条 response，这 K 条本身就是 sample-based 的 baseline。

所以 advantage 改成 group-relative：

```
A_i = (R_i − mean(R_{1..K})) / std(R_{1..K})
```

critic 模型砍掉，省一个模型的显存。importance ratio 和 clipping 还是 PPO 那一套，KL 也还在。GRPO 不是新算法，是"PPO 减一个模型 + group 当 baseline"。

更重要的是 GRPO 跟 verifier-style reward 配得很顺：math 对错、code exec、format match，本来就不用 learned RM——所以现实中 GRPO 实际跑起来往往是 policy + ref 两个模型，比 PPO 的四个干净得多。R1 出来之后基本所有开源 reasoning recipe 都是 GRPO 变种，我自己手头跑下来用得最多的也是它。

### KL 的几种 sample-based estimator

PPO / GRPO 的 KL penalty 项要算 `KL(π ‖ π_ref) = E_{x∼π}[log(π(x)/π_ref(x))]`。在 vocab 上 sum 太贵，所以用 sample 估计。社区沿用 John Schulman 那篇 [blog](http://joschu.net/blog/kl-approx.html) 总结的三种 estimator，叫 K1、K2、K3。统一记号：sample `x ∼ π`，令 `r = π_ref(x) / π(x)`。

**K1** = `−log r` = `log(π / π_ref)`

- **无偏**：`E_{x∼π}[−log r] = KL(π ‖ π_ref)`，定义即此。
- **可正可负**：单条 sample 可以是大的正数也可以是大的负数。
- **高方差**：最直接也最噪。

**K2** = `0.5 · (log r)²`

- **有偏**。它估计的是 `0.5 · E[(log r)²]`，**不是 KL 本身**。两者只在 `π ≈ π_ref` 时由 Taylor 展开重合：`log r ≈ (r − 1) − 0.5·(r − 1)² + …`，所以 `(log r)² ≈ (r − 1)²`，而 KL 在该 limit 下 ≈ `0.5·E[(r − 1)²]`。policy 漂得越远，K2 偏差越大。
- **永远非负**（平方）。
- **方差比 K1 小一个量级**。

**K3** = `(r − 1) − log r`

- **无偏**。关键是 `E[r − 1] = ∑ π · (π_ref/π) − 1 = ∑ π_ref − 1 = 0`，所以 `(r − 1)` 是一个均值为 0 的 control variate。把它加到 K1（也就是 `−log r`）上，期望不变（仍为 KL），但方差被压低——因为 `(r − 1)` 跟 `−log r` 同向相关，加起来抵消一部分噪声。
- **永远非负**。把 `−log r` Taylor 展回去：`K3 ≈ 0.5·(r − 1)² + higher order`，第一项 ≥ 0。等价的说法：`K3(1) = 0`、`K3'(1) = 0`、`K3''(r) = 1/r² > 0`，所以 K3 是 r 的凸函数，最小值在 1 处取 0。
- 无偏 + 方差比 K1 低。Schulman 推荐这个，DeepSeek / R1 系默认就是它。

直观上：K1 是最朴素的 plug-in 估计；K2 用平方换稳定，但 policy 漂远之后估的根本不是 KL；K3 通过 control variate 同时保住无偏和方差小。

实践含义只有一句：不同 paper 选不同 approximation 几乎不写理由，但同一个 RL 配方换 KL estimator 能差出 5–10% 的最终 reward。这是 numerical 陷阱，不是算法选型。

### GSPO：MoE 上的修补

Qwen3 那篇。在 MoE 上跑 GRPO，token-level importance ratio 噪声会大到病态——某个 token 在 rollout 时被 router 路给了 expert A，下一个 training step 这个 token 被路给了 expert B，importance ratio 就完全失控。

GSPO 的修法是把 importance ratio 抬到 sequence level，并且对序列长度做几何平均：

```
r_seq = (∏_t  π(a_t∣s_t) / π_old(a_t∣s_t))^(1/T)
```

token 级噪声被几何平均稀释，长度归一化保证不同长度的样本贡献可比。在 dense 模型上 GSPO 跟 GRPO 表现差别不大；在 MoE 上它是必须的——否则你要叠一堆 stabilization patch 才能勉强跑稳。

### 几个不动算法、提 throughput 的 trick

**Advantage filtering**：rollout 出来一个 batch，看 `|A|` 的分布，把 `|A| ≈ 0` 的 sample 直接丢掉。这种 sample 对 policy gradient 的贡献接近 0，但 forward / backward 一样花算力。GRPO 的 group-relative baseline 下，每组里 reward 落在中位数附近那条就是这类"学不到东西"的样本；过滤掉之后 effective batch 缩水，但 wall-clock 推进更快。需要相应调 lr / target batch。

**Reward / advantage 加小噪**：在 normalized advantage 或 reward 上叠一个小幅 Gaussian 噪声。看起来反直觉——噪声不是让训练变慢吗？但在 GRPO 这种 group-normalized 的 setting 下，组里若有一条 sample 的 reward 显著高过其他人，policy 会被过度推向那一条；加点 noise 让 update 不至于 over-fit 到 dominant sample 上，保住了 exploration。

两个都不动算法本身，但能在不上 async 的情况下把训练吞吐再挤一截。

### 工程：sync 还是 async

最后聊工程。同步 RL 是教科书写法：generate batch → train batch → 重复。每一 step 内 generation 和 training 串行。问题是 generation 时间不是常数——有些 prompt 50 token 就停了，有些跑到 8K，整个 batch 的 wall time 卡在最慢那条上。GPU 大部分时间在等。

异步把两端拆开：generation worker 持续往一个 queue 里塞 sample，training worker 持续从 queue 里取。代表工作是 Ant + 清华的 [AReaL](https://arxiv.org/abs/2505.24298)，throughput 报到同步版本的 2.7×。

但异步有自己的麻烦。sample 一旦堆在 queue 里就是 off-policy 的——它是某个旧 policy 跑出来的。训得越久，off-policy gap 越大。AReaL 给了一个 staleness-aware 的 PPO 变种来 handle 这件事，否则你训到一半会发现 importance ratio 整体偏掉，模型在 chase 一个其实早就过期的目标。

同步的优点是简单、稳定、好 debug；异步的优点是 throughput 高，但稳定性和 debug 难度都上一个台阶。我手头能玩的规模是 < 7B，同步够用；30B+ 我没卡训，看几篇大规模 RL paper 的 wall clock 数据，那个 scale 不异步基本完蛋。

---

## English

### What RL actually solves on top of SFT

After SFT you have a baseline policy π_0 that fits your corpus reasonably. SFT has no notion of preference — it treats every training example as equally desirable. The RL layer's job is to nudge π_0 toward a preferred direction using some reward signal. The reward can be a preference (human or RM vote), or a verifier (math correctness, code execution, format match).

What makes it hard: rewards are sparse, noisy, often hackable; policy updates have to be conservative or you catastrophically forget SFT capabilities; rollouts are expensive — orders of magnitude more compute than a forward pass. Every difference between PPO / DPO / GRPO / GSPO boils down to "how do we apply this nudge with less compute and more stability."

### PPO anatomy

PPO is the textbook version. Each training step:

1. **Rollout** — with the current policy π, sample K responses per prompt (K typically 1–16).
2. **Reward** — a reward model scores each response, giving R_i.
3. **Value baseline** — a separate critic V(s) estimates the per-token value baseline.
4. **Advantage** — A = R − V, "how much better than baseline is this sample." Usually smoothed with GAE.
5. **Importance ratio** — r_t = π(a_t∣s_t) / π_old(a_t∣s_t), "how much more likely the current policy makes this token than the rollout policy did."
6. **Clipped surrogate objective** — min(r·A, clip(r, 1−ε, 1+ε)·A). PPO's signature move; clipping the ratio prevents the policy from drifting too far from the rollout distribution within a single step.
7. **KL penalty** — an additional β · KL(π ‖ π_ref) pulls the current policy back toward a reference (usually post-SFT) model, guarding against behavioral drift.

That's four models in VRAM: policy, ref (for KL), critic (for V), reward model (for R). One token requires four forward passes to produce a loss. Heavy, brittle, slow. It's what InstructGPT used and it works because OpenAI had the budget.

### What DPO skips

DPO's insight reduces to one line: substitute the closed-form solution of KL-constrained reward maximization back into a likelihood framework, and the entire "RM + PPO" pipeline collapses into a binary classification problem on preference pairs.

In other words: give me `(prompt, chosen, rejected)`, I do supervised learning of a sigmoid over the likelihood ratio, and I've arrived at the optimum of the implicit-reward RL problem. No RM, no rollouts, no critic — only policy and ref in VRAM. Cheap, stable, easy to debug.

But there's an unfixable ceiling: DPO uses only preference data, and preference data only covers what you can already produce two candidate answers for and let someone pick one. Reasoning — the kind of problem where you need to sample dozens of rollouts and let a verifier filter the correct ones — DPO cannot learn. That's why DPO is great for tone, persona, refusal behavior, and why DPO does not produce R1.

### GRPO: kill the critic too

GRPO is DeepSeek's contribution. The critic exists to provide an advantage baseline; GRPO's observation is that if you sample K responses per prompt, the group itself is a sample-based baseline.

So advantage becomes group-relative:

```
A_i = (R_i − mean(R_{1..K})) / std(R_{1..K})
```

The critic model is dropped — one fewer model in VRAM. Importance ratio and clipping stay PPO; KL stays. GRPO isn't a new algorithm; it's "PPO minus one model plus a group baseline."

What makes GRPO actually a big deal is the natural fit with verifier rewards. Math correctness, code execution, format match — none of those need a learned RM. So in practice GRPO runs with just policy + ref in VRAM, much cleaner than PPO's four. After R1, nearly every open-weights reasoning recipe is a GRPO variant. It's the one I reach for most in my own experiments.

### Sample-based KL estimators

Both PPO and GRPO need to compute `KL(π ‖ π_ref) = E_{x∼π}[log(π(x)/π_ref(x))]`. The exact sum over vocab is too expensive, so you estimate from samples. The community settled on three estimators from John Schulman's [blog post](http://joschu.net/blog/kl-approx.html), called K1, K2, K3. With `x ∼ π` and `r = π_ref(x) / π(x)`:

**K1** = `−log r` = `log(π / π_ref)`

- **Unbiased**: `E_{x∼π}[−log r] = KL(π ‖ π_ref)` by definition.
- **Sign**: any single sample can be large positive or large negative.
- **High variance**: the plain plug-in estimator, also the noisiest.

**K2** = `0.5 · (log r)²`

- **Biased**. It's an estimator of `0.5 · E[(log r)²]`, **not KL itself**. They only coincide when `π ≈ π_ref`, by Taylor: `log r ≈ (r − 1) − 0.5·(r − 1)² + …`, so `(log r)² ≈ (r − 1)²`, and KL in that limit ≈ `0.5·E[(r − 1)²]`. The further the policy drifts, the larger the bias.
- **Always non-negative** (square).
- **Variance roughly an order of magnitude lower than K1**.

**K3** = `(r − 1) − log r`

- **Unbiased**. The trick: `E[r − 1] = ∑ π · (π_ref/π) − 1 = ∑ π_ref − 1 = 0`, so `(r − 1)` is a zero-mean control variate. Add it to K1 (= `−log r`) and the expectation stays at KL while the variance drops, because `(r − 1)` and `−log r` are correlated in the same direction — adding them cancels part of the noise.
- **Always non-negative**. Taylor-expand `−log r` back into the formula: `K3 ≈ 0.5·(r − 1)² + higher order`, and the leading term is ≥ 0. Equivalently: `K3(1) = 0`, `K3'(1) = 0`, `K3''(r) = 1/r² > 0`, so K3 is convex in r with its minimum at zero.
- Unbiased and lower-variance than K1. Schulman recommends this one; DeepSeek / R1-lineage code uses it by default.

Intuitively: K1 is the plug-in estimator; K2 trades variance for bias and ends up estimating the wrong quantity once the policy drifts; K3 uses a control variate to preserve both unbiasedness and low variance.

In practice the choice rarely shows up in papers and almost never with a reason, but the same RL recipe under different KL estimators can move the final reward by 5–10%. This is a numerical trap, not an algorithm choice.

### GSPO: the patch MoE needs

The Qwen3 paper. On MoE, GRPO's token-level importance ratio gets pathologically noisy — a token that the router sent to expert A during rollout might be routed to expert B during the next training step, and the importance ratio is no longer meaningful.

GSPO lifts the importance ratio to the sequence level and length-normalizes it:

```
r_seq = (∏_t π(a_t∣s_t) / π_old(a_t∣s_t))^(1/T)
```

Token-level noise is diluted by the geometric mean; length normalization makes sequences of different lengths comparable. On dense models GSPO doesn't differ much from GRPO. On MoE it's the difference between training and chasing your tail.

### Two algorithm-free throughput tricks

**Advantage filtering**: look at the distribution of `|A|` over a rollout batch and drop samples with `|A| ≈ 0`. These contribute almost nothing to the policy gradient but cost the same forward/backward. Under GRPO's group-relative baseline, the sample whose reward sits near the group median is exactly this kind — drop it and effective batch size shrinks while wall-clock progress accelerates. You will need to retune lr / target batch.

**Add small noise to reward or advantage**: a small Gaussian on the normalized advantage. It looks counterintuitive — shouldn't noise slow training? — but under group-normalized advantages, a single sample with much higher reward pulls the policy hard toward it. A bit of noise prevents the update from over-fitting to that dominant sample and preserves exploration.

Both leave the algorithm untouched. They squeeze extra throughput before you have to take on the complexity of async.

### Engineering: sync vs async

Synchronous RL is the textbook setup: generate batch → train batch → repeat. Generation and training serialize. The problem is that generation time isn't constant — some prompts stop at 50 tokens, others run to 8K, and the wall time of the whole batch bottlenecks on the slowest. GPUs spend a lot of time waiting.

Async decouples the two: a generation worker keeps filling a queue with samples, a training worker keeps consuming them. The reference work is [AReaL](https://arxiv.org/abs/2505.24298) from Ant + Tsinghua, reporting 2.7× throughput over a synchronous baseline.

Async has its own problem: any sample sitting in the queue is off-policy — it was generated by some older version of the policy. The longer training runs, the wider that gap. AReaL ships a staleness-aware PPO variant to handle this; without it your importance ratios drift systematically and the model chases a target that already expired.

Sync is simple, stable, easy to debug; async is faster but pays for it in stability and debugging complexity. The scale I can run on my own gear is < 7B, where sync is fine. I don't have the cluster for 30B+ — based on the wall-clock numbers in large-scale RL papers, async is basically required at that scale.
