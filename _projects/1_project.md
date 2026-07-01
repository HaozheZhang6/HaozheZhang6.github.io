---
layout: page
title: BenchCAD
description: "Industry-standard benchmark for programmatic CAD — used by Anthropic in the Claude Fable 5 / Mythos 5 and Sonnet 5 System Cards"
img: assets/img/projects/benchcad.png
importance: 1
category: ai
period: May 2026
---

BenchCAD is a comprehensive benchmark for evaluating how well large language models generate programmatic CAD code. It contains over 17,000 execution-verified CadQuery programs across 106 industrial part families — gears, springs, drills, brackets and more — and probes models across four tasks: visual question answering, code analysis, image-to-code conversion, and code editing.

Findings: current models often recover the coarse outer geometry of a part but fail to produce faithful parametric CAD programs. Common failure modes include missing structural details and oversimplified operations, and generalization to unseen part families remains limited even after fine-tuning.

[benchcad.com](https://benchcad.com) · [arXiv:2605.10865](https://arxiv.org/abs/2605.10865)

## Cited in Anthropic's System Cards

Anthropic has used BenchCAD in two official system cards to evaluate their frontier models on the Vision2Code task: the [Claude Fable 5 &amp; Mythos 5 System Card](https://www-cdn.anthropic.com/2f9323abbcc4abe219577539efe19a623c9ca2bd/Claude%20Fable%205%20&%20Claude%20Mythos%205%20System%20Card.pdf) (§8.16.4) and, most recently, the [Claude Sonnet 5 System Card](https://www-cdn.anthropic.com/480e0bb54327b9622282e9c39a83a4f490ed377e/Claude%20Sonnet%205%20System%20Card.pdf) (§8.10.3, June 30 2026). In the Fable 5 / Mythos 5 card they also ran a Python-tools ablation, where Vision2Code performance jumped from 0.379 to 0.650 voxel IoU once the model could render and visually verify its output.

<img src="/assets/img/projects/benchcad_syscard_full.png" alt="BenchCAD Vision2Code scores, full benchmark" style="display:block;max-width:100%;height:auto;margin:1rem auto;border-radius:6px;">

<img src="/assets/img/projects/benchcad_syscard_tools.png" alt="BenchCAD Vision2Code scores with and without Python tools" style="display:block;max-width:100%;height:auto;margin:1rem auto;border-radius:6px;">

<small>Figures: Anthropic, *Claude Fable 5 &amp; Claude Mythos 5 System Card* (June 2026), §8.16.4.</small>
