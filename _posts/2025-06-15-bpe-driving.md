---
layout: post
title: BPE 漂到了自动驾驶 / When BPE drifted into autonomous driving
date: 2025-06-15
description: 自动驾驶往 sequence modeling 走，BPE / tokenization 的概念也跟着漂过来——顺着 Tesla 公开过的 stack 看从 HydraNet 到 BEV、OccNet、V12、再到 world simulator，最后聊一下 humanoid robot 那边为什么 locomotion 不是真正的瓶颈
tags: [tesla, bev, occupancy-network, world-model]
categories: [autonomous-driving]
notion_id: 36358ac4-b0ac-8119-b41f-cd0cf089ff31
last_updated: 2026-05-15
bilingual: true
---

## 中文 {#cn}

NLP 那边的 BPE（Byte-Pair Encoding）是 2016 年 [Sennrich 等人那篇](https://arxiv.org/abs/1508.07909)定下来的——通过频率合并构造一个子词词汇表，把任意 string 编码成一串 token，然后做 next-token prediction。看起来跟自动驾驶八竿子打不着，但过去一两年这个概念真的开始在 driving 的 paper 和 ai day 里出现。原因不是算法本身转移过去，是范式转移：自动驾驶在从“per-task module 拼出来”的 modular stack，往“整个 scene 是 sequence model 的 token、下一步 action 是下一个 token”的 end-to-end sequence modeling 走。

Tesla 是这条路上公开信息最完整的一家。下面是按时间顺序看 AI Day（Tesla 每年一次的公开技术分享）这几年披露的 stack（HydraNet 多任务感知 → BEV transformer 鸟瞰图融合 → Occupancy Network 3D 体素占据预测 → V12 端到端）演化，最后聊聊为什么 humanoid robot 那边 locomotion（行走/平衡控制）不是真正的瓶颈。

### HydraNet → BEV transformer → Occupancy Network

AI Day 2021 上 Tesla 实际同时讲了两件事。一是 HydraNet——一个共享 backbone、上面挂多个 task head 的多任务网络（detection、segmentation、depth、lane 等），每个 camera 独立跑一遍 HydraNet 出 per-camera 的 prediction。二是 BEV transformer——把 8 个 camera 的 feature 通过 cross-attention 融合到一组统一的 bird’s-eye-view query 上：BEV 平面有一组 learned positional query，attend 回所有 camera 的 image-space feature 拿信息。这一步把“camera-to-BEV 这件事原本写在 C++ 里的几何投影逻辑”整个挪进了 network 自己学。从 raw pixel 到 BEV 表征第一次端到端可学，post-fusion 的复杂度大幅下降。

学术界更早的 BEV 走的是 IPM（inverse perspective mapping）这种几何方法：假设地面平整、相机标定完美，按 camera intrinsics / extrinsics 把 2D 像素直接 deproject 到地平面。问题是这套假设在 highway / 真实路面上很脆——上下坡、车身震动、camera 装配公差都会让 IPM 失真。Tesla 的 cross-attention 路线把这些 corner case 交给 network 自己学，不再需要 calibration 是 perfect 的——这是后面 OccNet 和 V12 路线能跑通的前提。

AI Day 2022 把 BEV 升级成 Occupancy Network——BEV 那个 2D query grid 变成 3D voxel grid，每个 voxel 预测占据概率 + flow（这个 voxel 正在往哪个方向移动）。OccNet 解决了 BEV 在 z 轴上的信息丢失（举着遮挡物的人、低矮障碍物、悬空线缆），并且不需要 LiDAR——8 个 camera 的视觉直接做 dense 3D 重建。学术界跟进的工作（[UniAD](https://arxiv.org/abs/2212.10156)、[VAD](https://arxiv.org/abs/2303.12077)、[OccWorld](https://arxiv.org/abs/2311.16038)）基本都建在 occupancy 这套表示之上。

OccNet 之所以是个分水岭，是它把视觉模型的输出从“2D 像素的 prediction”提升到“3D 几何 + 时变”这种结构化的世界 model。下一步 planning / control 不用再从 raw pixel 学起，可以直接吃这个结构化 representation——这件事不解决，端到端 neural 路线就走不通。

### V12：photons in, controls out

到 FSD V12 这个节点 Tesla 公开宣布把整个 stack 端到端神经网络化——从 8 个 camera 的 raw photon 到方向盘 / 油门 / 刹车 的输出，中间不再有 C++ planner 这种 hand-coded module。这一步在工程意义上比之前所有 module 的升级加起来都大：原来 planner 是几十万行代码处理各种 edge case，V12 这些全部交给一个大网络从数据里学。

走通这条路有两个前提。一是数据规模——Tesla 车队每天几百万小时的人类驾驶 video 是天然的 expert demonstration，端到端 imitation learning 在这个 scale 上才跑得起来。二是表征——OccNet 把视觉提到几何 3D 表征那一档，端到端那个大网络的 internal world model 不用从 raw pixel 学，本质上是吃 OccNet 这种 dense 3D feature 当输入。

BPE 进来就是这一段。V12 内部（公开披露能看到的部分）某种程度上把驾驶 sequence——过去若干秒的 scene state + ego action——当成一个 token sequence 处理，下一个 action 当 next token 预测。这是 NLP transformer + autoregressive 的标准做法，只是 token 不是 subword、是某种 scene-action token。Tesla 没完全公开 tokenization 细节，但这条路径在 [Waymo 的 EMMA](https://arxiv.org/abs/2410.23262) 和 [VAD](https://arxiv.org/abs/2303.12077) 这些公开工作里也是同一条——差异主要在 token 怎么定义、scene 怎么 discretize。

### World simulator：闭环训练的前置条件

光做 imitation learning 不够。expert demonstration 永远只覆盖 expert 真做过的事，遇到 rare / dangerous scenario 没法 collect 数据；并且纯 imitation 学出来的 policy 在 distribution shift 上很脆。要做 RL / closed-loop 训练，需要一个能 simulate “如果 ego car 换个动作，世界会怎么变化”的 world model。

Tesla AI Day 2022 展示了一个 world simulator demo——给一帧场景，让模型生成接下来几秒所有 camera 视角下的 video。这是个 generative model，本质上是 video diffusion / autoregressive video generation 的驾驶特化版。学术界类似工作如 [GAIA-1](https://arxiv.org/abs/2309.17080)（Wayve）、[OccWorld](https://arxiv.org/abs/2311.16038)、最近的 [Vista](https://arxiv.org/abs/2405.17398)。

World simulator 真正解锁的是 RL 训练循环：rollout 一个 hypothetical action，让 world simulator 生成后续 sensor stream，policy 在 simulated stream 上继续 act，最后 reward 从 outcome 算。这一套跑通之后，自动驾驶训练才真正跟 LLM RL training 同构——只是 action space 从 token 变成连续控制，verifier 从 “math 是否正确” 变成 “没撞 / 没违章 / 到目的地”。

### 顺着这条路看 humanoid robot

回到机器人。Optimus、Figure、Apptronik 这些 humanoid 公司里，外界谈得最多的还是“它能走得多稳、能跑多快”。但 locomotion 这一块从 Boston Dynamics 2005 年那条 BigDog 一路走到 [Unitree](https://www.unitree.com/) 那条狗，已经基本是 solved problem——MPC + RL fine-tune 就能跑得很自然，Unitree 那条狗几千美元就能拿到。Tesla 自己的线，FSD 已经把“3D scene understanding + long-horizon planning + control”这一整套打过一遍了，locomotion 是其中比驾驶简单的子问题（自由度少、约束 explicit、控制 frequency 也低）。

humanoid 真正难的是 manipulation 和 grounded perception——抓一个没见过形状的物品、在 cluttered 环境下完成任务、理解人类语言指令对应到 physical action。这部分跟自动驾驶的难点是同构的：world understanding 和 long-horizon planning。Tesla 的 bet 就是 FSD stack 在 humanoid 上能复用——OccNet 直接变成机器人周围的 occupancy estimate，end-to-end 那个大网络换一下 action space 就能 transfer。除非有人特别要求做后空翻，否则 locomotion 不会是 bottleneck。

把 BPE → 自动驾驶 → humanoid 这条线串起来看，真正在发生的事不是哪个算法迁移过去，是任务的抽象层级在变。原来“看一帧图，分类哪些 pixel 是车 / 行人 / lane”那种 framing 已经基本不是 frontier 在解的问题了。frontier 在做的，是把驾驶、操作、长程规划这些任务统一成“在一个高维 token 化的世界里，下一个 token 是什么”——剩下的差异是 token 怎么造、reward 怎么定义。NLP 在 transformer + tokenization 这条路上跑了八年的经验，可以原样拿过来用。

---

## English {#en}

In NLP, BPE (Byte-Pair Encoding) is the 2016 [Sennrich et al. paper](https://arxiv.org/abs/1508.07909) — frequency-based subword merging that encodes any string into a token sequence so the model can do next-token prediction. It seems irrelevant to autonomous driving, but over the past year or two the concept genuinely started showing up in driving papers and at AI Day. Not because the algorithm transfers, but because the paradigm does: autonomous driving is shifting from “per-task module stack” toward “the scene is a token sequence and the next action is the next token.”

Tesla is the company with the cleanest public timeline on this trajectory. What follows is a chronological read of the AI Day disclosures (Tesla’s annual public engineering talk) — HydraNet (multi-task vision backbone) → BEV transformer (bird’s-eye-view feature fusion) → Occupancy Network (3D voxel occupancy + flow) → V12 (end-to-end driving) — ending with why locomotion (walking / balance control) isn’t the bottleneck for humanoid robots.

### HydraNet → BEV transformer → Occupancy Network

AI Day 2021 actually presented two pieces side by side. First, HydraNet — a multi-task network with a shared backbone and a stack of task heads (detection, segmentation, depth, lanes), with each camera running its own HydraNet pass to produce per-camera predictions. Second, a BEV transformer — eight camera feature maps get fused via cross-attention into a unified bird’s-eye-view representation: a set of learned BEV positional queries attends back into image-space features from all cameras. That step pulled the camera-to-BEV mapping out of hand-written C++ geometry and into the network. From raw pixels to BEV, the projection became end-to-end learnable for the first time, and post-fusion complexity dropped sharply.

Academic BEV before this leaned on IPM (inverse perspective mapping) — assume a flat ground plane and perfect camera calibration, deproject 2D pixels straight onto the road. That breaks on real surfaces: gradients, body motion, mounting tolerance all distort the projection. Tesla’s cross-attention route hands those corner cases to the network instead of requiring perfect calibration, which is the prerequisite for the OccNet and V12 routes that come after.

AI Day 2022 upgraded BEV into the Occupancy Network — the 2D BEV query grid becomes a 3D voxel grid, each voxel carrying occupancy probability plus flow (which way it’s moving). OccNet fixed BEV’s z-axis information loss (people carrying objects overhead, low obstacles, suspended cables) without LiDAR — eight cameras feeding dense 3D reconstruction directly. The academic followups ([UniAD](https://arxiv.org/abs/2212.10156), [VAD](https://arxiv.org/abs/2303.12077), [OccWorld](https://arxiv.org/abs/2311.16038)) mostly build on top of occupancy representations.

OccNet matters because it pushes the vision model’s output from “predictions over 2D pixels” up to “a 3D geometric, time-varying world model.” Whatever runs downstream — planning, control, end-to-end — doesn’t have to start from raw pixels anymore; it can consume the structured representation directly. Without that step the end-to-end neural route doesn’t go through.

### V12: photons in, controls out

At FSD V12 Tesla publicly committed to the end-to-end neural network — from raw photons on eight cameras to steering / throttle / brake, with no C++ planner module in between. In engineering terms this is a bigger change than the sum of all prior module upgrades: the C++ planner was hundreds of thousands of lines handling edge cases, and V12 hands that responsibility to one large network learning from data.

Two preconditions made this work. First, data scale — Tesla’s fleet generates millions of hours of human driving video per day, which is natural expert demonstration. End-to-end imitation learning only works at that scale. Second, representation — OccNet lifts vision into a geometric 3D representation, so the end-to-end network’s internal world model doesn’t start from raw pixels; it consumes OccNet’s dense 3D features as input.

BPE enters at this stage. The V12 internals (what’s been publicly described) treat the driving sequence — recent scene state plus ego action — as a token sequence, with the next action as next-token prediction. That’s the NLP transformer + autoregressive pattern, the tokens just aren’t subwords; they’re some kind of scene-action tokenization. Tesla hasn’t published exactly how it’s done, but the direction matches [Waymo’s EMMA](https://arxiv.org/abs/2410.23262) and [VAD](https://arxiv.org/abs/2303.12077). The differences across labs are mostly in how the token vocabulary is defined and how scenes get discretized.

### World simulator: the closed-loop prerequisite

Imitation learning alone isn’t enough. Expert demonstrations only cover what the expert actually did — rare and dangerous scenarios can’t be collected from a fleet, and policies trained on imitation alone are brittle under distribution shift. To run RL or closed-loop training you need a world model that can simulate “what happens if the ego car takes a different action.”

Tesla AI Day 2022 showed a world-simulator demo — given one scene, generate the next few seconds of video across all camera views. That’s a generative model, essentially video diffusion / autoregressive video generation specialized to driving. Comparable academic work: [GAIA-1](https://arxiv.org/abs/2309.17080) (Wayve), [OccWorld](https://arxiv.org/abs/2311.16038), and more recently [Vista](https://arxiv.org/abs/2405.17398).

What a world simulator actually unlocks is the RL training loop: roll out a hypothetical action, let the world simulator generate the resulting sensor stream, let the policy act on the simulated stream, compute reward at the end. With that loop closed, autonomous driving training collapses onto the same workflow as LLM RL — the action space happens to be continuous control instead of tokens, and the verifier becomes “didn’t crash, didn’t violate, arrived” instead of “math is correct.”

### Why locomotion isn’t the bottleneck for humanoid robots

Back to robots. In the humanoid race — Optimus, Figure, Apptronik — the question outside engineering circles is still “how stably can it walk, how fast can it run.” But locomotion as a research problem has been mostly solved since Boston Dynamics’ BigDog in 2005, and the line that runs through [Unitree’s quadrupeds](https://www.unitree.com/) made it cheap and accessible — MPC plus RL fine-tuning produces natural-looking gaits, and a Unitree dog runs a few thousand dollars. Tesla has already trained the full stack of “3D scene understanding + long-horizon planning + control” on FSD, and locomotion is a simpler sub-problem than driving — fewer degrees of freedom, more explicit constraints, lower control frequency.

What’s actually hard for humanoids is manipulation and grounded perception — picking up an unfamiliar object, finishing a task in a cluttered scene, mapping language instructions to physical actions. The difficulty here is isomorphic to autonomous driving: world understanding and long-horizon planning. Tesla’s bet is that the FSD stack ports onto humanoid directly — OccNet becomes occupancy around the robot, the end-to-end network swaps its action space and transfers. Locomotion only becomes a bottleneck if someone specifically wants backflips.

String BPE → autonomous driving → humanoid together, and the underlying shift isn’t one algorithm migrating. It’s the abstraction level of the task changing. “Look at a frame, classify which pixels are car / pedestrian / lane” isn’t where the frontier sits anymore. The frontier is collapsing driving, manipulation, and long-horizon planning into “given a high-dimensional tokenized world, what’s the next token.” What remains different across tasks is how tokens are constructed and how rewards are defined. The eight years of NLP experience with transformer + tokenization is mostly portable from there.
