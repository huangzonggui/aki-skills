---
name: aki-adaptive-video-script-style
description: 从核心笔记或文章生成 Aki 风格中文口播脚本，时长自适应 15 秒到 5 分钟。用于多平台分发链路中的“视频口播文案”阶段，输出可直接进入视频生成/配音流程。
---

# Aki Adaptive Video Script Style

## Overview

输入一篇核心笔记或文章，输出一版可直接口播的中文脚本。  
重点是“爆点直给 + 动态 2-4 点展开 + 口语提纲感 + 个人判断”，并根据内容密度自动匹配时长（15s-5min）。

## When To Use

适用场景：

1. 已有 `core_note.md`，需要自动产出口播稿。
2. 需要覆盖多个时长段（短视频到较长讲解），不想手工改版。
3. 需要脚本风格更接近 Aki（去模板腔、观点密度高）。

## Workflow

1. 读取输入内容（Markdown/Text）。
2. 估算目标口播时长（或使用外部指定时长范围）。
3. 按 Aki 风格生成单一终稿：
   - 首句直接给出“为什么现在值得看”
   - 主体按题材动态展开，默认优先 2-4 点
   - 结尾给出判断句
4. 保存到指定输出路径。

## Script Entry

```bash
python scripts/generate_script.py \
  --input /abs/path/core_note.md \
  --output /abs/path/voice_script.md \
  --min-sec 15 \
  --max-sec 300
```

可选参数：

1. `--target-sec`：强制目标时长（秒），会被 `min/max` 约束。
2. `--model`：覆盖默认模型。
3. `--source-label`：为脚本添加来源标识（可选）。

## Output Format

输出文件是 Markdown 纯正文，默认结构：

```markdown
<4-20 行短句正文，按时长自适应>
```

## References

需要细化口播风格时，读取 [references/style-rules.md](references/style-rules.md)。

## Private Samples

这个 skill 还会读取用户自己的私有口播样本库，优先级高于公共规则。

默认目录：

- [/Users/aki/Documents/ObsidianVaults/Aki数字资产/02-IP个人话题/口播脚本资产](/Users/aki/Documents/ObsidianVaults/Aki数字资产/02-IP个人话题/口播脚本资产)

读取顺序：

1. 私有口播样本
2. 公共风格规则
3. 当前输入内容

私有样本只放在 Obsidian 资产目录，不放在 skill repo 里。
