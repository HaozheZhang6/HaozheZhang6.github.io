---
layout: post
title: "教扑克 bot 接近 GTO：从 CFR 到实时重解，和一次差点骗了我自己的实验 / Teaching a poker bot to approach GTO: from CFR to real-time re-solving, and the run that almost fooled me"
date: 2026-06-23
description: 一个业余 side project——用自对弈把德州扑克 bot 推向 GTO（CFR → R-NaD → ReBeL 实时重解 → 多人局），以及在 Slumbot 上几乎下错结论的方差教训
tags: [cfr, rebel, poker, self-play]
categories: [rl]
notion_id: 38858ac4-b0ac-810c-a15f-e88301b0506b
last_updated: 2026-06-23
bilingual: true
---

## 中文 {#cn}

**目录**

- [为什么不能直接“训个 RL agent 来赢”](#cn-why)
- [CFR：自对弈逼近均衡](#cn-cfr)
- [R-NaD：把它做成神经网络](#cn-rnad)
- [过度全下，和 tree-k](#cn-overjam)
- [真正的强度杠杆：实时重解（ReBeL）](#cn-resolve)
- [多人局](#cn-multi)
- [差点骗了我自己的那次实验](#cn-slumbot)
- [收获](#cn-takeaways)

先说清楚：这是个业余 side project，不是我的正经 research。但它把“诚实做实验”这件事教得比我大多数正经实验都狠，所以记一笔。

起点是一个很朴素的想法：写个德州扑克 bot，让它接近 **GTO**（game-theoretically optimal，博弈论最优——简单说就是纳什均衡策略：对手不管怎么打，你长期都不亏）。先做单挑（heads-up，两人），再推到多人。

### 为什么不能直接“训个 RL agent 来赢” {#cn-why}

我第一反应也是“上 RL 啊”。但扑克这种**不完全信息零和博弈**里，普通 RL（DQN / PPO 那一套，对着一个对手最大化收益）做不出 GTO——它学出来的是对**当前对手**的 best response（最优反制）。问题是 best response 自己是**可被剥削的**（exploitable）：换一个会针对你的对手，立刻把你按在地上打。两个一起自对弈的弱网还会陷进“我全下你不敢跟”的互相迁就里，看着收敛了，其实是个谁都不肯打牌的窝囊均衡。

要“不可被剥削”，得换一套数学。指标也很干净：**exploitability**（可剥削度——一个最佳对手能从你身上榨多少；为 0 就是纳什均衡）。这就是为什么扑克 AI 走的是博弈论那条线，不是经典 RL。

### CFR：自对弈逼近均衡 {#cn-cfr}

主力算法是 **CFR**（counterfactual regret minimization，反事实后悔最小化）：反复自对弈，每个决策点累计“当时改选别的动作会多赚多少”的后悔值，再按后悔值的比例调整策略。它有收敛保证——平均策略的 exploitability 会往 0 掉。

我先在两个玩具扑克（Kuhn、Leduc）上把 CFR 跑通，确认 exploitability 确实掉到接近 0——这是整条线的“correctness gate”（正确性闸门），后面每加一块都拿它验。真·德州扑克太大（10^160 量级状态）没法精确解，所以用 **MCCFR**（蒙特卡洛采样版）+ 动作抽象（把连续的下注尺度压成 弃/跟/几档下注/全下）。

### R-NaD：把它做成神经网络 {#cn-rnad}

手工分桶（把相似的牌归一类共享策略）会撞墙：筹码一深，信息集数量爆炸，表存不下也训不动。出路是把后悔表换成神经网络（**Deep CFR**），让网络在牌之间泛化，就不用手工分桶了。

再往前一步是 **R-NaD**（Regularized Nash Dynamics，正则化纳什动态——DeepMind 解 Stratego 用的那套）。它是真正意义上的“用 RL 得到 GTO 效果”：自对弈做策略提升，但每一步都用 KL 把策略往一个**定期冻结的“磁铁”快照**拉回去。这个正则化项是关键——它让迭代收敛到**last-iterate** 的纳什，而不是一个会被剥削的 best response。

### 过度全下，和 tree-k {#cn-overjam}

训出来的网有个难看的毛病：中等筹码深度下，几乎什么牌都爱**全下**（over-jam）。在对局界面里能直接看到——K 高、面对加注，它给自己的建议是 69% 全下。这显然不是 GTO，是病。

病根有两层。表层是“翻后打得烂，所以用全下躲开不会打的翻后”。但更底层的，是我自己一开始甩锅给“训练量不够 / GPU 不行”——被纠正后才想明白：是**信用分配（credit assignment）的方差**问题。单条 rollout（把一手牌打到底）的回报方差极大，价值下注的优势忽大忽小被噪声淹没，优化器系统性地偏向方差小的被动动作（跟 / 过牌）和“梭哈了事”。

修法是 **tree-k**：在每个我方决策点，对**每个动作**各跑 k 次 rollout 取平均，得到一个低方差的 per-action 价值，再据此算优势。配上温度退火（前期高温真的去打翻后、后期收紧），over-jam 砍掉了一大半。教训：先怀疑你的 credit 信号，再怀疑算力。

### 真正的强度杠杆：实时重解（ReBeL） {#cn-resolve}

这是整个项目最值的一块。所有超人扑克 bot（DeepStack、Libratus、Pluribus、ReBeL）的强度大头**不是来自更大的预训练策略，而是来自对局时实时重解当前局面**（subgame re-solving，子博弈重解）。

我先做了**河牌重解**。河牌牌面五张全开、没有未来牌，所以任何摊牌的价值是对手 range（手牌分布）上的**精确期望**——零蒙特卡洛噪声。这点很关键：我之前试过的“裸蒙特卡洛搜索”会因为 40bb 下 rollout 的 EV 方差远大于动作真实差，argmax 直接选到噪声（optimizer’s curse，优化器的诅咒），结果打不过平衡的对手。换成对双方 range 跑 CFR、用精确叶子，得到的是**平衡（低可剥削）**的策略，而不是会被反剥削的贪心反制。

往上一街是**转牌**。转牌后面还有河牌，叶子值不精确——这就需要一个 **value net**（价值网络）：我用河牌的精确解当监督标签，训了一个网，给定（牌面、双方 range、SPR）直接预测河牌子博弈的价值。在没见过的牌面上，它把河牌 CFV 预测到约 **3.5% 底池**的误差（解释了 87% 的信号）。转牌重解就用它当叶子——拿到了“每个叶子都重解河牌”的价值，却没那个代价。再往上同理可以叠到翻牌（flop）。

验证：每个 solver 的子博弈 exploitability 都→0；而**turn+river 重解 vs 它搜索的那个网，头对头 +59 bb/100**（bb/100 = 每 100 手赢多少个大盲，扑克胜率单位；配对 CRN 降方差，三个随机种子全为正）。也就是说，实时重解确实在它自己的基础网之上又拿到一截实打实的强度。

### 多人局 {#cn-multi}

把同一套 R-NaD 做成 N 无关的（位置、在场人数当特征），就能训 6 人、8 人桌。8 人桌的 bot 稳赢各种 baseline。但要诚实：**3 人以上没有纳什保证**（多人博弈求均衡是 PPAD-hard），所以这里只能讲“经验性的强”，不能像单挑那样讲 exploitability。

### 差点骗了我自己的那次实验 {#cn-slumbot}

最后想拿个外部强 bot 当标尺：**Slumbot**（公开可访问的、CFR 训出来的强单挑 bot，有个 API）。

先用**裸网**打：输 −200 到 −500 bb/100（数字飘，但明确是输）。然后给它叠上 turn+river 重解，跑了 **200 手：+125 bb/100**。我当时差点就写下“重解让我们打赢了 Slumbot！”——符号从负翻正，delta 看着远超噪声。

幸好多跑了一把。**500 手：−321 bb/100。** 啪，打脸。

那个 +125 是**方差**，不是真的。Slumbot 是 200bb 深筹，单手全下能 ±200bb，几百手样本的标准误差大概 ±400~500 bb/100——**几百手在这个方差下根本测不出任何东西**。−227、−523、+125、−321 这四个数全在同一个噪声带里乱跳；唯一可信的是最大那个样本（500 手 −321），说明：**到现在为止，没有证据表明我们能打过 Slumbot，最佳证据是还在输。**

为什么重解没救回来也想清楚了：我只重解了转牌和河牌，但 **200bb 深筹下钱主要在翻前和翻牌**——那两街还是裸弱网在打，被 Slumbot 在前街就罚了；加上转牌 value net 在 200bb 的高 SPR 上是外推、河牌重解的 range 又来自弱网。链条上每一环都漏。

### 收获 {#cn-takeaways}

- **打赢弱 baseline ≠ 打赢强 bot。** 那个高温版本把跟注站、随机 bot 打爆，正是因为它更激进；同样的激进被 Slumbot 一眼看穿、加倍惩罚。“crush fish, lose to sharks”。
- **可剥削的网，怎么训都扛不住强对手；不可剥削靠的是实时重解，不是再训几轮。**
- **几百手测不出深筹胜率。** 想要可信的数，得上千上万手 + AIVAT（方差缩减）。
- 最重要的：**verify before claim。** 我带着 caveat 还是差点下了错结论——一个噪声样本顺着你想要的方向，特别容易让你停下来庆祝。多跑那 300 手，比写那段庆祝值多了。

代码在 `poker-simulator`（CFR / MCCFR / Deep CFR / R-NaD / river·turn·flop 重解 / value net / 多人）。它不会上我的主页“selected work”——它不是我的研究主线，就是一个让我重新学会怎么诚实读数字的好玩练手。

---

## English {#en}

**Contents**

- [Why you can’t just “train an RL agent to win”](#en-why)
- [CFR: self-play toward equilibrium](#en-cfr)
- [R-NaD: making it neural](#en-rnad)
- [Over-jamming, and tree-k](#en-overjam)
- [The real strength lever: real-time re-solving (ReBeL)](#en-resolve)
- [Multiway](#en-multi)
- [The run that almost fooled me](#en-slumbot)
- [Takeaways](#en-takeaways)

Up front: this is a hobby side project, not my actual research. But it taught me “be honest with your experiments” harder than most of my real experiments have, so it’s worth a note.

It started simple: write a Texas Hold’em bot that approaches **GTO** (game-theoretically optimal — basically a Nash-equilibrium strategy: no matter how the opponent plays, you don’t lose in the long run). Heads-up (two players) first, then multiway.

### Why you can’t just “train an RL agent to win” {#en-why}

My first instinct was “just throw RL at it” too. But in an **imperfect-information zero-sum game** like poker, vanilla RL (DQN / PPO — maximize reward against an opponent) doesn’t get you GTO. It learns a **best response** to the *current* opponent, and a best response is itself **exploitable**: swap in an opponent who adapts to you and they crush you. Two weak self-play nets also collapse into a cozy “I shove, you don’t dare call” truce that looks converged but is just a game where nobody plays poker.

To be *un*-exploitable you need different math, with a clean metric: **exploitability** (how much a best-responding opponent can extract from you; zero = Nash). That’s why poker AI goes down the game-theory road, not classic RL.

### CFR: self-play toward equilibrium {#en-cfr}

The workhorse is **CFR** (counterfactual regret minimization): self-play repeatedly, accumulate at each decision point the “regret” of not having taken each other action, then adjust the strategy proportionally to regret. It has a convergence guarantee — the *average* strategy’s exploitability falls toward zero.

I first got CFR working on two toy pokers (Kuhn, Leduc) and confirmed exploitability drops to ~0 — that’s the correctness gate for the whole line, and I re-checked it against every new piece. Real Hold’em is far too big (~10^160 states) to solve exactly, so I use **MCCFR** (Monte-Carlo sampled CFR) plus an action abstraction (collapse the continuous bet space to fold / call / a few bet sizes / all-in).

### R-NaD: making it neural {#en-rnad}

Hand-bucketing (grouping similar hands to share a strategy) hits a wall: as stacks deepen, the number of information sets explodes past what a table can hold or train. The fix is to replace the regret table with a neural net (**Deep CFR**) that generalizes across hands — no hand buckets.

One step further is **R-NaD** (Regularized Nash Dynamics — the thing DeepMind used to crack Stratego). This is the real “use RL to get a GTO effect”: self-play policy improvement, but each step pulls the policy back toward a **periodically-frozen “magnet” snapshot** via a KL term. That regularizer is the point — it drives convergence to a **last-iterate** Nash rather than an exploitable best response.

### Over-jamming, and tree-k {#en-overjam}

The trained net had an ugly tic: at medium stack depths it loved to **shove all-in** with almost anything (over-jam). You could see it right in the play UI — K-high, facing a raise, and its own advice was 69% all-in. Not GTO. A bug.

Two layers to it. The surface cause: “it plays postflop badly, so it jams to avoid postflop spots it can’t handle.” The deeper one — which I first wrongly blamed on “not enough training / weak GPU,” and only saw after being corrected — is a **credit-assignment variance** problem. A single rollout (playing one hand to the end) has huge variance; the EV edge of a value-bet gets drowned in noise, so the optimizer systematically prefers low-variance passive actions (call / check) and “just shove and be done.”

The fix is **tree-k**: at each of our decision points, value *each action* by the mean of k rollouts → a low-variance per-action value, and compute the advantage from that. With temperature annealing on top (high early so self-play actually plays postflop, lower later to sharpen), the over-jam dropped a lot. Lesson: suspect your credit signal before you suspect your compute.

### The real strength lever: real-time re-solving (ReBeL) {#en-resolve}

This was the most worthwhile piece. Every superhuman poker bot (DeepStack, Libratus, Pluribus, ReBeL) gets most of its strength **not from a bigger precomputed strategy but from re-solving the current spot at play time** (subgame re-solving).

I built the **river** re-solver first. On the river the five-card board is complete — no future cards — so the value of any showdown is an **exact** expectation over the opponent’s range (the distribution over their hidden cards). Zero Monte-Carlo. That matters: a naive Monte-Carlo search I’d tried earlier loses to a balanced opponent because at 40bb the rollout EV variance dwarfs the true action edges, so `argmax` picks noise (the optimizer’s curse). Running CFR over both ranges with exact leaves instead gives a **balanced (low-exploitability)** strategy, not a greedy best-response that gets punished back.

One street up is the **turn**, which still has a river card to come, so its leaves aren’t exact — that needs a **value net**. I trained one on the river’s *exact* solves as labels: given (board, both ranges, SPR) it predicts the river subgame’s value directly. On unseen boards it predicts river CFVs to about **3.5% of the pot** (87% of the signal). The turn re-solver uses it at the leaves — getting the value of re-solving the river at every leaf without the cost. The same idea stacks up to the flop.

Validation: every solver’s subgame exploitability → 0; and **turn+river re-solve beats the net it searches on, +59 bb/100** (bb/100 = big blinds won per 100 hands, the poker win-rate unit; paired CRN for variance reduction, all three random seeds positive). So real-time re-solving really does buy a chunk of strength on top of the base net.

### Multiway {#en-multi}

Make the same R-NaD N-agnostic (position and live-player count as features) and you can train 6- and 8-max bots. The 8-max bot beats various baselines comfortably. But honestly: **for 3+ players there’s no Nash guarantee** (computing equilibria is PPAD-hard), so here you can only claim empirical strength, not exploitability like in heads-up.

### The run that almost fooled me {#en-slumbot}

Finally I wanted an external strong yardstick: **Slumbot** (a strong, publicly-accessible heads-up CFR bot with an API).

The **raw net** loses: −200 to −500 bb/100 (the number wanders, but it’s clearly losing). Then I added turn+river re-solve and ran **200 hands: +125 bb/100.** I nearly wrote “re-solving beats Slumbot!” — sign flipped from negative to positive, and the delta looked way past the noise.

Good thing I ran one more. **500 hands: −321 bb/100.** Splat.

That +125 was **variance**, not real. Slumbot plays 200bb deep, a single all-in swings ±200bb, and a few-hundred-hand sample has a standard error around ±400–500 bb/100 — **a few hundred hands at this variance measures nothing.** The four numbers (−227, −523, +125, −321) all bounce around inside one noise band; the only trustworthy one is the largest sample (500 hands, −321), which says: **so far, no evidence we beat Slumbot — the best evidence is we still lose.**

I also worked out why re-solve didn’t rescue it: I only re-solve the turn and river, but **at 200bb the money is in the preflop and flop** — those streets are still the weak raw net, which Slumbot punishes early; plus the turn value net extrapolates at 200bb’s high SPR, and the river re-solve’s ranges come from the weak net. Every link in the chain leaks.

### Takeaways {#en-takeaways}

- **Beating weak baselines ≠ beating a strong bot.** The high-temperature version crushed calling-stations and random bots *because* it’s more aggressive — and that same aggression gets read and doubly punished by Slumbot. Crush fish, lose to sharks.
- **An exploitable net can’t hold up against a strong opponent however long you train it; unexploitability comes from re-solving, not from a few more epochs.**
- **A few hundred hands can’t measure a deep-stack win-rate.** You need thousands of hands + AIVAT (variance reduction) for a trustworthy number.
- Most of all: **verify before you claim.** I had caveats and *still* almost drew the wrong conclusion — one noisy sample landing the way you want is exactly when you’re tempted to stop and celebrate. Running those extra 300 hands was worth far more than that celebration would have been.

The code lives in `poker-simulator` (CFR / MCCFR / Deep CFR / R-NaD / river·turn·flop re-solving / value net / multiway). It won’t go in my homepage “selected work” — it isn’t my research line, just a fun build that re-taught me how to read a number honestly.
