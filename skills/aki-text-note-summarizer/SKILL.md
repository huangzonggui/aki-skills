---
name: aki-text-note-summarizer
description: Generate a concise, human-sounding "价值笔记" from a specified article using Aki's "资深文本笔记总结者" style, and save the note next to the source article. Use when asked to summarize an article into a note or "笔记".
---

# Aki Text Note Summarizer

Create a shareable, opinionated note from a given article using the local style guide.

## Required inputs

- A concrete article path (Markdown or text file).

If the user does not provide a path, ask for it.

## Style guide

Always follow the rules in:

`/Users/aki/Downloads/Browsers/自媒体/1. AI个人IP话题/workflow/2. 创作原则/6. 资深文本笔记总结者.md`

Load only what you need from that file.

## Output format

Use three sections with headings:

1. 概览（<= 60字）
2. 干货列表（不工整的要点列表）
3. 感悟（强主观判断）

Avoid AI-ish tone, template openings, and filler. Add ~30% personal judgement without fabricating facts.

## File saving rules

Save the note in the same directory as the source article.

Filename: `<source-base>-笔记.md`

Example:

`/path/to/1.md` → `/path/to/1-笔记.md`

If the target file already exists, append `-v2`, `-v3`, etc.

## Workflow

1. Read the style guide.
2. Read the article.
3. Draft the note using the required tone and sections.
4. Save the note next to the article.
5. Reply with the saved path and the note content.
