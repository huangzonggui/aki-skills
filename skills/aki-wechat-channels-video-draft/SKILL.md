---
name: aki-wechat-channels-video-draft
description: 使用浏览器自动化将本地视频上传到微信视频号网页版创作者中心，并仅执行“保存草稿”而不发布。适用于用户明确要求“视频号网页版上传”“浏览器发视频号”“保存草稿不点击发送”“先存草稿再人工检查”的场景。
---

# WeChat Channels Video Draft

通过 `Playwright + Chrome` 自动打开视频号网页版，上传本地视频，填写标题/描述，并点击“保存草稿”。  
默认安全策略是草稿模式，不会点击任何“发布”按钮。

## Quick Start

1. 安装依赖（首次）：

```bash
cd /Users/aki/Development/code/aki-skills/skills/aki-wechat-channels-video-draft/scripts
bun install
```

2. 执行上传并保存草稿：

```bash
bun /Users/aki/Development/code/aki-skills/skills/aki-wechat-channels-video-draft/scripts/wechat-channels-draft.ts \
  --video /absolute/path/to/video.mp4 \
  --title "可选标题" \
  --description "可选描述"
```

## Parameters

- `--video <path>` 必填，本地视频绝对路径。
- `--cover <path>` 可选，封面图路径；不传时默认自动从视频同目录推断（优先同名、`-封面`、`_封面`）。
- `--title <text>` 可选，作品标题；未提供时默认取视频文件名。
- `--description <text>` 可选，作品描述；未提供时默认与标题一致。
- `--topics <list>` 可选，话题列表（逗号分隔），会自动拼接为 `#话题` 到描述末尾。
- `--profile-dir <path>` 可选，浏览器登录态目录。  
  默认：`~/Library/Application Support/aki-skills/publisher-profiles/zimeiti-publisher`
- `--profile-name <name>` 可选，发布账号 profile 名称（推荐）。  
  默认固定：`--profile-name zimeiti-publisher`（通常可不传）
- `--headless` 可选，无界面运行（不建议首次登录时使用）。
- `--close-after-save` 可选，保存草稿后关闭浏览器（默认不关闭，便于人工审核）。
- `--no-declare-original` 可选，不自动勾选“声明原创”（默认自动勾选并处理确认弹窗）。
- `--no-html-snapshot` 可选，不记录页面 HTML 快照（默认记录）。
- `--html-snapshot-dir <path>` 可选，HTML 快照目录（默认在 skill 的 `references/publish_html_snapshots/`）。
- `--login-timeout-sec <sec>` 可选，扫码登录等待时长，默认 `180` 秒。
- `--upload-timeout-sec <sec>` 可选，等待上传/转码完成时长，默认 `900` 秒。
- `--action-timeout-sec <sec>` 可选，普通交互超时，默认 `30` 秒。
- `--output-dir <path>` 可选，截图输出目录。
- `--keep-open` 显式保持打开（默认已开启，通常可不传）。

## Execution Flow

1. 打开 `https://channels.weixin.qq.com/platform/post/create`
2. 若检测到登录页，等待扫码登录
3. 定位视频上传控件并上传 `--video`
4. 自动尝试上传封面（`--cover` 或同目录自动推断）
5. 尝试填写标题、描述、话题并处理“声明原创”
6. 等待“保存草稿”按钮可点击（上传/转码完成）
7. 点击“保存草稿”
8. 输出 JSON 结果与过程截图；同时把页面 HTML 以时间戳快照记录到 `references` 目录，供后续适配网页变更时对照

## Safety Rules

- 仅允许草稿模式，不允许自动点击“发布”。
- 未经用户在当前会话明确确认，不做任何发布动作。
- 若页面结构变更导致按钮定位不稳定，停止并返回错误截图，不做“猜测性点击”。

## Profile Strategy

- 建议为每个账号固定一个 `profile-name`，长期复用，不要频繁切换临时 profile。
- 公众号与视频号默认共用 `zimeiti-publisher`，保持同一发布环境与指纹。

## Script

- `scripts/wechat-channels-draft.ts`：主执行脚本（上传 + 保存草稿）。
- `references/publish_html_snapshots/`：自动记录的发表页 HTML 快照（文件名含时间戳）。
- `references/troubleshooting.md`：故障排查与常见问题。

## Troubleshooting

详见 [references/troubleshooting.md](references/troubleshooting.md)。
