---
layout: post
title: 通勤一小时，做了个聊股票的 voice agent
date: 2025-11-30 18:00:00 -0800
description: 现成 voice 产品被 latency vs reasoning 卡死。换个思路：让大模型 offline 处理掉知识，voice 端只朗读
tags: llm voice agents
categories: engineering
---

## 中文

每天通勤要开一小时左右车。坐在驾驶座一小时不能干别的事，浪费得有点离谱。一开始想用 Siri / Alexa / ChatGPT voice，一聊深一点的话题就垮——这些产品都被同一个 trade-off 卡死：

**voice 路径要响应速度，所以必须用小模型；用了小模型，就放弃了 reasoning 深度。**

但这个 trade-off 只在"通用对话"的假设下成立。换个角度想：如果我提前知道用户这一天会聊什么，"reasoning 深度"就可以挪到 offline。让前线大模型在后台把当天相关的所有素材——新闻、研报、价格、社交信号——预处理一遍，整理成一个 query-friendly 的小知识库；voice 那一层只负责"从这个被大模型嚼过一遍的库里检索 + 朗读"。你既拿到了大模型的内容质量，又保留了小模型的响应速度。代价是只能在限定话题范围内对话。

**所以为什么市面上没有真正好用的通用 voice product？因为通用没解——真正可用的 voice 永远是 narrow domain。** Siri / ChatGPT voice 这些"什么都能聊"的产品被结构性地卡住了，"广度"和"深度"它们没法同时拿。narrow-domain voice 没这个限制。

我自己最关心的 narrow topic 是股票——每天追美股 earnings / macro / IV，是个 self-motivated 的固定主题。所以这个 agent 的内核很清晰：清晨大模型把当天所有相关 ticker 的 news + analyst note + price action 处理成一个带语义索引的 daily brief；中午开车时，我跟语音端聊 "NVDA 今天怎么了"、"AMD earnings call 重点"、"半导体板块今天为什么涨"，背后查的全是预处理好的语料。

实现在 [news_agent](https://github.com/HaozheZhang6/news_agent) repo。技术栈：

- **传输** FastAPI + WebSocket。WebRTC 试过 debug 太痛，binary frame WebSocket 已经够 cover 99% 延迟需求。
- **VAD** `webrtcvad`。轻量、CPU-friendly，缺点见下。
- **ASR** SenseVoice，~1GB 中文友好模型，比 Whisper 在中英混说场景更稳。
- **TTS** Edge-TTS。白嫖 Microsoft 嗓子，production 质量够。
- **LLM** GLM-4.5-air（ZhipuAI）。便宜、快、tool call 还可以。试过 gpt-4o-mini 和 Claude Haiku，并发限制和中文表现各有问题，最后回 GLM。
- **状态** Supabase 存对话 + 实体追踪，Upstash Redis 存 session 短期 buffer。

模型层就讲到这里。下面两块没解决的事才是真坑。

**VAD 不是 turn detection。** `webrtcvad` 告诉你"这一帧没人声"，跟"用户说完了一句话"完全是两件事。任何说话稍有停顿的人（一边想一边讲是常态）都会被 VAD 误判成"说完了"然后被打断。我的 workaround 是在 VAD 之上加一个 turn-detection 小模型，看 partial transcript 判断是不是句尾。多 ~100 ms 延迟，问题缓和，不能说根治。这是一个 *semantic* 问题（"这一段话表达完整了吗"），不是 signal 问题，所以单靠音频 feature 永远做不到位。开源社区现在没有真正好用的方案。

**异步 streaming 比想象中难。** voice pipeline 上面所有事都是 streaming：audio chunk 流进来、partial transcript 出来、LLM token 出来、TTS chunk 出来。每一段都不能等上一段全跑完，否则用户感受到的就是 sum-of-latencies。但 streaming 串起来之后，error handling 和 backpressure 都脆弱：任何一段卡 50 ms，下游就可能断点重连，整个 turn 重来。同步版本简单稳但慢，异步版本快但 race condition 一堆。我现在的版本只能说"勉强工作"。

**总结一句：voice agent 的瓶颈不在 LLM，是 turn detection 和 async streaming。模型层是这个 stack 里我花时间最少的部分。**

---

## English

My commute is about an hour each way. An hour in the driver's seat with nothing else to do is a lot of waste. I tried Siri / Alexa / ChatGPT voice; any non-trivial topic falls apart on all of them, because they're all stuck in the same trade-off:

**A voice path needs latency, which means a small model, which means giving up reasoning depth.**

That trade-off is real, but it binds only under one assumption — general-purpose conversation. Flip it: if you know in advance what the user will want to talk about today, you can push "reasoning depth" offline. A frontier model in the background digests the day's news, analyst reports, prices, and social signal, and structures them into a query-friendly knowledge base. The voice layer only retrieves from that pre-chewed base and reads the result out. You get the frontier model's content quality and the small model's latency. The price is you can only talk inside the scope.

**Which is why there is no good general-purpose voice product on the market. General doesn't have a solution. The only usable voice products are narrow-domain.** Siri and ChatGPT voice are structurally stuck because they promise breadth and depth at once, and the trade-off doesn't allow both. Narrow voice products don't have that constraint.

My personal narrow topic is stocks — US equities, earnings, macro, IV — a self-motivated daily subject. The agent's design becomes clean: every morning a frontier model turns the day's news, analyst notes, and price action for the tickers I care about into a semantically-indexed daily brief. At lunch, driving home, I ask "what's NVDA doing today" or "summarize the AMD earnings call" or "why are semis up." Everything it answers comes from the pre-processed brief.

The implementation is in the [news_agent](https://github.com/HaozheZhang6/news_agent) repo. Stack:

- **Transport** — FastAPI + WebSocket. WebRTC was tried, debugging browser-side fallback was rougher than the latency win was worth; a small binary-frame protocol over WebSocket already covers 99% of what we need.
- **VAD** — `webrtcvad`. Lightweight, CPU-friendly; caveat below.
- **ASR** — SenseVoice, ~1GB Chinese-friendly model. More stable than Whisper on Mandarin-English code-switching.
- **TTS** — Edge-TTS. Free Microsoft voices, production-quality.
- **LLM** — GLM-4.5-air (ZhipuAI). Cheap, fast, tool calls behave. I tried gpt-4o-mini and Claude Haiku; concurrency limits and Chinese quality kept pulling me back to GLM.
- **State** — Supabase for conversation history + entity tracking, Upstash Redis for the per-session short-term buffer.

That's the model layer. The two real holes sit underneath.

**VAD is not turn detection.** `webrtcvad` tells you "no voice in this frame," not "the user finished a sentence." Anyone who pauses mid-sentence — and most thinking-aloud speakers do — gets cut off. My workaround is a small turn-detection classifier on top of VAD reading the rolling transcript, +100 ms latency, which damps the failure without curing it. This is a *semantic* problem ("did that span express a complete thought?"), not a signal problem, so audio features alone will never close it. There is no good open-source solution yet.

**Async streaming is harder than it looks.** Every stage of the voice pipeline is streaming — audio chunks in, partial transcript out, LLM tokens out, TTS chunks out. Each stage has to start before the previous one finishes, or the user feels the sum of latencies. But once everything is streamed, error handling and backpressure get fragile: any 50 ms stall anywhere can cascade into a reconnect that restarts the whole turn. The sync version is simple and stable but slow; the async version is fast but full of race conditions. What I run now is "barely working."

**The take-away: the bottleneck in a voice agent is not the LLM. It's turn detection and async streaming. The model layer is the part of this stack I've spent the least time on.**
