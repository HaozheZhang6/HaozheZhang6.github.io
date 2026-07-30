---
layout: about
title: about
permalink: /
subtitle: Modeling Engineer at Tesla · LLMs & Physics-based ML · creator of BenchCAD

profile:
  align: right
  image: profile_pic.jpg
  address: >
    <p>Palo Alto, CA</p>
    <p>USA</p>

news: true  # includes a list of news items
selected_papers: true # includes a list of papers marked as "selected={true}"
social: true  # includes social icons at the bottom of the page
---


Hey, welcome to my page! 👋

I’m a modeling engineer at Tesla, working at the intersection of physics-based modeling and machine learning for next-generation battery cells — theoretical and computational modeling, reinforcement learning for automation, and data-driven optimization at scale-up.

My background is heavy on physics. I’ve spent years working out closed-form theoretical solutions across mechanics and multi-physics fields — soft-hard material integration, stretchable metasurfaces, mechanical Janus structures, nanoconfined fluid mechanics. I pair the theory with hands-on engineering, so most of what I’ve built has gone end-to-end from the math to a working system.

Outside the day job, what pulls me from one thing to the next is curiosity and a long-running urge to build new things. I keep gravitating toward LLMs, agentic systems, RL training infrastructure, voice agents for narrow domains, and AI for hardware. Two of those turned into projects worth pointing at:

**[BenchCAD](/projects/1_project/)** — a multimodal benchmark for programmatic CAD, the entrance to AI for hardware. A model sees four orthographic views of an industrial part and has to write the CadQuery program that rebuilds it; we score the re-executed geometry. 17,900 execution-verified parts across 106 industrial families, half of them anchored to real ISO / DIN / EN / ASME / IEC specification tables rather than free-form shapes. Both frontier labs now report it on their flagship models — Anthropic in three Claude system cards (Fable 5 / Mythos 5, Sonnet 5, Opus 5) and OpenAI in the GPT-5.6 launch table, next to OSWorld and BrowseComp. When both labs race the same benchmark and publish the gains themselves, AI for hardware has become a strategic front. [benchcad.com](https://benchcad.com) · [arXiv:2605.10865](https://arxiv.org/abs/2605.10865)

**[A voice agent for the stock market](/projects/2_project/)** — daily spoken conversation about earnings, macro, and ticker news. It sidesteps the usual latency-vs-reasoning trade-off in voice products: each morning a frontier model pre-processes the day's news into a semantically-indexed brief, and at runtime the voice layer only retrieves and speaks. Frontier-quality content at small-model latency, in exchange for being scoped to one domain. [laurionai.com](https://www.laurionai.com/)

Before Tesla, I earned my PhD in mechanical engineering from the University of Virginia and a BS from the University of Science and Technology of China. My doctoral work centered on theoretical and computational modeling of multi-physics fields.

In my spare time, I enjoy traveling and playing Leagues.
