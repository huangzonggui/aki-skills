#!/usr/bin/env bun
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { chromium, type Page } from 'playwright';

const WECHAT_HOST = 'mp.weixin.qq.com';

export type FetchOptions = {
  url: string;
  outputDir: string;
  downloadImages: boolean;
  timeout: number;
  headless: boolean;
  profileDir?: string;
};

interface ArticleData {
  title: string;
  author: string;
  publishTime: string;
  content: string;
  images: ImageInfo[];
}

interface ImageInfo {
  src: string;
  localPath?: string;
  alt: string;
}

function sanitizeFilename(name: string): string {
  return name
    .replace(/[\/\\:*?"<>|]/g, '_')
    .replace(/\s+/g, '_')
    .slice(0, 100);
}

function extractBiz(url: string): string {
  const match = url.match(/__biz=([^&]+)/);
  return match ? match[1] : 'unknown';
}

async function extractArticleData(page: Page): Promise<ArticleData> {
  const data = await page.evaluate(() => {
    // Title
    const titleEl = document.querySelector('h1.rich_media_title') ||
                    document.querySelector('#activity-name') ||
                    document.querySelector('.rich_media_title');
    const title = titleEl?.textContent?.trim() || 'Untitled';

    // Author
    const authorEl = document.querySelector('.rich_media_meta_text') ||
                     document.querySelector('#meta_content .rich_media_meta_text');
    const author = authorEl?.textContent?.trim() || '';

    // Publish time
    const timeEl = document.querySelector('#publish_time') ||
                   document.querySelector('.rich_media_meta.rich_media_meta_text');
    const publishTime = timeEl?.textContent?.trim() || '';

    // Content
    const contentEl = document.querySelector('#js_content') ||
                      document.querySelector('.rich_media_content');
    let content = '';

    if (contentEl) {
      // Process content: extract text and images
      const images: { src: string; alt: string }[] = [];
      const clones = contentEl.cloneNode(true) as HTMLElement;

      // Find all images
      clones.querySelectorAll('img').forEach((img, idx) => {
        const src = img.getAttribute('data-src') ||
                    img.getAttribute('data-original') ||
                    img.src || '';
        const alt = img.alt || `Image ${idx + 1}`;
        if (src) {
          images.push({ src, alt });
          // Replace with markdown image reference
          const replacement = document.createElement('p');
          const filename = src.split('/').pop()?.split('?')[0] || 'image.jpg';
          replacement.textContent = `![${alt}](${filename})`;
          img.replaceWith(replacement);
        }
      });

      // Get text content
      content = clones.innerHTML || clones.textContent || '';
    }

    // Extract images
    const images: { src: string; alt: string }[] = [];
    contentEl?.querySelectorAll('img').forEach((img, idx) => {
      const src = img.getAttribute('data-src') ||
                  img.getAttribute('data-original') ||
                  img.src || '';
      const alt = img.alt || `Image ${idx + 1}`;
      if (src && !src.includes('placeholder')) {
        images.push({ src, alt });
      }
    });

    return {
      title,
      author,
      publishTime,
      content,
      images,
    };
  });

  return data;
}

async function downloadImage(page: Page, src: string, outputPath: string): Promise<void> {
  const dir = path.dirname(outputPath);
  fs.mkdirSync(dir, { recursive: true });

  try {
    // Try to download through page context to avoid CORS
    const buffer = await page.evaluate(async (url) => {
      const res = await fetch(url);
      const blob = await res.blob();
      const arrayBuffer = await blob.arrayBuffer();
      return Array.from(new Uint8Array(arrayBuffer));
    }, src);

    fs.writeFileSync(outputPath, Buffer.from(buffer));
  } catch {
    // Fallback: download with Node.js fetch
    try {
      const res = await fetch(src);
      const arrayBuffer = await res.arrayBuffer();
      fs.writeFileSync(outputPath, Buffer.from(arrayBuffer));
    } catch (err) {
      console.warn(`Failed to download image: ${src}`);
    }
  }
}

async function fetchArticle(opts: FetchOptions): Promise<string> {
  const { url, outputDir, downloadImages, timeout, headless, profileDir } = opts;

  // Setup browser
  const launchOptions: any = {
    headless,
    args: [
      '--disable-blink-features=AutomationControlled',
      '--no-sandbox',
      '--disable-setuid-sandbox',
    ],
  };

  let context;
  if (profileDir) {
    context = await chromium.launchPersistentContext(profileDir, {
      ...launchOptions,
      viewport: { width: 1280, height: 900 },
    });
  } else {
    const browser = await chromium.launch(launchOptions);
    context = await browser.newContext({
      viewport: { width: 1280, height: 900 },
      userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    });
  }

  const page = context.pages()[0] || await context.newPage();
  page.setDefaultTimeout(timeout);

  try {
    // Navigate to article
    console.log(`Fetching: ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout });

    // Wait for content to load
    await page.waitForSelector('#js_content, .rich_media_content', { timeout })
      .catch(() => {
        console.warn('Content selector not found, attempting to extract anyway...');
      });

    // Extract article data
    const data = await extractArticleData(page);

    // Generate output filename
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const safeTitle = sanitizeFilename(data.title);
    const filename = `${timestamp}_${safeTitle}.md`;
    const outputPath = path.join(outputDir, filename);

    // Download images if requested
    const imagesDir = path.join(outputDir, 'images');
    const imageMap = new Map<string, string>();

    if (downloadImages && data.images.length > 0) {
      fs.mkdirSync(imagesDir, { recursive: true });

      for (let i = 0; i < data.images.length; i++) {
        const img = data.images[i];
        const ext = path.extname(new URL(img.src).pathname) || '.jpg';
        const imgFilename = `${timestamp}_img_${i + 1}${ext}`;
        const imgPath = path.join(imagesDir, imgFilename);

        console.log(`Downloading image ${i + 1}/${data.images.length}...`);
        await downloadImage(page, img.src, imgPath);

        imageMap.set(img.src, `images/${imgFilename}`);
      }
    }

    // Generate markdown
    let markdown = `# ${data.title}\n\n`;
    if (data.author) markdown += `**作者**: ${data.author}\n\n`;
    if (data.publishTime) markdown += `**发布时间**: ${data.publishTime}\n\n`;
    markdown += `**原文链接**: ${url}\n\n`;
    markdown += `---\n\n`;

    // Process content with image replacements
    let processedContent = data.content;
    data.images.forEach((img, idx) => {
      const localPath = imageMap.get(img.src);
      if (localPath) {
        const imgRegex = new RegExp(`!\\[.*?\\]\\(${path.basename(img.src)}|<img[^>]*src="${img.src}"[^>]*>`, 'gi');
        processedContent = processedContent.replace(imgRegex, `![${img.alt}](${localPath})`);
      }
    });

    // Convert HTML to markdown-like format
    processedContent = processedContent
      .replace(/<section[^>]*>/gi, '')
      .replace(/<\/section>/gi, '\n\n')
      .replace(/<p[^>]*>/gi, '')
      .replace(/<\/p>/gi, '\n\n')
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<strong[^>]*>/gi, '**')
      .replace(/<\/strong>/gi, '**')
      .replace(/<em[^>]*>/gi, '*')
      .replace(/<\/em>/gi, '*')
      .replace(/<h([1-6])[^>]*>/gi, (match, level) => '\n' + '#'.repeat(parseInt(level)) + ' ')
      .replace(/<\/h[1-6]>/gi, '\n\n')
      .replace(/<[^>]+>/g, '') // Remove remaining tags
      .replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/\n{3,}/g, '\n\n') // Normalize line breaks
      .trim();

    markdown += processedContent;

    // Write markdown file
    fs.mkdirSync(outputDir, { recursive: true });
    fs.writeFileSync(outputPath, markdown, 'utf-8');

    console.log(`\nSaved to: ${outputPath}`);
    console.log(`Images: ${data.images.length}`);

    return outputPath;

  } finally {
    await context.close();
  }
}

function parseArgs(argv: string[]): FetchOptions & { help: boolean } {
  const out: Record<string, string | boolean> = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i] ?? '';
    if (arg.startsWith('--')) {
      const key = arg.replace(/^--/, '');
      const next = argv[i + 1];
      if (next && !next.startsWith('--')) {
        out[key] = next;
        i += 1;
      } else {
        out[key] = true;
      }
    }
  }

  const url = String(out._ || argv[0] || '');
  if (out.help || out.h || !url) {
    console.log(`
WeChat Article Fetcher

Usage:
  bun fetch.ts <url> [options]

Arguments:
  url                    WeChat article URL (mp.weixin.qq.com)

Options:
  --output <dir>         Output directory (default: ./output)
  --no-images            Skip image download
  --timeout <ms>         Page load timeout in ms (default: 30000)
  --headless             Run in headless mode (default: true)
  --profile <path>       Chrome profile path for login state
  --help, -h             Show this message

Examples:
  # Fetch single article
  bun fetch.ts "https://mp.weixin.qq.com/s/xxxxx"

  # Fetch with custom output
  bun fetch.ts "https://mp.weixin.qq.com/s/xxxxx" --output "./articles"

  # Fetch without images
  bun fetch.ts "https://mp.weixin.qq.com/s/xxxxx" --no-images
`);
    process.exit(0);
  }

  return {
    url,
    outputDir: String(out.output || out.out || './output'),
    downloadImages: !out['no-images'],
    timeout: Number(out.timeout || 30000),
    headless: out.headless !== 'false',
    profileDir: String(out.profile || ''),
    help: false,
  };
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));

  if (args.help) {
    return;
  }

  const result = await fetchArticle(args);
  console.log(`\n✓ Successfully fetched article`);
}

if (import.meta.main) {
  main().catch((err) => {
    console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  });
}

export { fetchArticle };
