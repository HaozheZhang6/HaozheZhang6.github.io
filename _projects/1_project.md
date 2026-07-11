---
layout: page
title: BenchCAD
description: "The entrance to AI for hardware — an industry-standard multimodal benchmark for programmatic CAD (image → executable CadQuery): 17,900 verified parts across 106 industrial families"
img: assets/img/projects/benchcad.png
importance: 1
category: ai
period: May 2026
---

Programmatic CAD is the entrance to AI for hardware — the parametric code that turns a model's output into a manufacturable part. BenchCAD measures how well AI systems can reconstruct that code, which is a genuinely multimodal problem: it stacks cross-modal alignment, 3D spatial reasoning, and numeric-precision recovery into a single task.

The benchmark is built from **17,900 execution-verified CadQuery parts** across **106 industrial part families** — gears, springs, fittings, fasteners, and more. It's grounded in real engineering standards: **47 specification codes** (ISO, DIN, EN, ASME, IEC), with **52 of the 106 families** anchored to actual specification tables rather than free-form shapes.

It decomposes model capability into **four matched tasks** over the same underlying parts:

- **img2cq (Vision2Code)** — turn four orthographic renders into executable CadQuery code
- **qa_img (Vision QA)** — answer numeric geometric questions from rendered views, across capability levels L1–L4
- **qa_code (Code QA)** — the same questions, conditioned on the source code instead of images
- **edit_code (Code Edit)** — carry out instruction-guided edits to an existing program

Where models stand today: even the frontier's best re-graded IoU score is only **~0.29**. Models tend to recover a part's coarse outer shape but miss the internal structure and exact dimensions that make it manufacturable, and generalization to unseen families stays limited even after fine-tuning. Far from solved.

[benchcad.com](https://benchcad.com) · [arXiv:2605.10865](https://arxiv.org/abs/2605.10865)

## Featured in Anthropic's System Cards

BenchCAD is featured as a multimodal benchmark in two of Anthropic's official system cards, evaluating their frontier models on the Vision2Code task: the [Claude Fable 5 &amp; Mythos 5 System Card](https://www-cdn.anthropic.com/2f9323abbcc4abe219577539efe19a623c9ca2bd/Claude%20Fable%205%20&%20Claude%20Mythos%205%20System%20Card.pdf) (§8.16.4) and, most recently, the [Claude Sonnet 5 System Card](https://www-cdn.anthropic.com/480e0bb54327b9622282e9c39a83a4f490ed377e/Claude%20Sonnet%205%20System%20Card.pdf) (§8.10.3, June 30 2026). In the Fable 5 / Mythos 5 card they also ran a Python-tools ablation, where Vision2Code performance jumped from 0.379 to 0.650 voxel IoU once the model could render and visually verify its output.

<img src="/assets/img/projects/benchcad_syscard_full.png" alt="BenchCAD Vision2Code scores, full benchmark" style="display:block;width:100%;height:auto;margin:1rem auto;border-radius:6px;">

<img src="/assets/img/projects/benchcad_syscard_tools.png" alt="BenchCAD Vision2Code scores with and without Python tools" style="display:block;width:100%;height:auto;margin:1rem auto;border-radius:6px;">

<small>Figures from the *Claude Fable 5 &amp; Mythos 5 System Card* (§8.16.4).</small>

<img src="/assets/img/projects/benchcad_syscard_sonnet5.png" alt="BenchCAD Vision2Code subset scores in the Claude Sonnet 5 System Card" style="display:block;width:100%;height:auto;margin:1.5rem auto 1rem;border-radius:6px;">

<small>Figure from the *Claude Sonnet 5 System Card* (§8.10.3, June 30 2026).</small>
