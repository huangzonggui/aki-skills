---
name: aki-trendradar
description: AI-powered public opinion monitoring and trend analysis. Monitor keywords across multiple news platforms (Zhihu, Weibo, Douyin, Baidu, etc.), generate AI-powered insights, and push notifications to Feishu/WeChat/Email. Supports manual trigger by keyword and scheduled daily monitoring.
---

# aki-trendradar: AI 舆情监控与分析

基于 TrendRadar 的轻量级舆情分析工具，通过关键词监控全网热点，生成 AI 驱动的洞察报告。

## Quick Start

```bash
# 分析单个关键词
npx -y bun scripts/analyze.ts "DeepSeek"

# 分析并推送到飞书
npx -y bun scripts/analyze.ts "AI" --push feishu

# 使用深度分析模式
npx -y bun scripts/analyze.ts "比亚迪" --mode deep

# 查看历史数据
npx -y bun scripts/analyze.ts "比特币" --history 7
```

## Core Features

### 🎯 Manual Trigger (Keyword Analysis)
Simply speak a keyword, and the skill will:
1. Fetch latest news from multiple platforms
2. Filter by your keyword
3. Generate AI-powered insights
4. Deliver report to your preferred channel

### 📊 Report Modes

| Mode | Output | Use Case |
|------|-------|----------|
| **simple** (default) | Hot news summary + trend | Quick overview |
| **deep** | Sentiment analysis + trend prediction | In-depth research |

### 📢 Push Channels

| Channel | Status | Notes |
|---------|--------|-------|
| Feishu | ✅ MVP | Webhook push |
| WeChat | 🔜 Phase 2 | Enterprise WeChat app |
| Email | 🔜 Phase 2 | SMTP push |

### 🔍 Supported Platforms

- 知乎
- 微博
- 抖音
- 百度热搜
- 今日头条
- Bilibili
- 财联社
- 澎湃新闻
- 凤凰网
- 贴吧

## Configuration

### Keywords

Default AI-related keywords (config/keywords.txt):
```
AI
DeepSeek
ChatGPT
Claude
GPT
豆包
月之暗面
Kimi
智谱
```

### Environment Variables

```bash
# 飞书 Webhook (必需)
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"

# AI 分析 (可选，使用已配置的 Comfly/GLM/OpenAI 兼容模型)
# 自动复用本地 provider 配置
```

## Usage Examples

### Example 1: Quick Analysis
```
You: "分析一下 DeepSeek"
Skill: [Fetches news, generates simple report]
```

### Example 2: Deep Analysis with Push
```
You: "深度分析 AI 领域今天的热点，推送到飞书"
Skill: [Fetches news, generates deep report, pushes to Feishu]
```

### Example 3: Multi-keyword Comparison
```
You: "对比一下 DeepSeek 和 ChatGPT 的热度"
Skill: [Fetches both, generates comparison]
```

## Report Format

### Simple Report
```
📊 [关键词] 舆情简报
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔥 今日热度: 🔥 高 | 📈 趋势: 🔺上升

📰 相关热点 (今日共 X 条)
1. [新闻标题] - 平台 - 排名
...

💬 情感倾向: 正面 X% | 负面 Y% | 中性 Z%

📊 一句话总结: [AI 生成简短总结]
```

### Deep Report
```
📊 [关键词] 深度舆情分析
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 📈 热度走势分析
- 3日趋势分析
- 峰值时段
- 主要平台分布

## 🔥 核心热点解读
1. [热点1] - 详细解读
2. [热点2] - 详细解读

## 💬 舆论风向分析
- 正面情绪驱动因素
- 焦虑点和争议
- 负面情绪来源

## 📊 跨平台对比
- 各平台热度
- 话题侧重差异

## 🎯 趋势研判
- 短期预测
- 中期展望
- 风险提示
```

## Technical Details

### Data Source

Uses TrendRadar's HTTP API to fetch:
- Latest trending news from multiple platforms
- Keyword-filtered results
- Historical data (for trend analysis)

### AI Analysis

Powered by configured LLM backend:
- Uses Comfly/GLM/OpenAI-compatible chat-completions endpoint
- Generates insights based on aggregated news data
- Supports both simple and deep analysis modes

### Push Integration

- **Feishu**: Webhook integration with rich text formatting
- **WeChat**: Enterprise WeChat app (Phase 2)
- **Email**: SMTP push (Phase 2)

## Future Enhancements

- [ ] Scheduled daily monitoring
- [ ] WeChat & Email push
- [ ] Multi-keyword batch analysis
- [ ] Historical trend comparison
- [ ] Custom report templates
- [ ] Alert/Threshold notifications

## Requirements

- Node.js (via bun)
- Configured LLM API key (for AI analysis)
- Feishu Webhook URL
- Internet connection (for fetching news)

## Troubleshooting

**Q: No news found for keyword?**
- Try broader keywords
- Check platform connectivity
- Verify keyword spelling

**Q: Feishu push failed?**
- Verify webhook URL is correct
- Check webhook still active
- Ensure message format is valid

**Q: AI analysis timeout?**
- Check local LLM provider configuration
- Try simple mode instead of deep mode
- Verify internet connection
