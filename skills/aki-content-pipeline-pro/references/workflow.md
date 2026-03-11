# Workflow Notes

## Current Gates

1. `approve_core_note`
   - `core_note.md` 必须人工确认后，才允许进入统一分页与派生阶段。
2. `generate_prompts` -> `render_images`
   - 先写 `prompts/`，人工审核后，再带 `--approved-prompt-titles` 生图。

## Mode Policy

- `prod`
  - 默认渲染 `wechat`、`xiaohongshu`、`douyin` 三套图片。
  - 默认生成三平台视频时间轴与口播脚本。
- `test`
  - 默认只渲染 `wechat`。
  - 默认只继续 `wechat` 视频链路。

## Unified Asset Policy

1. 分页只在根目录算一次，结果写入：
   - `outline.md`
   - `meta/content_plan.json`
2. 提示词只保留一套：
   - `prompts/cover_prompt.md`
   - `prompts/series_XX_prompt.md`
3. 平台目录不再独立决定页数，只消费根目录统一结构。

## Image Policy

1. 同一套 prompt 默认派生三份平台图：
   - `images/wechat/`
   - `images/xiaohongshu/`
   - `images/douyin/`
2. 单张图片超过 `4MB` 时，在原目录补一张 `.jpg`。
3. 成本汇总只按真正调用生图模型的张数计算：`meta/image_cost_summary.*`

## Video Policy

1. 视频时间轴按图片节点生成，不再只按文章生成。
2. 默认顺序：
   - `cover_01`
   - `series_01 ... series_N`
3. 每个平台写自己的：
   - `video/<platform>/timeline.json`
   - `video/<platform>/voice_*.md`
   - `video/<platform>/output/`

## Rework Targets

1. `core_note`
2. `outline`
3. `prompts`
4. `images`
5. `video_scripts`
6. `video`

## State File

`meta/state.json` 仍然是唯一状态源，负责记录：

1. 当前模式
2. 各阶段状态
3. 关键产物路径
4. 上游变更后的下游失效
