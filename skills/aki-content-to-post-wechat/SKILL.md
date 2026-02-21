---
name: aki-content-to-post-wechat
description: 一站式内容创作流水线。从微信/网页链接生成口播文案、价值笔记、手绘封面图，并发布到微信公众号。触发词：链接转图文、链接转公众号、发布到微信公众号、公众号发布、文章转图文、图文发布、把链接变成图文、链接生成内容发布、内容创作流水线。
---

# Aki Content to WeChat (内容创作流水线)

## 核心规则

**每次调用必须创建话题文件夹，用于长期保存和复盘。**

```
./content/<话题名称>/
├── meta.json              # 元数据（作者/链接等）
├── source/article.md      # 原始文章
├── output/
│   ├── cover.png          # 手绘封面图
│   ├── script.md          # 口播文案 (15-30秒)
│   ├── note.md            # 价值笔记
│   └── wechat-copy.md     # 图文文案 (300字)
└── README.md              # 话题说明
```

## 流程

1. **自动生成话题名称** - 根据文章内容/URL自动提取，如"AI工具推荐"
2. **创建话题文件夹**
3. **下载文章** → source/article.md
4. **提取元数据** → meta.json（禁止出现在封面/文案中）
5. **生成封面** → output/cover.png
6. **生成文案** → output/script.md, note.md, wechat-copy.md
7. **发布到微信** - 两种方式可选：
   - `aki-wechat-api-imagepost` - 官方 API 发布（推荐，无需浏览器）
   - `aki-post-to-wechat` - 浏览器自动化发布

## 触发方式

- "把这个链接转成图文并发布到微信公众号"
- "链接转图文"
- "内容创作流水线"
