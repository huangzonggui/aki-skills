---
name: aki-content-pipeline-pro
description: 从多篇参考链接或本地文件先产出并人工审核“核心个人笔记”，再裂变为微信公众号文章、微信公众号图文、小红书图文与三平台视频成品包的总编排技能。适用于“个人笔记一稿多发”“先共创后分发”“需要提示词审核与断点续跑”的场景。支持微信文章抓取、视频链接占位导入、统一分页、统一提示词留档、返工重跑、公众号草稿发布。
---

# Aki Content Pipeline Pro

## Overview

以根目录 `core_note.md` 作为唯一母稿，先统一分页，再统一提示词，再派生平台文案、平台图片和平台视频。

这轮只重构创作与生图主链路：

1. 根目录先产出统一母稿和统一分页。
2. 全平台共用同一套页数、页序和提示词。
3. 生图前审核 prompt，生图后不做额外质量闸门。
4. 视频脚本对着图片节点写，不再只对着文章写。
5. `publish_wechat_drafts` 保持旧实现，只改上游资产编排。

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

1. `aki-wechat-fetcher`
2. `youtube-clipper`
3. `aki-text-note-summarizer`
4. `aki-handnote-cover`
5. `aki-dense-handnote-series`
6. `aki-adaptive-video-script-style`
7. `aki-image-article-video`
8. `aki-post-to-wechat-browser`

### 间接调用

1. `aki-deai-writing`
2. `aki-context-to-html`
3. `jianying-editor`

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

4. 进入母稿共创并人工修改 `core_note.md`：
```bash
python scripts/pipeline.py --intent co_create_core_note --topic-root "<topic_root>"
```

5. 人工确认 `core_note.md` 后批准继续：
```bash
python scripts/pipeline.py --intent approve_core_note --topic-root "<topic_root>"
```

6. 生成统一分页和平台文案：
```bash
python scripts/pipeline.py --intent derive_platform_copies --topic-root "<topic_root>"
```

6. 写出统一 prompt 文件：
```bash
python scripts/pipeline.py --intent generate_prompts --topic-root "<topic_root>"
```

7. 审核 prompt 后生图：
```bash
python scripts/pipeline.py --intent render_images --topic-root "<topic_root>" --approved-prompt-titles
```

8. 根据图片节点生成三平台口播脚本与时间轴：
```bash
python scripts/pipeline.py --intent derive_video_scripts --topic-root "<topic_root>"
```

9. 生成剪映草稿 / 视频包：
```bash
python scripts/pipeline.py --intent build_video_package --topic-root "<topic_root>"
```

10. 发布公众号草稿：
```bash
python scripts/pipeline.py --intent publish_wechat_drafts --topic-root "<topic_root>"
```

如果要在发布时明确指定公众号文章样式：

```bash
python scripts/pipeline.py --intent publish_wechat_drafts --topic-root "<topic_root>" --article-style part-guide
```

## 关键约束

1. `outline.md` 里的页数和页序只算一次，全平台共用。
2. `prompts/` 只保留一份统一提示词，平台只消费结果图。
3. 当前默认 `prod` 渲染三套图片：`wechat`、`xiaohongshu`、`douyin`。
4. `test` 默认只渲染 `wechat`。
5. 单图超过 `4MB` 时，在同目录补一张高质量 `jpg`，不再建 `upload_ready/`。
6. 当前默认按纯白底生成，并把 2K 级画布安全留白从 `16px` 提高到 `48px`。
7. 图片成本汇总只按真正发给生图模型的张数计费，不把本地 `jpg` 衍生图算进成本。
8. 视频脚本按图片节点拆段：封面 3-5 秒，后续每张系列图一段。
9. 视频工程默认写入系统剪映项目目录；如需迁移机器，继续通过 `JY_PROJECTS_ROOT` 覆盖。

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
