import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { chromium, type Page } from 'playwright';

const GEMINI_URL = 'https://gemini.google.com/app';

export type GenerateOptions = {
  prompt: string;
  outputPath: string;
  profileDir: string;
  headless: boolean;
  timeoutMs: number;
  keepOpen: boolean;
};

function defaultProfileDir(): string {
  const base = process.env.GEMINI_MCP_PROFILE_DIR
    || path.join(os.homedir(), 'Library', 'Application Support', 'baoyu-skills', 'gemini-mcp', 'chrome-profile');
  return base;
}

function resolveProfileDir(inputDir?: string): { userDataDir: string; profileName?: string } {
  const raw = inputDir?.trim() || defaultProfileDir();
  const base = path.basename(raw);
  if (base === 'Default' || base.startsWith('Profile ') || base === 'System Profile') {
    return {
      userDataDir: path.dirname(raw),
      profileName: base,
    };
  }
  return { userDataDir: raw };
}

function ensureDir(filePath: string): void {
  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true });
}

async function waitForComposer(page: Page, timeoutMs: number): Promise<void> {
  const start = Date.now();
  const inputLocator = page.locator('textarea, div[contenteditable="true"]');
  while (Date.now() - start < timeoutMs) {
    if (page.url().includes('accounts.google.com')) {
      // Still on login page
      await page.waitForTimeout(1000);
      continue;
    }
    const count = await inputLocator.count();
    if (count > 0) {
      const visible = await inputLocator.first().isVisible().catch(() => false);
      if (visible) return;
    }
    await page.waitForTimeout(1000);
  }
  throw new Error('Composer not ready. Please login to Gemini in the opened browser window.');
}

async function sendPrompt(page: Page, prompt: string): Promise<void> {
  const inputLocator = page.locator('textarea, div[contenteditable="true"]').first();
  await inputLocator.click({ timeout: 10_000 });
  const tagName = await inputLocator.evaluate((el) => el.tagName.toLowerCase());
  if (tagName === 'textarea') {
    await inputLocator.fill(prompt);
  } else {
    await page.keyboard.type(prompt, { delay: 10 });
  }
  await page.keyboard.press('Enter');
}

async function maybeSelectImageMode(page: Page): Promise<void> {
  const selectors = [
    'button:has-text("Image")',
    'button:has-text("Images")',
    'button:has-text("Create image")',
    'button:has-text("Generate image")',
    'button:has-text("图片")',
    'button:has-text("图像")',
    'button:has-text("生成图像")',
    'div[role="button"]:has-text("Image")',
    'div[role="button"]:has-text("图片")',
  ];
  for (const selector of selectors) {
    const locator = page.locator(selector).first();
    const visible = await locator.isVisible().catch(() => false);
    if (visible) {
      await locator.click().catch(() => undefined);
      return;
    }
  }
}

async function countLargeImages(page: Page): Promise<number> {
  return page.evaluate(() => {
    const minSize = 256;
    const images = Array.from(document.querySelectorAll('img'))
      .filter((img) => {
        const w = (img as HTMLImageElement).naturalWidth || (img as HTMLImageElement).width || 0;
        const h = (img as HTMLImageElement).naturalHeight || (img as HTMLImageElement).height || 0;
        return w >= minSize && h >= minSize;
      });
    const canvases = Array.from(document.querySelectorAll('canvas'))
      .filter((canvas) => canvas.width >= minSize && canvas.height >= minSize);
    return images.length + canvases.length;
  });
}

async function waitForImage(page: Page, timeoutMs: number): Promise<string> {
  const before = await countLargeImages(page);
  await page.waitForFunction(
    (count) => {
      const minSize = 256;
      const images = Array.from(document.querySelectorAll('img'))
        .filter((img) => {
          const w = (img as HTMLImageElement).naturalWidth || (img as HTMLImageElement).width || 0;
          const h = (img as HTMLImageElement).naturalHeight || (img as HTMLImageElement).height || 0;
          return w >= minSize && h >= minSize;
        });
      const canvases = Array.from(document.querySelectorAll('canvas'))
        .filter((canvas) => canvas.width >= minSize && canvas.height >= minSize);
      return images.length + canvases.length > count;
    },
    before,
    { timeout: timeoutMs }
  );

  const src = await page.evaluate(() => {
    const minSize = 256;
    const images = Array.from(document.querySelectorAll('img'))
      .filter((img) => {
        const w = (img as HTMLImageElement).naturalWidth || (img as HTMLImageElement).width || 0;
        const h = (img as HTMLImageElement).naturalHeight || (img as HTMLImageElement).height || 0;
        return w >= minSize && h >= minSize;
      });
    if (images.length > 0) {
      const last = images[images.length - 1] as HTMLImageElement;
      return last.currentSrc || last.src || '';
    }
    const canvases = Array.from(document.querySelectorAll('canvas'))
      .filter((canvas) => canvas.width >= minSize && canvas.height >= minSize);
    if (canvases.length > 0) {
      try {
        return (canvases[canvases.length - 1] as HTMLCanvasElement).toDataURL('image/png');
      } catch {
        return '';
      }
    }
    return '';
  });
  if (!src) throw new Error('Image src not found.');
  return src;
}

async function downloadImage(page: Page, src: string, outputPath: string): Promise<void> {
  if (src.startsWith('data:')) {
    const base64 = src.split(',')[1] || '';
    const buf = Buffer.from(base64, 'base64');
    ensureDir(outputPath);
    fs.writeFileSync(outputPath, buf);
    return;
  }

  if (src.startsWith('blob:')) {
    const bytes = await page.evaluate(async (url) => {
      const res = await fetch(url);
      const arr = new Uint8Array(await res.arrayBuffer());
      return Array.from(arr);
    }, src);
    ensureDir(outputPath);
    fs.writeFileSync(outputPath, Buffer.from(bytes));
    return;
  }

  const res = await fetch(src);
  if (!res.ok) throw new Error(`Image download failed: ${res.status}`);
  const arrayBuffer = await res.arrayBuffer();
  ensureDir(outputPath);
  fs.writeFileSync(outputPath, Buffer.from(arrayBuffer));
}

export async function generateImage(opts: GenerateOptions): Promise<{ outputPath: string; imageUrl: string } > {
  const profile = resolveProfileDir(opts.profileDir);
  const useChromeChannel = process.env.GEMINI_MCP_USE_CHROME === '1'
    || profile.userDataDir.includes('/Google/Chrome');
  const context = await chromium.launchPersistentContext(profile.userDataDir, {
    headless: opts.headless,
    viewport: { width: 1280, height: 900 },
    channel: useChromeChannel ? 'chrome' : undefined,
    args: [
      ...(profile.profileName ? [`--profile-directory=${profile.profileName}`] : []),
      '--disable-blink-features=AutomationControlled',
    ],
    ignoreDefaultArgs: ['--use-mock-keychain', '--password-store=basic', '--enable-automation'],
  });

  const page = context.pages()[0] ?? await context.newPage();
  page.setDefaultTimeout(opts.timeoutMs);
  page.setDefaultNavigationTimeout(opts.timeoutMs);
  await page.goto(GEMINI_URL, { waitUntil: 'domcontentloaded' });
  await waitForComposer(page, opts.timeoutMs);
  await maybeSelectImageMode(page);

  await sendPrompt(page, opts.prompt);
  let imageUrl = '';
  try {
    imageUrl = await waitForImage(page, opts.timeoutMs);
  } catch (err) {
    const debugPath = `${opts.outputPath}.debug.png`;
    await page.screenshot({ path: debugPath, fullPage: true }).catch(() => undefined);
    throw err;
  }
  await downloadImage(page, imageUrl, opts.outputPath);

  if (!opts.keepOpen) {
    await context.close();
  }

  return { outputPath: opts.outputPath, imageUrl };
}

function parseArgs(argv: string[]): Record<string, string | boolean> {
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
  return out;
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const prompt = String(args.prompt || '').trim();
  const promptFile = args['prompt-file'] ? String(args['prompt-file']) : '';

  let finalPrompt = prompt;
  if (!finalPrompt && promptFile) {
    finalPrompt = fs.readFileSync(promptFile, 'utf-8').trim();
  }
  if (!finalPrompt) {
    throw new Error('Missing --prompt or --prompt-file');
  }

  const outputPath = String(args.out || args.output || path.join(process.cwd(), 'gemini-image.png'));
  const profileDir = String(args.profile || defaultProfileDir());
  const headless = args.headless ? true : false;
  const keepOpen = args['keep-open'] ? true : false;
  const timeoutMs = Number(args.timeout || 180_000);

  const result = await generateImage({
    prompt: finalPrompt,
    outputPath,
    profileDir,
    headless,
    timeoutMs,
    keepOpen,
  });

  console.log(JSON.stringify(result, null, 2));
}

if (import.meta.main) {
  main().catch((err) => {
    console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  });
}
