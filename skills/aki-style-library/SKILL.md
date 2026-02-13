---
name: aki-style-library
description: Shared prompt library for reusable visual styles. Use when asked to reuse or reference handnote/masterpiece prompts across skills.
---

# Baoyu Style Library

Centralized style prompt library for reuse across multiple skills.

## Available Styles

- `手绘逻辑信息艺术设计师`: Concise hand-drawn note style for logical diagrams and summaries
- `masterpiece`: Warm, inspirational hand-drawn infographic with 3D lettering
- `dense-handdrawn-infographic`: High information density, colorful hand-drawn infographic cover

## Files

- `references/styles/手绘逻辑信息艺术设计师.md`
- `references/styles/masterpiece.md`
- `references/styles/dense-handdrawn-infographic.md`

## Usage

Reference these files from other skills when you need consistent styling:

- `../aki-style-library/references/styles/<style>.md`

This skill does not generate images by itself; it provides reusable prompt templates.
