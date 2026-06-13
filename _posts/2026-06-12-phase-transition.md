---
layout: post
title: 微观连续,宏观突变 / Continuous Below, Discontinuous Above
date: 2026-06-12
description: 从电池老化的 knee point 聊到相变——为什么连续的微观规律,会在宏观突然跳变;湍流、智能涌现、百倍股,以及线性世界里的非线性人生。
tags: [phase-transition, battery, emergence, turbulence]
categories: [physics]
notion_id: 37d58ac4-b0ac-81f0-890d-e765aaeacf5e
last_updated: 2026-06-12
bilingual: true
---

## 中文 {#cn}

这两天在公司和组里一位资深同事闲聊,话题偶然从日常的电芯建模,引到了一个让人头疼的电池现象——老化拐点(Knee Point)。

电池的整个生命周期里,各项内在成分和指标(比如 SEI 膜(固体电解质界面膜)的生长、活性物质的消耗)大多遵循着连续的物理化学规律,缓慢且线性地衰减。可当这些渐变累积到某个临界值,容量会突然迎来断崖式的"加速老化"。这位同事说,他非常想从根源上把这个"Knee"搞清楚。

于是我们聊到了一个我一直很着迷的物理概念:相变(phase transformation)。

其实仔细想想,相变——不管是冰化成水,还是水烧开成汽——宏观上看都是一种突然的割裂。但所有的"突变",底层都是无数个微观个体在老老实实地遵循连续的规律。

要在计算机里精确复现这种"量变到质变"的奇点,是个极其吃力不讨好的活儿:你必须下探到微观尺度做多尺度建模,而背后的计算量是指数级爆炸的。

顺着这个思路想,你会发现这根本不只是电池 Knee Point 的问题,它几乎是这个真实世界的底层逻辑。

比如湍流。一杯水里分子间的作用力是固定的,经典力学拿捏得死死的。可当雷诺数(Reynolds number,流动里惯性与粘性的比值)越过某个临界点,原本平滑有序的层流会瞬间崩溃成一团极度混沌的湍流。微观规则没变,宏观表现直接掀桌子。

再比如我们现在天天搞的 AI。调参、算梯度下降,权重矩阵(weights)里的数值是一点点、连续不断地在微调。看着 loss 慢慢降,模型能力好像在缓慢爬坡。可当参数规模真堆到千亿级别,那种让人心里发毛的"逻辑推理"和"智能",就像魔法一样突然涌现(emergence)了。底层的数学优化再连续,最终催生的却是离散的智能飞跃。

哪怕金融市场也是这样。SNDK,三年前不到 20 块,现在涨了一百多倍。没有任何一个量化模型能算准这种百倍股的"起飞点"。财富的积累和分配从来不是一条斜率固定的直线,没人能 predict。

我们之所以常常焦虑,大概是因为太习惯用"线性"的眼光去期待未来了。

总觉得今天干了多少活,明天就该有多少肉眼可见的回报;觉得资历熬到了,职级或者 Title 就该自然而然地上调。可现实往往是,你卡在某个阶段,看着身边一切都在缓慢地磨,迟迟等不来那个突破口。

这感觉,就像处在相变发生前的潜伏期。

但既然世界不是线性变化的,人生当然也不是。微观尺度上的看 paper、写代码、打磨技术,连同心智上的成熟,这些全都在遵循着连续的规律,默默进行。

在这个漫长、甚至有时让人憋屈的"线性期"里,其实能做的并不多。无非是多行善事,多攒手牌,持续迭代。

只要你还在**正确**的方向上,不断向系统里输入能量,属于你的那个"Knee Point"总会到来。在那之前,稳住,等待相变。

---

## English {#en}

These past couple of days I was chatting with a senior colleague on my team, and the conversation drifted from our everyday cell modeling to a battery phenomenon that gives everyone a headache — the aging knee (the "knee point").

Across a battery's life, its internal components and metrics (SEI growth — the solid-electrolyte interphase film — active-material loss, and the rest) mostly follow continuous physico-chemical laws, fading slowly and roughly linearly. But once those gradual changes pile up past some critical value, the capacity suddenly falls off a cliff into "accelerated aging." My colleague said he badly wants to understand this "knee" from first principles.

So we got onto a physics concept I've always found fascinating: phase transformation.

If you actually sit with it, a phase transformation — ice melting into water, water boiling into steam — looks like a sudden rupture at the macro scale. But underneath every one of those "jumps," countless microscopic individuals are dutifully obeying continuous rules.

Reproducing that "quantity-into-quality" singularity precisely on a computer is a thankless, brutal job: you have to drop down to the microscopic scale and do multi-scale modeling, and the compute behind it blows up exponentially.

Follow that thread and you realize this isn't just the battery knee point — it's almost the underlying logic of the real world.

Take turbulence. The forces between molecules in a glass of water are fixed; classical mechanics has them nailed down. Yet once the Reynolds number (the ratio of inertial to viscous forces in a flow) crosses a critical point, smooth, orderly laminar flow collapses in an instant into a mass of extreme chaos. The micro rules didn't change, but the macro behavior flips the table.

Or the AI we all work on day in and day out. You tune, you run gradient descent, and the numbers in the weight matrices shift bit by bit, continuously. You watch the loss come down, and the model's ability seems to climb a gentle slope. But once the parameter count really piles up into the hundreds of billions, that unnerving "reasoning" and "intelligence" emerges all at once, like magic. However continuous the underlying optimization is, what it gives birth to is a discrete leap in intelligence.

Even financial markets work this way. SNDK — under $20 three years ago, up more than a hundredfold now. No quant model can pin down the "liftoff point" of a hundred-bagger like that. The accumulation and distribution of wealth was never a straight line with a fixed slope; nobody can predict it.

The reason we so often feel anxious is probably that we're too used to expecting the future through a "linear" lens.

We assume that however much work we put in today, tomorrow owes us a visible return; that once we've put in the years, the level or the title should bump up on its own. But the reality is usually that you're stuck at some stage, watching everything around you grind along slowly, waiting and waiting for a breakthrough that won't come.

It feels exactly like the dormant stretch right before a phase transition.

But if the world doesn't change linearly, then neither does a life. At the microscopic scale, reading papers, writing code, sharpening your craft — along with simply growing up — all of it keeps proceeding quietly under continuous rules.

In that long, sometimes suffocating "linear period," there really isn't much you can do. Just do more good, hold more cards, keep iterating.

As long as you keep pumping energy into the system in the **right** direction, your own "knee point" will come. Until then, hold steady, and wait for the phase transition.
