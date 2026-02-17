# aki-wechat-api-imagepost

通过微信官方 API 将本地图片目录发布为公众号草稿，不依赖网页自动化。

- 官方直连模式（推荐）：`stable_token + media/uploadimg + material/add_material + draft/add`
- 兼容模式：`wenyan-cli` 发布

## 1. 功能特性

- 支持本地图片目录一键生成图文草稿
- 支持自动选取封面，或手动指定封面
- 支持作者、摘要、原文链接参数
- 使用官方接口，稳定且可审计
- 返回草稿 `media_id`，便于后续管理

## 2. 目录结构

```text
aki-wechat-api-imagepost/
├── SKILL.md
├── README.md
└── scripts/
    ├── publish-official-draft.py
    └── publish-image-post.sh
```

## 3. 环境要求

- Python 3.9+
- 公众号已开通开发者能力
- 调用机公网 IP 已加入公众号 API 白名单

可选：
- Node.js（仅当使用 `publish-image-post.sh` + `wenyan-cli` 模式时需要）

## 4. 凭证配置（推荐独立目录）

在 `~/.config/wechat/config` 新建配置文件：

```bash
mkdir -p ~/.config/wechat
cat > ~/.config/wechat/config <<'CFG'
WECHAT_ID=你的AppID
WECHAT_TOKEN=你的AppSecret
CFG
chmod 600 ~/.config/wechat/config
```

兼容键名：

- AppID: `WECHAT_APP_ID` / `WECHAT_ID` / `APPID`
- AppSecret: `WECHAT_APP_SECRET` / `WECHAT_TOKEN` / `APPSECRET`

也可直接通过环境变量传入：

```bash
export WECHAT_APP_ID=你的AppID
export WECHAT_APP_SECRET=你的AppSecret
```

## 5. 快速开始

### 5.1 官方 API 直连（推荐）

```bash
python3 ./scripts/publish-official-draft.py \
  --dir "/path/to/images" \
  --title "你的标题"
```

常用可选参数：

```bash
python3 ./scripts/publish-official-draft.py \
  --dir "/path/to/images" \
  --title "你的标题" \
  --cover "/path/to/cover.jpg" \
  --author "作者名" \
  --digest "摘要（120字以内）" \
  --source-url "https://example.com"
```

成功返回示例：

```json
{
  "media_id": "xxxxxx",
  "item": [
    { "index": 0, "ad_count": 0 }
  ]
}
```

### 5.2 wenyan 兼容模式

```bash
./scripts/publish-image-post.sh \
  --dir "/path/to/images" \
  --title "你的标题" \
  --publish
```

## 6. 参数说明（官方 API 脚本）

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--dir` | 是 | 图片目录 |
| `--title` | 是 | 标题（<=64 字） |
| `--cover` | 否 | 封面图路径，默认第一张 |
| `--author` | 否 | 作者 |
| `--digest` | 否 | 摘要（<=120 字） |
| `--source-url` | 否 | 原文链接 |
| `--appid` | 否 | 覆盖配置中的 AppID |
| `--secret` | 否 | 覆盖配置中的 AppSecret |
| `--force-refresh-token` | 否 | 强制刷新 stable token |

## 7. 官方 API 调用链路

1. `POST /cgi-bin/stable_token`
2. `POST /cgi-bin/material/add_material?type=image`（上传封面，拿 `thumb_media_id`）
3. `POST /cgi-bin/media/uploadimg`（上传正文图片，拿可用 URL）
4. `POST /cgi-bin/draft/add`（写入草稿箱）

## 8. 常见问题

### Q1: `errcode=40164 invalid ip not in whitelist`
调用机 IP 不在白名单。到微信开发者平台添加当前公网 IP 后重试。

### Q2: `invalid appid / invalid appsecret`
检查 `~/.config/wechat/config` 内容是否正确，注意不要把 token 和 appsecret 混淆。

### Q3: 图片上传失败
- 正文图建议使用 jpg/png 且小于 1MB
- 检查文件是否可读、路径是否正确
- 检查网络连通性

### Q4: 草稿创建成功但后台没看到
确认登录的是同一个公众号账号；草稿在公众号后台草稿箱中查看。

## 9. 安全建议

- 不要把 `~/.config/wechat/config` 提交到 Git
- 设置权限为 `600`
- 定期轮换 AppSecret

## 10. 参考文档

- 获取稳定版 Token: https://developers.weixin.qq.com/doc/service/api/base/api_getstableaccesstoken.html
- 上传图文消息图片: https://developers.weixin.qq.com/doc/service/api/material/permanent/api_uploadimage.html
- 上传永久素材: https://developers.weixin.qq.com/doc/service/api/material/permanent/api_addmaterial.html
- 新增草稿: https://developers.weixin.qq.com/doc/service/api/draftbox/draftmanage/api_draft_add
