---
name: aki-wechat-api-imagepost
description: 通过 API 将本地图片目录发布为微信公众号图文草稿（不使用浏览器自动化）。支持官方接口直连发布（stable_token + draft/add）和 wenyan 发布。
---

# Aki WeChat API 图文发布

通过 API 将本地图片目录发布为微信公众号草稿箱，不依赖网页自动化。

当前提供两种发布路径：

1. `wenyan-cli` 路径（兼容旧流程）
2. 微信官方 API 直连路径（推荐）

## 适用场景

- 你已经有一组本地图片，想快速发布成“图文”草稿。
- 你不希望用 Playwright/浏览器自动化。
- 你接受“先发到草稿箱，再到公众号后台手动点发布”的流程。

## 前置要求

1. Python 3.9+（官方 API 直连脚本使用）。
2. 如需 `wenyan` 路径，安装 Node.js（建议 18+）。
2. 可访问微信公众号 API。
3. 配置公众号凭证（推荐第一种）：
   - 环境变量：
     - `WECHAT_APP_ID`
     - `WECHAT_APP_SECRET`
   - `~/.config/wechat/config` 中包含（推荐）：
     - `WECHAT_ID=...`
     - `WECHAT_TOKEN=...`
     - 或：
       - `WECHAT_APP_ID=...`
       - `WECHAT_APP_SECRET=...`
   - `~/.openclaw/workspace/TOOLS.md` 中包含：
     - `export WECHAT_APP_ID=...`
     - `export WECHAT_APP_SECRET=...`

说明：
- `wenyan` 路径依赖 `wenyan-cli`，脚本会在缺失时自动安装 `@wenyan-md/cli`。
- 官方 API 直连脚本不依赖第三方发布服务。

## 脚本

- `scripts/publish-image-post.sh`
- `scripts/publish-official-draft.py`

## 用法

```bash
# 官方 API 直连（推荐）：直接上传图片并新增草稿
python3 ./scripts/publish-official-draft.py \
  --dir "/path/to/images" \
  --title "你的标题"

# 仅生成图文 markdown（不发布）
./scripts/publish-image-post.sh \
  --dir "/path/to/images" \
  --title "你的标题"

# 生成并发布到公众号草稿箱
./scripts/publish-image-post.sh \
  --dir "/path/to/images" \
  --title "你的标题" \
  --publish
```

可选参数：

- `--cover <path>`：指定封面图；默认使用目录内第一张图片。
- `--out <path>`：指定输出 markdown 路径；默认 `<图片目录>/wechat-image-post.md`。
- `--theme <name>`：wenyan 主题，默认 `lapis`。
- `--highlight <name>`：代码高亮主题，默认 `solarized-light`。
- 官方 API 直连额外参数：
  - `--appid <id>` / `--secret <secret>`：覆盖环境变量。
  - `--cover <path>`：指定封面图；默认第一张图。
  - `--author <name>`：作者名。
  - `--digest <text>`：摘要。
  - `--source-url <url>`：原文链接。
  - `--force-refresh-token`：强制刷新 token。

## 输出结果

- Markdown 文件：默认 `wechat-image-post.md`
- 若带 `--publish`：直接调用 API 写入公众号草稿箱。
- 官方 API 直连执行成功后，会返回 `media_id`（草稿 ID）。

## 示例（你的当前目录）

```bash
cd /Users/aki/Development/code/aki-skills/skills/aki-wechat-api-imagepost
python3 ./scripts/publish-official-draft.py \
  --dir "/Users/aki/Downloads/Browsers/自媒体/1. AI个人IP话题/17. 春晚机器人/imgs" \
  --title "春晚机器人：4张图看懂趋势"

# 或继续使用 wenyan 路径
./scripts/publish-image-post.sh \
  --dir "/Users/aki/Downloads/Browsers/自媒体/1. AI个人IP话题/17. 春晚机器人/imgs" \
  --title "春晚机器人：4张图看懂趋势" \
  --publish
```

## 常见失败原因

1. `WECHAT_APP_ID/WECHAT_APP_SECRET` 未配置。
2. 服务器 IP 不在公众号白名单。
3. 图片路径不存在或目录为空。
4. 使用官方 API 时，正文图片需通过 `uploadimg`，单图应为 jpg/png 且 <= 1MB。
5. 网络问题导致上传失败。

## 官方文档（2026-02-17 核对）

- 获取稳定版接口调用凭据：`POST /cgi-bin/stable_token`
- 上传图文消息图片：`POST /cgi-bin/media/uploadimg`
- 上传永久素材：`POST /cgi-bin/material/add_material`
- 新增草稿：`POST /cgi-bin/draft/add`
