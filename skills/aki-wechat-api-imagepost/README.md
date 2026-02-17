# aki-wechat-api-imagepost

通过微信官方 API 发布公众号草稿，不依赖浏览器自动化。支持多模式：

- `imagepost`：图片目录 -> 图文草稿
- `article`：Markdown/HTML -> 文章草稿
- `wenyan` 兼容模式（保留）

## 1. 能力概览

| 能力 | 说明 | 脚本 |
| --- | --- | --- |
| 图文发布 | 从本地图片目录发布 | `publish-official-draft.py --mode imagepost` |
| 文章发布（Markdown） | 自动解析标题、上传本地图片并替换 URL | `publish-official-draft.py --mode article --markdown` |
| 文章发布（HTML） | 自动上传 HTML 内本地图片并替换 URL | `publish-official-draft.py --mode article --html` |
| 文章发布（直传 HTML） | 直接传入 HTML 字符串 | `publish-official-draft.py --mode article --content-html` |
| 兼容发布 | 生成 markdown 并用 wenyan 发布 | `publish-image-post.sh` |

## 2. 官方 API 流程

脚本使用以下官方接口：

1. `POST /cgi-bin/stable_token`
2. `POST /cgi-bin/material/add_material?type=image`（封面 -> `thumb_media_id`）
3. `POST /cgi-bin/media/uploadimg`（正文图片 -> URL）
4. `POST /cgi-bin/draft/add`（新增草稿）

## 3. 环境要求

- Python 3.9+
- 公众号开通开发者能力
- 调用机公网 IP 已加入公众号 API 白名单

可选：
- Node.js（仅 `publish-image-post.sh` 需要）

## 4. 凭证配置（推荐独立目录）

```bash
mkdir -p ~/.config/wechat
cat > ~/.config/wechat/config <<'CFG'
WECHAT_ID=你的AppID
WECHAT_TOKEN=你的AppSecret
CFG
chmod 600 ~/.config/wechat/config
```

支持键名映射：

- AppID：`WECHAT_APP_ID` / `WECHAT_ID` / `APPID` / `APP_ID`
- AppSecret：`WECHAT_APP_SECRET` / `WECHAT_TOKEN` / `APPSECRET` / `APP_SECRET`

也支持环境变量：

```bash
export WECHAT_APP_ID=你的AppID
export WECHAT_APP_SECRET=你的AppSecret
```

## 5. 快速开始

### 5.1 图文模式（图片目录）

```bash
python3 ./scripts/publish-official-draft.py \
  --mode imagepost \
  --dir "/path/to/images" \
  --title "你的标题"
```

### 5.2 文章模式（Markdown）

```bash
python3 ./scripts/publish-official-draft.py \
  --mode article \
  --markdown "/path/to/article.md"
```

说明：
- 若不传 `--title`，会尝试从 Markdown 的第一个 `# 标题` 提取。
- Markdown 里的本地图片会自动上传并替换为微信 URL。
- 若无本地图片，请手动传 `--cover /path/to/cover.jpg`。

### 5.3 文章模式（HTML 文件）

```bash
python3 ./scripts/publish-official-draft.py \
  --mode article \
  --html "/path/to/article.html"
```

说明：
- 会自动扫描 `<img src="...">` 中的本地路径并上传替换。
- 若未传 `--title`，会尝试从 `<h1>` 或 `<title>` 提取。

### 5.4 文章模式（直传 HTML）

```bash
python3 ./scripts/publish-official-draft.py \
  --mode article \
  --content-html "<h1>标题</h1><p>正文</p>" \
  --title "标题" \
  --cover "/path/to/cover.jpg"
```

### 5.5 常用增强参数

```bash
python3 ./scripts/publish-official-draft.py \
  --mode article \
  --markdown "/path/to/article.md" \
  --author "Aki" \
  --digest "摘要（<=120字）" \
  --source-url "https://example.com" \
  --force-refresh-token
```

## 6. 参数说明（publish-official-draft.py）

| 参数 | 说明 |
| --- | --- |
| `--mode imagepost|article` | 发布模式（默认 `imagepost`） |
| `--dir` | 图片目录（`imagepost` 必填） |
| `--markdown` | Markdown 文件（`article` 三选一） |
| `--html` | HTML 文件（`article` 三选一） |
| `--content-html` | HTML 内容字符串（`article` 三选一） |
| `--title` | 标题（<=64） |
| `--cover` | 封面图路径（未自动推断时必填） |
| `--author` | 作者 |
| `--digest` | 摘要（<=120） |
| `--source-url` | 原文链接 |
| `--appid` / `--secret` | 临时覆盖配置中的凭证 |
| `--force-refresh-token` | 强制刷新 token |

## 7. 封面规则

- `imagepost`：默认用目录第一张图片作为封面。
- `article`：默认尝试使用正文中第一张本地图片作为封面。
- 若无法自动推断，必须传 `--cover`。

## 8. 返回结果

成功时返回：

```json
{
  "media_id": "...",
  "item": [{ "index": 0, "ad_count": 0 }]
}
```

其中 `media_id` 即草稿 ID，可在公众号后台草稿箱查看。

## 9. 常见问题

### 9.1 `errcode=40164 invalid ip not in whitelist`
调用机 IP 不在白名单。到微信开发者平台添加该公网 IP 后重试。

### 9.2 `invalid appid / invalid appsecret`
检查 `~/.config/wechat/config`。注意 `WECHAT_TOKEN` 在这里是 AppSecret（不是公众号消息推送 token）。

### 9.3 图片上传失败
- 正文图建议 jpg/png 且 < 1MB（`uploadimg` 接口约束）
- 检查文件路径和文件权限
- 检查网络连通性

### 9.4 草稿成功但后台没看到
确认登录的是同一公众号账号，在“草稿箱”中查看。

## 10. 安全建议

- `~/.config/wechat/config` 权限设为 `600`
- 不要把凭证提交到仓库
- 定期轮换 AppSecret

## 11. 官方文档

- 稳定版 Token: https://developers.weixin.qq.com/doc/service/api/base/api_getstableaccesstoken.html
- 上传图文消息图片: https://developers.weixin.qq.com/doc/service/api/material/permanent/api_uploadimage.html
- 上传永久素材: https://developers.weixin.qq.com/doc/service/api/material/permanent/api_addmaterial.html
- 新增草稿: https://developers.weixin.qq.com/doc/service/api/draftbox/draftmanage/api_draft_add
