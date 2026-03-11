# Coze Workflow -> Skill Blueprint

- Source file: `/Users/aki/Downloads/Browsers/最新觉醒视频.txt`
- Workflow ID: `7587458832180740132`
- Space ID: `7523989714307907603`
- Nodes: `33`
- Edges: `31`

## Node Types
- `1` Start: 1
- `13` Output: 8
- `15` TextProcess: 1
- `2` End: 1
- `21` Loop: 1
- `23` ImageGenerate: 1
- `28` PromptGenerate: 1
- `3` LLM: 3
- `31` Comment: 4
- `32` VariableMerge: 1
- `4` Plugin: 9
- `5` Code: 1
- `8` Selector: 1

## Phase Distribution
- `其他`: 5
- `分镜规划`: 1
- `剪映编排`: 4
- `启动与输入`: 1
- `图片生成`: 4
- `字幕处理`: 1
- `控制与数据处理`: 4
- `文案生成`: 2
- `状态回传`: 8
- `结束与输出`: 1
- `音频处理`: 2

## Ordered Flow (Topological)
| # | NodeID | Type | Title | Phase |
|---|---|---|---|---|
| 1 | 1322889 | Comment | Node-1322889 | 其他 |
| 2 | 119986 | Comment | Node-119986 | 其他 |
| 3 | 100001 | Start | 开始 | 启动与输入 |
| 4 | 193149 | Comment | Node-193149 | 其他 |
| 5 | 1986088 | Comment | Node-1986088 | 其他 |
| 6 | 184968 | Output | 输出 | 状态回传 |
| 7 | 122566 | Selector | 选择器_1 | 控制与数据处理 |
| 8 | 174904 | Output | 输出_1 | 状态回传 |
| 9 | 121637 | LLM | LLM：文案生成 | 文案生成 |
| 10 | 113556 | VariableMerge | 变量聚合 | 控制与数据处理 |
| 11 | 178451 | Output | 输出_2 | 状态回传 |
| 12 | 141237 | LLM | LLM：文案分镜分割师 | 文案生成 |
| 13 | 180549 | ImageGenerate | 背景图 | 图片生成 |
| 14 | 148389 | Output | 输出_3 | 状态回传 |
| 15 | 153755 | Output | 输出_5 | 状态回传 |
| 16 | 120709 | TextProcess | 文本处理 | 控制与数据处理 |
| 17 | 175800 | LLM | LLM：图片提示词生成师 | 图片生成 |
| 18 | 195020 | Loop | 批量生成音频 | 音频处理 |
| 19 | 162624 | Output | 输出_4 | 状态回传 |
| 20 | 194925 | PromptGenerate | 画面内容 | 分镜规划 |
| 21 | 163517 | Output | 输出_6 | 状态回传 |
| 22 | 117044 | Code | 组合结构代码 | 控制与数据处理 |
| 23 | 145928 | Output | 输出_7 | 状态回传 |
| 24 | 163434 | Plugin | 创建草稿 | 剪映编排 |
| 25 | 167928 | Plugin | 添加背景图到剪映草稿 | 图片生成 |
| 26 | 182393 | Plugin | 添加背景大字到剪映草稿 | 剪映编排 |
| 27 | 133604 | Plugin | 批量添加图片到剪映草稿 | 图片生成 |
| 28 | 174790 | Plugin | caption_infos | 字幕处理 |
| 29 | 199678 | Plugin | 添加文案字幕到剪映草稿 | 剪映编排 |
| 30 | 157066 | Plugin | add_effects特效 | 其他 |
| 31 | 187473 | Plugin | 增加背景音乐 | 音频处理 |
| 32 | 120765 | Plugin | 添加文案配音到剪映草稿 | 剪映编排 |
| 33 | 900001 | End | 结束 | 结束与输出 |

## Skill Architecture Proposal (Non-TTS First)
- **输入标准化模块**
  - Purpose: 文章/已有文案/图片目录标准化为统一输入
  - Implementation: 新增 `--coze-mode` 参数，支持从主题或文案直接进入分镜流程
- **文案生成模块**
  - Purpose: 当未提供口播稿时先生成脚本
  - Implementation: 复用已有 article-transformer；输出可直接用于 SRT/配音
- **分镜规划模块**
  - Purpose: 把脚本切分为镜头段并生成每段结构化时间线
  - Implementation: 新增 `scripts/storyboard_from_script.py`（待实现）
- **图片生成与聚合模块**
  - Purpose: 批量生成/收集分镜图片并映射到时间轴
  - Implementation: 新增 `scripts/collect_image_assets.py`（待实现）
- **剪映草稿编排模块**
  - Purpose: 创建新草稿并写入图片轨、字幕轨、转场与特效
  - Implementation: 复用 `build_video_from_article_assets.py` + `jianying-editor`
- **可选音频模块**
  - Purpose: 配音与背景音乐按开关启用
  - Implementation: 当前默认 `--skip-audio`，等待 MiniMax API 后接入
- **质检与索引模块**
  - Purpose: 检查丢失媒体、轨道完整性，并将草稿置顶
  - Implementation: 保留 `root_meta_info.json` 注入逻辑

## Immediate Action Items
- Keep current pipeline in non-TTS mode by default (`--skip-audio`).
- Add storyboard splitter from script to structured timeline.
- Add image collector to map generated images to timeline nodes.
- Keep JianYing JSON patch and root index update as stable sink layer.
