---
name: aki-domestic-platform-risk-check
description: Use when writing, rewriting, reviewing, or publishing Chinese content for Xiaohongshu, Douyin, WeChat Official Account, Video Account, Bilibili, or multi-platform self-media, especially before finalizing platform copies, titles, captions, image prompts, video scripts, or posts that may contain sensitive words, risk words, platform moderation issues, exaggerated claims, finance-like wording, attack language, account-risk wording, or ad-law absolute terms.
---

# Aki Domestic Platform Risk Check

## Purpose

Before Aki publishes or turns a draft into platform assets, check whether the wording is likely to trigger domestic self-media moderation, limit exposure, or feel too aggressive for Xiaohongshu/Douyin/WeChat style.

This is not an official forbidden-word database. Treat it as a pragmatic preflight check: catch risky wording early, soften it without killing the punch, and keep a short report the user can act on.

## When To Run

Run this skill whenever the user asks to:

- create or polish Xiaohongshu, Douyin, WeChat, Video Account, Bilibili, or multi-platform content
- generate platform copies from `aki-content-pipeline-pro`
- write titles, cover text, image prompts, video scripts, captions, hashtags, or post copy
- publish, schedule, or upload Chinese self-media content
- check "违禁词", "敏感词", "限流词", "风控词", "小红书能不能发", or "会不会违规"

For content pipelines, run the check after platform copy is drafted and before image prompts, video scripts, or publishing. If the user is still brainstorming, use the risk patterns while writing and run the script once a concrete draft exists.

## Quick Command

Use the bundled checker on one or more Markdown/text files:

```bash
python3 /Users/aki/Development/code/aki-skills/skills/aki-domestic-platform-risk-check/scripts/check_platform_risk.py \
  --platform xiaohongshu \
  --rewrite \
  "/path/to/xiaohongshu_post.md"
```

For all platforms:

```bash
python3 /Users/aki/Development/code/aki-skills/skills/aki-domestic-platform-risk-check/scripts/check_platform_risk.py \
  --platform all \
  --rewrite \
  "/path/to/copy.md"
```

## Report Rules

Return a short, direct report:

1. Overall risk: `high`, `medium`, `low`, or `clean`
2. A table of findings: file/line, risky word, severity, why it matters, replacement
3. A safer rewrite if the user is preparing to publish or asks for fixes
4. A reminder that platform rules change and this is not an official legal/compliance guarantee

Keep the user's voice. Do not sterilize the copy into bland corporate language. Replace risky words with equally clear but safer phrases.

## Replacement Style

Prefer these patterns:

- `下注` / `押注` -> `加码` / `投入` / `支持`
- `死敌` -> `主要对手` / `直接竞争者`
- `孤立无援` -> `处境更被动` / `压力变大`
- `封号严重` -> `账号风控偏严格`
- `卖身契` -> `独家绑定协议` / `旧协议`
- `金主` -> `重要合作方` / `主要支持方`
- `分手` -> `关系重写` / `合作调整`
- `没落` -> `被继续追赶` / `增长承压`
- `更搞笑的是` -> `更值得关注的是`

## Risk Categories

### High

Strongly recommend changing before publish:

- account penalty wording: `封号`, `封禁`, `封杀`, `黑号`
- gambling/speculation-like verbs: `下注`, `押注`, especially in titles
- direct hostile labels: `死敌`, `围剿`, `干死`, `血洗`
- panic/scam/illegal terms if not necessary: `暴雷`, `跑路`, `割韭菜`

### Medium

Usually soften for Xiaohongshu/Douyin:

- dramatic isolation or decline: `孤立无援`, `没落`, `崩了`, `跪了`
- finance-heavy or dependency labels: `金主`, `卖身契`, `砸钱`
- absolute claims: `唯一`, `第一`, `最强`, `绝对`, `保证`, `100%`

### Low

Often okay, but polish if the post feels aggressive or clickbait:

- social-media slang: `官宣`, `分手`, `更搞笑的是`
- overly sharp contrast: `吊打`, `碾压`, `完爆`

## If No File Exists Yet

When drafting from scratch, apply the style guardrails directly:

- titles can be sharp, but avoid gambling/hostile/account-punishment terms
- prefer "关系变化、生态重排、压力变大、加码、支持" over "下注、死敌、孤立无援、封号"
- after writing, run the script on the generated file before presenting it as final

## Updating The Lexicon

The bundled list is in `references/risk-lexicon.zh.json`. Add terms there when the user flags a new platform-risk pattern. Use:

- `severity`: `high`, `medium`, or `low`
- `category`: short Chinese label
- `reason`: one concise reason
- `suggestions`: safer replacements, strongest first
