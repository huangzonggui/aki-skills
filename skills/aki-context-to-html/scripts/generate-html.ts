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
  // Try options first
  if (options?.apiUrl && options?.apiKey) {
    return {
      apiUrl: options.apiUrl,
      apiKey: options.apiKey,
      model: options.model || 'glm-4-flash',
    };
  }

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

  // Extract title
  let title = frontmatter.title ?? '';
  if (!title) {
    const h1Match = body.match(/^#\s+(.+)$/m);
    if (h1Match) title = h1Match[1]!;
  }

  // Remove H1 from body if it exists
  body = body.replace(/^#\s+.+\r?\n?/m, '');

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
  const prompt = `You are an expert content editor and visual designer specializing in Chinese content.

Your task is to take the provided article and wrap it in semantic HTML for a high-impact, modern layout.

### CORE PRINCIPLES:
1. **NO DARK BACKGROUNDS**: Do not use dark colors as backgrounds. Use light backgrounds (#ffffff, #f8fafc) only.

2. **VISUAL HIERARCHY**:
   - Use <h1> for the absolute primary title/hook.
   - Use <h2> for major arguments or section leads with red left border.
   - Use <h3> for supporting sub-points.
   - Headers should be LARGE and act as primary anchors.

3. **WORD-FOR-WORD**: DO NOT CHANGE A SINGLE WORD of the original content.

4. **STYLING ELEMENTS**:
   - Use <mark> for key quotes or "gold nuggets" (most important insights).
   - Use <em> for keywords highlighted in RED (product names, important concepts).
   - Use <strong> for important phrases needing bold.
   - Use <blockquote> for summary conclusions with blue left border.

5. **STRUCTURE**:
   - Group related paragraphs under <h3> subheaders.
   - Use <hr> to separate major sections.
   - Ensure clear visual flow.

6. **CLEAN FINISH**: No trailing punctuation in headers unless in source.

### OUTPUT:
Return ONLY the HTML content. No markdown, no <html> or <body> tags, no code blocks.

Example structure:
<h1>Main Title</h1>
<p>Introduction with <mark>key insight</mark> and <em>keyword</em>.</p>
<h2>Section Title</h2>
<h3>Subsection</h3>
<p>Content...</p>
<blockquote>Key conclusion</blockquote>

CONTENT:
${articleText}`;

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

    return cleaned;
  } catch (error) {
    console.error('LLM API Error:', error);
    throw new Error(`Failed to generate styled HTML: ${error instanceof Error ? error.message : String(error)}`);
  }
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
