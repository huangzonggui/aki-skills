---
name: aki-wechat-api-imagepost
description: 通过官方 API 发布微信公众号草稿（不依赖浏览器自动化）。支持多模式：图文（图片目录）与文章（Markdown/HTML）。
---

# Aki WeChat API Publisher

通过官方接口发布公众号草稿，不走网页自动化。

## 支持模式

1. `imagepost`：本地图片目录 -> 图文草稿
2. `article`：Markdown/HTML -> 文章草稿
3. 兼容模式：`publish-image-post.sh` + wenyan

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

## 典型用法

### 1) 图文模式

```bash
python3 ./scripts/publish-official-draft.py \
  --mode imagepost \
  --dir "/path/to/images" \
  --title "标题"
```

### 2) 文章模式（Markdown）

```bash
python3 ./scripts/publish-official-draft.py \
  --mode article \
  --markdown "/path/to/article.md"
```

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

## 输出

执行成功会返回草稿 `media_id`，用于在公众号后台草稿箱定位。

## 参考

- `README.md`（完整使用说明）
- 稳定 token：`/cgi-bin/stable_token`
- 上传正文图：`/cgi-bin/media/uploadimg`
- 上传封面：`/cgi-bin/material/add_material`
- 新增草稿：`/cgi-bin/draft/add`
