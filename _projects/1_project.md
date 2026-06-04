---
layout: page
title: BenchCAD
description: Industry-standard benchmark for programmatic CAD with LLMs
img: assets/img/projects/benchcad.png
importance: 1
category: ai
period: May 2026
---

BenchCAD is a comprehensive benchmark for evaluating how well large language models generate programmatic CAD code. It contains over 17,000 execution-verified CadQuery programs across 106 industrial part families — gears, springs, drills, brackets and more — and probes models across four tasks: visual question answering, code analysis, image-to-code conversion, and code editing.

Findings: current models often recover the coarse outer geometry of a part but fail to produce faithful parametric CAD programs. Common failure modes include missing structural details and oversimplified operations, and generalization to unseen part families remains limited even after fine-tuning.

[Project page](https://benchcad.github.io/BenchCAD_webpage/) · [arXiv:2605.10865](https://arxiv.org/abs/2605.10865)
