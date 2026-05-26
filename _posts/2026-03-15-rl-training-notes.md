---
layout: post
title: 从 PPO 到 SAPO：每一代 RL 算法究竟在改什么 / From PPO to SAPO, what each version actually changes
date: 2026-03-15
description: PPO/DPO/GRPO/DAPO/GSPO/SAPO 的 anatomy、KL estimator、sync vs async、pass@k 上限
tags: [ppo, grpo, dpo, dapo, gspo, sapo]
categories: [rl]
notion_id: 36358ac4-b0ac-817e-9b9f-cf24d5abf14c
last_updated: 2026-05-16
bilingual: true
---

## 中文 {#cn}

**目录**

- [PPO：四个模型的 baseline](#cn-ppo)
- [DPO：用闭式解干掉 RM 和 rollout](#cn-dpo)
- [GRPO：用 rollout 自己当 baseline，再砍掉 critic](#cn-grpo)
- [DAPO：GRPO 在 long-CoT 上的四个补丁](#cn-dapo)
- [GSPO：MoE 上的 importance ratio 修补](#cn-gspo)
- [SAPO：把 hard clip 换成 soft adaptive gate](#cn-sapo)
- [两个不动算法、提 throughput 的 trick](#cn-tricks)
- [同步 vs 异步](#cn-async)
- [还没解决的部分](#cn-open)
- [References](#cn-refs)

LLM RL 这几年新缩写出得很密——PPO (Schulman et al., 2017)、DPO (Rafailov et al., 2023)、GRPO (Shao et al., DeepSeek 2024)、DAPO (ByteDance & Tsinghua AIR, 2025)、GSPO (Qwen3, 2025)、SAPO (Gao et al., Qwen, 2025)、AReaL (Ant Research, 2025)。但文献里很少把"改了什么"和"为什么改"放在一起说清楚。这篇是按时间顺序串这条 timeline。KL estimator（K1 / K2 / K3）那一段单独拆到 [估 KL penalty 的三个 estimator]({% post_url 2026-03-22-kl-estimators %}) 里。

表面看是不同 reward、不同 objective，本质上每一版都在解同一个问题：把 reward signal 注入 policy，同时控制 **gradient variance** 和每步 **compute**。Variance 高就训不稳，需要更多 sample 平均、更小 learning rate、更多 KL 约束；compute 高就养不起几个模型、rollout 贵、scale 不上去。PPO 这两条都拉满，后面每个新缩写都是在这两条轴上往左下挪——少一个模型、少一些 rollout、KL 估计更稳、importance ratio 不抖。

### PPO：四个模型的 baseline {#cn-ppo}

PPO（Schulman et al., 2017）是经典版，每一步 training 要做的事情比这个名字暗示的重得多。用当前 policy π 对一个 batch 的 prompt 各采 K 条 response（K 一般 1–16）；用一个独立的 **reward model** 给每条 response 打分得到 R_i；用第三个独立的 **critic** 模型 V(s) 估算每条 response 在每个 token 位置的 baseline value；**advantage** 取 A = R − V，一般再做 GAE 在 token 级别 smooth 一下；**importance ratio** 是 r_t = π(a_t∣s_t) / π_old(a_t∣s_t)；**clipped surrogate objective** 写成 min(r·A, clip(r, 1−ε, 1+ε)·A) 防止 policy 在一个 step 内偏离 rollout 分布太远；最后再加 β · KL(π ‖ π_ref) 把当前 policy 往 reference model（一般是 SFT 完那个）拉，防止行为漂移。

跑一套下来显存里要养四个模型：policy、ref、critic、reward model。一个 token 要过四次 forward 才能凑出一个 loss。InstructGPT（Ouyang et al., 2022）用的就是这套，能跑出来是因为 OpenAI 有那个 budget。

### DPO：用闭式解干掉 RM 和 rollout {#cn-dpo}

DPO（Rafailov et al., 2023）的洞察一行讲完：把 KL-constrained reward maximization 的 closed-form 解代回 likelihood 框架，整个"RM + PPO"流水线在数学上就退化成一个 preference pair 上的二分类。给定 `(prompt, chosen, rejected)`，直接 supervised 学一个 likelihood ratio 的 sigmoid，就拿到了"在隐含 reward 下做 RL 的最优解"。RM 不用了，rollout 不用了，critic 不用了——VRAM 里只剩 policy 和 ref，两个模型，cheap、稳、debug 友好。

代价是 reasoning 那条天花板。DPO 只吃 **preference data**，preference data 只覆盖"能写出两个候选答案让人选一个"这部分能力。"先采几十条 rollout，靠 verifier 筛出对的"这类 reasoning 任务，DPO 学不到——closed-form 那一步建立在"answer space 在 pair 里可枚举"的隐含假设上。这就是为什么 DPO 改 tone / persona / refusal 都很好，但 DPO 不出 R1。

### GRPO：用 rollout 自己当 baseline，再砍掉 critic {#cn-grpo}

GRPO（Shao et al., DeepSeek 2024）的观察是：critic 模型存在的目的是给 advantage 提供 baseline，如果对同一个 prompt 已经采了 K 条 response，这 K 条本身就是一个 sample-based baseline。Advantage 改成 group-relative，`A_i = (R_i − mean(R_{1..K})) / std(R_{1..K})`，critic 模型砍掉，又少一个模型。Importance ratio、clipping、KL 都还是 PPO 那套。GRPO 不是新算法，是 PPO 减一个模型、加一个 group baseline。

GRPO 真正爆出来是因为它跟 **verifier-style rewards** 配得太好——math 对错、code exec、format match 这种本来就不用 learned RM——所以现实里 GRPO 跑起来只需要 policy + ref 两个模型在 VRAM 里。R1（DeepSeek-AI, 2025）之后基本所有开源 reasoning recipe 都是 GRPO 变种。代价是 rollout 量没省（K 必须 ≥ 4 否则 group baseline 没意义），group 内 reward 还得有区分度，math 那种二值 reward 用 group 归一化效果一般，要在 verifier 那头做 reward shaping。

KL penalty 这一项要 sample 估计，三种 estimator（K1 / K2 / K3）的推导和实际差距单独拆到 [估 KL penalty 的三个 estimator]({% post_url 2026-03-22-kl-estimators %}) 这一篇——下面默认是 K3。

### DAPO：GRPO 在 long-CoT 上的四个稳定性补丁 {#cn-dapo}

GRPO 在标准 math reasoning 上跑得很顺，但在 long-CoT、long-rollout 这种 setting 下问题就出来了。DAPO（ByteDance & Tsinghua AIR, NeurIPS 2025）报告了四个具体的稳定性洞和对应的修法。

第一个是 **entropy collapse**。PPO 的对称 clip `[1−ε, 1+ε]` 在 token-level 上对 high-prob token 不利——它压住了向上探索的空间，policy 越训越窄，最后只输出几个 mode。DAPO 的 **Clip-Higher** 把上下两边做成不对称（典型 ε_high = 0.28、ε_low = 0.20），让 low-prob token 有机会被向上 explore。

第二个是 wasted compute。GRPO 一组 K 个 rollout 如果 reward 全一样（典型是全对或全错），group baseline 算出 advantage 全为 0，整组对 gradient 完全没贡献，但 forward / backward 算力照花。**Dynamic Sampling** 是在 rollout 后重新检查每组的 reward 分布，全相同的 prompt 直接丢掉重采，保证 batch 里每个 prompt 至少有一条非 0 advantage。

第三个是 sample-level normalization 在 long sequence 上偏。GRPO 默认 per-sample normalize advantage，一条 8K token 的 response 和一条 200 token 的 response 对最终 loss 贡献被算成一样，长 sequence 上的 per-token gradient 被稀释。DAPO 改成 **Token-Level Policy Gradient Loss**，直接在 token 级别加权，让长 response 按 token 数对应贡献——long-CoT 训练里这一项影响很大。

第四个是 overlong response 的 reward 噪声。模型生成到 context window 上限被强制截断的样本，verifier 通常给低 reward——但低 reward 不是因为"答错"，是因为没写完。直接 mask 掉会丢一部分信号，DAPO 用 **Overlong Reward Shaping** 做一个 length-aware penalty，让 reward 平滑过渡。

DAPO 在 Qwen2.5-32B 上 AIME 2024 拿到 50 分，比 DeepSeek-R1-Zero-Qwen-32B 的 47 分高，并且只用了 50% 的 training step。代码集成在 verl 上，是目前开源 long-CoT GRPO recipe 的事实 baseline。

### GSPO：MoE 上的 importance ratio 修补 {#cn-gspo}

MoE 上跑 GRPO，token-level importance ratio 噪声会大到病态——某个 token 在 rollout 时被 router 路给了 expert A，下一个 training step 这个 token 被路给了 expert B，importance ratio 完全失控。GSPO（Qwen3, 2025）把 importance ratio 抬到 sequence level 并做几何平均，`r_seq = (∏_t π(a_t∣s_t) / π_old(a_t∣s_t))^(1/T)`，token 级噪声被几何平均稀释，长度归一化保证不同长度样本贡献可比。

Dense 模型上 GSPO 跟 GRPO 差别不大——这是个 conditional improvement，主要在 MoE 那一档显出来；trl 和 verl 都已经把 sequence-level aggregation 支上了，实现成本不大。

### SAPO：把 hard clip 换成 soft adaptive gate {#cn-sapo}

PPO、GRPO、GSPO 的 clipping 都是 hard——ratio 落在 `[1−ε, 1+ε]` 之外就被硬卡掉，update surface 在 boundary 上不连续。SAPO（Gao et al., Qwen, 2025）把这个 hard clip 换成一个温度可控的 soft gate：ratio 偏离 1 越远 update 被衰减得越多，但永远不归零；衰减的速率本身是个可调的 temperature 参数。

SAPO 同时是 sequence-coherent（继承 GSPO）+ token-adaptive（细颗粒度衰减），训练曲线比 GSPO 更平滑，尤其 MoE 上稳得更好。Dense 模型上跟 GRPO / GSPO 差距很小——跟 GSPO 一样是 conditional improvement，是 GSPO 这条路的自然延伸。

### 两个不动算法、提 throughput 的 trick {#cn-tricks}

第一个是 **advantage filtering**：rollout 出来一个 batch，看 `|A|` 的分布，把 `|A| ≈ 0` 那些 sample 直接丢掉。它们对 policy gradient 贡献接近 0，但 forward / backward 一样花算力。在 GRPO 的 group-relative baseline 下，每组里 reward 落在中位数附近那条就是这类"学不到东西"的样本。Filter 之后 effective batch 缩水，但 wall-clock 推进更快，配套要重新调 lr / target batch。

第二个是在 normalized advantage 或 reward 上叠一个小幅 Gaussian 噪声——看起来反直觉，但 GRPO 这种 group-normalized setting 下，一条 reward 显著高过其他人的 sample 会把 policy 过度推向那一条；加点 noise 让 update 不至于 over-fit 到 dominant sample 上，保住 exploration。

两个都不动算法本身，能在不上 async 的情况下把训练吞吐再挤一截。两套都得重新扫 hyperparam，并且效果跟 verifier 质量绑——verifier 一糊，filter 会把"reward 错给的"样本一起留下来，集中在训练里反而把 model 推到错的方向上。

### 同步 vs 异步 {#cn-async}

教科书的同步 RL 是 generate batch → train batch → 重复，generation 和 training 串行。问题是 generation 时间不是常数——有些 prompt 50 token 就停了，有些跑到 8K——整个 batch 的 wall time 卡在最慢那条上，GPU 大部分时间在等。

异步把两端拆开：generation worker 持续往 queue 里塞 sample，training worker 持续从 queue 里取。代表工作是 AReaL（Ant Research, 2025），throughput 报到同步版本的 2.7×。但 queue 里的 sample 一旦堆住就是 **off-policy** 的——它是某个旧 policy 跑出来的——训得越久，off-policy gap 越大。AReaL 给了一个 staleness-aware 的 PPO 变种 handle 这件事，否则训到一半会发现 importance ratio 整体偏掉，模型在 chase 一个早就过期的目标。

同步简单稳定 debug 友好，异步快但稳定性和 debug 难度都上一个台阶。Commodity GPU 规模（< 7B）下同步够用；30B+ 上从公开 RL paper 的 wall-clock 数据看，不异步基本完蛋。本质上同步用 GPU 空转换 on-policy 干净，异步用 pipeline 满载换 off-policy stale，AReaL 那套 staleness-aware loss 把后一边压回去一点，但消不掉。

### 还没解决的部分 {#cn-open}

回头看，真正没人讲清楚的不是算法本身，是 **verifier**。GRPO + verifier 看上去 reward 是 ground truth，但 verifier 自己会被绕——math 上 model 学会输出特定 LaTeX 让 parser 通过，code 上学会让 unit test 因为 import 失败而 trivially pass。从公开 recipe 复现看，verifier 设计花的时间往往比 RL 配方调参多得多，一个好 verifier 配 PPO 也常常比糙 verifier 配 GRPO 强。社区里"X 方法比 Y 强"的论文，多半得先问 verifier 是不是同一个。

**Off-policy staleness** 是第二个洞。AReaL 的 staleness-aware loss 在 staleness 小的时候有效，但只要 queue 一深（几个 epoch 之前的 sample 还在 in-flight），importance ratio 的 variance 就开始爆。这块工作明显少于 GRPO 变体那边。

第三件是 hyperparam 的麻烦比 paper 上看起来大很多。同一份 GRPO 代码，KL coefficient 改一个 zero、clip ε 从 0.2 调到 0.3、advantage 要不要 normalize，最终 reward 能差到 single-digit 百分点。社区里"换了某种 loss 就提升 X%"的 claim，多半经不起一次像样的 hyperparam sweep 对齐。

最后一件更颠覆。直觉上 **RLVR**（RL with verifiable rewards）的上限是 verifier 质量——干净的 reward → 干净的 gradient → 训得动。这条逻辑成立，但真正的上限可能更低。Yue et al. (NeurIPS 2025)，"Does Reinforcement Learning Really Incentivize Reasoning Capacity in LLMs Beyond the Base Model?" 的核心实验是：RLVR 训出来的模型在 pass@1 上确实赢 base model，但把 k 调到足够大（k = 256 之类），base model 反而赢回去——RLVR 模型解的每条推理 path，base model 在大量采样下都能采到。RL 没在 base model 之外学到新 reasoning pattern，只是把 base model 已有 distribution 里那些好 path 上的采样概率拉高了——**sampling refinement**，不是 **capacity extension**。

对没有特别强 generalization 的 base model 来说，RLVR 的天花板就是 base model 的 **pass@k**——verifier 质量决定的是能不能贴近这个上限，不能突破它。Paper 里也明确说 distillation 是能加 capacity 的（teacher 提供 base 自己采不到的 pattern），所以这条限制不是无解，但 self-play RLVR 自己绕不开。落到 recipe 层面，这意味着大量"上 RL 之前先 distill / 先 SFT 一波"的工作其实是在做加 capacity 的部分，RL 那一段只是把已经存在的能力收紧成 pass@1。

### References {#cn-refs}

- Ant Research (2025). AReaL: Asynchronous Reinforcement Learning for Large-Scale Language Model Training. [arXiv:2505.24298](https://arxiv.org/abs/2505.24298)
- ByteDance & Tsinghua AIR (2025). DAPO: An Open-Source LLM Reinforcement Learning System at Scale. NeurIPS 2025. [arXiv:2503.14476](https://arxiv.org/abs/2503.14476)
- DeepSeek-AI (2025). DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning. [arXiv:2501.12948](https://arxiv.org/abs/2501.12948)
- Gao et al., Qwen (2025). SAPO: Soft Adaptive Policy Optimization. [arXiv:2511.20347](https://arxiv.org/abs/2511.20347)
- Ouyang et al. (2022). Training Language Models to Follow Instructions with Human Feedback (InstructGPT). [arXiv:2203.02155](https://arxiv.org/abs/2203.02155)
- Qwen3 Team (2025). GSPO: Group Sequence Policy Optimization. [arXiv:2507.18071](https://arxiv.org/abs/2507.18071)
- Rafailov et al. (2023). Direct Preference Optimization: Your Language Model is Secretly a Reward Model. [arXiv:2305.18290](https://arxiv.org/abs/2305.18290)
- Schulman et al. (2017). Proximal Policy Optimization Algorithms. [arXiv:1707.06347](https://arxiv.org/abs/1707.06347)
- Shao et al., DeepSeek (2024). DeepSeekMath / GRPO. [arXiv:2402.03300](https://arxiv.org/abs/2402.03300)
- Yue et al. (2025). Does Reinforcement Learning Really Incentivize Reasoning Capacity in LLMs Beyond the Base Model? NeurIPS 2025. [arXiv:2504.13837](https://arxiv.org/abs/2504.13837) · [project page](https://limit-of-rlvr.github.io/)

---

## English {#en}

**Contents**

- [PPO: the four-model baseline](#en-ppo)
- [DPO: a closed form drops the RM and the rollouts](#en-dpo)
- [GRPO: rollouts as their own baseline, no critic](#en-grpo)
- [DAPO: four stability patches for long-CoT GRPO](#en-dapo)
- [GSPO: a sequence-level importance ratio for MoE](#en-gspo)
- [SAPO: soft adaptive clipping instead of a hard band](#en-sapo)
- [Two algorithm-free throughput tricks](#en-tricks)
- [Sync vs async at scale](#en-async)
- [What's still open](#en-open)
- [References](#en-refs)

LLM RL has produced a dense run of new acronyms over the past few years — PPO (Schulman et al., 2017), DPO (Rafailov et al., 2023), GRPO (Shao et al., DeepSeek 2024), DAPO (ByteDance & Tsinghua AIR, 2025), GSPO (Qwen3, 2025), SAPO (Gao et al., Qwen, 2025), AReaL (Ant Research, 2025). The literature rarely puts "what changed" and "why" on the same page. These notes thread the timeline. The KL estimator (K1 / K2 / K3) section lives in its own post, [Three ways to estimate the KL penalty]({% post_url 2026-03-22-kl-estimators %}).

Strip the surface and every variant is the same problem: inject a reward signal into the policy while keeping **gradient variance** and per-step **compute** under control. High variance means unstable training, smaller learning rate, more KL regularization. High compute means too many models in VRAM and rollouts you can't afford. PPO maxes out both, and every method after it is a step in the other direction — one fewer model, fewer rollouts, a lower-variance KL estimator, a steadier importance ratio.

### PPO: the four-model baseline {#en-ppo}

PPO (Schulman et al., 2017) is the textbook version, and the work per training step is heavier than the label suggests. With the current policy π, sample K responses per prompt (typically 1–16). Score each response with a separate **reward model**. Estimate per-token baseline value with a separate **critic** V(s). Compute **advantage** A = R − V, usually smoothed across tokens with GAE. Form an **importance ratio** r_t = π(a_t∣s_t) / π_old(a_t∣s_t). Optimize the **clipped surrogate** min(r·A, clip(r, 1−ε, 1+ε)·A) to prevent the policy from drifting too far from the rollout distribution within a single step. Add a KL penalty β · KL(π ‖ π_ref) to pull the policy back toward a reference (typically post-SFT) model.

End result: four models in VRAM at once — policy, ref, critic, reward model — and four forward passes per token to produce a loss. InstructGPT (Ouyang et al., 2022) shipped this; it worked because OpenAI had the budget for it.

### DPO: a closed form drops the RM and the rollouts {#en-dpo}

DPO (Rafailov et al., 2023) reduces to one line: substitute the closed-form solution of KL-constrained reward maximization back into a likelihood framework, and the "RM plus PPO" pipeline collapses into a binary classifier over preference pairs. Given `(prompt, chosen, rejected)`, supervised-learning a sigmoid over the likelihood ratio recovers the optimum of the implicit-reward RL problem. No RM, no rollouts, no critic — VRAM holds policy and ref, two models, cheap and easy to debug.

The price is the reasoning ceiling. DPO only sees **preference data**, and preference data only covers what you can already produce two candidate answers for. Problems whose shape is "sample dozens of rollouts and let a verifier filter the correct ones" — math, code execution, formal reasoning — are unreachable, because the closed-form substitution implicitly assumes the answer space is enumerable in pairs. That's why DPO is great for tone, persona, and refusal behavior, and why DPO does not produce R1.

### GRPO: rollouts as their own baseline, no critic {#en-grpo}

GRPO (Shao et al., DeepSeek 2024) makes one observation: the critic exists to provide an advantage baseline, and if you already sample K responses per prompt, those K responses are themselves a sample-based baseline. Advantage becomes group-relative, `A_i = (R_i − mean(R_{1..K})) / std(R_{1..K})`, the critic drops out, and one more model leaves VRAM. The importance ratio, clipping, and KL penalty stay PPO-style. GRPO isn't a new algorithm; it's PPO minus the critic plus a group baseline.

GRPO became dominant because it composes naturally with **verifier-style rewards** — math correctness, code execution, format match — none of which need a learned reward model in the first place. In practice GRPO runs with just policy and ref in VRAM, much cleaner than PPO's four. Every open-weights reasoning recipe after R1 (DeepSeek-AI, 2025) is a GRPO variant. The cost isn't zero: rollouts aren't reduced, K has to be ≥ 4 for the group baseline to mean anything, and group rewards need spread. Binary math reward inside a group needs verifier-side shaping or the normalization is useless.

The KL penalty term needs a sample-based estimator. The three options (K1 / K2 / K3) and the bias / variance trade-offs between them are in [Three ways to estimate the KL penalty]({% post_url 2026-03-22-kl-estimators %}); the rest of this post assumes K3.

### DAPO: four stability patches for long-CoT GRPO {#en-dapo}

GRPO is fine on standard math reasoning, but on long-CoT, long-rollout training, four specific stability problems show up. DAPO (ByteDance & Tsinghua AIR, NeurIPS 2025) documents each and offers a fix.

The first is **entropy collapse**. PPO's symmetric clip `[1−ε, 1+ε]` is biased against keeping room for high-probability tokens — it allows downward moves to clamp them — and the policy narrows over training until it produces only a few modes. DAPO replaces the symmetric band with **Clip-Higher**: an asymmetric clip with `ε_high > ε_low` (typically 0.28 vs 0.20), giving low-probability tokens more room to be explored upward.

The second is wasted compute. If all K rollouts in a GRPO group land at the same reward (all correct or all wrong), the group baseline zeros out the advantage and the entire group contributes nothing to the gradient — yet forward and backward still cost the same. **Dynamic Sampling** rechecks group reward dispersion after rollout, drops prompts whose K rollouts agree, and resamples until every prompt in the training batch carries some non-zero advantage.

The third is sample-level advantage normalization understating long sequences. GRPO normalizes advantage per sample, which means an 8K-token response and a 200-token response contribute equally to the loss — diluting per-token gradient on the long one. DAPO switches to **Token-Level Policy Gradient Loss**, weighting by token count. In long-CoT regimes this matters a lot.

The fourth is reward noise on truncated responses. When a rollout hits the context-window cap and gets cut off, the verifier usually scores it low — not because the answer was wrong, but because it never finished. Simply masking those samples discards signal; DAPO applies **Overlong Reward Shaping**, a length-aware penalty that smooths the reward transition.

DAPO scores 50 on AIME 2024 with Qwen2.5-32B, beating DeepSeek-R1-Zero-Qwen-32B's 47 in half the training steps. The code is integrated into verl, and DAPO is the de facto open-source baseline for long-CoT GRPO recipes today.

### GSPO: a sequence-level importance ratio for MoE {#en-gspo}

On MoE, GRPO's token-level importance ratio gets pathologically noisy — a token routed to expert A during rollout might be routed to expert B during the next training step, and the importance ratio becomes meaningless. GSPO (Qwen3, 2025) lifts the importance ratio to the sequence level and length-normalizes it, `r_seq = (∏_t π(a_t∣s_t) / π_old(a_t∣s_t))^(1/T)`, which dilutes token-level noise via the geometric mean and keeps sequences of different lengths comparable.

On dense models GSPO doesn't differ much from GRPO — it's a conditional improvement, visible only on MoE. Implementation cost is small, since trl and verl already aggregate logprob at sequence level.

### SAPO: soft adaptive clipping instead of a hard band {#en-sapo}

PPO, GRPO, and GSPO all rely on a hard `[1−ε, 1+ε]` clip — ratios outside the band get clamped and the update surface is non-smooth at the boundary. SAPO (Gao et al., Qwen, 2025) replaces the hard clip with a temperature-controlled soft gate: ratios farther from 1 get attenuated more, but never clamped to zero, and the attenuation rate is itself a learnable temperature.

SAPO ends up both sequence-coherent (inherited from GSPO) and token-adaptive (the soft gate adjusts per token), producing smoother training curves than GSPO especially on MoE. On dense models the gap to GRPO / GSPO is small — like GSPO, this is a conditional improvement that mainly helps MoE training, and sits naturally as a successor along the GSPO line.

### Two algorithm-free throughput tricks {#en-tricks}

**Advantage filtering**: in a rollout batch, look at the distribution of `|A|` and drop the samples close to zero. They contribute almost nothing to the policy gradient but still cost the same forward and backward pass. Under GRPO's group-relative baseline, the response whose reward sits near the group median is exactly this kind. Filtering shrinks effective batch size, accelerates wall-clock progress, and requires retuning lr and target batch.

Adding a small Gaussian to the normalized advantage looks counterintuitive — noise shouldn't help training. But under group-normalized advantages, a single response with much higher reward than the others pulls the policy hard toward itself; a touch of noise prevents that update from over-fitting to a dominant sample and preserves exploration.

Both leave the algorithm untouched and squeeze out extra throughput before paying the complexity cost of async. Their hyperparameters need re-sweeping, and both depend on verifier quality — when the verifier is noisy, filtering ends up concentrating the mislabeled-reward samples rather than discarding them.

### Sync vs async at scale {#en-async}

Textbook synchronous RL is generate-batch → train-batch → repeat, with generation and training serialized. Generation time isn't constant — some prompts stop at 50 tokens, others run to 8K — so the wall time of a batch is bottlenecked by its slowest sample, and GPUs spend most of their time waiting.

Async decouples generation and training: a generation worker keeps pushing samples into a queue, a training worker keeps consuming them. The reference work is AReaL (Ant Research, 2025), reporting 2.7× throughput over a synchronous baseline. The cost is that any sample sitting in the queue is **off-policy** — it was generated by an older version of the policy — and the longer training runs, the wider the gap. AReaL ships a staleness-aware PPO variant to handle this; without it, importance ratios drift systematically and the model chases a target that's already expired.

Sync is simple, stable, easy to debug. Async is fast at the price of stability and debuggability. At commodity-GPU scale (< 7B) sync is enough; at 30B+, the wall-clock numbers in published large-scale RL papers make async essentially required. The two architectures trade idle GPUs for clean on-policy gradients against saturated pipelines for off-policy staleness, and AReaL's staleness-aware loss closes some of the gap on the latter side but not all of it.

### What's still open {#en-open}

Looking back at the whole timeline, the part nobody actually nails is the **verifier**. GRPO with verifier rewards looks like reward is ground truth, but the verifier itself gets gamed — the model learns to emit specific LaTeX the math parser accepts, or to make unit tests pass trivially by causing an import failure. Across published recipes, verifier design tends to consume more iteration time than RL recipe tuning, and a good verifier with PPO often beats a sloppy verifier with GRPO. Most "X beats Y" claims in the literature should really be read as "X's verifier was better than Y's."

**Off-policy staleness** is the second hole. AReaL's staleness-aware loss works when staleness is small; once the queue is deep enough that samples a few epochs old are still in flight, importance-ratio variance explodes. The literature here is much thinner than the pile of GRPO variants.

Hyperparameter sensitivity is also larger than the papers suggest. In the same GRPO codebase, an order-of-magnitude change to the KL coefficient, clip ε from 0.2 to 0.3, or advantage normalization on/off all move the final reward by single-digit percentage points. A lot of "method X improves by Y%" claims don't survive a real hyperparam sweep aligned across both sides.

The most unsettling open question is whether verifier quality is actually the ceiling on **RLVR** (RL with verifiable rewards). The intuitive story is that a clean verifier produces clean reward, clean reward gives a usable gradient, and training proceeds. That story is true, but the real ceiling may sit lower. Yue et al. (NeurIPS 2025), "Does Reinforcement Learning Really Incentivize Reasoning Capacity in LLMs Beyond the Base Model?", measure pass@k for RLVR-trained models against their base models. At small k (k = 1) the RLVR model wins as expected. At large enough k (k = 256-ish, deep in the high-pass@k regime) the base model wins back: every reasoning path the RLVR model produces was already in the base model's sampling distribution. RL didn't teach the model anything new — it raised the probability of good paths that were already there. **Sampling refinement**, not **capacity extension**.

For a base model without strong generalization, RLVR's real ceiling is the base model's **pass@k**. Verifier quality determines how close you can get to that ceiling, not whether you can push past it. The paper notes distillation can extend capacity — the teacher contributes patterns the base can't sample — so this isn't a hard limit on RL training in general, just on self-play RLVR. At the recipe level, much of the "distill or SFT before RL" practice in current open-weights pipelines is doing the capacity-extension work; the RL stage then tightens existing capability into pass@1.

### References {#en-refs}

- Ant Research (2025). AReaL: Asynchronous Reinforcement Learning for Large-Scale Language Model Training. [arXiv:2505.24298](https://arxiv.org/abs/2505.24298)
- ByteDance & Tsinghua AIR (2025). DAPO: An Open-Source LLM Reinforcement Learning System at Scale. NeurIPS 2025. [arXiv:2503.14476](https://arxiv.org/abs/2503.14476)
- DeepSeek-AI (2025). DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning. [arXiv:2501.12948](https://arxiv.org/abs/2501.12948)
- Gao et al., Qwen (2025). SAPO: Soft Adaptive Policy Optimization. [arXiv:2511.20347](https://arxiv.org/abs/2511.20347)
- Ouyang et al. (2022). Training Language Models to Follow Instructions with Human Feedback (InstructGPT). [arXiv:2203.02155](https://arxiv.org/abs/2203.02155)
- Qwen3 Team (2025). GSPO: Group Sequence Policy Optimization. [arXiv:2507.18071](https://arxiv.org/abs/2507.18071)
- Rafailov et al. (2023). Direct Preference Optimization: Your Language Model is Secretly a Reward Model. [arXiv:2305.18290](https://arxiv.org/abs/2305.18290)
- Schulman et al. (2017). Proximal Policy Optimization Algorithms. [arXiv:1707.06347](https://arxiv.org/abs/1707.06347)
- Shao et al., DeepSeek (2024). DeepSeekMath / GRPO. [arXiv:2402.03300](https://arxiv.org/abs/2402.03300)
- Yue et al. (2025). Does Reinforcement Learning Really Incentivize Reasoning Capacity in LLMs Beyond the Base Model? NeurIPS 2025. [arXiv:2504.13837](https://arxiv.org/abs/2504.13837) · [project page](https://limit-of-rlvr.github.io/)
