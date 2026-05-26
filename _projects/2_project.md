---
layout: page
title: voice agent for stocks
description: LLM-powered voice agent for daily stock-market chat, with offline KB pre-processing
img: assets/img/projects/krono.jpg
importance: 2
category: ai
period: 2025 — present
---

A voice agent for daily stock-market conversation — earnings, macro, ticker news. The design sidesteps the usual latency-vs-reasoning trade-off in voice products: every morning a frontier model pre-processes the day's news, analyst notes, and price action into a semantically-indexed brief; at runtime the voice layer only retrieves from that brief and reads it out. You get frontier-quality content with small-model latency, at the cost of being scoped to a single domain.

Stack: FastAPI + WebRTC, `webrtcvad`, Whisper ASR (SenseVoice as self-hosted fallback), Edge-TTS, GLM-4.5-air, Supabase + Upstash Redis.

[news_agent repo](https://github.com/HaozheZhang6/news_agent) · [Writeup](/engineering/2025/12/01/voice-agent.html)
