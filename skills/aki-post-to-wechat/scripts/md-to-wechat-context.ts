import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import process from 'node:process';

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

interface ParseOptions {
  title?: string;
  tempDir?: string;
  htmlOutPath?: string;
}

function loadEnvFile(dotenvPath: string): void {
  if (!fs.existsSync(dotenvPath)) return;
  const lines = fs.readFileSync(dotenvPath, 'utf-8').split('\n');
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const [key, ...rest] = line.split('=');
    const value = rest.join('=').trim().replace(/^['"]|['"]$/g, '');
    const k = key.trim();
    if (k && !process.env[k]) process.env[k] = value;
  }
}

function loadProxyEnv(): void {
  const scriptDir = path.dirname(new URL(import.meta.url).pathname);
  const skillDir = path.resolve(scriptDir, '..');
  loadEnvFile(path.join(skillDir, '.proxy.env'));
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
      console.error(`[md-to-wechat-context] Downloading: ${imagePath}`);
      const result = spawnSync('curl', ['-s', '-o', localPath, imagePath], { stdio: 'inherit' });
      if (result.status !== 0) throw new Error(`Failed to download: ${imagePath}`);
    }
    return localPath;
  }

  if (path.isAbsolute(imagePath)) return imagePath;
  return path.resolve(baseDir, imagePath);
}

function parseFrontmatter(content: string): { frontmatter: Record<string, string>; body: string } {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/);
  if (!match) return { frontmatter: {}, body: content };

  const frontmatter: Record<string, string> = {};
  for (const raw of match[1]!.split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    const colonIdx = line.indexOf(':');
    if (colonIdx <= 0) continue;
    const key = line.slice(0, colonIdx).trim();
    let value = line.slice(colonIdx + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    frontmatter[key] = value;
  }

  return { frontmatter, body: match[2]! };
}

function inferSummary(body: string): string {
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
      return cleanText.length > 120 ? `${cleanText.slice(0, 117)}...` : cleanText;
    }
  }
  return '';
}

function findContextToHtmlScript(): string {
  const candidates = [
    process.env.AKI_CONTEXT_TO_HTML_DIR,
    process.env.CONTEXT_TO_HTML_DIR,
    '/Users/aki/.codex/skills/aki-context-to-html',
    '/Users/aki/Development/code/aki-skills/skills/aki-context-to-html',
    '/Users/aki/.claude/skills/aki-context-to-html',
    path.join(os.homedir(), '.codex/skills/context-to-html'),
  ].filter((v): v is string => Boolean(v));

  for (const dir of candidates) {
    const script = path.join(dir, 'scripts', 'generate-html.ts');
    if (fs.existsSync(script)) return script;
  }

  throw new Error(
    'Cannot find aki-context-to-html/scripts/generate-html.ts. Set AKI_CONTEXT_TO_HTML_DIR or CONTEXT_TO_HTML_DIR.',
  );
}

function extractContentArea(html: string): string {
  const match = html.match(/<div[^>]*class=["'][^"']*content-area[^"']*["'][^>]*>([\s\S]*?)<\/div>/i);
  return match ? match[1]! : html;
}

function inlineWechatStyles(contentHtml: string): string {
  let html = contentHtml;

  // Normalize excessive line breaks produced by template conversion.
  html = html.replace(/<\/p>\s*<br\s*\/?>/gi, '</p>');
  html = html.replace(/<\/ul>\s*<br\s*\/?>/gi, '</ul>');
  html = html.replace(/<\/ol>\s*<br\s*\/?>/gi, '</ol>');
  html = html.replace(/<\/blockquote>\s*<br\s*\/?>/gi, '</blockquote>');

  // Headings
  html = html.replace(
    /<h1(?![^>]*style=)[^>]*>/gi,
    '<h1 style="font-size: 34px; font-weight: 900; line-height: 1.4; margin-top: 46px; margin-bottom: 30px; color: #1a1a1a; text-align: center;">',
  );
  html = html.replace(
    /<h2(?![^>]*style=)[^>]*>/gi,
    '<h2 style="font-size: 30px; font-weight: 700; color: #1a1a1a; margin-top: 42px; margin-bottom: 22px; padding-left: 14px; border-left: 8px solid #e53e3e; line-height: 1.3;">',
  );
  html = html.replace(
    /<h3(?![^>]*style=)[^>]*>/gi,
    '<h3 style="font-size: 24px; font-weight: 700; color: #2c3e50; margin-top: 34px; margin-bottom: 16px; padding-left: 10px; border-left: 4px solid #e53e3e; line-height: 1.4;">',
  );

  // Inline emphasis styles
  html = html.replace(/<em(?![^>]*style=)[^>]*>/gi, '<em style="color: #e53e3e; font-weight: 700; font-style: normal;">');
  html = html.replace(
    /<mark(?![^>]*style=)[^>]*>/gi,
    '<mark style="background-color: #fff59d; color: #000000; font-weight: 700; border-bottom: 2px solid #ff9800; border-radius: 4px; padding: 2px 8px;">',
  );
  html = html.replace(/<strong(?![^>]*style=)[^>]*>/gi, '<strong style="font-weight: 700; color: #1a1a1a;">');

  // Paragraph/list/quote body styles
  html = html.replace(
    /<p(?![^>]*style=)[^>]*>/gi,
    '<p style="font-size: 18px; line-height: 1.9; color: #333; margin-top: 0; margin-bottom: 20px; text-align: justify;">',
  );
  html = html.replace(/<ul(?![^>]*style=)[^>]*>/gi, '<ul style="margin: 16px 0 18px; padding-left: 28px;">');
  html = html.replace(/<ol(?![^>]*style=)[^>]*>/gi, '<ol style="margin: 16px 0 18px; padding-left: 28px;">');
  html = html.replace(
    /<li(?![^>]*style=)[^>]*>/gi,
    '<li style="font-size: 17px; line-height: 1.85; color: #333; margin-bottom: 12px; text-align: justify;">',
  );
  html = html.replace(
    /<blockquote(?![^>]*style=)[^>]*>/gi,
    '<blockquote style="border-left: 6px solid #4a9eff; padding: 10px 0 10px 20px; margin: 28px 0; background: rgba(74, 158, 255, 0.08); color: #475569; font-size: 18px; line-height: 1.9;">',
  );

  // Images
  html = html.replace(/<img(?![^>]*style=)([^>]*)>/gi, '<img$1 style="display: block; max-width: 100%; margin: 0.2em auto 0.6em; border-radius: 4px;">');

  return html;
}

function normalizePlaceholderBlocks(contentHtml: string): string {
  let html = contentHtml;

  // Convert any plain placeholder token to a standalone paragraph.
  html = html.replace(/\bIMAGE_PLACEHOLDER_\d+\b/g, (m) => `<p>${m}</p>`);

  // Collapse accidental nested <p><p>PLACEHOLDER</p></p>.
  html = html.replace(/<p[^>]*>\s*<p>\s*(IMAGE_PLACEHOLDER_\d+)\s*<\/p>\s*<\/p>/gi, '<p>$1</p>');
  html = html.replace(/<p>\s*(IMAGE_PLACEHOLDER_\d+)\s*<\/p>\s*<p>\s*\1\s*<\/p>/gi, '<p>$1</p>');

  return html;
}

function buildWeChatHtml(contentHtml: string, title: string): string {
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${title}</title>
  <style>
    body { margin: 0; padding: 24px; background: #ffffff; }
    #output {
      max-width: 860px;
      margin: 0 auto;
      font-family: -apple-system-font, BlinkMacSystemFont, Helvetica Neue, PingFang SC, Hiragino Sans GB, Microsoft YaHei UI, Microsoft YaHei, Arial, sans-serif;
      font-size: 18px;
      line-height: 1.85;
      color: #333;
    }
    #output img { display: block; max-width: 100%; margin: 0.2em auto 0.6em; border-radius: 4px; }
  </style>
</head>
<body>
  <div id="output">
    <section class="content-area">${contentHtml}</section>
  </div>
</body>
</html>`;
}

async function parseMarkdownWithContext(markdownPath: string, options?: ParseOptions): Promise<ParsedResult> {
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

  const author = frontmatter.author ?? 'Aki聊AI';
  const summary = frontmatter.summary ?? frontmatter.description ?? inferSummary(body);

  const images: Array<{ src: string; placeholder: string }> = [];
  let imageCounter = 0;
  const modifiedBody = body.replace(/!\[[^\]]*\]\(([^)]+)\)/g, (_match, src) => {
    const placeholder = `IMAGE_PLACEHOLDER_${++imageCounter}`;
    images.push({ src, placeholder });
    return placeholder;
  });

  const tempMdPath = path.join(tempDir, 'temp-article-context.md');
  const tempMdContent = `---\ntitle: ${title || ''}\nauthor: ${author}\n---\n\n${modifiedBody}`;
  await writeFile(tempMdPath, tempMdContent, 'utf-8');

  const tempHtmlPath = path.join(tempDir, 'temp-article-context.html');
  const generateHtmlScript = findContextToHtmlScript();
  const bunBin = process.env.BUN_BIN || process.env.BUN_PATH || 'bun';
  const modelOverride = process.env.COMFLY_CHAT_MODEL || process.env.COMFLY_MODEL || '';
  const generateArgs = [generateHtmlScript, tempMdPath, '--output', tempHtmlPath];
  if (modelOverride) generateArgs.push('--model', modelOverride);

  console.error(`[md-to-wechat-context] Calling aki-context-to-html${modelOverride ? ` with model: ${modelOverride}` : ''}...`);
  const result = spawnSync(bunBin, generateArgs, {
    stdio: ['inherit', 'pipe', 'pipe'],
    cwd: baseDir,
  });

  if (result.status !== 0) {
    const stderr = result.stderr?.toString() || '';
    throw new Error(`context-to-html failed: ${stderr}`);
  }

  if (!fs.existsSync(tempHtmlPath)) {
    throw new Error(`Generated HTML not found: ${tempHtmlPath}`);
  }

  const generatedHtml = fs.readFileSync(tempHtmlPath, 'utf-8');
  let contentHtml = extractContentArea(generatedHtml);

  // WeChat page title is filled separately by wechat-article.ts.
  // Remove body H1 to avoid duplicated title in article content.
  contentHtml = contentHtml.replace(/<h1[^>]*>[\s\S]*?<\/h1>/gi, '');

  contentHtml = normalizePlaceholderBlocks(contentHtml);
  contentHtml = inlineWechatStyles(contentHtml);

  const defaultHtmlPath = path.join(baseDir, `${path.parse(markdownPath).name}.wechat.html`);
  const finalHtmlPath = path.resolve(options?.htmlOutPath ?? defaultHtmlPath);
  await mkdir(path.dirname(finalHtmlPath), { recursive: true });
  await writeFile(finalHtmlPath, buildWeChatHtml(contentHtml, title), 'utf-8');
  console.error(`[md-to-wechat-context] HTML saved: ${finalHtmlPath}`);

  const contentImages: ImageInfo[] = [];
  for (const img of images) {
    const localPath = await resolveImagePath(img.src, baseDir, tempDir);
    contentImages.push({
      placeholder: img.placeholder,
      localPath,
      originalPath: img.src,
    });
  }

  return { title, author, summary, htmlPath: finalHtmlPath, contentImages };
}

function printUsage(): never {
  console.log(`Convert Markdown to WeChat-ready HTML using aki-context-to-html\n\nUsage:\n  npx -y bun md-to-wechat-context.ts <markdown_file> [options]\n\nOptions:\n  --title <title>       Override title\n  --html-out <path>     Output final WeChat HTML path (default: <markdown_dir>/<name>.wechat.html)\n  --temp-dir <path>     Temp working directory for intermediate files/images\n  --help                Show this help\n`);
  process.exit(0);
}

async function main(): Promise<void> {
  loadProxyEnv();

  const args = process.argv.slice(2);
  if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
    printUsage();
  }

  let markdownPath: string | undefined;
  let title: string | undefined;
  let htmlOutPath: string | undefined;
  let tempDir: string | undefined;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i]!;
    if (arg === '--title' && args[i + 1]) {
      title = args[++i];
    } else if (arg === '--html-out' && args[i + 1]) {
      htmlOutPath = args[++i];
    } else if (arg === '--temp-dir' && args[i + 1]) {
      tempDir = args[++i];
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

  const result = await parseMarkdownWithContext(markdownPath, { title, htmlOutPath, tempDir });
  console.log(JSON.stringify(result, null, 2));
}

await main().catch((err) => {
  console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
  process.exit(1);
});
