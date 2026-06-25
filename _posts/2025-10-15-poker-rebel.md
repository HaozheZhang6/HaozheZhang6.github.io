---
layout: post
title: "教扑克 bot 接近 GTO：从 CFR 到实时重解，还有差点把我骗了的那次实验 / Teaching a poker bot to approach GTO: from CFR to real-time re-solving, and the run that almost fooled me"
date: 2025-10-15
description: 一个业余 side project——用自对弈把德州扑克 bot 推向 GTO（CFR → R-NaD → ReBeL 实时重解 → 多人局），以及在 Slumbot 上几乎下错结论的方差教训
tags: [cfr, rebel, poker, self-play]
categories: [rl]
notion_id: 38858ac4-b0ac-810c-a15f-e88301b0506b
last_updated: 2026-06-25
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
- [那次实验，差点把我骗了](#cn-slumbot)
- [收获](#cn-takeaways)

先把丑话说前头：这是个业余的副业项目，不是我的正经研究。但有意思的是，“怎么老老实实做实验”这一课，它教得比我手上大多数正经课题都狠——所以值得记一笔。

起点是个很朴素的想法：写个德州扑克 bot，让它逼近 GTO（game-theoretically optimal，博弈论最优——说白了就是纳什均衡：对手怎么打，你长期都不亏）。先做单挑（两人），再往多人推。

### 为什么不能直接“训个 RL agent 来赢” {#cn-why}

我第一反应也是“上 RL 啊”。但扑克是不完全信息的零和博弈，普通 RL（DQN、PPO 那一套，盯着一个对手最大化收益）做不出 GTO——它学到的只是对当前这个对手的最优反制。麻烦在于，最优反制本身是能被反过来剥削的：换一个会针对你的对手，立刻把你按在地上打。再说，两个都很弱的网自己跟自己打，还容易陷进“我一全下、你就不敢跟”的互相迁就，表面上收敛了，其实是个谁都不肯认真打牌的窝囊均衡。

想做到“没法被剥削”，就得换一套数学，好在衡量的指标很干净：可剥削度——一个最强的对手最多能从你身上榨走多少；等于 0，就是纳什均衡。这也是为什么扑克 AI 走的是博弈论这条路，而不是经典 RL。

### CFR：自对弈逼近均衡 {#cn-cfr}

主力算法是 CFR（counterfactual regret minimization，反事实后悔最小化）：反复自己跟自己打，在每个决策点累计“当时要是改打别的、能多赚多少”的后悔值，再照后悔值的比例去调策略。它有收敛保证——平均策略的可剥削度会一路往 0 掉。

我先在两个玩具扑克（Kuhn、Leduc）上把 CFR 跑通，确认可剥削度确实掉到接近 0——这是整条线的正确性闸门，后面每加一块都拿它来验。真正的德州扑克太大了，状态数在 10 的 160 次方这个量级，没法精确解，所以改用 MCCFR（蒙特卡洛采样版的 CFR），再加动作抽象——把连续的下注尺度压成几档：弃牌、跟注、几个下注尺寸、全下。

### R-NaD：把它做成神经网络 {#cn-rnad}

手工分桶（把相近的牌归成一类、共用一套策略）会撞墙：筹码一深，信息集的数量就爆炸，表既存不下也训不动。出路是把后悔表换成一张神经网络（Deep CFR），让它自己在牌与牌之间泛化，手工分桶就省了。

再往前一步是 R-NaD（Regularized Nash Dynamics，正则化纳什动态——DeepMind 解 Stratego 用的就是这套）。它才算真正意义上“用 RL 跑出 GTO 效果”：一样是自对弈做策略提升，但每一步都用 KL 把策略往一个定期冻结的“磁铁”快照上拽。关键就是这个正则项——有它，迭代才会真正收敛到纳什均衡（last-iterate 意义下，不是靠平均才均衡），而不是一个随时会被剥削的最优反制。

### 过度全下，和 tree-k {#cn-overjam}

训出来的网有个难看的毛病：在中等筹码深度下，几乎拿什么牌都爱全下。对局界面里看得一清二楚——一手 K 高、面对加注，它给自己的建议居然是 69% 全下。这显然不是 GTO，是病。

病根有两层。表面那层是“翻后打得烂，所以干脆全下，躲开自己不会打的翻后”。更深一层，是我一开始把锅甩给“训练量不够、GPU 不行”——被人点醒之后才想明白：真正的问题出在功劳分配的方差上。把一手牌从头打到底、只拿最后的输赢算账，这个回报的方差极大，价值下注那点优势忽大忽小，直接被噪声盖掉；优化器于是系统性地偏向那些方差小的被动选择——跟注、过牌，还有“一把梭了事”。

修法叫 tree-k：在我方每个决策点，对每个动作分别跑 k 次到底再取平均，得到一个方差更小、逐动作的价值估计，优势就按它来算。再配上温度退火（前期高温，逼它真的去打翻后；后期收紧），爱全下的毛病砍掉了一大半。教训是：先怀疑你的功劳信号，再怀疑算力。

### 真正的强度杠杆：实时重解（ReBeL） {#cn-resolve}

这是整个项目最值的一块。那些超人级的扑克 bot——DeepStack、Libratus、Pluribus、ReBeL——强度的大头都不是来自一个更大的预训练策略，而是来自对局当下、实时把眼前这个局面重新解一遍（子博弈重解）。

我先做河牌重解。河牌时牌面五张全摊开、后面没牌了，所以任何摊牌的价值，都是在对手手牌分布上的一个精确期望——没有半点蒙特卡洛噪声。这点很要紧：我早先试过的“裸蒙特卡洛搜索”，在 40bb 深度下，一把把模拟到底算出来的收益方差，远比动作之间的真实差距大，取最大值（argmax）等于直接挑中噪声（这就是所谓优化器的诅咒），结果打不过一个打得平衡的对手。换成在双方的手牌分布上跑 CFR、叶子用精确值，得到的才是平衡、不易被剥削的策略，而不是那种会被人反咬一口的贪心反制。

再往上一条街是转牌。转牌后面还有河牌没发，叶子的值就不再精确——这时候需要一张价值网络：拿河牌那些精确解当标签训出来，喂给它牌面、双方手牌分布和 SPR，它直接吐出这个河牌子博弈的价值。在没见过的牌面上，它对河牌价值的预测误差大约是底池的 3.5%（也就是说，对得上 87% 的信号）。转牌重解就拿它当叶子——等于把“每个叶子都重解一遍河牌”那份收益白拿到手，却不用真去付那份算力。再往上，同样的套路可以一路叠到翻牌。

验证也跟上了：每个 solver 的子博弈可剥削度都压到了 0；而“转牌+河牌重解”对上它所搜索的那张基础网，头对头是 +59 bb/100（bb/100 就是每 100 手赢多少个大盲，扑克里的胜率单位；用配对 CRN 降方差，三个随机种子全是正的）。换句话说，实时重解确实在它自己那张基础网之上，又实打实拿到了一截强度。

### 多人局 {#cn-multi}

把同一套 R-NaD 改成跟人数无关的（位置、在场几个人都当特征喂进去），就能训 6 人桌、8 人桌。8 人桌那个 bot 稳赢各路对手。但得说句实在话：3 人以上是没有纳什均衡保证的（多人博弈里求均衡是 PPAD-hard 的难题），所以这里只能讲“经验上挺强”，没法像单挑那样拿可剥削度来背书。

### 那次实验，差点把我骗了 {#cn-slumbot}

最后我想找个外部的强 bot 当尺子：Slumbot——一个公开能打、用 CFR 训出来的强单挑 bot，还提供 API。

先用裸网上：输 −200 到 −500 bb/100（数字在飘，但明确是输）。然后给它叠上“转牌+河牌重解”，跑了 200 手：+125 bb/100。我当时差点就敲下“重解让我们打赢 Slumbot 了！”——符号从负翻正，差值看着也远超噪声。

幸好我又多跑了一把。**500 手：−321 bb/100。** 啪，打脸。

那个 +125 是方差，不是真本事。Slumbot 打的是 200bb 深筹，单手一个全下就能摆动 ±200bb，几百手的样本，标准误差大概在 ±400~500 bb/100——在这种方差下，几百手其实什么都测不出来。−227、−523、+125、−321 这四个数，全在同一条噪声带里乱跳；唯一能信的是样本最大的那次（500 手，−321），它说明的是：到目前为止，没有任何证据表明我们能赢 Slumbot，最靠谱的证据反而是——我们还在输。

为什么重解没把它救回来，我也想明白了：我只重解了转牌和河牌，可在 200bb 深筹下，钱主要是在翻前和翻牌这两条街上输赢的——而这两街还是那张裸弱网在打，Slumbot 在前面几街就把它罚了；再加上转牌的价值网络在 200bb 这种高 SPR 下属于外推、河牌重解用的手牌分布又来自那张弱网。整条链子，每一环都在漏。

### 收获 {#cn-takeaways}

- **打赢弱对手 ≠ 打得过强 bot。** 那个高温版本能把跟注站、随机 bot 打爆，恰恰是因为它更激进；可同样这股激进，被 Slumbot 一眼看穿，还加倍惩罚。所谓 crush fish, lose to sharks——屠鱼有余、遇鲨即死。
- **可剥削的网，怎么训都扛不住强对手；不可剥削靠的是实时重解，不是再训几轮。**
- **几百手根本测不出深筹下的胜率。** 想要一个能信的数，得上千上万手，再配上 AIVAT 这类方差缩减。
- **最重要的一条：先验证，再下结论。** 我明明一路都带着各种 caveat，最后还是差点下了个错结论——一个噪声样本恰好顺着你想要的方向冒出来，最容易让你停下来开香槟。多跑的那 300 手，比那段庆祝值钱多了。

代码都在 poker-simulator 里（CFR、MCCFR、Deep CFR、R-NaD，河牌/转牌/翻牌重解，价值网络，多人局）。它不会进我主页的“selected work”——它不是我的研究主线，就是个好玩的练手，顺带把“怎么老老实实读一个数字”这件事又教了我一遍。

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
