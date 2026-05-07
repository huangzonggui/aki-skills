---
name: aki-content-pipeline-pro
description: 从多篇参考链接或本地文件先产出并人工审核“核心个人笔记”，再裂变为微信公众号文章、微信公众号图文、小红书图文与三平台视频成品包的总编排技能。适用于“个人笔记一稿多发”“先共创后分发”“需要提示词审核与断点续跑”的场景。支持微信文章抓取、视频链接占位导入、统一分页、统一提示词留档、返工重跑、公众号草稿发布。
---

# Aki Content Pipeline Pro

## Overview

以根目录 `core_note.md` 作为唯一母稿，先统一分页，再统一提示词，再派生平台文案、平台图片和平台视频。

这轮只重构创作与生图主链路：

1. 根目录先产出统一母稿和统一分页。
2. 全平台共用同一套页数、页序和提示词，但不同平台必须独立生图，不能复制或复用别的平台结果图。
3. 生图前审核 prompt，生图后不做额外质量闸门。
4. 视频脚本对着图片节点写，不再只对着文章写。
5. `publish_wechat_drafts` 走微信公众号官方 API，不走 Playwright / 浏览器自动化。

## 根目录结构

```text
<topic_root>/
  core_note.md
  core_note.draft.md
  outline.md
  prompts/
    cover_prompt.md
    series_01_prompt.md
    ...
  copies/
    wechat_article.md
    wechat_imagepost_copy.md
    xiaohongshu_post.md
  images/
    wechat/
      cover_01.png
      cover_01.jpg
      series_01.png
      series_01.jpg
      ...
    xiaohongshu/
      ...
    douyin/
      ...
  video/
    wechat/
      timeline.json
      voice_wechat_video.md
      output/
    xiaohongshu/
      timeline.json
      voice_xhs_video.md
      output/
    douyin/
      timeline.json
      voice_douyin_video.md
      output/
  refs/
  meta/
    state.json
    content_plan.json
    prompt_title_review.md
    image_cost_summary.md
    image_cost_summary.json
```

## 依赖技能关系

### 直接调用

1. `youtube-clipper`
2. `aki-text-note-summarizer`
3. `aki-handnote-cover`
4. `aki-dense-handnote-series`
5. `aki-adaptive-video-script-style`
6. `aki-image-article-video`
7. `aki-wechat-api-imagepost`
8. `aki-domestic-platform-risk-check`

### 间接调用

1. `aki-deai-writing`
2. `aki-context-to-html`
3. `jianying-editor`

`summarize_core_note` 的入口 skill 是 `aki-text-note-summarizer`。
该 skill 的 `rewrite` 会通过 Reusable Contract 引用 `aki-deai-writing`，因此 pipeline 不再自己定义摘要和去 AI 味规则。

## 脚本入口

主入口：

```bash
python scripts/pipeline.py --intent <intent> ...
```

可用 intent：

1. `init_topic`
2. `ingest_sources`
3. `summarize_core_note`
4. `approve_core_note`
5. `derive_platform_copies`
6. `generate_prompts`
7. `render_images`
8. `derive_video_scripts`
9. `build_video_package`
10. `publish_wechat_drafts`
11. `resume`
12. `continue_from_last`
13. `rework`

兼容别名：

- `co_create_core_note` 仍可调用。若 `core_note.md` 还不存在，它会先用 `core_note.draft.md` 生成一份可编辑母稿，然后阻塞在人工确认步骤。

## 标准流程

目录命名约定：`<最小可用序号>. <爆款标题>-<YYYYMMDD-HHMM>`。

1. 创建话题目录：
```bash
python scripts/pipeline.py --intent init_topic --cwd . --title "你的爆款标题" --mode prod
```

2. 收集来源：
```bash
python scripts/pipeline.py --intent ingest_sources --topic-root "<topic_root>" \
  --source "https://mp.weixin.qq.com/s/xxxx" \
  --source "/path/to/local.md"
```

3. 生成核心母稿：
```bash
python scripts/pipeline.py --intent summarize_core_note --topic-root "<topic_root>"
```
这一步只会生成 `core_note.draft.md`，不会自动把草稿写进 `core_note.md`。
摘要链路会按 contract 依次执行：
1. `aki-text-note-summarizer#draft`
2. `aki-deai-writing#rewrite`（由 summarizer 引用）
3. `aki-text-note-summarizer#heading_repair`

4. 进入母稿共创并人工修改 `core_note.md`：
```bash
python scripts/pipeline.py --intent co_create_core_note --topic-root "<topic_root>"
```

5. 人工确认 `core_note.md` 后批准继续：
```bash
python scripts/pipeline.py --intent approve_core_note --topic-root "<topic_root>"
```

## 母稿共创写作约束

以下约束只用于 `co_create_core_note` / `approve_core_note` 之间的人稿共创阶段，目标是把 `core_note.md` 改成可继续派生的平台母稿，而不是写成“资料综述”或“AI总结稿”。

### 1. 去掉来源痕迹

默认不要出现这类暴露资料来源的句式，除非用户明确要求保留来源感或引用感：

- `几篇文章里反复提到`
- `按这些文章的说法`
- `文章里提到`
- `从这些资料看`
- `结合几篇文章来看`
- `有文章认为`
- `资料显示`
- `从上面的内容可以看出`

默认做法：

1. 直接写判断句。
2. 直接写结论句。
3. 直接写场景句。

不要先铺一层“资料怎么说”，再绕回观点。

### 2. 先结构，后展开

如果用户没有指定别的结构，`core_note.md` 默认按“问题 -> 结论 -> 分点”组织，不要堆成长段。

推荐顺序：

1. `它增强了什么能力`
2. `它的价格怎么样`
3. `普通人现在怎么用得上`
4. `它有什么缺点`
5. `不同用户场景下的模型选择建议`

默认要求：

1. 每个二级标题只回答一个问题。
2. 每个二级标题下面先给一句总判断。
3. 再拆成 2-4 个三级小点或项目符号。
4. 优先短句和短段，不要一坨一坨写成长解释。

### 3. 优先“可扫读”，不要“散文化长段”

`core_note.md` 是平台母稿，不是最终长文。可扫读性优先。

默认做法：

1. 多用三级标题。
2. 多用项目符号。
3. 多用并列分点。
4. 控制单段长度。

避免：

1. 一个二级标题下面只有一大段解释。
2. 同一段里混着背景、观点、例子、结论。
3. 用很多过渡句把简单信息拖长。

### 4. 负面信息要显式入稿

如果参考资料里同时有优点和缺点，母稿不能只写优点。

至少要明确落一类负面信息：

1. 使用限制
2. 成本问题
3. 翻车案例
4. 不适用场景
5. 并非全场景第一的地方

不要把负面信息埋在句中顺手带过，至少给独立分点。

### 5. 场景建议要写成可执行选择

如果母稿涉及“该不该用”“适合谁用”，优先写成明确分组，而不是泛泛而谈。

例如：

- 轻度用户怎么选
- 重度用户怎么选
- 已在第三方工具里的用户怎么选
- 对价格敏感的用户怎么选

目标是让读者一眼知道“我属于哪一类，我该怎么选”。

6. 生成统一分页和平台文案：
```bash
python scripts/pipeline.py --intent derive_platform_copies --topic-root "<topic_root>"
```

7. 平台风控词预检：
```bash
python3 /Users/aki/Development/code/aki-skills/skills/aki-domestic-platform-risk-check/scripts/check_platform_risk.py \
  --platform xiaohongshu \
  --rewrite \
  "<topic_root>/copies/xiaohongshu_post.md"
```

如果小红书/抖音/视频号/公众号文案出现 `high` 风险词，先按报告改稿，再进入图片 prompt、视频脚本或发布环节。

8. 写出统一 prompt 文件：
```bash
python scripts/pipeline.py --intent generate_prompts --topic-root "<topic_root>"
```

9. 审核 prompt 后生图：
```bash
python scripts/pipeline.py --intent render_images --topic-root "<topic_root>" --approved-prompt-titles
```

10. 根据图片节点生成三平台口播脚本与时间轴：
```bash
python scripts/pipeline.py --intent derive_video_scripts --topic-root "<topic_root>"
```

9. 人工审核视频脚本后批准继续：
```bash
python scripts/pipeline.py --intent approve_video_scripts --topic-root "<topic_root>"
```

10. 生成剪映草稿 / 视频包：
```bash
python scripts/pipeline.py --intent build_video_package --topic-root "<topic_root>"
```

11. 发布公众号草稿：
```bash
python scripts/pipeline.py --intent publish_wechat_drafts --topic-root "<topic_root>"
```

发布链路使用 `aki-wechat-api-imagepost` 的官方 API 草稿接口；不启动浏览器，也不调用 Playwright。

## 关键约束

1. `outline.md` 里的页数和页序只算一次，全平台共用。
2. `prompts/` 只保留一份统一提示词，但三平台必须各自独立渲染图片；禁止直接复制 `wechat` 到 `xiaohongshu/douyin`，也禁止跨平台复用成图，以避免平台判重或抄袭风险。
3. 当前默认 `prod` 独立渲染三套图片：`wechat`、`xiaohongshu`、`douyin`。
4. `test` 默认只渲染 `wechat`。
5. 单图超过 `4MB` 时，在同目录补一张高质量 `jpg`，不再建 `upload_ready/`。
6. 当前默认按纯白底生成，并把 2K 级画布安全留白从 `16px` 提高到 `48px`。
7. 图片成本汇总只按真正发给生图模型的张数计费，不把本地 `jpg` 衍生图算进成本。
8. 视频脚本按图片节点拆段：封面 3-5 秒，后续每张系列图一段。
9. 当前默认短视频目标总时长约 30 秒，不要默认生成长口播。
10. 前 3-5 秒必须先给 hook，优先抛出“新发布 / 数字重点 / 价格变化 / 使用限制 / 翻车风险”这类抓手，不要先铺背景。
11. `derive_video_scripts` 只负责产出展示稿 `video/<platform>/voice_*.md` 和时间轴；必须先人工审核展示稿，再执行 `approve_video_scripts` 生成对应的 `TTS` 稿，最后才能继续 `build_video_package`。
12. 视频工程默认写入系统剪映项目目录；如需迁移机器，继续通过 `JY_PROJECTS_ROOT` 覆盖。
13. 如果某个平台图片质量不合格，返工时应只重跑该平台的生图；不要把其他平台图片直接拷过去顶替。
14. 视频脚本优先用普通人能直接听懂的话，不要堆“长链路、工具协同、全链路、上下文管理”这类抽象词；能翻成人话就先翻成人话。
15. 目录按需懒创建：`init_topic` 只创建话题根目录和写入状态所需的 `meta/`；`refs/`、`copies/`、`prompts/`、`images/`、`video/` 只有在对应步骤真正写文件时才创建，返工后也不要重新铺空目录。
16. 抖音图片规则必须发生在生图调用入口：当 `render_images` 的平台列表包含 `douyin` 时，给底层生图请求传入 `douyin_series_safe_84` profile，并把请求参数 `aspect_ratio` 设为 `9:16`；平台列表不包含 `douyin` 时，不要发起任何抖音系列图片请求，也不要附加抖音 profile。

## 抖音系列生图参数

`aki-content-pipeline-pro` 是创作编排 skill。它先通过 `aki-dense-handnote-series` 生成统一分页和统一 prompt，再由 `render_images` 按平台把审核后的 prompt 传给底层生图能力。

当本次确实要生成抖音系列图片时，`render_images` 必须在调用生图前附加以下参数，而不是在成图后再本地修图：

1. `profile`: `douyin_series_safe_84`
2. `aspect_ratio`: `9:16`
3. prompt 追加抖音安全出血要求：纯白背景、完整构图放在居中的 `84%` 安全内容区内，四边保留纯白出血，标题、正文、图标、箭头、标注和核心信息都不得进入外侧边缘区域。

输出仍按平台目录管理：

1. `images/douyin/originals/*.png`：抖音 profile 下由模型直接生成的原图。
2. `images/douyin/*.jpg`：同一张模型图的 JPG 转换版，方便下游剪映 / 发布链路读取。

不要把微信或小红书图片复制到抖音目录，也不要用本地后处理伪造抖音安全版来替代抖音 profile 生图。

## 返工

查看下一步：

```bash
python scripts/pipeline.py --intent resume --topic-root "<topic_root>"
```

常用返工目标：

```bash
python scripts/pipeline.py --intent rework --topic-root "<topic_root>" --target core_note
python scripts/pipeline.py --intent rework --topic-root "<topic_root>" --target outline
python scripts/pipeline.py --intent rework --topic-root "<topic_root>" --target prompts
python scripts/pipeline.py --intent rework --topic-root "<topic_root>" --target images
python scripts/pipeline.py --intent rework --topic-root "<topic_root>" --target video_scripts
python scripts/pipeline.py --intent rework --topic-root "<topic_root>" --target video
```

中文别名：

1. `返工核心笔记`
2. `返工统一分页`
3. `返工提示词`
4. `返工图片`
5. `返工视频脚本`
6. `返工视频`

## 备注

1. 公众号发布链路仍走旧的发布脚本，只是文章、图文文案和发布图片改为从新根目录结构派生。
2. 视频来源如果自动抽取逐字稿失败，仍会写入手工补录占位文件并阻断后续流程。
3. 统一分页结果和 prompt 文本会存到 `meta/content_plan.json`，供后续 prompt、生图、视频脚本复用。
