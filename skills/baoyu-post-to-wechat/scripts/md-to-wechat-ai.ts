import fs from 'node:fs';
import path from 'node:path';
import { mkdir, writeFile } from 'node:fs/promises';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import process from 'node:process';

function loadEnvFile(dotenvPath: string): void {
  if (!fs.existsSync(dotenvPath)) return;
  const lines = fs.readFileSync(dotenvPath, 'utf-8').split('\n');
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const [key, ...rest] = line.split('=');
    const value = rest.join('=').trim().replace(/^['\"]|['\"]$/g, '');
    const k = key.trim();
    if (k && !process.env[k]) process.env[k] = value;
  }
}

function loadProxyEnv(): void {
  const scriptDir = path.dirname(new URL(import.meta.url).pathname);
  const skillDir = path.resolve(scriptDir, '..');
  const proxyPath = path.join(skillDir, '.proxy.env');
  loadEnvFile(proxyPath);
}

loadProxyEnv();

interface ImageInfo {
  placeholder: string;
  localPath: string;
  originalPath: string;
}

interface ParsedResult {
  title: string;
  author: string;
  summary: string;
  htmlPath: string;
  contentImages: ImageInfo[];
}

function getImageExtension(urlOrPath: string): string {
  const match = urlOrPath.match(/\.(jpg|jpeg|png|gif|webp)(\?|$)/i);
  return match ? match[1]!.toLowerCase() : 'png';
}

async function resolveImagePath(imagePath: string, baseDir: string, tempDir: string): Promise<string> {
  if (imagePath.startsWith('http://') || imagePath.startsWith('https://')) {
    const hash = createHash('md5').update(imagePath).digest('hex').slice(0, 8);
    const ext = getImageExtension(imagePath);
    const localPath = path.join(tempDir, `remote_${hash}.${ext}`);

    if (!fs.existsSync(localPath)) {
      // Download using curl or similar
      console.error(`[md-to-wechat-ai] Downloading: ${imagePath}`);
      const result = spawnSync('curl', ['-s', '-o', localPath, imagePath], { stdio: 'inherit' });
      if (result.status !== 0) {
        throw new Error(`Failed to download: ${imagePath}`);
      }
    }
    return localPath;
  }

  if (path.isAbsolute(imagePath)) {
    return imagePath;
  }

  return path.resolve(baseDir, imagePath);
}

function parseFrontmatter(content: string): { frontmatter: Record<string, string>; body: string } {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/);
  if (!match) return { frontmatter: {}, body: content };

  const frontmatter: Record<string, string> = {};
  const lines = match[1]!.split('\n');
  for (const line of lines) {
    const colonIdx = line.indexOf(':');
    if (colonIdx > 0) {
      const key = line.slice(0, colonIdx).trim();
      let value = line.slice(colonIdx + 1).trim();
      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1);
      }
      frontmatter[key] = value;
    }
  }

  return { frontmatter, body: match[2]! };
}

async function parseMarkdownWithAI(
  markdownPath: string,
  options?: { title?: string; tempDir?: string },
): Promise<ParsedResult> {
  const content = fs.readFileSync(markdownPath, 'utf-8');
  const baseDir = path.dirname(markdownPath);
  const tempDir = options?.tempDir ?? path.join(os.tmpdir(), 'wechat-article-images');

  await mkdir(tempDir, { recursive: true });

  const { frontmatter, body } = parseFrontmatter(content);

  let title = options?.title ?? frontmatter.title ?? '';
  if (!title) {
    const h1Match = body.match(/^#\s+(.+)$/m);
    if (h1Match) title = h1Match[1]!;
  }

  const defaultAuthor = 'Aki聊AI';
  const author = frontmatter.author ?? defaultAuthor;
  let summary = frontmatter.summary ?? frontmatter.description ?? '';

  if (!summary) {
    const lines = body.split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      if (trimmed.startsWith('#')) continue;
      if (trimmed.startsWith('![')) continue;
      if (trimmed.startsWith('>')) continue;
      if (trimmed.startsWith('-') || trimmed.startsWith('*')) continue;
      if (/^\d+\./.test(trimmed)) continue;

      const cleanText = trimmed
        .replace(/\*\*(.+?)\*\*/g, '$1')
        .replace(/\*(.+?)\*/g, '$1')
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
        .replace(/`([^`]+)`/g, '$1');

      if (cleanText.length > 20) {
        summary = cleanText.length > 120 ? cleanText.slice(0, 117) + '...' : cleanText;
        break;
      }
    }
  }

  // Extract images and replace with placeholders
  const images: Array<{ src: string; placeholder: string }> = [];
  let imageCounter = 0;

  const modifiedBody = body.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, alt, src) => {
    const placeholder = `IMAGE_PLACEHOLDER_${++imageCounter}`;
    images.push({ src, placeholder });
    return placeholder;
  });

  // Call aki-context-to-html's generate-html.ts
  const akiSkillDir = '/Users/aki/.claude/skills/aki-context-to-html';
  const generateHtmlScript = path.join(akiSkillDir, 'scripts/generate-html.ts');

  // Create temp markdown file with modified body
  const tempMdPath = path.join(tempDir, 'temp-article-ai.md');
  const tempMdContent = `---
title: ${title || ''}
author: ${author}
---

${modifiedBody}`;
  await writeFile(tempMdPath, tempMdContent, 'utf-8');

  const tempHtmlPath = path.join(tempDir, 'temp-article-ai.html');
  const bunBin = process.env.BUN_BIN || process.env.BUN_PATH || 'bun';

  console.error(`[md-to-wechat-ai] Calling AI for intelligent styling...`);
  const result = spawnSync(bunBin, [generateHtmlScript, tempMdPath, '--output', tempHtmlPath], {
    stdio: ['inherit', 'pipe', 'pipe'],
    cwd: baseDir,
  });

  if (result.status !== 0) {
    const stderr = result.stderr?.toString() || '';
    throw new Error(`AI styling failed: ${stderr}`);
  }

  if (!fs.existsSync(tempHtmlPath)) {
    throw new Error(`AI HTML not generated: ${tempHtmlPath}`);
  }

  // Now we need to convert the AI-generated HTML to WeChat-compatible format
  // and replace image placeholders back
  const aiHtml = fs.readFileSync(tempHtmlPath, 'utf-8');

  // Extract the content-area part
  const contentMatch = aiHtml.match(/<div class="content-area"[^>]*>([\s\S]*?)<\/div>/);
  let contentHtml = contentMatch ? contentMatch[1]! : aiHtml;

  // Replace image placeholders back to markdown-style for wechat-article.ts
  for (const img of images) {
    // The placeholder might be in various forms
    contentHtml = contentHtml.replace(new RegExp(img.placeholder, 'g'), `<p>${img.placeholder}</p>`);
  }

  // Build WeChat-compatible HTML with aki-style
  const wechatHtml = buildWeChatHtml(contentHtml, title);

  const finalHtmlPath = path.join(tempDir, 'temp-article.html');
  await writeFile(finalHtmlPath, wechatHtml, 'utf-8');

  const contentImages: ImageInfo[] = [];
  for (const img of images) {
    const localPath = await resolveImagePath(img.src, baseDir, tempDir);
    contentImages.push({
      placeholder: img.placeholder,
      localPath,
      originalPath: img.src,
    });
  }

  return {
    title,
    author,
    summary,
    htmlPath: finalHtmlPath,
    contentImages,
  };
}

function buildWeChatHtml(contentHtml: string, title: string): string {
  // Post-process content HTML to add inline styles for WeChat compatibility
  // WeChat strips many CSS properties, so we add inline styles to critical elements

  // ========================================
  // IMPORTANT: Remove <br> tags first to avoid double spacing
  // ========================================
  contentHtml = contentHtml.replace(/<\/p><br>/g, '</p>');
  contentHtml = contentHtml.replace(/<\/p>\s*<br>/g, '</p>');
  contentHtml = contentHtml.replace(/<\/ul><br>/g, '</ul>');
  contentHtml = contentHtml.replace(/<\/ol><br>/g, '</ol>');
  contentHtml = contentHtml.replace(/<\/blockquote><br>/g, '</blockquote>');

  // ========================================
  // HEADING STYLES - Hierarchical Design
  // ========================================
  // H1: Main title - largest, most prominent
  // H2: Section titles - with red left border
  // H3: Subsection titles - smaller, with lighter border
  // H4: Minor titles - even smaller
  // H5-H6: Maintain hierarchy

  // H1 - Article Title (36px, 900 weight)
  contentHtml = contentHtml.replace(/<h1 class="article-title">/g,
    '<h1 style="font-size: 36px; font-weight: 900; line-height: 1.4; margin-top: 48px; margin-bottom: 32px; color: #1a1a1a; text-align: center;">'
  );
  contentHtml = contentHtml.replace(/<h1>/g,
    '<h1 style="font-size: 36px; font-weight: 900; line-height: 1.4; margin-top: 48px; margin-bottom: 32px; color: #1a1a1a; text-align: center;">'
  );

  // H2 - Section Title (32px, 700 weight, 10px red border)
  contentHtml = contentHtml.replace(/<h2 class="section-title">/g,
    '<h2 style="font-size: 32px; font-weight: 700; color: #1a1a1a; margin-top: 48px; margin-bottom: 24px; padding-left: 15px; border-left: 10px solid #e53e3e; line-height: 1.2;">'
  );
  contentHtml = contentHtml.replace(/<h2>/g,
    '<h2 style="font-size: 32px; font-weight: 700; color: #1a1a1a; margin-top: 48px; margin-bottom: 24px; padding-left: 15px; border-left: 10px solid #e53e3e; line-height: 1.2;">'
  );

  // H3 - Subsection Title (26px, 700 weight, 6px red border)
  contentHtml = contentHtml.replace(/<h3>/g,
    '<h3 style="font-size: 26px; font-weight: 700; color: #2c3e50; margin-top: 36px; margin-bottom: 18px; padding-left: 12px; border-left: 6px solid #e53e3e; line-height: 1.3;">'
  );

  // H4 - Minor Title (22px, 600 weight, 4px gray border)
  contentHtml = contentHtml.replace(/<h4>/g,
    '<h4 style="font-size: 22px; font-weight: 600; color: #4a5568; margin-top: 28px; margin-bottom: 16px; padding-left: 10px; border-left: 4px solid #cbd5e0; line-height: 1.4;">'
  );

  // H5 - Small Title (20px, 600 weight, 2px gray border)
  contentHtml = contentHtml.replace(/<h5>/g,
    '<h5 style="font-size: 20px; font-weight: 600; color: #718096; margin-top: 20px; margin-bottom: 14px; padding-left: 8px; border-left: 2px solid #cbd5e0; line-height: 1.5;">'
  );

  // H6 - Smallest Title (18px, 500 weight)
  contentHtml = contentHtml.replace(/<h6>/g,
    '<h6 style="font-size: 18px; font-weight: 500; color: #718096; margin-top: 16px; margin-bottom: 12px; line-height: 1.5;">'
  );

  // ========================================
  // INLINE TEXT STYLES
  // ========================================

  // em - Red emphasis (for company names, terms)
  contentHtml = contentHtml.replace(/<em>/g,
    '<em style="color: #e53e3e; font-weight: 700; font-style: normal;">'
  );

  // mark - Yellow highlight with orange underline (for key insights)
  contentHtml = contentHtml.replace(/<mark>/g,
    '<mark style="background-color: #fff59d; color: #000000; font-weight: bold; border-bottom: 3px solid #ff9800; border-radius: 4px; padding: 2px 8px;">'
  );

  // strong - Bold (general emphasis)
  contentHtml = contentHtml.replace(/<strong>/g,
    '<strong style="font-weight: 700; color: #1a1a1a;">'
  );

  // ========================================
  // PARAGRAPH AND CONTENT STYLES
  // ========================================

  // p - Body paragraphs (20px for readability)
  contentHtml = contentHtml.replace(/<p>/g,
    '<p style="font-size: 20px; line-height: 1.8; color: #333; margin-top: 0; margin-bottom: 24px; text-align: justify;">'
  );

  // ul - Unordered lists
  contentHtml = contentHtml.replace(/<ul>/g,
    '<ul style="margin: 20px 0; padding-left: 30px; list-style-type: disc;">'
  );

  // li - List items (18px, slightly smaller than body)
  contentHtml = contentHtml.replace(/<li>/g,
    '<li style="font-size: 18px; line-height: 1.8; color: #333; margin-bottom: 14px; text-align: justify;">'
  );

  // blockquote - Block quotes (blue left border)
  contentHtml = contentHtml.replace(/<blockquote>/g,
    '<blockquote style="border-left: 8px solid #4a9eff; padding: 10px 0 10px 30px; font-style: italic; margin: 40px 0; font-size: 20px; background: rgba(74, 158, 255, 0.05); color: #475569;">'
  );

  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${title}</title>
  <style>
    /* Base styles - compatible with WeChat */
    body {
      margin: 0;
      padding: 24px;
      background: #ffffff;
    }

    #output {
      max-width: 860px;
      margin: 0 auto;
      font-family: -apple-system-font, BlinkMacSystemFont, Helvetica Neue, PingFang SC, Hiragino Sans GB, Microsoft YaHei UI, Microsoft YaHei, Arial, sans-serif;
      font-size: 20px;
      line-height: 1.8;
      text-align: left;
    }

    /* Images */
    img {
      display: block;
      max-width: 100%;
      margin: 0.1em auto 0.5em;
      border-radius: 4px;
    }
  </style>
</head>
<body>
  <div id="output">
    <section class="container">${contentHtml}</section>
  </div>
</body>
</html>`;
}

function printUsage(): never {
  console.log(`Convert Markdown to WeChat-ready HTML with AI styling (aki-context-to-html)

Usage:
  npx -y bun md-to-wechat-ai.ts <markdown_file> [options]

Options:
  --title <title>     Override title
  --help              Show this help

Output JSON format:
{
  "title": "Article Title",
  "author": "Aki聊AI",
  "summary": "Article summary",
  "htmlPath": "/tmp/wechat-article-images/temp-article.html",
  "contentImages": [
    {
      "placeholder": "IMAGE_PLACEHOLDER_1",
      "localPath": "/tmp/wechat-article-images/img.png",
      "originalPath": "imgs/image.png"
    }
  ]
}

Example:
  npx -y bun md-to-wechat-ai.ts article.md
`);
  process.exit(0);
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
    printUsage();
  }

  let markdownPath: string | undefined;
  let title: string | undefined;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i]!;
    if (arg === '--title' && args[i + 1]) {
      title = args[++i];
    } else if (!arg.startsWith('-')) {
      markdownPath = arg;
    }
  }

  if (!markdownPath) {
    console.error('Error: Markdown file path required');
    process.exit(1);
  }

  if (!fs.existsSync(markdownPath)) {
    console.error(`Error: File not found: ${markdownPath}`);
    process.exit(1);
  }

  const result = await parseMarkdownWithAI(markdownPath, { title });
  console.log(JSON.stringify(result, null, 2));
}

await main().catch((err) => {
  console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
  process.exit(1);
});
