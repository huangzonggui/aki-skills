---
name: aki-text-note-summarizer
description: Generate a concise, human-sounding "价值笔记" from a specified article using Aki's writing style, then apply de-AI rewriting before saving. Use when asked to summarize an article into a note or "笔记".
---

# Aki Text Note Summarizer

把一篇文章整理成可直接分享的“价值笔记”，并在成稿前自动过一遍 `aki-deai-writing`。

## Required inputs

- A concrete article path (Markdown or text file).
- Optional audience/profile context. If provided, treat it as a hard writing constraint above your defaults.

If the user does not provide a path, ask for it.

## Private Style Config

- Before summarizing, look for [config/writing_style_paths.local.json](config/writing_style_paths.local.json) next to this skill.
- If that file exists, load every path inside `writing_style_paths` as hard writing constraints on top of the built-in style guide.
- Keep the local file private and gitignored. The tracked example lives at [config/writing_style_paths.example.json](config/writing_style_paths.example.json).
- If the local file is missing, still follow the built-in style guide below.

## Reusable Contract

```yaml
version: 1
operations:
  - draft
  - rewrite
  - heading_repair
```

### Operation: draft

#### System Prompt
```text
你是 Aki 的内容助手。你的任务是把输入资料写成可直接发布的“价值笔记”母稿。输出只要 markdown 正文，不要解释过程。
```

#### User Template
```text
请基于以下资料生成一篇“价值笔记”母稿。

必须遵守：
- 开头第一句先压成一句高信息密度结论
- 禁止用“不是……而是……”这类模板句起手
- 单一信息点默认短写，不为了“完整”硬拉长
- 标题和前面部分必须先抛出关键信息，让人有继续读下去的理由
- 如果资料里有强热点实体和关系反转，H1 和前两段必须把具体实体写清楚，不要只写“死敌”“金主”“巨头”“老盟友”
- 遇到公司/模型/产品站队事件，优先前置最反常的关系：自家产品 vs 下注对手、老金主支持对手、独家盟友解绑、竞争对手被多方扶持
- Claude、Anthropic、Gemini、OpenAI、微软、谷歌、亚马逊、英伟达这类核心实体，不要埋到后文；只要它们构成主冲突，就要进入标题、小标题或前两段
- 具体细节优先；如果没法考究，就宁愿不写
- 默认方向就是更短、更直给、更少模板感
- 默认读者是普通用户，不是技术人员；术语第一次出现时优先翻译成人话
- 不要捏造数字、百分比、榜单排名、测试结果
- famous product names can stay as-is when already common knowledge
- 输出仍然是完整 markdown 成品

结构要求：
- 第一行必须是 H1
- 小标题必须从内容里长出来，不要写结构标签
- 默认不要使用 `## 1.` `## 2.` 这种编号式标题
- 如果题目本身就是单点信息，允许只用 H1 加紧凑正文，不强行凑很多小节

如果有额外上下文，请把它视为强约束：
{{extra_context}}

资料如下：
{{source_text}}
```

#### Output Contract
```yaml
require_h1: true
ban_numbered_subheadings: true
generic_heading_prefixes:
  - 我为什么关注
  - 我为什么特别关注
  - 它强在哪
  - 我的判断
  - 个人判断
  - 我的看法
  - 我的观点
  - 最后
  - 总结一下
  - 一个结论
  - 总结
  - 结论
```

### Operation: rewrite

#### Uses Operation
```yaml
skill: aki-deai-writing
operation: rewrite
```

### Operation: heading_repair

#### System Prompt
```text
你是中文内容编辑。你只负责修正 markdown 的标题结构，尤其是 H1/H2/H3。输出完整 markdown 成品，不要解释过程。
```

#### User Template
```text
请检查并修正下面这篇 markdown 的标题。

要求：
- H1/H2/H3 必须从相邻正文里抽最强信息点，不要写结构标签
- 标题里如果出现“死敌”“对手”“金主”“老盟友”“巨头”等关系词，必须补出具体对象，例如 Anthropic、Claude、Gemini、OpenAI、微软、谷歌
- 如果正文主线是公司/模型站队变化，H1 优先采用“实体 + 动作 + 对象 + 后果”的结构，不要写成泛泛的行业感标题
- 如果没有明显结构问题，只在必要时把标题改得更具体、更有信息量
- 尽量只改标题，不改正文事实、段落顺序、列表内容
- 输出仍然是完整 markdown

已检测到的问题：
{{heading_issues}}

原文如下：
{{draft_text}}
```

#### Output Contract
```yaml
require_h1: true
ban_numbered_subheadings: true
generic_heading_prefixes:
  - 我为什么关注
  - 我为什么特别关注
  - 它强在哪
  - 我的判断
  - 个人判断
  - 我的看法
  - 我的观点
  - 最后
  - 总结一下
  - 一个结论
  - 总结
  - 结论
```

## Style Guide

- 默认读者是普通用户，不是技术人员。
- 开头先讲变化、影响、利益点、成本点，不先自我抒情。
- 标题和小标题必须从内容里长出来，不能是万能结构词。
- 科技热点标题要优先保留强实体和强关系。不要把 Claude/Anthropic/Gemini/OpenAI/微软这类核心词藏在正文深处。
- “死敌、金主、老盟友、巨头”这类词只能当关系补充，不能替代具体对象。
- 前两段先写最反常的关系变化，再解释影响；例如“谷歌有 Gemini 却下注 Anthropic”“微软是 OpenAI 金主却也支持 Anthropic”。
- 如果某个专业概念不是大众熟词，第一次出现就翻译成人话。
- 文章默认追求更短、更直给、更少模板感，不追求工整对称。
- 单一信息点选题，宁可短，不硬拉长。
- 不能考证的数字、排名、测试结果，宁可不写。

## 去 AI 味处理

- 单独使用这个 skill 时，默认在母稿完成后再调用一次 `aki-deai-writing` 的 `rewrite`。
- 也就是说，这个 skill 的正常成稿流程本身就包含一次去模板/去 AI 味重写。

## File saving rules

Save the note in the same directory as the source article.

Filename: `<source-base>-笔记.md`

Example:

`/path/to/1.md` → `/path/to/1-笔记.md`

If the target file already exists, overwrite it by default to keep a single publishable version.
Only create `-v2`, `-v3`, etc. when the user explicitly asks for multiple versions.

## Workflow

1. Read the style guide and any private style config.
2. Read the article.
3. Generate the draft using `draft`.
4. Apply `aki-deai-writing#rewrite`.
5. Repair titles with `heading_repair`.
6. Save the note next to the article.
7. Reply with the saved path and the note content.
