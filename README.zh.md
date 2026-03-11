# aki-skills

[English](./README.md) | 中文

Aki 的本地技能集合，聚焦内容生产流程、发布自动化和多媒体处理。

## 前置依赖

- Bun（用于 TypeScript 脚本，命令形态：`npx -y bun ...`）
- Python 3（用于 Python 脚本）
- Google Chrome（用于浏览器自动化类技能）

## 目录结构

每个技能位于 `skills/<skill-name>/`，通常包含：

- `SKILL.md`：技能定义与使用说明
- `scripts/`：可执行脚本（TypeScript/Python/Shell）
- `references/` 或 `prompts/`：模板与参考文档

## 常用命令示例

```bash
# 抓取公众号文章
npx -y bun skills/aki-wechat-fetcher/scripts/fetch.ts --url "<wechat-article-url>"

# 发布 Markdown 到公众号草稿
npx -y bun skills/aki-post-to-wechat/scripts/wechat-browser.ts --markdown article.md --images ./images
```

## 核心技能

- `aki-content-pipeline-pro`：内容流水线（多源输入 -> 核心笔记 -> 多平台产出）
- `aki-context-to-html`：文本/文章转样式化 HTML 与长图素材
- `aki-post-to-wechat`：浏览器优先的公众号发布
- `aki-wechat-api-imagepost`：公众号 API 备用发布通道
- `aki-wechat-fetcher`：公众号文章抓取
- `aki-image-article-video`：图文到剪映草稿流水线
- `aki-gemini-playwright-mcp`：基于 Playwright MCP 的 Gemini 网页生图
- `aki-gemini-web-curl`：基于 Chrome 登录态 Cookie + curl 的 Gemini 网页生图，带 raw 留档、比例重试与下载校验
- `aki-trendradar`：舆情监控与分析

## 插件元数据

插件元数据位于 [.claude-plugin/marketplace.json](./.claude-plugin/marketplace.json)。

## 说明

- Marketplace 元数据定义在 `.claude-plugin/marketplace.json`。
