#!/usr/bin/env bun
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(__dirname, '..');

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

// Get API configuration
function getApiConfig(options?: Options): { apiUrl: string; apiKey: string; model: string } {
  // Try to read from ~/.cloud-code-api-key file
  const homeDir = process.env.HOME || process.env.USERPROFILE || '';
  const apiKeyFile = path.join(homeDir, '.cloud-code-api-key');

  let apiKey = '';
  let apiUrl = '';
  let model = '';

  if (fs.existsSync(apiKeyFile)) {
    const content = fs.readFileSync(apiKeyFile, 'utf-8');
    const lines = content.split('\n');

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('API_KEY=')) {
        apiKey = trimmed.split('=')[1]?.trim() || '';
      } else if (trimmed.startsWith('API_URL=')) {
        apiUrl = trimmed.split('=')[1]?.trim() || '';
      } else if (trimmed.startsWith('MODEL=')) {
        model = trimmed.split('=')[1]?.trim() || '';
      } else if (trimmed && !trimmed.startsWith('#')) {
        // If line doesn't have =, treat it as raw API key
        apiKey = trimmed;
      }
    }
  }

  // Command-line options override config file
  if (options?.apiUrl) {
    apiUrl = options.apiUrl;
  }
  if (options?.apiKey) {
    apiKey = options.apiKey;
  }
  if (options?.model) {
    model = options.model;
  }

  // Fallback to environment variables
  if (!apiKey) {
    apiKey = process.env.CLOUD_CODE_API_KEY
      || process.env.GLM_API_KEY
      || process.env.OPENAI_API_KEY
      || process.env.API_KEY
      || '';
  }

  // Fallback for API URL
  if (!apiUrl) {
    // Use ANTHROPIC_BASE_URL from env, convert to OpenAI format
    const anthropicUrl = process.env.ANTHROPIC_BASE_URL;
    if (anthropicUrl) {
      // Convert https://open.bigmodel.cn/api/anthropic to OpenAI format
      apiUrl = anthropicUrl.replace('/anthropic', '/paas/v4/chat/completions');
    }

    apiUrl = apiUrl || process.env.CLOUD_CODE_API_URL
      || process.env.GLM_API_URL
      || process.env.OPENAI_API_URL
      || 'https://open.bigmodel.cn/api/paas/v4/chat/completions';
  }

  // Fallback for model
  if (!model) {
    model = process.env.CLOUD_CODE_MODEL
      || process.env.GLM_MODEL
      || process.env.MODEL
      || process.env.ANTHROPIC_MODEL
      || 'glm-4-flash';
  }

  if (!apiKey) {
    throw new Error(`
API Key not found!

Please set your API key in one of these ways:

1. Create/edit ~/.cloud-code-api-key with your API key:
   echo "API_KEY=your-api-key-here" > ~/.cloud-code-api-key

2. Or set environment variable:
   export CLOUD_CODE_API_KEY="your-api-key"

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

  // Extract title for display (keep original Markdown in body)
  let title = frontmatter.title ?? '';
  if (!title) {
    const h1Match = body.match(/^#\s+(.+)$/m);
    if (h1Match) title = h1Match[1]!;
  }

  // Return ORIGINAL Markdown content (don't remove H1 or any formatting)
  // The LLM will convert Markdown to HTML
  return { title: title || 'Untitled', content: body.trim() };
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Call LLM API (GLM/OpenAI compatible) to generate styled HTML
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
      return `<p>${trimmed.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')}</p>`;
    })
    .filter(line => line !== '')
    .join('\n');

  const prompt = `你是一位专业的中文内容编辑，擅长将 Markdown 内容转换为语义化的 HTML。

你的任务是对提供的 HTML 进行智能格式化高亮。不要改变结构，只添加语义化标签。

### 关键要求：
1. **保持现有 HTML 结构**：保留所有 <h1>, <h2>, <h3>, <p>, <ul>, <li>, <blockquote> 标签
2. **只添加高亮标签**：添加 <mark>, <em>, <strong> 等语义标签
3. **不要添加内联样式**：不要添加 style="..." 属性
4. **不要添加 div 包装**：不要用 <div> 标签包裹内容
5. **段落间需要空行**：每个 <p> 标签前后要有换行，确保内容有呼吸感

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
  const styledHtml = await generateStyledHtmlWithLLM(parsed.content, apiConfig);

  // Override title if provided
  const title = options.title ?? parsed.title;

  // Read template
  const templatePath = path.join(SKILL_DIR, 'scripts', 'template.html');
  const template = fs.readFileSync(templatePath, 'utf-8');

  // Replace placeholders - use global replace for TITLE
  const titleMarker = '___TITLE_PLACEHOLDER___';
  let html = template.replaceAll('{{TITLE}}', titleMarker);
  html = html.replaceAll(titleMarker, escapeHtml(title));

  // Replace content and other placeholders
  const width = options.width ?? 600;
  const ratio = options.ratio ?? '3:4';

  html = html.replaceAll('{{CONTENT}}', styledHtml);
  html = html.replaceAll('{{RATIO}}', ratio);
  html = html.replaceAll('{{TARGET_WIDTH}}', String(width));

  const targetHeight = ratio === '3:5' ? 1000 : 800;
  html = html.replaceAll('{{TARGET_HEIGHT}}', String(targetHeight));

  return html;
}

function printUsage(): never {
  console.log(`
Aki Context to HTML - Generate styled HTML with AI (GLM/OpenAI compatible)

Usage:
  npx -y bun generate-html.ts <input.md> [options]

Options:
  --output <path>    Output HTML path (default: <input-dir>/article.html)
  --ratio <ratio>    Aspect ratio: 3:4 or 3:5 (default: 3:4)
  --width <px>       Target width in pixels (default: 600)
  --title <text>     Override article title
  --api-url <url>   API URL (default: GLM API)
  --api-key <key>   API key (or use CLOUD_CODE_API_KEY env var)
  --model <name>    Model name (default: glm-4-flash)
  -h, --help         Show this help

Environment Variables:
  CLOUD_CODE_API_KEY    API key (supports GLM, OpenAI compatible)
  CLOUD_CODE_API_URL    API URL (default: GLM API)
  CLOUD_CODE_MODEL      Model name (default: glm-4-flash)

  Alternative variables:
  GLM_API_KEY, OPENAI_API_KEY, API_KEY
  GLM_API_URL, OPENAI_API_URL

Examples:
  npx -y bun generate-html.ts article.md
  npx -y bun generate-html.ts article.md --output ./output.html
  npx -y bun generate-html.ts article.md --ratio 3:5

Note: This skill uses LLM (GLM by default) to intelligently analyze content
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
