#!/usr/bin/env bun
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(__dirname, '..');
const COMFLY_DEFAULT_BASE_URL = 'https://ai.comfly.chat';
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
  output?: string;
  ratio?: '3:4' | '3:5';
  width?: number;
  title?: string;
  apiUrl?: string;
  apiKey?: string;
  model?: string;
}

interface ParsedContent {
  title: string;
  content: string;
}

function normalizeChatUrl(url: string): string {
  const trimmed = url.trim();
  if (!trimmed) return '';
  if (trimmed.includes(COMFLY_CHAT_PATH)) {
    return trimmed;
  }
  const base = trimmed.replace(/\/+$/, '');
  if (base.endsWith('/v1')) {
    return base + '/chat/completions';
  }
  return base + COMFLY_CHAT_PATH;
}

function isComflyUrl(url: string): boolean {
  return /comfly/i.test(url);
}

function parseEnvLikeFile(filePath: string): Record<string, string> {
  const out: Record<string, string> = {};
  if (!filePath || !fs.existsSync(filePath)) return out;

  const lines = fs.readFileSync(filePath, 'utf-8').split('\n');
  for (const rawLine of lines) {
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

// Get API configuration
function getApiConfig(options?: Options): { apiUrl: string; apiKey: string; model: string } {
  const providerConfig = loadComflyConfig();
  const fileApiKey = providerConfig.COMFLY_API_KEY || providerConfig.API_KEY || '';
  const fileApiUrl = providerConfig.COMFLY_API_URL || providerConfig.API_URL || '';
  const fileApiBaseUrl = providerConfig.COMFLY_API_BASE_URL || '';
  const fileModel = providerConfig.COMFLY_CHAT_MODEL
    || providerConfig.COMFLY_MODEL
    || providerConfig.MODEL
    || '';

  let apiKey = options?.apiKey ?? '';
  let apiUrl = options?.apiUrl ?? '';
  let model = options?.model ?? '';

  // Prefer explicit environment variables, then provider file.
  if (!apiKey) {
    apiKey = process.env.COMFLY_API_KEY
      || process.env.CLOUD_CODE_API_KEY
      || process.env.GLM_API_KEY
      || process.env.OPENAI_API_KEY
      || process.env.API_KEY
      || fileApiKey
      || '';
  }

  if (!apiUrl) {
    const envApiUrl = process.env.COMFLY_API_URL
      || process.env.CLOUD_CODE_API_URL
      || process.env.GLM_API_URL
      || process.env.OPENAI_API_URL
      || '';
    const fileUrl = isComflyUrl(fileApiUrl) ? fileApiUrl : '';
    apiUrl = envApiUrl || fileUrl || '';
  }

  const baseUrl = process.env.COMFLY_API_BASE_URL || fileApiBaseUrl || '';
  apiUrl = normalizeChatUrl(apiUrl || baseUrl || COMFLY_DEFAULT_BASE_URL);

  // Model fallback
  if (!model) {
    model = process.env.COMFLY_CHAT_MODEL
      || process.env.COMFLY_MODEL
      || fileModel
      || process.env.CLOUD_CODE_MODEL
      || process.env.GLM_MODEL
      || process.env.ANTHROPIC_MODEL
      || process.env.MODEL
      || 'gemini-3-pro-preview-thinking-*';
  }

  if (!apiKey) {
    throw new Error(`
API Key not found!

Please set your API key in one of these ways:

1. Set Comfly API key in environment:
   export COMFLY_API_KEY="your-api-key"

2. Or create/edit ${COMFLY_CONFIG_PATH}:
   COMFLY_API_KEY=your-api-key-here
   COMFLY_CHAT_MODEL=gpt-4o-mini

3. Or use command line option:
   --api-key "your-api-key"

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

  // Extract title for display (prefer frontmatter, then first H1)
  let title = (frontmatter.title ?? '').trim();
  const h1Regex = /^#\s+(.+)$/m;
  const h1Match = body.match(h1Regex);
  if (h1Match) {
    const h1Text = (h1Match[1] ?? '').trim();
    if (!title) {
      title = h1Text;
    }
    // Remove the first H1 from body to avoid duplicate title rendering
    body = body.replace(h1Regex, '').trim();
  }

  // Return Markdown content (H1 removed if used as title)
  // The LLM will convert Markdown to HTML
  return { title, content: body.trim() };
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Call Comfly Chat Completions (OpenAI compatible) to generate styled HTML
async function generateStyledHtmlWithLLM(articleText: string, config: { apiUrl: string; apiKey: string; model: string }): Promise<string> {
  // Pre-convert basic Markdown to HTML to ensure consistency
  let preConverted = articleText
    // Convert # headings (H1 - main title, KEEP IT!)
    .replace(/^#\s+(.+)$/gm, '<h1>$1</h1>')
    // Convert ## headings (H2 - sections)
    .replace(/^##\s+(.+)$/gm, '<h2>$1</h2>')
    // Convert ### headings (H3 - subsections)
    .replace(/^###\s+(.+)$/gm, '<h3>$1</h3>')
    // Convert - lists
    .replace(/^-\s+(.+)$/gm, '<li>$1</li>')
    // Wrap consecutive <li> in <ul>
    .replace(/(<li>.*<\/li>\n?)+/g, '<ul>\n$&</ul>')
    // Convert > blockquotes
    .replace(/^>\s+(.+)$/gm, '<blockquote>$1</blockquote>')
    // Convert paragraphs (lines that don't start with block tag)
    .split('\n')
    .map(line => {
      const trimmed = line.trim();
      if (!trimmed) return '';
      // Check if line starts with a block-level tag
      if (/^<(h[1-6]|ul|li|blockquote|hr)/.test(trimmed)) {
        return trimmed;
      }
      // Otherwise, wrap in <p> and convert inline **bold**
      return `<p>${trimmed.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')}</p><br>`;
    })
    .filter(line => line !== '')
    .join('\n');

  const prompt = `你是一位专业的中文内容编辑，擅长将 Markdown 内容转换为语义化的 HTML。

你的任务是对提供的 HTML 进行智能格式化高亮。不要改变结构，只添加语义化标签。

### 关键要求：
1. **保持现有 HTML 结构**：保留所有 <h1>, <h2>, <h3>, <p>, <ul>, <li>, <blockquote> 标签
2. **保留 <br> 标签**：每个 <p> 标签后的 <br> 标签必须保留，这是用于段落间距的
3. **只添加高亮标签**：添加 <mark>, <em>, <strong> 等语义标签
4. **不要添加内联样式**：不要添加 style="..." 属性
5. **不要添加 div 包装**：不要用 <div> 标签包裹内容
6. **段落间需要空行**：每个 <p> 标签必须保留后面的 <br> 标签，确保段落间距

### 智能高亮规则：
你必须识别并标记：

**<mark> 金句高亮**（最重要）：
- 识别文章中的"金句"——即最有价值、最值得引用的句子
- 金句特征：精炼总结、反常识观点、核心论点、启发性结论
- 每篇文章标记 3-5 个金句，用 <mark> 标签包裹
- 金句示例：
  * "AI有泡沫不代表就全盘否定不参与，每一场风口都会伴随泡沫"
  * "现在的泡沫，可能就是明天的基建红利"
  * "我们要做的是避开泡沫，拥抱AI价值"

**<em> 强调标记**：
- 产品名称、公司名：Oracle, CoreWeave, OpenAI, Google, DeepSeek等
- 技术术语：CDS, GPU, TPU, AI, API等
- 数据强调：2-3年、6年、美股七姐妹等

**<strong> 一般强调**：
- 已有粗体保持不变，用于一般强调

### 金句识别标准（用 <mark> 标记）：
1. **总结性观点** - 对整篇文章的核心结论
2. **反常识观点** - 与大众认知不同的见解
3. **启发性结论** - 给读者带来新认知的句子
4. **精炼表达** - 短小精悍但含义深刻的句子
5. **行动指引** - 告诉读者应该怎么做的句子

### 示例：
- <em>Oracle</em> - 公司名用红色强调
- <mark>现在的泡沫，可能就是明天的基建红利</mark> - 金句用黄色高亮
- <strong>关键点</strong> - 一般强调

### 输入 HTML：
${preConverted}

### 输出要求：
返回增强后的 HTML。注意：
1. 所有的 <h2> 标签必须添加 class="section-title"
2. 所有的 <blockquote> 标签保持不变
3. 只添加高亮标签，不要改变其他任何内容
4. 确保段落之间有换行（<p> 标签前后要有 \\n）
5. 不要添加代码块标记。`;

  try {
    const response = await fetch(config.apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
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
        tools: [],
        tool_choice: 'none',
        temperature: 0.6,
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
      .replace(/^```html\n?/gm, '')
      .replace(/^```\n?/gm, '')
      .replace(/^`.*\n?/gm, '')
      .trim();

    // Remove any wrapper tags
    cleaned = cleaned
      .replace(/<\/?html[^>]*>/gi, '')
      .replace(/<\/?body[^>]*>/gi, '')
      .replace(/<\/?head[^>]*>.*?<\/head>/gis, '')
      .trim();

    // Clean up AI-generated inline styles and wrapper divs
    cleaned = cleanAIOutput(cleaned);

    return cleaned;
  } catch (error) {
    console.error('LLM API Error:', error);
    throw new Error(`Failed to generate styled HTML: ${error instanceof Error ? error.message : String(error)}`);
  }
}

// Clean up AI-generated HTML
function cleanAIOutput(html: string): string {
  let cleaned = html;

  // Remove all inline style attributes
  cleaned = cleaned.replace(/\s*style="[^"]*"/gi, '');

  // Remove ALL div tags (both opening and closing) - AI should only use semantic tags
  cleaned = cleaned.replace(/<div[^>]*>/gi, '');
  cleaned = cleaned.replace(/<\/div>/gi, '');

  // Clean up extra blank lines
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n');

  return cleaned.trim();
}

// Ensure key structural classes exist even if the model forgets to add them.
function normalizeHeadingClasses(html: string): string {
  return html.replace(/<h2(?![^>]*\bclass=)([^>]*)>/gi, '<h2 class="section-title"$1>');
}

async function generateHtml(
  inputPath: string,
  options: Options = {},
): Promise<string> {
  // Parse input
  const parsed = parseMarkdown(inputPath);

  // Get API config
  const apiConfig = getApiConfig(options);

  console.error(`🤖 Calling ${apiConfig.model} for intelligent styling...`);

  // Generate styled HTML with LLM
  const styledHtml = normalizeHeadingClasses(
    await generateStyledHtmlWithLLM(parsed.content, apiConfig),
  );

  // Override title if provided
  const displayTitle = (options.title ?? parsed.title ?? '').trim();
  const hasDisplayTitle = Boolean(displayTitle);
  const docTitle = hasDisplayTitle
    ? displayTitle
    : path.basename(inputPath, path.extname(inputPath));

  // Read template
  const templatePath = path.join(SKILL_DIR, 'scripts', 'template.html');
  const template = fs.readFileSync(templatePath, 'utf-8');

  // Replace placeholders - use global replace for TITLE
  const titleMarker = '___TITLE_PLACEHOLDER___';
  let html = template.replaceAll('{{TITLE}}', titleMarker);
  html = html.replaceAll(titleMarker, escapeHtml(docTitle));

  // Replace content and other placeholders
  const width = options.width ?? 600;
  const ratio = options.ratio ?? '3:4';

  html = html.replaceAll('{{CONTENT}}', styledHtml);
  html = html.replaceAll('{{RATIO}}', ratio);
  html = html.replaceAll('{{TARGET_WIDTH}}', String(width));

  const targetHeight = ratio === '3:5' ? 1000 : 800;
  html = html.replaceAll('{{TARGET_HEIGHT}}', String(targetHeight));

  if (!hasDisplayTitle) {
    html = html.replace(/\s*<h1 class="article-title">[\s\S]*?<\/h1>\s*/i, '');
  }

  return html;
}

function printUsage(): never {
  console.log(`
Aki Context to HTML - Generate styled HTML with Comfly Chat Completions

Usage:
  npx -y bun generate-html.ts <input.md> [options]

Options:
  --output <path>    Output HTML path (default: <input-dir>/article.html)
  --ratio <ratio>    Aspect ratio: 3:4 or 3:5 (default: 3:4)
  --width <px>       Target width in pixels (default: 600)
  --title <text>     Override article title
  --api-url <url>   API URL (default: Comfly chat completions)
  --api-key <key>   API key (or use COMFLY_API_KEY env var)
  --model <name>    Model name (default: gemini-3-pro-preview-thinking-*)
  -h, --help         Show this help

Environment Variables:
  COMFLY_API_KEY         Comfly API key (required)
  COMFLY_API_BASE_URL    Comfly base URL (default: https://ai.comfly.chat)
  COMFLY_API_URL         Full Comfly chat completions URL (optional)
  COMFLY_CHAT_MODEL      Model name (default: gemini-3-pro-preview-thinking-*)
  COMFLY_MODEL           Alias for COMFLY_CHAT_MODEL

Provider Config (user-level):
  ~/.config/comfly/config

Examples:
  npx -y bun generate-html.ts article.md
  npx -y bun generate-html.ts article.md --output ./output.html
  npx -y bun generate-html.ts article.md --ratio 3:5

Note: This skill uses Comfly Chat Completions (Gemini 3 Pro Preview Thinking by default) to intelligently analyze content
and apply semantic HTML formatting with smart highlights.

Output sizes:
  - 3:4 ratio: 600 × 800px
  - 3:5 ratio: 600 × 1000px
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

    if (arg === '--output' && args[i + 1]) {
      options.output = args[++i];
    } else if (arg === '--ratio' && args[i + 1]) {
      const ratio = args[++i];
      if (ratio === '3:4' || ratio === '3:5') {
        options.ratio = ratio;
      }
    } else if (arg === '--width' && args[i + 1]) {
      options.width = parseInt(args[++i]!, 10);
    } else if (arg === '--title' && args[i + 1]) {
      options.title = args[++i];
    } else if (arg === '--api-url' && args[i + 1]) {
      options.apiUrl = args[++i];
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

  // Determine output path
  const outputPath = options.output ?? path.join(path.dirname(inputPath), 'article.html');

  // Generate HTML
  const html = await generateHtml(inputPath, options);

  // Write output
  fs.writeFileSync(outputPath, html, 'utf-8');

  console.error(`✓ HTML generated: ${outputPath}`);
  console.error(`  Open in browser to view and export PNG slices`);
}

main().catch((err) => {
  console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
  process.exit(1);
});
