#!/usr/bin/env bun
import { $ } from 'bun';
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
const HOME_DIR = process.env.HOME || process.env.USERPROFILE || '';
const COMFLY_CONFIG_PATH = path.join(
  HOME_DIR,
  '.config',
  'comfly',
  'config',
);
const COMFLY_CONFIG_LEGACY_PATHS = [
  path.join(HOME_DIR, '.config', 'providers', 'comfly.env'),
  path.join(HOME_DIR, '.config', 'aki', 'providers', 'comfly.env'),
];

// 加载项目本地配置（.env.local）
const envLocalPath = path.join(process.cwd(), '.env.local');
if (existsSync(envLocalPath)) {
  const envContent = readFileSync(envLocalPath, 'utf-8');
  envContent.split('\n').forEach(line => {
    const trimmed = line.trim();
    if (trimmed && !trimmed.startsWith('#') && trimmed.includes('=')) {
      const [key, ...valueParts] = trimmed.split('=');
      const value = valueParts.join('=').trim();
      if (key && value && !process.env[key]) {
        process.env[key] = value;
      }
    }
  });
}

interface AnalysisOptions {
  push?: string;           // feishu, email, wechat
  mode?: 'simple' | 'deep';
  history?: number;        // 历史天数
  compare?: string[];      // 对比关键词
  output?: string;         // 输出文件路径
}

interface NewsItem {
  title: string;
  platform: string;
  rank: number;
  url: string;
  time: string;
  hotness: number;
}

interface TrendRadarResponse {
  success: boolean;
  data?: {
    news?: NewsItem[];
    summary?: string;
    platform?: string;
  };
  error?: string;
}

// 默认配置
const CONFIG = {
  trendradar: {
    baseUrl: process.env.TRENDRADAR_API_URL || 'http://localhost:3333',
  },
};

function parseEnvLikeFile(filePath: string): Record<string, string> {
  const out: Record<string, string> = {};
  if (!filePath || !existsSync(filePath)) return out;
  const content = readFileSync(filePath, 'utf-8');
  for (const rawLine of content.split('\n')) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const eqIdx = line.indexOf('=');
    if (eqIdx <= 0) continue;
    const key = line.slice(0, eqIdx).trim();
    const value = line.slice(eqIdx + 1).trim().replace(/^['"]|['"]$/g, '');
    if (key && !(key in out)) out[key] = value;
  }
  return out;
}

function loadComflyConfig(): Record<string, string> {
  let merged: Record<string, string> = {};
  for (const p of COMFLY_CONFIG_LEGACY_PATHS) {
    merged = { ...merged, ...parseEnvLikeFile(p) };
  }
  merged = { ...merged, ...parseEnvLikeFile(COMFLY_CONFIG_PATH) };
  return merged;
}

// GLM API 配置（与 aki-context-to-html 共用配置）
function getGLMConfig(): { apiUrl: string; apiKey: string; model: string } {
  const provider = loadComflyConfig();
  let apiKey = provider.COMFLY_API_KEY || provider.API_KEY || '';
  let apiUrl = provider.COMFLY_API_URL || provider.API_URL || '';
  let model = provider.COMFLY_CHAT_MODEL || provider.COMFLY_MODEL || provider.MODEL || '';

  // Fallback to environment variables
  if (!apiKey) {
    apiKey = process.env.COMFLY_API_KEY
      || process.env.CLOUD_CODE_API_KEY
      || process.env.GLM_API_KEY
      || process.env.OPENAI_API_KEY
      || process.env.API_KEY
      || '';
  }

  if (!apiUrl) {
    apiUrl = process.env.COMFLY_API_URL
      || process.env.CLOUD_CODE_API_URL
      || process.env.GLM_API_URL
      || process.env.OPENAI_API_URL
      || 'https://open.bigmodel.cn/api/paas/v4/chat/completions';
  }

  if (!model) {
    model = process.env.COMFLY_CHAT_MODEL
      || process.env.COMFLY_MODEL
      || process.env.CLOUD_CODE_MODEL
      || process.env.GLM_MODEL
      || process.env.MODEL
      || 'glm-4-flash';
  }

  return { apiUrl, apiKey, model };
}

// 调用 GLM/OpenAI 兼容 API
async function callLLM(prompt: string): Promise<string> {
  const config = getGLMConfig();

  if (!config.apiKey) {
    throw new Error(`API Key not found! Please configure ${COMFLY_CONFIG_PATH} or set COMFLY_API_KEY environment variable.`);
  }

  const response = await fetch(config.apiUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${config.apiKey}`,
    },
    body: JSON.stringify({
      model: config.model,
      messages: [
        {
          role: 'user',
          content: prompt,
        },
      ],
      temperature: 0.7,
      max_tokens: 4000,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API request failed: ${response.status} ${errorText}`);
  }

  const data = await response.json();
  const result = data.choices?.[0]?.message?.content || data.content || '';

  // Clean up the response
  return result
    .replace(/^```[a-z]*\n?/gm, '')
    .replace(/^```\n?/gm, '')
    .trim();
}

// AI 相关关键词
const AI_KEYWORDS = [
  'AI', 'DeepSeek', 'ChatGPT', 'Claude', 'GPT', '豆包',
  '月之暗面', 'Kimi', '智谱', '通义', '文心一言',
  '特斯拉', '马斯克', '比亚迪', '理想', '蔚来', '小鹏',
  'A股', '港股', '比特币', '以太坊', '区块链',
];

// RSS 数据源（使用 rss2json API 解析）
const RSS2JSON_API = 'https://api.rss2json.com/v1/api.json?rss_url=';

// 各平台对应的 RSS 源（精选可靠的源）
const RSS_SOURCES: Record<string, string> = {
  // 中文科技媒体
  '36kr': 'https://36kr.com/feed',
  'ifanr': 'https://www.ifanr.com/feed',
  'sspai': 'https://sspai.com/feed',
  'geekpark': 'https://www.geekpark.net/rss',

  // 国际科技媒体
  'techcrunch': 'https://techcrunch.com/feed/',
  'wired': 'https://www.wired.com/feed/rss',
  'verge': 'https://www.theverge.com/rss/index.xml',
  'arstechnica': 'https://feeds.arstechnica.com/arstechnica/index',
  'mit-tech': 'https://www.technologyreview.com/feed/',

  // AI/ML 专业媒体
  'venturebeat': 'https://venturebeat.com/ai/feed/',
  'ai-news': 'https://artificialintelligence-news.com/feed/',

  // 商业/财经
  'bloomberg-tech': 'https://feeds.bloomberg.com/technology/news.rss',
  'ft-tech': 'https://www.ft.com/rss/companies/technology',

  // Hacker News (通过 RSS)
  'hackernews': 'https://news.ycombinator.com/rss',
};

function printUsage(): never {
  console.log(`
aki-trendradar: AI 舆情监控与分析

Usage:
  npx -y bun scripts/analyze.ts <keyword> [options]

Arguments:
  keyword              要分析的关键词
  --push <channel>     推送到: feishu (飞书), email (邮件), wechat (微信)
  --mode <type>       分析模式: simple (简单), deep (深度)
  --history <days>     查看历史天数
  --compare <kw>       对比关键词 (多个关键词用空格分隔)
  --output <path>      输出到文件

Examples:
  # 简单分析
  npx -y bun scripts/analyze.ts "DeepSeek"

  # 深度分析并推送到飞书
  npx -y bun scripts/analyze.ts "AI" --push feishu --mode deep

  # 对比分析
  npx -y bun scripts/analyze.ts "DeepSeek" --compare "ChatGPT GPT"

  # 查看历史趋势
  npx -y bun scripts/analyze.ts "特斯拉" --history 7

Environment Variables:
  FEISHU_WEBHOOK_URL    飞书 Webhook 地址
  COMFLY_API_KEY        LLM API Key (可选，支持 Comfly/GLM/OpenAI 兼容接口)
  TRENDRADAR_API_URL    TrendRadar API 地址 (可选)
`);
  process.exit(0);
}

async function fetchNewsFromPlatform(platform: string, keyword: string): Promise<NewsItem[]> {
  const rss_url = RSS_SOURCES[platform];
  if (!rss_url) {
    throw new Error(`Unsupported platform: ${platform}`);
  }

  try {
    // 使用 rss2json API 解析 RSS
    const api_url = `${RSS2JSON_API}${encodeURIComponent(rss_url)}`;
    const response = await fetch(api_url);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();

    // 检查 RSS 状态
    if (data.status !== 'ok') {
      console.error(`[fetchNewsFromPlatform] ${platform} RSS error:`, data.message);
      return [];
    }

    const items = data.items || [];

    // 过滤包含关键词的新闻
    return items
      .filter((item: any) => {
        const title = item.title || '';
        const content = (item.description || '').toLowerCase();
        const searchKey = keyword.toLowerCase();
        return title.toLowerCase().includes(searchKey) || content.includes(searchKey);
      })
      .map((item: any, index: number) => {
        // 计算热度：基于发布时间和顺序
        const pubDate = item.pubDate ? new Date(item.pubDate).getTime() : Date.now();
        const hoursAgo = (Date.now() - pubDate) / (1000 * 60 * 60);
        // 越新的新闻热度越高（24小时内线性衰减）
        const freshnessBonus = Math.max(0, 100 - hoursAgo);
        const baseHotness = 50; // 基础热度
        const hotness = Math.min(100, Math.round(baseHotness + freshnessBonus * 0.5));

        return {
          title: item.title?.trim() || '',
          platform: platform,
          rank: index + 1,
          url: item.link || item.guid || '',
          time: item.pubDate || new Date().toISOString(),
          hotness: hotness,
        } as NewsItem;
      })
      .filter((item) => item.title.length > 0);
  } catch (error) {
    console.error(`[fetchNewsFromPlatform] ${platform} error:`, error);
    return [];
  }
}

async function fetchAllNews(keyword: string): Promise<NewsItem[]> {
  console.error(`[aki-trendradar] Fetching RSS news for: ${keyword}`);
  const platforms = Object.keys(RSS_SOURCES);
  const allNews: NewsItem[] = [];

  for (const platform of platforms) {
    const items = await fetchNewsFromPlatform(platform, keyword);
    allNews.push(...items);
  }

  // 按热度排序
  allNews.sort((a, b) => b.hotness - a.hotness);

  console.error(`[aki-trendradar] Found ${allNews.length} news items`);
  return allNews;
}

async function generateSimpleAnalysis(newsItems: NewsItem[], keyword: string): Promise<string> {
  if (newsItems.length === 0) {
    return `未找到关于"${keyword}"的相关新闻`;
  }

  const totalHotness = newsItems.reduce((sum, item) => sum + item.hotness, 0);
  const avgHotness = totalHotness / newsItems.length;
  const maxHotness = Math.max(...newsItems.map(item => item.hotness));

  // 平台分布
  const platformCount: Record<string, number> = {};
  newsItems.forEach(item => {
    platformCount[item.platform] = (platformCount[item.platform] || 0) + 1;
  });

  // 热度判断
  const hotness = avgHotness > 95 ? '🔥 爆' : avgHotness > 80 ? '🔥 高' : avgHotness > 50 ? '📊 中' : '📉 低';
  const trend = avgHotness > 85 ? '🔺 爆发' : avgHotness > 60 ? '➖ 热门' : avgHotness > 30 ? '→ 持平' : '🔻 降温';

  let report = `📊 [${keyword}] 舆情简报\n`;
  report += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n`;
  report += `🔥 热度: ${hotness}  |  📈 趋势: ${trend}  |  📰 共 ${newsItems.length} 条\n`;
  report += `📊 平均热度: ${avgHotness.toFixed(1)}  |  最高: ${maxHotness}\n\n`;
  report += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n`;

  // 显示所有新闻（前20条）
  const topNews = newsItems.slice(0, Math.min(20, newsItems.length));

  // 分析新闻时间范围
  const timestamps = newsItems
    .map(item => new Date(item.time).getTime())
    .filter(ts => !isNaN(ts));
  const latestTime = timestamps.length > 0 ? new Date(Math.max(...timestamps)) : null;
  const earliestTime = timestamps.length > 0 ? new Date(Math.min(...timestamps)) : null;

  topNews.forEach((item, index) => {
    report += `${index + 1}. ${item.title}\n`;
    report += `   📱 ${item.platform}  |  🔥热度: ${item.hotness}`;

    // 格式化时间显示
    if (item.time && item.time !== new Date().toISOString()) {
      const date = new Date(item.time);
      const now = new Date();
      const hoursAgo = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60));
      if (hoursAgo < 24) {
        report += `  |  ⏰ ${hoursAgo}小时前`;
      } else if (hoursAgo < 48) {
        report += `  |  ⏰ ${Math.floor(hoursAgo / 24)}天前`;
      } else {
        report += `  |  ⏰ ${date.toLocaleDateString('zh-CN')}`;
      }
    }

    if (item.url) {
      report += `\n   🔗 ${item.url}`;
    }
    report += `\n\n`;
  });

  // 添加时间范围说明
  if (latestTime && earliestTime) {
    report += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n`;
    report += `📅 新闻时间范围: ${earliestTime.toLocaleDateString('zh-CN')} ~ ${latestTime.toLocaleDateString('zh-CN')}\n`;
  }

  report += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n`;
  report += `📊 平台分布:\n`;
  Object.entries(platformCount)
    .sort((a, b) => b[1] - a[1])
    .forEach(([platform, count]) => {
      const percent = Math.round((count / newsItems.length) * 100);
      report += `  • ${platform}: ${count}条 (${percent}%)`;
      report += `\n`;
    });

  return report;
}

async function generateDeepAnalysis(newsItems: NewsItem[], keyword: string): Promise<string> {
  if (newsItems.length === 0) {
    return `未找到关于"${keyword}"的相关新闻，无法进行深度分析。`;
  }

  // 准备数据用于 AI 分析
  const newsSummary = newsItems
    .slice(0, 10)
    .map((item, index) => `${index + 1}. [${item.platform}] ${item.title}`)
    .join('\n');

  const platformStats = analyzePlatforms(newsItems);
  const hotnessData = analyzeHotness(newsItems);

  let prompt = `请基于以下舆情数据，对"${keyword}"进行深度舆情分析：

【新闻数据】
${newsSummary}

【平台统计】
${JSON.stringify(platformStats, null, 2)}

【热度数据】
${JSON.stringify(hotnessData, null, 2)}

请按以下格式生成深度分析报告（直接输出分析内容，不要代码块标记）：

📊 [${keyword}] 深度舆情分析

## 📈 热度走势分析
（基于当前数据进行分析）

## 🔥 核心热点解读
（选取2-3个最重要的热点进行深度解读）

## 💬 舆论风向分析

## 📊 平台对比分析

## 🎯 趋势研判

注意：
1. 保持客观中立
2. 基于数据说话
3. 标注分析依据
4. 语言简洁明了`;

  // 调用 LLM 生成深度分析
  try {
    const aiText = await callLLM(prompt);
    return `${aiText}\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📊 数据来源: ${newsItems.length}条新闻 | 分析时间: ${new Date().toLocaleString('zh-CN')}`;
  } catch (error) {
    console.error('[generateDeepAnalysis] AI analysis failed:', error);
    return `AI 分析失败，使用简单模式:\n\n${await generateSimpleAnalysis(newsItems, keyword)}`;
  }
}

function analyzePlatforms(newsItems: NewsItem[]) {
  const stats: Record<string, { count: number; avgRank: number; totalHotness: number }> = {};

  newsItems.forEach(item => {
    if (!stats[item.platform]) {
      stats[item.platform] = { count: 0, avgRank: 0, totalHotness: 0 };
    }
    stats[item.platform].count++;
    stats[item.platform].avgRank += item.rank;
    stats[item.platform].totalHotness += item.hotness;
  });

  Object.keys(stats).forEach(platform => {
    stats[platform].avgRank = stats[platform].avgRank / stats[platform].count;
  });

  return stats;
}

function analyzeHotness(newsItems: NewsItem[]) {
  const hotnessValues = newsItems.map(item => item.hotness);
  const total = hotnessValues.reduce((sum, h) => sum + h, 0);
  const avg = total / hotnessValues.length;
  const max = Math.max(...hotnessValues);
  const min = Math.min(...hotnessValues);

  return {
    total,
    average: avg,
    max,
    min,
    count: hotnessValues.length,
  };
}

async function pushToFeishu(content: string, keyword: string): Promise<void> {
  const webhookUrl = process.env.FEISHU_WEBHOOK_URL || '';
  if (!webhookUrl) {
    console.error('[pushToFeishu] FEISHU_WEBHOOK_URL not configured');
    return;
  }

  try {
    // 使用飞书文本消息格式（更简单可靠）
    const payload = {
      msg_type: 'text',
      content: {
        text: content
      }
    };

    const response = await fetch(webhookUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    const result = await response.json();
    console.error('[pushToFeishu] API Response:', JSON.stringify(result));

    if (!response.ok || (result.code !== undefined && result.code !== 0)) {
      throw new Error(`HTTP ${response.status}: ${response.statusText} | ${result.msg}`);
    }

    console.error('[pushToFeishu] Pushed to Feishu successfully');
  } catch (error) {
    console.error('[pushToFeishu] Push failed:', error);
  }
}

async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0 || args[0] === '--help' || args[0] === '-h') {
    printUsage();
  }

  const keyword = args[0];
  const options: AnalysisOptions = {};

  // 解析参数
  for (let i = 1; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--push' && args[i + 1]) {
      options.push = args[++i];
    } else if (arg === '--mode' && args[i + 1]) {
      options.mode = args[++i] as 'simple' | 'deep';
    } else if (arg === '--history' && args[i + 1]) {
      options.history = parseInt(args[++i]);
    } else if (arg === '--compare' && args[i + 1]) {
      options.compare = args[++i].split(' ');
    } else if (arg === '--output' && args[i + 1]) {
      options.output = args[++i];
    }
  }

  console.error(`[aki-trendradar] Keyword: ${keyword}`);
  console.error(`[aki-trendradar] Mode: ${options.mode || 'simple'}`);
  console.error(`[aki-trendradar] Fetching news from multiple platforms...`);

  // 1. 获取新闻数据
  const newsItems = await fetchAllNews(keyword);

  // 2. 生成分析报告
  let report: string;
  const mode = options.mode || 'simple';

  if (mode === 'deep') {
    console.error('[aki-trendradar] Generating deep analysis with AI...');
    report = await generateDeepAnalysis(newsItems, keyword);
  } else {
    console.error('[aki-trendradar] Generating simple analysis...');
    report = await generateSimpleAnalysis(newsItems, keyword);
  }

  // 3. 输出报告
  if (options.output) {
    await $`echo "${report}" > ${options.output}`.quiet();
    console.error(`[aki-trendradar] Report saved to: ${options.output}`);
  } else {
    console.error('\n' + '─'.repeat(50));
    console.error(report);
    console.error('─'.repeat(50));
  }

  // 4. 推送（如果指定）
  if (options.push === 'feishu') {
    console.error('[aki-trendradar] Pushing to Feishu...');
    await pushToFeishu(report, keyword);
  } else if (options.push) {
    console.error(`[aki-trendradar] Push to ${options.push} not yet supported (MVP phase)`);
  }
}

main().catch((error) => {
  console.error('Error:', error);
  process.exit(1);
});
