#!/usr/bin/env bun
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(__dirname, '..');
const COMFLY_CHAT_PATH = '/v1/chat/completions';
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

interface Options {
  mode?: 'rewrite' | 'script';
  output?: string;
  platform?: string;
  duration?: number;
  apiUrl?: string;
  apiKey?: string;
  model?: string;
}

interface ParsedContent {
  title: string;
  content: string;
}

function parseEnvLikeFile(filePath: string): Record<string, string> {
  const out: Record<string, string> = {};
  if (!filePath || !fs.existsSync(filePath)) return out;

  for (const rawLine of fs.readFileSync(filePath, 'utf-8').split('\n')) {
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

function normalizeComflyChatUrl(url: string): string {
  const trimmed = url.trim();
  if (!trimmed) return '';
  if (trimmed.includes(COMFLY_CHAT_PATH)) return trimmed;
  const base = trimmed.replace(/\/+$/, '');
  if (base.endsWith('/v1')) return base + '/chat/completions';
  return base + COMFLY_CHAT_PATH;
}

// Get API configuration
function getApiConfig(options?: Options): { apiUrl: string; apiKey: string; model: string } {
  const providerConfig = loadComflyConfig();
  let apiKey = providerConfig.COMFLY_API_KEY || providerConfig.API_KEY || '';
  let apiUrl = providerConfig.COMFLY_API_URL || providerConfig.API_URL || '';
  let model = providerConfig.COMFLY_CHAT_MODEL
    || providerConfig.COMFLY_MODEL
    || providerConfig.MODEL
    || '';

  // Command-line options override config file
  if (options?.apiUrl) apiUrl = options.apiUrl;
  if (options?.apiKey) apiKey = options.apiKey;
  if (options?.model) model = options.model;

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
    const comflyBase = process.env.COMFLY_API_BASE_URL || providerConfig.COMFLY_API_BASE_URL || '';
    const comflyUrl = process.env.COMFLY_API_URL || '';
    if (comflyUrl) {
      apiUrl = comflyUrl;
    } else if (comflyBase) {
      apiUrl = normalizeComflyChatUrl(comflyBase);
    }
  }

  if (!apiUrl) {
    const anthropicUrl = process.env.ANTHROPIC_BASE_URL;
    if (anthropicUrl) {
      apiUrl = anthropicUrl.replace('/anthropic', '/paas/v4/chat/completions');
    }
    apiUrl = apiUrl || process.env.CLOUD_CODE_API_URL
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
      || process.env.ANTHROPIC_MODEL
      || 'glm-4-flash';
  }

  if (!apiKey) {
    throw new Error(`
API Key not found!

Please set your API key in one of these ways:

1. Create/edit ${COMFLY_CONFIG_PATH}:
   COMFLY_API_KEY=your-api-key-here
   COMFLY_CHAT_MODEL=gpt-4o-mini

2. Or set environment variable:
   export COMFLY_API_KEY="your-api-key"

3. Or use command line option:
   --api-key "your-api-key"

Get your GLM API key at: https://open.bigmodel.cn/

Detected configuration:
  - API URL: ${apiUrl}
  - Model: ${model}
`);
  }

  return { apiUrl, apiKey, model };
}

function parseMarkdown(filePath: string): ParsedContent {
  const content = fs.readFileSync(filePath, 'utf-8');

  // Extract frontmatter
  const frontmatterMatch = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/);
  let body = content;
  let frontmatter: Record<string, string> = {};

  if (frontmatterMatch) {
    const lines = frontmatterMatch[1]!.split('\n');
    for (const line of lines) {
      const colonIdx = line.indexOf(':');
      if (colonIdx > 0) {
        const key = line.slice(0, colonIdx).trim();
        const value = line.slice(colonIdx + 1).trim().replace(/^["']|["']$/g, '');
        frontmatter[key] = value;
      }
    }
    body = frontmatterMatch[2]!;
  }

  let title = frontmatter.title ?? '';
  if (!title) {
    const h1Match = body.match(/^#\s+(.+)$/m);
    if (h1Match) title = h1Match[1]!;
  }

  // Remove the main H1 from body for processing
  body = body.replace(/^#\s+.+$\r?\n/m, '');

  return { title: title || 'Untitled', content: body.trim() };
}

// Get platform-specific guidance
function getPlatformGuidance(platform: string): string {
  const guidanceMap: Record<string, string> = {
    xiaohongshu: `
- 使用小红书风格：更多emoji表情符号
- 标题要吸睛，使用数字、疑问句
- 段落更短，每段2-3句话
- 加入话题标签 #xxx
- 语气更亲切、像姐妹分享
- 可以加入"姐妹们"、"宝子们"等称呼`,
    zhihu: `
- 使用知乎风格：更专业、理性
- 可以引用数据、案例
- 保持逻辑性，适合深度阅读
- 避免过于口语化
- 加入"谢邀"、"谢邀"等知乎梗（适度）`,
    toutiao: `
- 使用今日头条风格：标题要抓眼球
- 开头要有吸引点
- 使用热点、数字等元素
- 段落适中
- 适合快速阅读`,
    generic: `
- 保持专业性但不失亲和力
- 结构清晰，易于阅读
- 适合大多数平台`,
  };

  return guidanceMap[platform] || guidanceMap.generic;
}

// Rewrite article with 30% information variation
async function rewriteArticle(
  articleText: string,
  title: string,
  platform: string,
  config: { apiUrl: string; apiKey: string; model: string }
): Promise<string> {
  const platformGuidance = getPlatformGuidance(platform);

  const prompt = `你是一位专业的内容创作者，擅长将文章改写为不同平台的内容。

# 任务
将提供的文章改写为一个**新版本**，要求：
1. **保持核心观点和主旨不变**
2. **30%的信息变化**：改变例子、比喻、支撑细节
3. **加入新鲜角度**，让老读者也有新收获
4. **使用更口语化、更有感染力的表达**

${platformGuidance}

# 文章信息
标题：${title}

原文内容：
\`\`\`
${articleText}
\`\`\`

# 改写要求
- 输出Markdown格式
- 保持原文的结构（如果有小标题，请保留）
- 重新组织语言，不要逐句翻译
- 改变至少30%的内容（例子、数据、说法）
- 让文字更有感染力和传播力

# 输出格式
请直接输出改写后的Markdown内容，不要包含任何解释性文字。`;

  try {
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
        temperature: 0.8,
        top_p: 0.95,
        max_tokens: 8000,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`API request failed: ${response.status} ${errorText}`);
    }

    const data = await response.json();
    const result = data.choices?.[0]?.message?.content || data.content || '';

    // Clean up the response
    let cleaned = result
      .replace(/^```markdown\n?/gi, '')
      .replace(/^```md\n?/gi, '')
      .replace(/^```\n?/gm, '')
      .trim();

    return cleaned;
  } catch (error) {
    console.error('LLM API Error:', error);
    throw new Error(`Failed to rewrite article: ${error instanceof Error ? error.message : String(error)}`);
  }
}

// Generate video script with authentic style based on user's hand-written script
async function generateVideoScript(
  articleText: string,
  title: string,
  duration: number,
  config: { apiUrl: string; apiKey: string; model: string }
): Promise<string> {
  const prompt = `你是一位真诚的内容创作者，创作口播文案时要**直接、自然、有个人观点**。

# 任务
从文章中提取核心信息，创作一个**口播脚本**。
注意：不要限制字数，把该说的话说完就行。

# 风格要求（非常重要）
1. **开头用提问**：引发观众思考，如"你是否还在..."
2. **真诚自然**：用"我已经..."这样的第一人称表达
3. **直接表达**：开门见山，不要绕弯子
4. **人味十足**：像跟朋友认真说话，不是在念稿子
5. **结尾号召行动**：告诉观众具体该做什么
6. **禁止套话**：不要用"你知道吗"、"你知道吗"、"我的朋友"等模板化表达

# 参考风格（完全按照这个结构和语气来写）
"你是否还在拼音输入打字？
AI时代，我已经全面说话代替打字了。因为说话输入比打字高效不止10倍。还能练习口语

这也是为什么最近飞书AI录音豆最近上市，899块钱买一个录音器？普通人真的有必要买吗？

如果你还没把语音输入作为主流输入多话，先用软件录音也挺香，我现在用的AI录音软件也能帮我剔除口水话，因为它输出前会用AI整理一遍

快去把你的电脑输入、微信回复、跟 AI 对话用语音对话吧"

# 结构要求（必须遵守）
第1段：提问开头 + 我已经怎么做 + 原因
第2段：这也是为什么...引入话题 + 价格/疑问
第3段：如果你...建议 + 我的经验
第4段：行动号召（快去...）

每段2-3句话，不要更多

# 严格禁止
- 不要加任何开头填充词：哎、哇、呀、呢、吧、嘿等
- 不要用"你知道吗"、"我的朋友"、"所以"、"因此"等套话
- 每段直接说事，不要铺垫

# 重要提示
- 不要把文章的所有细节都放进去，只提取核心观点
- 保持简洁，像在跟朋友说话，不是在讲课
- 每段2-3句话就够了，用换行分隔
- 重点放在"我已经怎么做"和"你应该怎么做"上
- 整个脚本控制在4-5段以内，不要长篇大论

# 文章信息
标题：${title}
原文：
\`\`\`
${articleText}
\`\`\`

# 输出要求
- 不限制字数，把话说完整
- 直接输出脚本内容，不要任何说明文字
- 不要使用emoji表情符号
- 用换行分段，每段表达一个完整意思
- 不要用【停顿】等标记，用自然的换行表达节奏`;

  try {
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
        temperature: 0.9,
        top_p: 0.95,
        max_tokens: 2000,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`API request failed: ${response.status} ${errorText}`);
    }

    const data = await response.json();
    const result = data.choices?.[0]?.message?.content || data.content || '';

    // Clean up the response
    let cleaned = result
      .replace(/^```\n?/gm, '')
      .replace(/^["']|["']$/g, '')
      .trim();

    return cleaned;
  } catch (error) {
    console.error('LLM API Error:', error);
    throw new Error(`Failed to generate script: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function printUsage(): never {
  console.log(`
Aki Article Transformer - Transform articles for different platforms

Usage:
  npx -y bun transform.ts <input.md> --mode <mode> [options]

Modes:
  rewrite    Rewrite article for other platform (30% information variation)
  script     Generate video script (口播文案)

Options:
  --mode <mode>           Transformation mode (rewrite|script) [required]
  --output <path>         Output file path
  --platform <name>       Target platform for rewrite: xiaohongshu, zhihu, toutiao, generic
  --duration <seconds>    Target duration for script (default: 20)
  --api-key <key>         API key (or use COMFLY_API_KEY env var)
  --model <name>          Model name (default: glm-4-flash)
  -h, --help              Show this help

Environment Variables:
  COMFLY_API_KEY        API key (preferred)
  COMFLY_API_BASE_URL   API base URL (optional)
  COMFLY_CHAT_MODEL     Model name (optional)
  CLOUD_CODE_API_KEY    API key (legacy fallback)
  CLOUD_CODE_API_URL    API URL (default: GLM API)
  CLOUD_CODE_MODEL      Model name (default: glm-4-flash)

Provider Config (user-level):
  ~/.config/comfly/config

Examples:
  # Rewrite for generic platform
  npx -y bun transform.ts article.md --mode rewrite

  # Rewrite for Xiaohongshu
  npx -y bun transform.ts article.md --mode rewrite --platform xiaohongshu

  # Generate 20-second video script
  npx -y bun transform.ts article.md --mode script

  # Generate 30-second script with custom output
  npx -y bun transform.ts article.md --mode script --duration 30 --output script.txt
`);
  process.exit(0);
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);

  if (args.length === 0 || args.includes('-h') || args.includes('--help')) {
    printUsage();
  }

  let inputPath: string | undefined;
  const options: Options = {};

  for (let i = 0; i < args.length; i++) {
    const arg = args[i]!;

    if (arg === '--mode' && args[i + 1]) {
      const mode = args[++i];
      if (mode === 'rewrite' || mode === 'script') {
        options.mode = mode;
      }
    } else if (arg === '--output' && args[i + 1]) {
      options.output = args[++i];
    } else if (arg === '--platform' && args[i + 1]) {
      options.platform = args[++i];
    } else if (arg === '--duration' && args[i + 1]) {
      options.duration = parseInt(args[++i]!, 10);
    } else if (arg === '--api-key' && args[i + 1]) {
      options.apiKey = args[++i];
    } else if (arg === '--model' && args[i + 1]) {
      options.model = args[++i];
    } else if (!arg.startsWith('-')) {
      inputPath = arg;
    }
  }

  if (!inputPath) {
    console.error('Error: Input file path required');
    process.exit(1);
  }

  if (!fs.existsSync(inputPath)) {
    console.error(`Error: File not found: ${inputPath}`);
    process.exit(1);
  }

  if (!options.mode) {
    console.error('Error: --mode is required (rewrite or script)');
    process.exit(1);
  }

  // Parse input
  const parsed = parseMarkdown(inputPath);

  // Get API config
  const apiConfig = getApiConfig(options);

  // Determine output path
  const defaultOutputName = options.mode === 'rewrite' ? 'rewritten.md' : 'script.txt';
  const outputPath = options.output ?? path.join(path.dirname(inputPath), defaultOutputName);

  // Generate transformed content
  let result: string;
  if (options.mode === 'rewrite') {
    const platform = options.platform || 'generic';
    console.error(`🔄 Rewriting article for platform: ${platform}...`);
    result = await rewriteArticle(parsed.content, parsed.title, platform, apiConfig);

    // Prepend title to rewritten content
    result = `# ${parsed.title}\n\n${result}`;
  } else {
    const duration = options.duration ?? 20;
    console.error(`📝 Generating ${duration}-second video script...`);
    result = await generateVideoScript(parsed.content, parsed.title, duration, apiConfig);

    // Add metadata as comment
    const charCount = result.replace(/[【】停顿\s]/g, '').length;
    result = `# ${parsed.title}\n# 时长: ${duration}秒 | 字数: ${charCount}\n\n${result}`;
  }

  // Write output
  fs.writeFileSync(outputPath, result, 'utf-8');

  console.error(`✓ Output saved: ${outputPath}`);
}

main().catch((err) => {
  console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
  process.exit(1);
});
