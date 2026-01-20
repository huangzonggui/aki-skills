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
}

interface ParsedContent {
  title: string;
  content: string;
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

function convertMarkdownToHtml(markdown: string): string {
  const lines = markdown.split('\n');
  const blocks: string[] = [];
  let inList = false;
  let listItems: string[] = [];
  let listType: 'ul' | 'ol' = 'ul';

  const flushList = () => {
    if (listItems.length > 0) {
      const tag = listType === 'ol' ? 'ol' : 'ul';
      blocks.push(`<${tag}>${listItems.map((item) => `<li>${item}</li>`).join('')}</${tag}>`);
      listItems = [];
      inList = false;
    }
  };

  const processInline = (text: string): string => {
    // Bold
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Highlight/Mark (for manual highlighting)
    text = text.replace(/==(.+?)==/g, '<mark>$1</mark>');

    // Italic
    text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Links
    text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

    // Inline code
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');

    return text;
  };

  for (const line of lines) {
    // Empty line
    if (line.trim() === '') {
      flushList();
      continue;
    }

    // Heading (H2-H6 become h2, H1 is skipped as it's the title)
    const headingMatch = line.match(/^(#{2,6})\s+(.+)$/);
    if (headingMatch) {
      flushList();
      blocks.push(`<h2>${processInline(headingMatch[2]!)}</h2>`);
      continue;
    }

    // Blockquote
    if (line.startsWith('> ')) {
      flushList();
      blocks.push(`<blockquote>${processInline(line.slice(2))}</blockquote>`);
      continue;
    }

    // Unordered list
    const ulMatch = line.match(/^[-*]\s+(.+)$/);
    if (ulMatch) {
      if (!inList || listType !== 'ul') {
        flushList();
        inList = true;
        listType = 'ul';
      }
      listItems.push(processInline(ulMatch[1]!));
      continue;
    }

    // Ordered list
    const olMatch = line.match(/^\d+\.\s+(.+)$/);
    if (olMatch) {
      if (!inList || listType !== 'ol') {
        flushList();
        inList = true;
        listType = 'ol';
      }
      listItems.push(processInline(olMatch[1]!));
      continue;
    }

    // Horizontal rule
    if (/^[-*_]{3,}\s*$/.test(line)) {
      flushList();
      blocks.push('<hr>');
      continue;
    }

    // Regular paragraph
    flushList();
    blocks.push(`<p>${processInline(line)}</p>`);
  }

  flushList();

  return blocks.join('\n');
}

async function generateHtml(
  inputPath: string,
  options: Options = {},
): Promise<string> {
  // Parse input
  const parsed = parseMarkdown(inputPath);

  // Convert markdown to HTML
  const htmlBody = convertMarkdownToHtml(parsed.content);

  // Override title if provided
  const title = options.title ?? parsed.title;

  // Read template
  const templatePath = path.join(SKILL_DIR, 'scripts', 'template.html');
  const template = fs.readFileSync(templatePath, 'utf-8');

  // Replace placeholders
  // Default width is 600px as per requirements
  const width = options.width ?? 600;
  const ratio = options.ratio ?? '3:4';

  let html = template
    .replace('{{TITLE}}', escapeHtml(title))
    .replace('{{CONTENT}}', htmlBody)
    .replace('{{RATIO}}', ratio)
    .replace('{{TARGET_WIDTH}}', String(width));

  // Note: TARGET_HEIGHT is no longer used in template (hardcoded as 800/1000)
  // But we keep it for backwards compatibility
  const targetHeight = ratio === '3:5' ? 1000 : 800;
  html = html.replace('{{TARGET_HEIGHT}}', String(targetHeight));

  return html;
}

function printUsage(): never {
  console.log(`
Aki Context to HTML - Generate styled HTML with smart highlights

Usage:
  npx -y bun generate-html.ts <input.md> [options]

Options:
  --output <path>    Output HTML path (default: <input-dir>/article.html)
  --ratio <ratio>    Aspect ratio: 3:4 or 3:5 (default: 3:4)
  --width <px>       Target width in pixels (default: 600)
  --title <text>     Override article title
  -h, --help         Show this help

Examples:
  npx -y bun generate-html.ts article.md
  npx -y bun generate-html.ts article.md --output ./output.html
  npx -y bun generate-html.ts article.md --ratio 3:5 --width 800

Note: Default width is 600px for optimal readability. Output sizes:
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
