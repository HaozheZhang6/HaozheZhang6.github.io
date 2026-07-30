---
layout: page
title: BenchCAD
description: "The entrance to AI for hardware — an industry-standard multimodal benchmark for programmatic CAD (image → executable CadQuery): 17,900 verified parts across 106 industrial families, now reported by Anthropic and OpenAI in their frontier model cards"
img: assets/img/projects/benchcad.png
importance: 1
category: ai
period: May 2026
---

Programmatic CAD is the entrance to AI for hardware — the parametric code that turns a model's output into a manufacturable part. BenchCAD measures how well AI systems can reconstruct that code, which is a genuinely multimodal problem: it stacks cross-modal alignment, 3D spatial reasoning, and numeric-precision recovery into a single task.

The benchmark is built from 17,900 execution-verified CadQuery parts across 106 industrial part families — gears, springs, fittings, fasteners, and more. It's grounded in real engineering standards: 47 specification codes (ISO, DIN, EN, ASME, IEC), with 52 of the 106 families anchored to actual specification tables rather than free-form shapes.

It decomposes model capability into four matched tasks over the same underlying parts:

- **img2cq (Vision2Code)** — turn four orthographic renders into executable CadQuery code
- **qa_img (Vision QA)** — answer numeric geometric questions from rendered views, across capability levels L1–L4
- **qa_code (Code QA)** — the same questions, conditioned on the source code instead of images
- **edit_code (Code Edit)** — carry out instruction-guided edits to an existing program

<img src="/assets/img/projects/benchcad_capability_pyramid.png" alt="BenchCAD capability tiers with example Vision-QA and Code-QA items" style="display:block;width:100%;height:auto;margin:1rem auto;border-radius:6px;">

<small>The four capability tiers, with example Vision-QA and Code-QA items.</small>

Where models stood at paper time (May 2026): the frontier's best re-graded IoU was only ~0.29. Models recovered a part's coarse outer shape but missed the internal structure and exact dimensions that make it manufacturable, and generalization to unseen families stayed limited even after fine-tuning. The frontier has moved fast since — see the lab-reported numbers below — but it moved mostly by giving models tools to render and check their own output, not by getting better at reading a drawing in one shot.

[benchcad.com](https://benchcad.com) · [arXiv:2605.10865](https://arxiv.org/abs/2605.10865)

## Reported by frontier labs

BenchCAD is now part of how frontier labs report their models. Both Anthropic and OpenAI evaluate their flagship models on the Vision2Code task and publish the numbers:

- **Anthropic** — [Claude Fable 5 &amp; Mythos 5 System Card](https://www-cdn.anthropic.com/2f9323abbcc4abe219577539efe19a623c9ca2bd/Claude%20Fable%205%20&%20Claude%20Mythos%205%20System%20Card.pdf) (§8.16.4), [Claude Sonnet 5 System Card](https://www-cdn.anthropic.com/480e0bb54327b9622282e9c39a83a4f490ed377e/Claude%20Sonnet%205%20System%20Card.pdf) (§8.10.3, June 30 2026), and the [Claude Opus 5 System Card](https://www.anthropic.com/claude-opus-5-system-card) (July 24 2026), which also upstreamed two fixes to our reference implementation.
- **OpenAI** — BenchCAD appears in the [GPT-5.6 launch table](https://openai.com/index/gpt-5-6/) (July 9 2026), alongside OSWorld and BrowseComp.

When both labs race the same benchmark and publish the gains themselves, AI for hardware stops being a niche and becomes a strategic front — and this is the yardstick they measure against.

The recurring finding across all of the reports is that tool use matters more than raw model scale on this task. In the Opus 5 card's ablation, voxel IoU on the Vision2Code subset goes 0.378 → 0.678 for Mythos 5 and 0.366 → 0.821 for Opus 5 once the model can render and visually verify its own output. Models that can look at what they built close most of the gap; models that cannot, do not.

<img src="/assets/img/projects/benchcad_syscard_opus5.png" alt="BenchCAD Vision2Code subset scores across GPT-5.6 Sol and four Claude models, with and without tools" style="display:block;width:100%;height:auto;margin:1rem auto;border-radius:6px;">

<small>Figure from the *Claude Opus 5 System Card* — Vision2Code with and without tools, including OpenAI's publicly reported GPT-5.6 Sol scores.</small>

<img src="/assets/img/projects/benchcad_gpt56_launch.png" alt="BenchCAD scores for GPT-5.6 Sol, Luna, Terra and GPT-5.5, with and without a Python tool" style="display:block;width:100%;height:auto;margin:1.5rem auto 1rem;border-radius:6px;">

<small>The BenchCAD rows of OpenAI's *GPT-5.6* launch table. The same tools effect shows up: +13 points for Sol, +16 for Terra.</small>

<img src="/assets/img/projects/benchcad_syscard_full.png" alt="BenchCAD Vision2Code scores, full benchmark" style="display:block;width:100%;height:auto;margin:1.5rem auto 1rem;border-radius:6px;">

<img src="/assets/img/projects/benchcad_syscard_tools.png" alt="BenchCAD Vision2Code scores with and without Python tools" style="display:block;width:100%;height:auto;margin:1rem auto;border-radius:6px;">

<small>Figures from the *Claude Fable 5 &amp; Mythos 5 System Card* (§8.16.4) — the first system-card appearance, where the Python-tools ablation ran 0.379 → 0.650 voxel IoU.</small>

<img src="/assets/img/projects/benchcad_syscard_sonnet5.png" alt="BenchCAD Vision2Code subset scores in the Claude Sonnet 5 System Card" style="display:block;width:100%;height:auto;margin:1.5rem auto 1rem;border-radius:6px;">

<small>Figure from the *Claude Sonnet 5 System Card* (§8.10.3, June 30 2026).</small>
