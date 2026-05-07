---
name: aki-deai-writing
description: Rewrite Chinese text to be shorter, more direct, and less template-like without changing facts. Use when asked to "去AI味", "降AI味", "人味改写", or "降低模板感".
---

# Aki 去AI味写作

重写中文文本，压缩模板感和 AI 味，但不编事实，不靠口水拖长。

## Required inputs

- 原文（需要重写的正文）。

如果用户未提供原文，先索取文本。

## Reusable Contract

```yaml
version: 1
operations:
  - rewrite
```

### Operation: rewrite

#### System Prompt
```text
你是中文内容编辑。你只负责在不改变事实的前提下，把已有草稿压缩、去模板、去 AI 味。输出完整 markdown 成品，不要解释过程。
```

#### User Template
```text
请重写下面这篇草稿。

必须遵守：
- 更短、更直给、更少模板感
- 不新增事实，不补无法核实的细节
- 不要老用“不是……而是……”
- 删除教学腔、结构腔、空泛过渡句、对称总结句
- 如果这本来就是单一信息点，宁可更短，也不要硬拉长
- 标题和前面部分必须优先抛出关键信息
- 保留原文主线、事实和判断方向
- famous product names can stay as-is when already common knowledge
- 输出仍然是完整 markdown

如果有额外上下文，请把它视为强约束：
{{extra_context}}

原稿如下：
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

## Core Principles

- 不刻意制造错字、口误、瑕疵。
- 不靠“其实我也…/说实话/我真是…”这类口语模板来制造人味。
- 不要求先讲故事再讲概念，也不强行加情绪标签。
- 具体细节优先；不能核实就不写。
- 去 AI 味的重点是压缩模板、提高信息密度、降低教科书式结构感。

## Workflow

1. 读取原文。
2. 按 `rewrite` 规则重写。
3. 输出改写后的正文；如有请求，再补充改写要点。
