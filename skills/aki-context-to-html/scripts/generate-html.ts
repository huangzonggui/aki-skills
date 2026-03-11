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

type StyleName = 'classic' | 'part-guide';

interface Options {
  output?: string;
  ratio?: '3:4' | '3:5';
  width?: number;
  title?: string;
  apiUrl?: string;
  apiKey?: string;
  model?: string;
  style?: StyleName;
}

interface ParsedContent {
  title: string;
  content: string;
}

interface ApiConfig {
  apiUrl: string;
  apiKey: string;
  model: string;
}

const STYLE_TEMPLATES: Record<StyleName, string> = {
  classic: 'template.html',
  'part-guide': 'template-part-guide.html',
};

function resolveExplicitStyleName(style?: string): StyleName | undefined {
  const value = (style ?? '').trim().toLowerCase();
  if (!value) return undefined;
  if (value === 'part-guide' || value === 'art-guide' || value === 'wechat-guide') {
    return 'part-guide';
  }
  if (value === 'classic') {
    return 'classic';
  }
  return undefined;
}

const DEFAULT_STYLE_ENV = 'AKI_CONTEXT_TO_HTML_DEFAULT_STYLE';
const DEFAULT_STYLE: StyleName = resolveExplicitStyleName(process.env[DEFAULT_STYLE_ENV]) ?? 'part-guide';

function normalizeChatUrl(url: string): string {
  const trimmed = url.trim();
  if (!trimmed) return '';
  if (trimmed.includes(COMFLY_CHAT_PATH)) {
    return trimmed;
  }
  const base = trimmed.replace(/\/+$/, '');
  if (base.endsWith('/v1')) {
    return `${base}/chat/completions`;
  }
  return `${base}${COMFLY_CHAT_PATH}`;
}

function isComflyUrl(url: string): boolean {
  return /comfly/i.test(url);
}

function normalizeStyleName(style?: string): StyleName {
  return resolveExplicitStyleName(style) ?? DEFAULT_STYLE;
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

function getApiConfig(options?: Options): ApiConfig {
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

  const frontmatterMatch = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/);
  let body = content;
  const frontmatter: Record<string, string> = {};

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

  let title = (frontmatter.title ?? '').trim();
  const h1Regex = /^#\s+(.+)$/m;
  const h1Match = body.match(h1Regex);
  if (h1Match) {
    const h1Text = (h1Match[1] ?? '').trim();
    if (!title) {
      title = h1Text;
    }
    body = body.replace(h1Regex, '').trim();
  }

  return { title, content: body.trim() };
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatInlineMarkdown(text: string): string {
  const inlineCode: string[] = [];
  let index = 0;

  let formatted = text.replace(/`([^`]+)`/g, (_, code: string) => {
    const token = `@@INLINE_CODE_${index}@@`;
    inlineCode.push(`<code>${escapeHtml(code)}</code>`);
    index += 1;
    return token;
  });

  formatted = formatted
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

  for (let i = 0; i < inlineCode.length; i++) {
    formatted = formatted.replace(`@@INLINE_CODE_${i}@@`, inlineCode[i]!);
  }

  return formatted;
}

function preConvertMarkdownToHtml(articleText: string): string {
  const codeBlocks: string[] = [];
  let codeBlockIndex = 0;

  let preConverted = articleText.replace(
    /```([^\n`]*)\r?\n([\s\S]*?)```/g,
    (_, rawInfo: string, rawCode: string) => {
      const info = rawInfo.trim().split(/\s+/)[0] ?? '';
      const safeInfo = info.replace(/[^a-z0-9_-]/gi, '').toLowerCase();
      const classAttr = safeInfo ? ` class="language-${safeInfo}"` : '';
      const token = `@@CODE_BLOCK_${codeBlockIndex}@@`;
      codeBlocks.push(`<pre${classAttr}><code>${escapeHtml(rawCode.trim())}</code></pre>`);
      codeBlockIndex += 1;
      return token;
    },
  );

  preConverted = preConverted
    .replace(/^#\s+(.+)$/gm, (_, text: string) => `<h1>${formatInlineMarkdown(text)}</h1>`)
    .replace(/^##\s+(.+)$/gm, (_, text: string) => `<h2>${formatInlineMarkdown(text)}</h2>`)
    .replace(/^###\s+(.+)$/gm, (_, text: string) => `<h3>${formatInlineMarkdown(text)}</h3>`)
    .replace(/^\s*[-*]\s+(.+)$/gm, (_, text: string) => `<li data-list="ul">${formatInlineMarkdown(text)}</li>`)
    .replace(/^\s*\d+\.\s+(.+)$/gm, (_, text: string) => `<li data-list="ol">${formatInlineMarkdown(text)}</li>`)
    .replace(/(?:<li data-list="ul">.*<\/li>\n?)+/g, match => `<ul>\n${match}</ul>`)
    .replace(/(?:<li data-list="ol">.*<\/li>\n?)+/g, match => `<ol>\n${match}</ol>`)
    .replace(/\sdata-list="(?:ul|ol)"/g, '')
    .replace(/^>\s+(.+)$/gm, (_, text: string) => `<blockquote>${formatInlineMarkdown(text)}</blockquote>`)
    .replace(/^---$/gm, '<hr>')
    .split('\n')
    .map(line => {
      const trimmed = line.trim();
      if (!trimmed) return '';
      if (/^<(h[1-6]|ul|ol|li|blockquote|pre|hr)/.test(trimmed)) {
        return trimmed;
      }
      if (/^@@CODE_BLOCK_\d+@@$/.test(trimmed)) {
        return trimmed;
      }
      return `<p>${formatInlineMarkdown(trimmed)}</p><br>`;
    })
    .filter(line => line !== '')
    .join('\n');

  for (let i = 0; i < codeBlocks.length; i++) {
    preConverted = preConverted.replace(`@@CODE_BLOCK_${i}@@`, codeBlocks[i]!);
  }

  return preConverted;
}

function buildClassicPrompt(preConvertedHtml: string): string {
  return `你是一位专业的中文内容编辑，擅长将 Markdown 内容转换为语义化的 HTML。

你的任务是对提供的 HTML 进行智能格式化高亮。不要改变结构，只添加语义化标签。

### 关键要求：
1. **保持现有 HTML 结构**：保留所有 <h1>, <h2>, <h3>, <p>, <ul>, <li>, <blockquote>, <pre>, <code> 标签
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

**<em> 强调标记**：
- 产品名称、公司名：Oracle, CoreWeave, OpenAI, Google, DeepSeek 等
- 技术术语：CDS, GPU, TPU, AI, API 等
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
${preConvertedHtml}

### 输出要求：
返回增强后的 HTML。注意：
1. 所有的 <h2> 标签必须添加 class="section-title"
2. 所有的 <blockquote> 标签保持不变
3. 只添加高亮标签，不要改变其他任何内容
4. 确保段落之间有换行（<p> 标签前后要有 \\n）
5. 不要添加代码块标记。`;
}

function buildWechatGuidePrompt(preConvertedHtml: string): string {
  return `你是一位擅长排版中文教程、工具指南和微信公众号长图文章的编辑。

你的任务是对提供的 HTML 做“教程型排版增强”。默认保持原有结构，只做适度的语义增强，让结果适合一种简洁、克制、偏教程感的长图样式。

### 关键要求：
1. 保留现有主体结构：保留 <h1>, <h2>, <h3>, <p>, <ul>, <ol>, <li>, <blockquote>, <pre>, <code>
2. 所有 <h2> 必须带 class="section-title"
3. 所有 <h3> 优先带 class="subsection-title"
4. 保留每个段落后的 <br> 标签，除非该段落被你改成 <pre><code>...</code></pre>
5. 只允许增加语义标签或 class，不要添加内联样式，不要添加 <div>
6. 输出必须是干净 HTML，不要包裹 html/body，不要加 Markdown 代码块

### 教程风格增强规则：
1. **<mark> 用于关键结论/最值得停顿阅读的句子**
2. **<em> 用于绿色强调**：动作词、核心对象、收益点、要点结论
3. **<strong> 用于深色强调**：少量重点，不要滥用
4. **<code> 用于短标签**：工具名、Skill 名、命令名、平台名、按钮名
5. 如果某一整行明显是命令行、安装命令、PowerShell 命令，可以改成 <pre><code>...</code></pre>
6. 如果某行是 “Step 1 / Step 2 / 步骤 1” 这种步骤标题，可以给对应段落加 class="step-row"，并把步骤标签包成 <span class="step-badge">...</span>

### 内容判断标准：
- 重点优先标记：结论句、安装/操作关键动作、限制条件、注意事项
- 少做情绪化修饰，整体保持教程感、工具感、信息密度感
- 一篇文章里 <mark> 控制在 3-6 处，<em> 和 <code> 可以更常见，但不要每句都加

### 输入 HTML：
${preConvertedHtml}

### 输出要求：
1. 返回增强后的 HTML
2. 不要使用内联样式
3. 不要添加多余包裹层
4. 命令段如果改成 <pre>，就不要再额外跟一个 <br>
5. h2 / h3 的 class 要保留`;
}

function buildPrompt(preConvertedHtml: string, style: StyleName): string {
  if (style === 'part-guide') {
    return buildWechatGuidePrompt(preConvertedHtml);
  }
  return buildClassicPrompt(preConvertedHtml);
}

async function generateStyledHtmlWithLLM(
  articleText: string,
  config: ApiConfig,
  style: StyleName,
): Promise<string> {
  const preConverted = preConvertMarkdownToHtml(articleText);
  const prompt = buildPrompt(preConverted, style);

  try {
    const response = await fetch(config.apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        Authorization: `Bearer ${config.apiKey}`,
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

    let cleaned = result
      .replace(/^```html\n?/gm, '')
      .replace(/^```\n?/gm, '')
      .replace(/^`.*\n?/gm, '')
      .trim();

    cleaned = cleaned
      .replace(/<\/?html[^>]*>/gi, '')
      .replace(/<\/?body[^>]*>/gi, '')
      .replace(/<\/?head[^>]*>.*?<\/head>/gis, '')
      .trim();

    return cleanAIOutput(cleaned);
  } catch (error) {
    console.error('LLM API Error:', error);
    throw new Error(`Failed to generate styled HTML: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function cleanAIOutput(html: string): string {
  let cleaned = html;
  cleaned = cleaned.replace(/\s*style="[^"]*"/gi, '');
  cleaned = cleaned.replace(/<div[^>]*>/gi, '');
  cleaned = cleaned.replace(/<\/div>/gi, '');
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
  return cleaned.trim();
}

function addClassToAttributes(attributes: string, className: string): string {
  if (/\bclass="/i.test(attributes)) {
    return attributes.replace(/\bclass="([^"]*)"/i, (_, classes: string) => {
      const merged = `${classes} ${className}`.trim().replace(/\s+/g, ' ');
      return `class="${merged}"`;
    });
  }
  return `${attributes} class="${className}"`;
}

function ensureTagClass(html: string, tagName: string, className: string): string {
  const pattern = new RegExp(`<${tagName}([^>]*)>`, 'gi');

  return html.replace(pattern, (fullMatch, attributes: string) => {
    if (new RegExp(`\\b${className}\\b`, 'i').test(fullMatch)) {
      return fullMatch;
    }
    return `<${tagName}${addClassToAttributes(attributes, className)}>`;
  });
}

function normalizeHeadingClasses(html: string): string {
  return ensureTagClass(html, 'h2', 'section-title');
}

function stripHtmlTags(html: string): string {
  return html
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<\/?[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/\s+/g, ' ')
    .trim();
}

function looksLikeCommandLine(text: string): boolean {
  if (!text || text.length > 220) return false;

  const starters = /^(?:curl|wget|bash|sh|zsh|fish|iex\s*\(|irm\s+https?:\/\/|powershell|pwsh|brew|npm|pnpm|yarn|npx|git|uv|python(?:3)?|pip(?:3)?|node|deno|docker|claude|openclaw|export\s+[A-Z_]+|set\s+[A-Z_]+)/i;
  if (starters.test(text)) {
    return true;
  }

  if (/https?:\/\//i.test(text) && /[|()]/.test(text) && !/[\u4e00-\u9fa5]/.test(text)) {
    return true;
  }

  return false;
}

function splitCommandAndNarration(text: string): { command: string; narration: string } {
  if (!text) {
    return { command: '', narration: '' };
  }

  const firstCjkIndex = text.search(/[\u4e00-\u9fa5]/);
  if (firstCjkIndex <= 0) {
    return { command: text.trim(), narration: '' };
  }

  const command = text.slice(0, firstCjkIndex).trim();
  const narration = text.slice(firstCjkIndex).trim();

  if (!command || !looksLikeCommandLine(command)) {
    return { command: text.trim(), narration: '' };
  }

  return { command, narration };
}

function convertCommandParagraphs(html: string): string {
  return html.replace(
    /<p([^>]*)>([\s\S]*?)<\/p>(\s*<br\s*\/?>)?/gi,
    (fullMatch, _attributes: string, innerHtml: string) => {
      const plainText = stripHtmlTags(innerHtml);
      if (!looksLikeCommandLine(plainText)) {
        return fullMatch;
      }

      const { command, narration } = splitCommandAndNarration(plainText);
      if (!command) {
        return fullMatch;
      }

      const commandHtml = `<pre class="command-block"><code>${escapeHtml(command)}</code></pre>`;
      if (!narration) {
        return commandHtml;
      }

      return `${commandHtml}\n<p>${narration}</p><br>`;
    },
  );
}

function normalizeStepParagraphs(html: string): string {
  return html.replace(
    /<p([^>]*)>(?:<strong>)?((?:Step|STEP|步骤)\s*\d+)(?:<\/strong>)?(?:\s*[：:.\-]\s*|\s+)([\s\S]*?)<\/p>(\s*<br\s*\/?>)?/gi,
    (_fullMatch, attributes: string, rawStepLabel: string, rawStepText: string) => {
      const stepLabel = rawStepLabel.trim();
      const stepText = rawStepText.trim();
      if (!stepText) {
        return _fullMatch;
      }

      const mergedAttributes = addClassToAttributes(attributes, 'step-row');
      return `<p${mergedAttributes}><span class="step-badge">${stepLabel}</span><span class="step-text">${stepText}</span></p>`;
    },
  );
}

function splitGuideHeading(innerHtml: string): { main: string; kicker: string } {
  const trimmed = innerHtml.trim();
  if (!trimmed) {
    return { main: '', kicker: '' };
  }

  const brParts = trimmed.split(/<br\s*\/?>/i);
  if (brParts.length >= 2) {
    return {
      main: brParts[0]!.trim(),
      kicker: brParts.slice(1).join(' ').trim(),
    };
  }

  for (const separator of ['｜', '|', '//', ' / ']) {
    const separatorIndex = trimmed.indexOf(separator);
    if (separatorIndex <= 0) continue;
    const main = trimmed.slice(0, separatorIndex).trim();
    const kicker = trimmed.slice(separatorIndex + separator.length).trim();
    if (main && kicker && kicker.length <= 42) {
      return { main, kicker };
    }
  }

  return { main: trimmed, kicker: '' };
}

function decorateGuideSections(html: string): string {
  let sectionIndex = 0;

  return html.replace(/<h2([^>]*)>([\s\S]*?)<\/h2>/gi, (fullMatch, attributes: string, innerHtml: string) => {
    if (/section-side|section-number|section-main/.test(innerHtml)) {
      return fullMatch;
    }

    sectionIndex += 1;
    const { main, kicker } = splitGuideHeading(innerHtml);
    const sectionNumber = String(sectionIndex).padStart(2, '0');
    const kickerHtml = kicker ? `<span class="section-kicker">${kicker}</span>` : '';

    return `<h2${attributes}><span class="section-side"><span class="section-number">${sectionNumber}</span><span class="section-part">PART</span></span><span class="section-copy"><span class="section-main">${main}</span>${kickerHtml}</span></h2>`;
  });
}

function normalizeGuideHtml(html: string): string {
  let normalized = ensureTagClass(html, 'h3', 'subsection-title');

  normalized = convertCommandParagraphs(normalized);
  normalized = normalizeStepParagraphs(normalized);
  normalized = decorateGuideSections(normalized);

  return normalized;
}

function normalizeHtmlForStyle(html: string, style: StyleName): string {
  const withHeadingClasses = normalizeHeadingClasses(html);

  if (style === 'part-guide') {
    return normalizeGuideHtml(withHeadingClasses);
  }

  return withHeadingClasses;
}

function resolveTemplatePath(style: StyleName): string {
  return path.join(SKILL_DIR, 'scripts', STYLE_TEMPLATES[style]);
}

async function generateHtml(
  inputPath: string,
  options: Options = {},
): Promise<string> {
  const parsed = parseMarkdown(inputPath);
  const apiConfig = getApiConfig(options);
  const style = normalizeStyleName(options.style);

  console.error(`🤖 Calling ${apiConfig.model} for intelligent styling...`);
  console.error(`🎨 Using style preset: ${style}`);

  const styledHtml = normalizeHtmlForStyle(
    await generateStyledHtmlWithLLM(parsed.content, apiConfig, style),
    style,
  );

  const displayTitle = (options.title ?? parsed.title ?? '').trim();
  const hasDisplayTitle = Boolean(displayTitle);
  const docTitle = hasDisplayTitle
    ? displayTitle
    : path.basename(inputPath, path.extname(inputPath));

  const templatePath = resolveTemplatePath(style);
  const template = fs.readFileSync(templatePath, 'utf-8');

  const titleMarker = '___TITLE_PLACEHOLDER___';
  let html = template.replaceAll('{{TITLE}}', titleMarker);
  html = html.replaceAll(titleMarker, escapeHtml(docTitle));

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
  --style <name>     Style preset: classic or part-guide (default: ${DEFAULT_STYLE})
  --api-url <url>    API URL (default: Comfly chat completions)
  --api-key <key>    API key (or use COMFLY_API_KEY env var)
  --model <name>     Model name (default: gemini-3-pro-preview-thinking-*)
  -h, --help         Show this help

Environment Variables:
  COMFLY_API_KEY         Comfly API key (required)
  COMFLY_API_BASE_URL    Comfly base URL (default: https://ai.comfly.chat)
  COMFLY_API_URL         Full Comfly chat completions URL (optional)
  COMFLY_CHAT_MODEL      Model name (default: gemini-3-pro-preview-thinking-*)
  COMFLY_MODEL           Alias for COMFLY_CHAT_MODEL
  AKI_CONTEXT_TO_HTML_DEFAULT_STYLE  Override default style (classic|part-guide)

Provider Config (user-level):
  ~/.config/comfly/config

Examples:
  npx -y bun generate-html.ts article.md
  npx -y bun generate-html.ts article.md --style part-guide
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
    } else if (arg === '--style' && args[i + 1]) {
      options.style = normalizeStyleName(args[++i]);
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

  const outputPath = options.output ?? path.join(path.dirname(inputPath), 'article.html');
  const html = await generateHtml(inputPath, options);

  fs.writeFileSync(outputPath, html, 'utf-8');

  console.error(`✓ HTML generated: ${outputPath}`);
  console.error('  Open in browser to view and export PNG slices');
}

main().catch((err) => {
  console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
  process.exit(1);
});
