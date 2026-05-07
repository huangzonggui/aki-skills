import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { chromium, type Locator, type Page } from 'playwright';

const GEMINI_URL = 'https://gemini.google.com/app';

export type GenerateOptions = {
  prompt: string;
  outputPath: string;
  profileDir: string;
  cdpUrl?: string;
  headless: boolean;
  timeoutMs: number;
  keepOpen: boolean;
};

function defaultProfileDir(): string {
  const base = process.env.GEMINI_MCP_PROFILE_DIR
    || path.join(os.homedir(), 'Library', 'Application Support', 'aki-skills', 'gemini-mcp', 'chrome-profile');
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
  while (Date.now() - start < timeoutMs) {
    if (page.url().includes('accounts.google.com')) {
      const waitMs = Date.now() - start;
      if (waitMs > 15_000) {
        throw new Error('Not logged in to Gemini profile. Please login first to use Pro model.');
      }
      await page.waitForTimeout(1000);
      continue;
    }
    const inputLocator = await composerLocator(page);
    const visible = await inputLocator.isVisible().catch(() => false);
    if (visible) {
      return;
    }
    await page.waitForTimeout(1000);
  }
  throw new Error('Composer not ready. Please login to Gemini in the opened browser window.');
}

async function composerLocator(page: Page): Promise<Locator> {
  const inputs = page.locator('textarea, div[contenteditable="true"]');
  const count = await inputs.count();
  for (let idx = 0; idx < count; idx += 1) {
    const candidate = inputs.nth(idx);
    const visible = await candidate.isVisible().catch(() => false);
    if (visible) return candidate;
  }
  return inputs.first();
}

async function sendPrompt(page: Page, prompt: string): Promise<void> {
  const inputLocator = await composerLocator(page);
  await inputLocator.click({ timeout: 10_000 });
  // Use a single-shot paste-like write to avoid accidental multi-send by line breaks.
  await inputLocator.fill(prompt).catch(async () => {
    await page.keyboard.insertText(prompt);
  });
}

async function waitForSubmissionSignal(page: Page, timeoutMs = 5_000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const inputLocator = await composerLocator(page);
    const hasPrompt = await inputLocator.evaluate((input) => {
      const element = input as HTMLElement;
      if (element.tagName.toLowerCase() === 'textarea') {
        return ((element as HTMLTextAreaElement).value || '').trim().length > 0;
      }
      return (element.textContent || '').trim().length > 0;
    }).catch(() => false);
    const hasStop = await page.locator(
      'button[aria-label*="Stop" i],button[aria-label*="停止"],div[role="button"][aria-label*="Stop" i],div[role="button"][aria-label*="停止"]'
    ).first().isVisible().catch(() => false);
    const submitted = hasStop || !hasPrompt;
    if (submitted) return true;
    await page.waitForTimeout(250);
  }
  return false;
}

async function submitPrompt(page: Page): Promise<void> {
  // First try shortcuts that submit without introducing line breaks.
  const hotkeys = ['Meta+Enter', 'Control+Enter'];
  for (const hotkey of hotkeys) {
    await page.keyboard.press(hotkey).catch(() => undefined);
    if (await waitForSubmissionSignal(page)) return;
  }

  const selectors = [
    'button[type="submit"]',
    'form button[type="submit"]',
    'button[aria-label*="send" i]',
    'button[aria-label*="发送"]',
    'button[aria-label="Send message"]',
    'button[aria-label="发送消息"]',
    'button:has-text("Send")',
    'button:has-text("发送")',
    'div[role="button"][aria-label="Send message"]',
    'div[role="button"][aria-label="发送消息"]',
  ];

  for (const selector of selectors) {
    const btn = page.locator(selector).first();
    const visible = await btn.isVisible().catch(() => false);
    if (visible) {
      await btn.click({ timeout: 5_000 }).catch(() => undefined);
      if (await waitForSubmissionSignal(page)) return;
    }
  }

  // Last resort
  await page.keyboard.press('Enter');
  if (!(await waitForSubmissionSignal(page))) {
    throw new Error('Prompt submit failed. Send button/shortcut did not trigger.');
  }
}

async function hasPromptInComposer(page: Page): Promise<boolean> {
  const inputLocator = await composerLocator(page);
  return inputLocator.evaluate((input) => {
    const element = input as HTMLElement;
    if (element.tagName.toLowerCase() === 'textarea') {
      return ((element as HTMLTextAreaElement).value || '').trim().length > 0;
    }
    return (element.textContent || '').trim().length > 0;
  }).catch(() => false);
}

async function ensureProAvailability(page: Page): Promise<void> {
  const upgradeHints = [
    'text=/Upgrade to Gemini Advanced/i',
    'text=/Get Gemini Advanced/i',
    'text=/Try Gemini Advanced/i',
    'text=/升级到 Gemini Advanced/i',
    'text=/升级到 Gemini 高级版/i',
  ];
  for (const selector of upgradeHints) {
    const visible = await page.locator(selector).first().isVisible().catch(() => false);
    if (visible) {
      throw new Error('Current Gemini account is not Pro/Advanced. Please login with a Pro-enabled account.');
    }
  }
}

async function maybeSelectImageMode(page: Page): Promise<void> {
  const selectors = [
    'button:has-text("Image")',
    'button:has-text("Images")',
    'button:has-text("Create image")',
    'button:has-text("Generate image")',
    'button:has-text("制作图片")',
    'button:has-text("图片")',
    'button:has-text("图像")',
    'button:has-text("生成图像")',
    'div[role="button"]:has-text("Image")',
    'div[role="button"]:has-text("制作图片")',
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

export type VisualCandidate = {
  key: string;
  src: string;
  score: number;
  y: number;
};

function isSvgLikeSource(src: string): boolean {
  return (
    /^data:image\/svg\+xml/i.test(src)
    || /image\/svg\+xml/i.test(src)
    || /\.svg(?:[?#].*)?$/i.test(src)
  );
}

function isKnownGeminiPlaceholder(src: string): boolean {
  return /gstatic\.com\/lamda\/images\/gemini_/i.test(src)
    || /gstatic\.com\/lamda\/images\/.*(?:sparkle|aurora|logo|star)/i.test(src);
}

function sourcePriority(src: string): number {
  if (isKnownGeminiPlaceholder(src)) return -500;
  if (src.startsWith('blob:')) return 500;
  if (src.startsWith('data:') && !isSvgLikeSource(src)) return 400;
  if (isSvgLikeSource(src)) return -200;
  if (/\.(?:png|jpe?g|webp|avif|bmp|gif)(?:[?#].*)?$/i.test(src)) return 300;
  if (/^https?:/i.test(src)) return 200;
  return 100;
}

function compareCandidates(a: VisualCandidate, b: VisualCandidate): number {
  const priorityDiff = sourcePriority(b.src) - sourcePriority(a.src);
  if (priorityDiff !== 0) return priorityDiff;
  const scoreDiff = b.score - a.score;
  if (scoreDiff !== 0) return scoreDiff;
  return b.y - a.y;
}

export function pickBestVisualCandidate(
  candidates: VisualCandidate[],
  beforeKeys: Set<string> = new Set()
): VisualCandidate | undefined {
  const usable = candidates.filter((candidate) => candidate.src);
  const nonPlaceholder = usable.filter((candidate) => !isKnownGeminiPlaceholder(candidate.src));
  const primaryPool = nonPlaceholder.length > 0 ? nonPlaceholder : usable;
  const freshPool = primaryPool.filter((candidate) => !beforeKeys.has(candidate.key));
  const pool = freshPool.length > 0 ? freshPool : primaryPool;
  return pool.sort(compareCandidates)[0];
}

async function collectVisualCandidates(page: Page): Promise<VisualCandidate[]> {
  return page.evaluate(() => {
    const minSize = 96;
    const out: Array<{ key: string; src: string; score: number; y: number }> = [];

    const images = Array.from(document.querySelectorAll('img'));
    for (const img of images) {
      const el = img as HTMLImageElement;
      const w = el.naturalWidth || el.width || 0;
      const h = el.naturalHeight || el.height || 0;
      if (w < minSize || h < minSize) continue;
      const src = el.currentSrc || el.src || '';
      if (!src) continue;
      const key = `img:${src}|${w}x${h}`;
      const rect = el.getBoundingClientRect();
      out.push({ key, src, score: w * h, y: rect.top + window.scrollY });
    }

    const canvases = Array.from(document.querySelectorAll('canvas'));
    canvases.forEach((canvas, i) => {
      const el = canvas as HTMLCanvasElement;
      const w = el.width || 0;
      const h = el.height || 0;
      if (w < minSize || h < minSize) return;
      try {
        const dataUrl = el.toDataURL('image/png');
        if (!dataUrl) return;
        const key = `canvas:${i}|${w}x${h}|${dataUrl.slice(0, 128)}`;
        const rect = el.getBoundingClientRect();
        out.push({ key, src: dataUrl, score: w * h, y: rect.top + window.scrollY });
      } catch {
        // Cross-origin canvas may be tainted; skip it.
      }
    });

    const bgNodes = Array.from(document.querySelectorAll('[style*="background-image"], [role="img"]'));
    for (const node of bgNodes) {
      const el = node as HTMLElement;
      const rect = el.getBoundingClientRect();
      const w = Math.round(rect.width || 0);
      const h = Math.round(rect.height || 0);
      if (w < minSize || h < minSize) continue;
      const style = getComputedStyle(el);
      const bg = style.backgroundImage || '';
      if (!bg || bg === 'none') continue;
      const match = bg.match(/url\((['"]?)(.*?)\1\)/i);
      const src = (match?.[2] || '').trim();
      if (!src) continue;
      const key = `bg:${src}|${w}x${h}`;
      out.push({ key, src, score: w * h, y: rect.top + window.scrollY });
    }

    return out;
  });
}

async function waitForImage(page: Page, timeoutMs: number): Promise<string> {
  const before = await collectVisualCandidates(page);
  const beforeKeys = new Set(before.map((x) => x.key));
  const beforeKeyList = Array.from(beforeKeys);

  await page.waitForFunction(
    (existingKeys) => {
      const minSize = 96;
      const isSvgLikeSource = (src: string) =>
        /^data:image\/svg\+xml/i.test(src)
        || /image\/svg\+xml/i.test(src)
        || /\.svg(?:[?#].*)?$/i.test(src);
      const isKnownGeminiPlaceholder = (src: string) =>
        /gstatic\.com\/lamda\/images\/gemini_/i.test(src)
        || /gstatic\.com\/lamda\/images\/.*(?:sparkle|aurora|logo|star)/i.test(src);
      const isRenderableVisual = (src: string) =>
        !!src && !isKnownGeminiPlaceholder(src) && !isSvgLikeSource(src);

      const images = Array.from(document.querySelectorAll('img'));
      const imageCandidates = images
        .map((img) => {
          const el = img as HTMLImageElement;
          const w = el.naturalWidth || el.width || 0;
          const h = el.naturalHeight || el.height || 0;
          if (w < minSize || h < minSize) return null;
          const src = el.currentSrc || el.src || '';
          if (!src) return null;
          return { key: `img:${src}|${w}x${h}`, src };
        })
        .filter(Boolean) as Array<{ key: string; src: string }>;

      const canvases = Array.from(document.querySelectorAll('canvas'));
      const canvasKeys = canvases
        .map((canvas, i) => {
          const el = canvas as HTMLCanvasElement;
          const w = el.width || 0;
          const h = el.height || 0;
          if (w < minSize || h < minSize) return '';
          try {
            const dataUrl = el.toDataURL('image/png');
            if (!dataUrl) return '';
            return `canvas:${i}|${w}x${h}|${dataUrl.slice(0, 128)}`;
          } catch {
            return '';
          }
        })
        .filter(Boolean);

      const bgNodes = Array.from(document.querySelectorAll('[style*="background-image"], [role="img"]'));
      const bgCandidates = bgNodes
        .map((node) => {
          const el = node as HTMLElement;
          const rect = el.getBoundingClientRect();
          const w = Math.round(rect.width || 0);
          const h = Math.round(rect.height || 0);
          if (w < minSize || h < minSize) return null;
          const style = getComputedStyle(el);
          const bg = style.backgroundImage || '';
          if (!bg || bg === 'none') return null;
          const match = bg.match(/url\((['"]?)(.*?)\1\)/i);
          const src = (match?.[2] || '').trim();
          if (!src) return null;
          return { key: `bg:${src}|${w}x${h}`, src };
        })
        .filter(Boolean) as Array<{ key: string; src: string }>;

      const nowKeys = [
        ...imageCandidates.map((candidate) => candidate.key),
        ...canvasKeys,
        ...bgCandidates.map((candidate) => candidate.key),
      ];
      const hasFreshRenderableImage = imageCandidates.some(
        (candidate) => !existingKeys.includes(candidate.key) && isRenderableVisual(candidate.src)
      );
      const hasFreshCanvas = canvasKeys.some((key) => !existingKeys.includes(key));
      const hasFreshRenderableBackground = bgCandidates.some(
        (candidate) => !existingKeys.includes(candidate.key) && isRenderableVisual(candidate.src)
      );
      if (hasFreshRenderableImage || hasFreshCanvas || hasFreshRenderableBackground) return true;

      const bodyText = document.body?.innerText || '';
      const loading = /正在加载|Loading/i.test(bodyText);
      const stopButton = document.querySelector(
        'button[aria-label*="Stop" i],button[aria-label*="停止"],div[role="button"][aria-label*="Stop" i],div[role="button"][aria-label*="停止"]'
      );
      const hasStop = !!stopButton;
      const hasRenderableVisual = imageCandidates.some((candidate) => isRenderableVisual(candidate.src))
        || bgCandidates.some((candidate) => isRenderableVisual(candidate.src))
        || canvasKeys.length > 0;
      return !hasStop && !loading && hasRenderableVisual && nowKeys.length > 0;
    },
    beforeKeyList,
    { timeout: timeoutMs }
  );

  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight)).catch(() => undefined);
  await page.waitForTimeout(500).catch(() => undefined);
  const after = await collectVisualCandidates(page);
  const best = pickBestVisualCandidate(after, beforeKeys);
  if (!best) {
    throw new Error('Image src not found.');
  }
  return best.src;
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
    const dataUrl = await page.evaluate(async (url) => {
      const images = Array.from(document.querySelectorAll('img'));
      const target = images.find((img) => {
        const el = img as HTMLImageElement;
        return (el.currentSrc || el.src || '') === url;
      }) as HTMLImageElement | undefined;
      if (!target) return '';
      if ('decode' in target) {
        await target.decode().catch(() => undefined);
      }
      const width = target.naturalWidth || target.width || 0;
      const height = target.naturalHeight || target.height || 0;
      if (!width || !height) return '';
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) return '';
      ctx.drawImage(target, 0, 0, width, height);
      return canvas.toDataURL('image/png');
    }, src);
    if (dataUrl) {
      const base64 = dataUrl.split(',')[1] || '';
      ensureDir(outputPath);
      fs.writeFileSync(outputPath, Buffer.from(base64, 'base64'));
      return;
    }

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
  const cdpUrl = (opts.cdpUrl || '').trim();
  const launchedLocally = !cdpUrl;
  let context;
  let cdpBrowser;
  if (launchedLocally) {
    const profile = resolveProfileDir(opts.profileDir);
    const useChromeChannel = process.env.GEMINI_MCP_USE_CHROME === '1'
      || profile.userDataDir.includes('/Google/Chrome');
    const proxyServer = process.env.GEMINI_MCP_PROXY
      || process.env.HTTPS_PROXY
      || process.env.HTTP_PROXY
      || '';
    console.log(`[Gemini MCP] Launching browser (chromeChannel=${useChromeChannel ? 'on' : 'off'})`);
    if (proxyServer) {
      console.log(`[Gemini MCP] Using proxy: ${proxyServer}`);
    }
    context = await chromium.launchPersistentContext(profile.userDataDir, {
      headless: opts.headless,
      viewport: { width: 1280, height: 900 },
      channel: useChromeChannel ? 'chrome' : undefined,
      proxy: proxyServer ? { server: proxyServer } : undefined,
      args: [
        ...(profile.profileName ? [`--profile-directory=${profile.profileName}`] : []),
        '--disable-blink-features=AutomationControlled',
      ],
      ignoreDefaultArgs: ['--use-mock-keychain', '--password-store=basic', '--enable-automation'],
    });
  } else {
    console.log(`[Gemini MCP] Connecting to CDP browser: ${cdpUrl}`);
    cdpBrowser = await chromium.connectOverCDP(cdpUrl);
    context = cdpBrowser.contexts()[0] ?? await cdpBrowser.newContext({
      viewport: { width: 1280, height: 900 },
    });
  }

  const existingGeminiPage = context.pages().find((p) => p.url().includes('gemini.google.com/app'));
  const page = existingGeminiPage ?? context.pages()[0] ?? await context.newPage();
  page.setDefaultTimeout(opts.timeoutMs);
  page.setDefaultNavigationTimeout(opts.timeoutMs);
  console.log('[Gemini MCP] Opening Gemini...');
  if (!page.url().includes('gemini.google.com/app')) {
    await page.goto(GEMINI_URL, { waitUntil: 'domcontentloaded' });
  }
  console.log('[Gemini MCP] Waiting composer...');
  await waitForComposer(page, opts.timeoutMs);
  await ensureProAvailability(page);
  await maybeSelectImageMode(page);

  console.log('[Gemini MCP] Sending prompt...');
  await sendPrompt(page, opts.prompt);
  if (!(await hasPromptInComposer(page))) {
    throw new Error('Prompt was not inserted into composer. Check selector/login state.');
  }
  await submitPrompt(page);
  let imageUrl = '';
  try {
    console.log('[Gemini MCP] Waiting generated image...');
    imageUrl = await waitForImage(page, opts.timeoutMs);
  } catch (err) {
    const debugPath = `${opts.outputPath}.debug.png`;
    await page.screenshot({ path: debugPath, fullPage: true }).catch(() => undefined);
    throw err;
  }
  await downloadImage(page, imageUrl, opts.outputPath);

  if (!opts.keepOpen) {
    if (launchedLocally) {
      await context.close();
    } else {
      await cdpBrowser?.close().catch(() => undefined);
    }
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
  const cdpUrl = String(args.cdp || args['cdp-url'] || process.env.GEMINI_MCP_CDP_URL || '');
  const headless = args.headless ? true : false;
  const keepOpen = args['keep-open'] ? true : false;
  const timeoutMs = Number(args.timeout || 180_000);

  const result = await generateImage({
    prompt: finalPrompt,
    outputPath,
    profileDir,
    cdpUrl,
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
