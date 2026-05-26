---
layout: post
title: 通勤一小时，做了个聊股票的 voice agent / An hour-long commute, a voice agent for stocks
date: 2025-11-30
description: 围绕 sub-1 秒延迟预算讲 voice agent 每一层的设计——WebRTC、endpointing、streaming ASR/TTS、offline KB、subagent timeout，带 ITU-T G.114 / LiveKit / OpenAI Realtime / Picovoice VAD 这些数字
tags: [webrtc, latency, asr-tts]
categories: [agents]
notion_id: 36358ac4-b0ac-8198-b920-de4d2346d200
last_updated: 2026-05-14
bilingual: true
---

## 中文 {#cn}

每天通勤要开一小时左右车。一开始想用 Siri、Alexa、ChatGPT voice mode 来打发时间，发现稍微深一点的对话全部会垮，所以做了一个聊股票的 voice agent。

voice modality 跟 chat 真正的差距是延迟。用户能感觉到的只有一个数字——讲完到 agent 第一次出声的那段时间——而人对这一个数字的敏感度比对几乎任何其他交互延迟都高。ITU-T G.114 给的工业 baseline 是单向语音延迟 ≤ 400 ms 算自然、400–600 ms 还能忍、超过 600–700 ms 就开始"感觉机器人在卡"。人之间对话的 inter-turn gap median 大概 200 ms。所以 sub-1 秒端到端是 voice agent 工程的底线，sub-500 ms 才算真接近人。

一条 turn 端到端的延迟拆开大概是 ~50 ms 网络 + ~30 ms WebRTC pickup + ~200 ms VAD/endpointing + ~50 ms streaming ASR + ~300 ms LLM TTFT + ~200 ms TTS first chunk，合计 ~830 ms。跟公开 benchmark 上做得最好的几套 730–750 ms（GPT-4 Nano + Cartesia Sonic-Turbo，[dev.to 30-stack benchmark](https://dev.to/cloudx/cracking-the-1-second-voice-loop-what-we-learned-after-30-stack-benchmarks-427)）相差不大。后面每一个工程决策都是奔着把这条 loop 压在 1 秒以内。

### 为什么是 WebRTC，不是 WebSocket

最初想用 WebSocket + raw PCM frame，看起来轻。Prototype 跑下来死路：voice 对 5–10% 丢包基本无感，但 TCP 重传带来的延迟尖峰致命，UDP 底层没得替；echo cancellation 和 noise suppression 浏览器原生 audio pipeline 是免费的，自己在 WebSocket + raw PCM 上叠 RNNoise / WebRTC AEC 那一套，做不到 production 质量；网络抖动时 Opus codec 自适应降码率，jitter buffer 缓冲乱序，手搓 WebSocket 永远追不上。

WebRTC 不便宜，要处理 ICE 做 NAT 穿透、DTLS/SRTP 做媒体加密、SDP 协商 codec，调试链比 HTTP 长一个量级。OpenAI 自己也是这条路：[Realtime API 跑在 WebRTC 上](https://openai.com/index/delivering-low-latency-voice-ai-at-scale/)，他们用 Pion 写了一个专门的 transceiver service 做媒体终结，用 ICE Trickle 让协商和媒体传输并行省掉数百 ms 初始握手，又写了一个根据网络遥测动态调整大小的 jitter buffer。这套基础设施工程量很大，但没有它就跑不到 sub-1 秒。

### Endpointing 比想象的难

下一步是 VAD 和 endpointing——决定"用户讲完一句话了没"。这一层做错的代价不对称：慢了 agent 显得反应迟钝（一条 1500 ms 静默规则单这一项就吃掉超过一半 1 秒预算），快了 agent 抢话——[AssemblyAI 把这个叫"the biggest challenge in voice agent development"](https://www.assemblyai.com/blog/turn-detection-endpointing-voice-agent)。

帧级 VAD 用 [`webrtcvad`](https://github.com/wiseman/py-webrtcvad)：10 ms 一帧、纯 CPU、GMM-based、单帧延迟可忽略。它不是最准的，[Picovoice 的 VAD benchmark](https://picovoice.ai/blog/best-voice-activity-detection-vad/) 显示 5% false-positive rate 下 Silero VAD 的 true-positive 是 87.7%、WebRTC VAD 是 50%，差 4 倍。留着只因为 webrtcvad 做"音频里有没有人声"够用，语义层面的判断放在上一档。

[LiveKit 的 turn detection 综述](https://livekit.com/blog/turn-detection-voice-agents-vad-endpointing-model-based-detection) 把工业界做法分成四类——纯 silence rule、STT provider 给的 end-of-utterance 信号、partial transcript 上的小分类器、纯 audio prosody 模型。我们走 LiveKit 同一条路：在 webrtcvad 之上加一个小一档的 turn detector，吃 streaming ASR 的 partial transcript token stream，判一句话语义是否完整。决策合并成"音频静默 400 ms 且分类器认为是句尾"，推断 ~50 ms，抢话问题缓解掉大半但没根治——剩下那部分需要 prosody、社交线索、对话状态，光靠 text 还不够。

商业 voice infra（[Vapi](https://vapi.ai/)、[Retell](https://retellai.com/)）都自己训了 endpointing model，OpenAI 的 ChatGPT voice mode 也是 dedicated end-of-speech detection 进 server-side VAD。这一层是过去两年 voice agent UX 提升最大的地方，开源端目前没有真正能打的方案。

### Streaming ASR 让 STT 几乎从预算里消失，但要求每一段都 overlap

ASR 主路用 OpenAI Whisper streaming API，partial transcript 每 ~300 ms 一次，结束给 final；fallback 用 [SenseVoice](https://github.com/FunAudioLLM/SenseVoice)，一个 ~1 GB 的 FunASR 子模型，本地推断在中文上比 Whisper-large 快几倍，准确率略低。两条路接同一个上层接口，endpointing 不关心底下是哪个。

ASR 延迟今天已经不是瓶颈。[Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) 用 CTranslate2 优化的 Whisper-large-v3-turbo 在 RTX 4090 + INT8 下每个 chunk ~22 ms（[Simplismart 1300× real-time benchmark](https://simplismart.ai/blog/fastest-whisper-v3-turbo-serving-millions-of-requests-at-1300-real-time-with-simplismart)）；Speechmatics 的 streaming STT 在 partial → final 切换上甚至能压到 <5 ms（[STT metrics that matter](https://www.speechmatics.com/company/articles-and-news/speed-you-can-trust-the-stt-metrics-that-matter-for-voice-agents)）。结论是 streaming 一上 STT 基本可以从 1 秒预算里抹掉。

TTS 用 [Edge-TTS](https://github.com/rany2/edge-tts)——免费的 Microsoft Cognitive Services 语音，一百多个嗓子。voice 里 TTS 看的不是音色丰富度，是 time-to-first-audio-chunk（TTFA）：LLM 出第一个 token 之后多久开始有声音。公开数字是 ElevenLabs 350–700 ms、Cartesia Sonic-2 430–520 ms、Cartesia Sonic-Turbo 380–520 ms；Edge-TTS 在我们 setup 上 ~200 ms 起播，剩下流式跟上。音色不如 ElevenLabs 自然，但 voice agent 用户对"有没有立刻出声"远比"嗓子好不好"敏感。

整条 pipeline 只有在每一段都 overlap 才加得起来。partial transcript 一出来 LLM 就开始喂，LLM 出 token 就喂 TTS，TTS 出 chunk 就开始 SRTP 回播。任何一段串行化，端到端延迟就退化成各段之和，直接出 1 秒预算。[dev.to 30-stack benchmark](https://dev.to/cloudx/cracking-the-1-second-voice-loop-what-we-learned-after-30-stack-benchmarks-427) 的实测结论也是这条：LLM TTFT + TTS TTFB 占总 loop 时间 90% 以上，streaming recognizer 一上 STT 基本可忽略。

### LLM 不能坐在 voice 路径上

到这里全部是 voice modality 自己的工程延迟。但 voice agent 还有第二个延迟源：LLM TTFT 本身。通用 voice 产品被锁在 latency 跟 reasoning 之间——voice 路径要 sub-1 秒就只能选小模型，小模型 reasoning 又不行——这是 Siri 和 ChatGPT voice 一聊深就垮的结构性原因。

我们的解决办法是把大模型整个挪出 voice 路径。每天清晨一个 frontier model 在后台把当天股票相关的素材（news headlines、analyst notes、price action、social signal）预处理成一个语义索引的 daily brief。voice 端只做"从这个被大模型嚼过一遍的库里 retrieval + 朗读"，跑在 voice 路径上的是小模型。代价是 agent 只在股票这个 narrow domain 里管用，收益是用户感受到的是大模型的内容质量 + 小模型的延迟。

这也是为什么市面上真正能用的 voice 产品都是窄场景——叫车、订餐、客服都行，因为答案空间可以提前嚼烂。Siri 和 ChatGPT voice 没办法 pre-compute，它们必须随便什么话题都接住，所以同样的取舍他们做不了。窄场景不是 voice agent 的天花板，是目前已知唯一能同时跑赢延迟和质量的路径。

### Subagent 长尾会把前面省的 ms 全吃光

最后一个 production 坑：一条回答经常 fan-out 出几个并行 subagent（fundamentals API、news scrape、IV 计算），整 turn 卡在最慢那个 subagent 上。前四层省下来的所有毫秒，一个 5 秒级慢 subagent 就能吃光。这是 [Dean & Barroso 2013 *The Tail at Scale*](https://research.google/pubs/the-tail-at-scale/) 那篇在 voice 里的复刻——任何 fan-out 系统，整体响应都被 tail latency 主导。

Google 的标准做法是 hedged requests / speculative execution——同时打几份请求，先回来的算数——voice 也能这么干，但成本翻倍而且不一定够。我们用的更朴素：timeout-based deferred response。到点把已经回来的结果先讲，长尾的塞进下一轮 conversation——"刚才你问的那个 IV，刚算完，是 0.42"。chat 用户能看着 typing indicator 等 10 秒，voice 用户不行，所以这套 timeout-defer 没得选。代价是用户偶尔会感觉 agent 自己接前面没回答完的问题，但比死等强很多。

### 还没解决的部分

五层都对着 1 秒预算调过之后，剩下两个真正的洞。一是 semantic endpointing 离做对还差最后 20%——单 turn 多句意图、用户中途澄清、显式"等一下"这些场景下 turn detector 还会误判；开源端没有 production-ready 的方案，OpenAI / Vapi / Retell 都靠各自训的 closed model 占着上风。二是 subagent 长尾用 timeout + defer 是临时方案，更合理应该是带 budget tracking 的 hedged execution——agent 知道自己还剩多少 ms，超时之前主动切换到"够用的最佳答案"——这块没看到好的开源实现。

WebRTC 后端的工程门槛远比想象高，[OpenAI 那篇 blog](https://openai.com/index/delivering-low-latency-voice-ai-at-scale/) 大半篇幅在讲他们怎么把 Pion 重新封成一个 transceiver service 让 K8s 上跑得动；我们用了 managed SFU（[LiveKit Cloud](https://livekit.io/cloud)、[Daily](https://daily.co/)）整个绕开。ASR 还有 code-switching 和 domain jargon 的问题——tickers 和行业术语经常被音译成奇怪东西，SenseVoice 可以加 domain phrase boosting，Whisper API 上目前没有等价 hook。

---

## English {#en}

An hour-each-way commute doesn't pair well with radio or Spotify. Siri, Alexa, and ChatGPT voice mode collapse on anything past surface conversation, so I built a scoped voice agent for talking through US equities. What follows is the engineering it took to make that work.

What voice changes about a chat product is the latency it forces you to hit. The user notices one number — the gap between finishing a sentence and the agent's first audio chunk — and they notice it more than almost any other number in interactive systems. ITU-T G.114's baseline puts one-way speech latency ≤ 400 ms in the "natural" range, 400–600 ms in "acceptable," and above 600–700 ms it starts to read as a robot stalling. Human-to-human inter-turn gap median is around 200 ms. Sub-1s end-to-end is the floor for voice agents; sub-500 ms is where it stops feeling like a machine.

A single turn breaks down roughly as ~50 ms network + ~30 ms WebRTC pickup + ~200 ms VAD/endpointing + ~50 ms streaming ASR + ~300 ms LLM TTFT + ~200 ms TTS first chunk, totaling ~830 ms — within range of the best published end-to-end numbers (730–750 ms for GPT-4 Nano + Cartesia Sonic-Turbo, [dev.to 30-stack benchmark](https://dev.to/cloudx/cracking-the-1-second-voice-loop-what-we-learned-after-30-stack-benchmarks-427)). Every engineering decision in the rest of this post is in service of that budget.

### Why WebRTC, not WebSocket

The first attempt was WebSocket plus raw PCM frames. It looked light. It died in prototype because three things WebSocket can't provide turn into production blockers in voice. Voice tolerates 5–10% packet loss imperceptibly but cannot tolerate the latency spikes that TCP retransmits introduce — UDP underneath is non-negotiable. Echo cancellation and noise suppression are free in the browser audio pipeline; stacking RNNoise / WebRTC AEC on top of WebSocket and raw PCM in userland doesn't reach production quality. And when the network jitters, Opus negotiates a lower bitrate while the jitter buffer absorbs reordering — a hand-rolled WebSocket transport never matches that.

WebRTC isn't free either. ICE for NAT traversal, DTLS/SRTP for media encryption, SDP for codec negotiation — the debug chain is an order of magnitude longer than HTTP. OpenAI's own [Realtime API runs on WebRTC](https://openai.com/index/delivering-low-latency-voice-ai-at-scale/), and they had to write a dedicated transceiver service on Pion to make the standard fit Kubernetes deployment, plus ICE Trickle to overlap negotiation with media transport and a telemetry-driven jitter buffer. The infrastructure work is substantial, and there isn't a lighter transport that lands sub-1s.

### Endpointing is the hard layer

Endpointing — deciding when the user has actually finished speaking — is where most voice agents fall over. Error costs are asymmetric: too slow and the agent feels sluggish (a 1500 ms silence rule alone eats more than half the budget); too fast and the agent interrupts, which [AssemblyAI calls "the biggest challenge in voice agent development."](https://www.assemblyai.com/blog/turn-detection-endpointing-voice-agent)

Frame-level VAD is [`webrtcvad`](https://github.com/wiseman/py-webrtcvad) — 10 ms frames, pure CPU, GMM-based, frame latency negligible. It isn't the most accurate option ([Picovoice's VAD benchmark](https://picovoice.ai/blog/best-voice-activity-detection-vad/) puts Silero at 87.7% true-positive rate vs WebRTC VAD's 50% at the same 5% false-positive rate, a 4× error gap), but for the "is there voice in this frame" question it's sufficient. The semantic decision lives a layer above.

[LiveKit's turn-detection survey](https://livekit.com/blog/turn-detection-voice-agents-vad-endpointing-model-based-detection) sorts production approaches into four categories — silence-only rules, the STT provider's end-of-utterance signal, a small classifier on the partial transcript, and audio prosody models. We use LiveKit's own approach: a small turn-detector model that consumes the streaming ASR's partial transcript and predicts whether the span is semantically complete. The composite trigger is "400 ms of silence AND classifier says end-of-thought," inference is around 50 ms, and it cleans up most of the interruption problem without fully solving it. The remainder needs prosody, social cues, and conversational state, none of which the text stream alone can carry.

Commercial voice infrastructure ([Vapi](https://vapi.ai/), [Retell](https://retellai.com/)) ships its own trained endpointing models; OpenAI's ChatGPT voice mode runs a dedicated end-of-speech detection model server-side. This layer is where voice agent UX has improved most in the past two years, and the open-source side hasn't caught up.

### Streaming pulls ASR out of the budget — if every stage overlaps

ASR uses OpenAI Whisper streaming API as the primary route (partial transcripts every ~300 ms, plus a final at end-of-speech), with [SenseVoice](https://github.com/FunAudioLLM/SenseVoice) as fallback — a ~1 GB Chinese-friendly open model from FunASR that runs faster than Whisper-large on Mandarin with slightly lower accuracy. Both routes flow into the same upstream interface so the endpointing layer doesn't care which is in use.

ASR latency stopped being a bottleneck a couple of years ago. [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) running CTranslate2-optimized Whisper-large-v3-turbo handles a chunk in around 22 ms on an RTX 4090 at INT8 ([Simplismart's 1300× real-time benchmark](https://simplismart.ai/blog/fastest-whisper-v3-turbo-serving-millions-of-requests-at-1300-real-time-with-simplismart)); Speechmatics' streaming STT delivers partial-to-final transitions in under 5 ms ([STT metrics that matter](https://www.speechmatics.com/company/articles-and-news/speed-you-can-trust-the-stt-metrics-that-matter-for-voice-agents)). With streaming, STT effectively rounds out of the budget.

TTS is [Edge-TTS](https://github.com/rany2/edge-tts) — free Microsoft Cognitive Services voices, more than a hundred of them. The metric that matters in voice isn't voice variety but time-to-first-audio-chunk (TTFA): how long after the LLM emits its first token does sound start playing. Published numbers are ElevenLabs 350–700 ms, Cartesia Sonic-2 430–520 ms, Cartesia Sonic-Turbo 380–520 ms; Edge-TTS in our setup runs around 200 ms with the rest streamed. The voice is less natural than ElevenLabs, but voice agent users react far more to "did audio start" than to "does the voice sound good."

The pipeline only adds up because every stage overlaps. Partial transcripts feed the LLM the instant they appear, LLM tokens feed the TTS as they're emitted, TTS chunks stream out over SRTP as they're produced. Serialize any stage and end-to-end latency collapses into the sum of stages, which blows the budget immediately. The [dev.to 30-stack benchmark](https://dev.to/cloudx/cracking-the-1-second-voice-loop-what-we-learned-after-30-stack-benchmarks-427) is explicit on this: LLM TTFT plus TTS TTFB account for over 90% of total loop time, and with streaming recognizers STT is effectively negligible.

### The LLM doesn't sit on the voice path

Everything so far is voice-modality engineering latency. There's a second source: the LLM TTFT itself. A general-purpose voice product is stuck between latency and reasoning — sub-1s response means a small model, and a small model can't reason. That's the structural problem Siri and ChatGPT voice can't escape.

The way around it is to push the big model off the voice path entirely. Every morning a frontier model ingests the day's stock-related material — news headlines, analyst notes, price action, social signal — and produces a semantically-indexed daily brief, a RAG-friendly dense store. At runtime the voice layer retrieves from a store the frontier model has already chewed through, and reads it aloud. The model in the voice path is small.

This only works because the agent is scoped to a single domain. The cost is conversational breadth; the benefit is users get frontier-quality content at small-model latency. Every voice product that actually works in production is similarly scoped — ride dispatch, food orders, customer support — and the reason is identical: the answer space can be pre-chewed. Siri and ChatGPT voice can't make that move because they have to take any topic at all. Narrow domain isn't where voice agents stop scaling; it's the only place they currently work.

### Subagent long-tail eats the savings

A single answer often fans out into parallel subagents — fundamentals API, news scrape, IV calculation — and the entire turn waits on the slowest one. Every millisecond saved in the prior four layers can be erased by one 5-second subagent. This is exactly [Dean and Barroso's *The Tail at Scale*](https://research.google/pubs/the-tail-at-scale/) showing up in a voice context: in any fan-out system, tail latency dominates the response.

Google's textbook mitigation is hedged execution — fire several copies and take the first to return. Voice can do that, but the cost doubles and it doesn't always close the tail. Our approach is simpler: timeout-based deferred response. Speak whatever subagent results arrived by the deadline, and tack the long-tail ones onto the next turn — "that IV you asked about, just came back, it's 0.42." A chat user can wait 10 seconds while a typing indicator runs; a voice user cannot, so this pattern has no real alternative. The cost is the user occasionally hears the agent resume an earlier question on its own, which is much better than dead air.

### What's still open

After tuning every layer against the 1-second budget, two gaps stay genuinely unsolved. Semantic endpointing reaches roughly 80% — multi-clause turns, mid-turn clarifications, explicit "wait a second" still misfire; the open-source side has no production-ready answer, and the closed end-of-speech models from OpenAI, Vapi, and Retell are where those vendors actually win. Subagent long-tail via timeout + defer is a stopgap; the cleaner answer is hedged execution with explicit budget tracking — the agent knows it has X ms left and downshifts before the deadline — and there's no clean implementation of that yet.

Two smaller items. WebRTC backend engineering is a project of its own — [OpenAI's Realtime post](https://openai.com/index/delivering-low-latency-voice-ai-at-scale/) is largely an account of rewriting Pion's deployment model to fit Kubernetes; we sidestepped that work entirely by using a managed SFU ([LiveKit Cloud](https://livekit.io/cloud), [Daily](https://daily.co/)). ASR still trips on code-switching and domain jargon — tickers and industry terms get phonetically misheard. SenseVoice supports domain phrase boosting; the Whisper API doesn't currently expose an equivalent hook.
