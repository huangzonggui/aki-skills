---
name: aki-post-to-wechat
description: 微信公众号发布 API 备用通道。用于用户明确要求 API 发布，或浏览器自动化不可用时，通过官方 API 发布草稿（图文/文章）。
---

# Aki WeChat API Publisher

通过官方接口发布公众号草稿，不走网页自动化。该 skill 作为浏览器优先策略下的备用路径。

默认策略：
- 优先使用浏览器版 `aki-post-to-wechat-browser`。
- 仅当用户明确要求 API，或浏览器链路不可用时，使用本 skill。

文档基准入口（公众号 / 订阅号 API）：
- https://developers.weixin.qq.com/doc/subscription/api/

## 支持模式

1. `imagepost`：本地图片目录 -> 图文草稿
2. `article`：Markdown/HTML -> 文章草稿
3. 兼容模式：`publish-image-post.sh` + wenyan

默认类型：
- `imagepost` => `article_type=newspic`
- `article` => `article_type=news`

## 模式锁定规则（防混淆）

- 用户明确说“贴图 / 图文 / 多图 / 发图片”：
  - 固定走 `imagepost`（默认 `article_type=newspic`）。
  - 不得擅自切换到 `article`。
- 用户明确说“文章 / 长文 / Markdown文章发布”：
  - 才走 `article`。
- 如果为了解决排版问题考虑切模式：
  - 必须先征得用户明确确认，再切换。

评论控制：
- `--open-comment` => `need_open_comment=1`
- `--fans-only-comment` => `only_fans_can_comment=1`（自动开启评论）

“只开留言”（推荐口径）：
- 使用 `--open-comment`
- 不加 `--fans-only-comment`
- 目标字段应为：`need_open_comment=1`、`only_fans_can_comment=0`

## 前置要求

1. Python 3.9+
2. 调用机 IP 在公众号 API 白名单中
3. 凭证已配置（推荐独立目录）

推荐配置文件：`~/.config/wechat/config`

```bash
WECHAT_ID=你的AppID
WECHAT_TOKEN=你的AppSecret
```

兼容键名：
- AppID: `WECHAT_APP_ID` / `WECHAT_ID` / `APPID`
- AppSecret: `WECHAT_APP_SECRET` / `WECHAT_TOKEN` / `APPSECRET`

## 脚本

- `scripts/publish-official-draft.py`：官方 API 直连发布（推荐）
- `scripts/publish-image-post.sh`：wenyan 兼容路径
- `scripts/cache-subscription-docs.py`：缓存订阅号 API 文档到本地

## 文档缓存（建议先用本地）

先缓存文档（避免重复在线抓取）：  
```bash
python3 ./scripts/cache-subscription-docs.py
```

缓存目录：
- `references/subscription-api/cache/`
- 索引：`references/subscription-api/cache/manifest.json`

发布链路参考：
- `references/subscription-api/publish-api-map.md`

## 典型用法

### 1) 图文模式

```bash
python3 ./scripts/publish-official-draft.py \
  --mode imagepost \
  --dir "/path/to/images" \
  --title "标题" \
  --open-comment

# 可覆盖类型
python3 ./scripts/publish-official-draft.py \
  --mode imagepost \
  --article-type news \
  --dir "/path/to/images" \
  --title "标题"
```

### 1.1 图文模式：只开留言（可直接复用）

```bash
python3 ./scripts/publish-official-draft.py \
  --mode imagepost \
  --article-type newspic \
  --dir "/path/to/images" \
  --title "标题" \
  --text "正文" \
  --open-comment \
  --force-refresh-token
```

### 2) 文章模式（Markdown）

```bash
python3 ./scripts/publish-official-draft.py \
  --mode article \
  --markdown "/path/to/article.md"
```

说明：`--markdown` 默认走 `context-to-html` 样式渲染（`--markdown-renderer context`）。  
如需回退基础渲染可显式传：`--markdown-renderer basic`。

### 3) 文章模式（HTML）

```bash
python3 ./scripts/publish-official-draft.py \
  --mode article \
  --html "/path/to/article.html"
```

### 4) 文章模式（直接 HTML）

```bash
python3 ./scripts/publish-official-draft.py \
  --mode article \
  --content-html "<h1>标题</h1><p>正文</p>" \
  --title "标题" \
  --cover "/path/to/cover.jpg"
```

## 自动处理规则

- Markdown/HTML 中的本地图片会自动上传并替换为微信 URL
- `article` 模式会自动尝试提取标题与摘要
- 封面优先级：`--cover` > 正文第一张本地图 >（无则报错）
- `newspic` 会按文档写入 `image_info.image_list[].image_media_id`

## 输出

执行成功会返回草稿 `media_id`，用于在公众号后台草稿箱定位。

## 故障经验沉淀（复用）

- `errcode=40164 invalid ip not in whitelist` 不一定是脚本逻辑问题。实战中常见为：
  1. 白名单刚更新，微信侧尚未生效（通常需要 1-5 分钟）。
  2. token 请求命中旧校验状态。
  3. 请求实际走了代理出口 IP。
- 复用重试策略：
  - 加 `--force-refresh-token` 强制刷新 token。
  - 必要时临时禁用代理变量后重试（`HTTP(S)_PROXY` / `ALL_PROXY`，并设 `NO_PROXY='*'`）。

## 参考

- `README.md`（完整使用说明）
- 稳定 token：`/cgi-bin/stable_token`
- 上传正文图：`/cgi-bin/media/uploadimg`
- 上传封面：`/cgi-bin/material/add_material`
- 新增草稿：`/cgi-bin/draft/add`
