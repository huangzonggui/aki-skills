#!/usr/bin/env bun
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium, type Locator, type Page } from 'playwright';

const CHANNELS_CREATE_URL = 'https://channels.weixin.qq.com/platform/post/create';
const DEFAULT_PUBLISHER_PROFILE_NAME = 'zimeiti-publisher';
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = path.resolve(SCRIPT_DIR, '..');
const DEFAULT_HTML_SNAPSHOT_DIR = path.join(SKILL_ROOT, 'references', 'publish_html_snapshots');

const LOGIN_HINT_SELECTORS = [
  'text=扫码登录',
  'text=微信扫码登录',
  'text=视频号助手',
  'text=请使用微信扫码',
];

const UPLOAD_ENTRY_SELECTORS = [
  'button:has-text("上传视频")',
  'button:has-text("发表视频")',
  'text=上传视频',
  'text=发表视频',
];

const TITLE_SELECTORS = [
  'input[placeholder*="标题"]',
  'input[placeholder*="请输入标题"]',
  'input[placeholder*="作品标题"]',
  'input[placeholder*="短标题"]',
  'input[placeholder*="概括视频主要内容"]',
  'input[placeholder*="字数建议"]',
];

const DESCRIPTION_SELECTORS = [
  '.post-desc-box .input-editor[contenteditable="true"]',
  'textarea[placeholder*="添加描述"]',
  'textarea[placeholder*="描述"]',
  'textarea[placeholder*="介绍"]',
  'textarea[placeholder*="内容"]',
  '[contenteditable="true"][data-placeholder*="添加描述"]',
  '[contenteditable="true"][data-placeholder*="描述"]',
  '[contenteditable="true"][placeholder*="添加描述"]',
  '[contenteditable="true"][placeholder*="描述"]',
  '.ql-editor[contenteditable="true"]',
  '[role="textbox"][contenteditable="true"]',
];

const DECLARE_ORIGINAL_ROW_SELECTORS = [
  '.declare-original-checkbox label.ant-checkbox-wrapper',
  'label:has-text("声明原创")',
  'text=声明原创',
];

const DECLARE_ORIGINAL_DIALOG_SELECTORS = [
  '.declare-original-dialog .weui-desktop-dialog__wrp[style*="display: block"]',
  '.declare-original-dialog .weui-desktop-dialog:has-text("原创权益")',
  '.weui-desktop-dialog:has-text("原创权益")',
];

const DECLARE_ORIGINAL_CONFIRM_SELECTORS = [
  '.declare-original-dialog .weui-desktop-btn_primary:has-text("声明原创")',
  '.weui-desktop-dialog .weui-desktop-btn_primary:has-text("声明原创")',
];

const COVER_EDIT_ENTRY_SELECTORS = [
  '.cover-preview-wrap .edit-btn',
  '.edit-btn:has-text("编辑")',
  'button:has-text("编辑封面")',
  'text=编辑封面',
];

const COVER_UPLOAD_INPUT_SELECTORS = [
  '.single-cover-uploader-wrap input[type="file"][accept*="image"]',
  '.edit-cover-dialog-container input[type="file"][accept*="image"]',
  'input[type="file"][accept*="image"]',
];

const COVER_CONFIRM_SELECTORS = [
  '.edit-cover-dialog-container .weui-desktop-btn_primary:has-text("确认")',
  '.edit-cover-dialog-container .weui-desktop-btn_primary:has-text("确定")',
  '.weui-desktop-dialog .weui-desktop-btn_primary:has-text("确认")',
  '.weui-desktop-dialog .weui-desktop-btn_primary:has-text("确定")',
];

const SAVE_DRAFT_SELECTORS = [
  'button:has-text("保存草稿")',
  'button:has-text("存草稿")',
  'text=保存草稿',
  'text=存草稿',
];

const SAVE_SUCCESS_TEXTS = [
  '草稿保存成功',
  '保存草稿成功',
  '已保存到草稿箱',
  '保存成功',
];

type CliOptions = {
  videoPath: string;
  coverPath?: string;
  title?: string;
  description?: string;
  topics: string[];
  profileDir?: string;
  profileName?: string;
  headless: boolean;
  keepOpen: boolean;
  declareOriginal: boolean;
  enableHtmlSnapshot: boolean;
  htmlSnapshotDir?: string;
  loginTimeoutMs: number;
  uploadTimeoutMs: number;
  actionTimeoutMs: number;
  outputDir?: string;
  help: boolean;
};

function printHelp(): void {
  console.log(`
WeChat Channels Draft Uploader (Draft-only, no publish)

Usage:
  bun ./scripts/wechat-channels-draft.ts --video /abs/path/video.mp4 [options]

Options:
  --video <path>               Required. Local video path.
  --cover <path>               Optional. Cover image path. Default: auto-detect from video folder.
  --title <text>               Optional. Video title.
  --description <text>         Optional. Video description.
  --topics <list>              Optional. Topics list, comma-separated. Example: "AI,OpenClaw".
  --profile-dir <path>         Optional. Browser profile dir.
  --profile-name <name>        Optional. Publisher profile name (default: zimeiti-publisher).
  --headless                   Optional. Run browser in headless mode (default: false).
  --keep-open                  Keep browser open after run (default: true).
  --close-after-save           Close browser after save.
  --no-declare-original        Do not auto-check "声明原创" (default: checked).
  --no-html-snapshot           Do not save page HTML snapshots.
  --html-snapshot-dir <path>   Optional. HTML snapshot output dir in skill refs.
  --login-timeout-sec <sec>    Optional. Wait time for QR login (default: 180).
  --upload-timeout-sec <sec>   Optional. Wait time for upload/transcode (default: 900).
  --action-timeout-sec <sec>   Optional. Default UI action timeout (default: 30).
  --output-dir <path>          Optional. Output screenshots directory.
  --help                       Show this help.

Safety:
  - This script only clicks "保存草稿/存草稿".
  - This script never clicks any publish button.
  `.trim());
}

function readArgValue(args: string[], index: number, name: string): string {
  const value = args[index + 1];
  if (!value || value.startsWith('--')) {
    throw new Error(`Missing value for ${name}`);
  }
  return value;
}

function parseArgs(argv: string[]): CliOptions {
  const opts: CliOptions = {
    videoPath: '',
    coverPath: undefined,
    title: undefined,
    description: undefined,
    topics: [],
    profileDir: undefined,
    profileName: undefined,
    headless: false,
    keepOpen: true,
    declareOriginal: true,
    enableHtmlSnapshot: true,
    htmlSnapshotDir: undefined,
    loginTimeoutMs: 180_000,
    uploadTimeoutMs: 900_000,
    actionTimeoutMs: 30_000,
    outputDir: undefined,
    help: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i] ?? '';
    switch (arg) {
      case '--video':
        opts.videoPath = readArgValue(argv, i, arg);
        i += 1;
        break;
      case '--cover':
        opts.coverPath = readArgValue(argv, i, arg);
        i += 1;
        break;
      case '--title':
        opts.title = readArgValue(argv, i, arg);
        i += 1;
        break;
      case '--description':
        opts.description = readArgValue(argv, i, arg);
        i += 1;
        break;
      case '--topics':
        opts.topics = readArgValue(argv, i, arg)
          .split(',')
          .map((x) => x.trim())
          .filter(Boolean);
        i += 1;
        break;
      case '--profile-dir':
        opts.profileDir = readArgValue(argv, i, arg);
        i += 1;
        break;
      case '--profile-name':
        opts.profileName = readArgValue(argv, i, arg);
        i += 1;
        break;
      case '--output-dir':
        opts.outputDir = readArgValue(argv, i, arg);
        i += 1;
        break;
      case '--html-snapshot-dir':
        opts.htmlSnapshotDir = readArgValue(argv, i, arg);
        i += 1;
        break;
      case '--login-timeout-sec':
        opts.loginTimeoutMs = Number(readArgValue(argv, i, arg)) * 1000;
        i += 1;
        break;
      case '--upload-timeout-sec':
        opts.uploadTimeoutMs = Number(readArgValue(argv, i, arg)) * 1000;
        i += 1;
        break;
      case '--action-timeout-sec':
        opts.actionTimeoutMs = Number(readArgValue(argv, i, arg)) * 1000;
        i += 1;
        break;
      case '--headless':
        opts.headless = true;
        break;
      case '--keep-open':
        opts.keepOpen = true;
        break;
      case '--close-after-save':
        opts.keepOpen = false;
        break;
      case '--no-declare-original':
        opts.declareOriginal = false;
        break;
      case '--no-html-snapshot':
        opts.enableHtmlSnapshot = false;
        break;
      case '--help':
      case '-h':
        opts.help = true;
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (!opts.help && !opts.videoPath) {
    throw new Error('Missing required argument: --video <path>');
  }

  return opts;
}

function defaultProfileRoot(): string {
  const explicitRoot = process.env.AKI_PUBLISHER_PROFILE_ROOT?.trim();
  if (explicitRoot) return path.resolve(explicitRoot);

  if (process.platform === 'darwin') {
    return path.join(os.homedir(), 'Library', 'Application Support', 'aki-skills', 'publisher-profiles');
  }

  if (process.platform === 'win32') {
    const appData = process.env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming');
    return path.join(appData, 'aki-skills', 'publisher-profiles');
  }

  const base = process.env.XDG_DATA_HOME || path.join(os.homedir(), '.local', 'share');
  return path.join(base, 'aki-skills', 'publisher-profiles');
}

function normalizeProfileName(raw: string): string {
  const normalized = raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return normalized || 'main';
}

function defaultProfileDir(profileName?: string): string {
  const legacy = process.env.WECHAT_BROWSER_PROFILE_DIR?.trim();
  if (legacy) return path.resolve(legacy);

  const name = normalizeProfileName(
    profileName
    || process.env.AKI_PUBLISHER_PROFILE_NAME
    || DEFAULT_PUBLISHER_PROFILE_NAME,
  );
  return path.join(defaultProfileRoot(), name);
}

function resolveProfileDir(
  inputDir?: string,
  inputProfileName?: string,
): { userDataDir: string; profileName?: string } {
  const raw = (inputDir || defaultProfileDir(inputProfileName)).trim();
  const base = path.basename(raw);
  if (base === 'Default' || base.startsWith('Profile ') || base === 'Guest Profile') {
    return {
      userDataDir: path.dirname(raw),
      profileName: base,
    };
  }
  return { userDataDir: raw };
}

function ensureFileExists(filePath: string, label: string): void {
  const abs = path.resolve(filePath);
  if (!fs.existsSync(abs)) throw new Error(`${label} does not exist: ${abs}`);
  if (!fs.statSync(abs).isFile()) throw new Error(`${label} is not a file: ${abs}`);
}

function inferTitle(videoPath: string): string {
  const base = path.basename(videoPath, path.extname(videoPath));
  const normalized = base.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
  return normalized || '视频号草稿';
}

function normalizeTopic(raw: string): string {
  return raw.trim().replace(/^#+/, '').replace(/\s+/g, '');
}

function appendTopicsToDescription(base: string, topics: string[]): string {
  let out = base.trim();
  for (const raw of topics) {
    const topic = normalizeTopic(raw);
    if (!topic) continue;
    const marker = `#${topic}`;
    if (out.includes(marker)) continue;
    out = `${out}${out ? ' ' : ''}${marker}`;
  }
  return out.trim();
}

function isImageFile(filePath: string): boolean {
  return /\.(png|jpe?g|webp|bmp)$/i.test(filePath);
}

function inferCoverPath(videoPath: string, explicitCoverPath?: string): string | null {
  if (explicitCoverPath && explicitCoverPath.trim()) {
    const abs = path.resolve(explicitCoverPath.trim());
    if (fs.existsSync(abs) && fs.statSync(abs).isFile() && isImageFile(abs)) {
      return abs;
    }
    return null;
  }

  const dir = path.dirname(videoPath);
  const stem = path.basename(videoPath, path.extname(videoPath));
  const extOrder = ['.jpg', '.jpeg', '.png', '.webp', '.bmp'];

  const directCandidates: string[] = [];
  for (const ext of extOrder) {
    directCandidates.push(path.join(dir, `${stem}${ext}`));
    directCandidates.push(path.join(dir, `${stem}-封面${ext}`));
    directCandidates.push(path.join(dir, `${stem}_封面${ext}`));
    directCandidates.push(path.join(dir, `${stem}封面${ext}`));
    directCandidates.push(path.join(dir, 'cover' + ext));
    directCandidates.push(path.join(dir, '封面' + ext));
  }
  for (const candidate of directCandidates) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate;
  }

  const files = fs.readdirSync(dir)
    .map((name) => path.join(dir, name))
    .filter((p) => fs.statSync(p).isFile() && isImageFile(p));
  const containsCover = files.filter((p) => path.basename(p).includes('封面'));
  const withStem = containsCover.filter((p) => path.basename(p).includes(stem));
  if (withStem.length > 0) return withStem.sort()[0];
  if (containsCover.length > 0) return containsCover.sort()[0];
  return null;
}

function nowLabel(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

function nowIsoLabel(): string {
  return new Date().toISOString();
}

function ensureDir(dirPath: string): void {
  fs.mkdirSync(dirPath, { recursive: true });
}

function bringChromeToFront(): void {
  if (process.platform !== 'darwin') return;
  try {
    spawnSync('osascript', ['-e', 'tell application "Google Chrome" to activate'], { stdio: 'ignore' });
  } catch {}
}

async function safeScreenshot(page: Page, outDir: string, fileName: string): Promise<string> {
  const abs = path.resolve(outDir, fileName);
  await page.screenshot({ path: abs, fullPage: true });
  return abs;
}

async function saveHtmlSnapshot(
  page: Page,
  stage: string,
  snapshotDir: string,
): Promise<string> {
  const ts = nowLabel();
  const safeStage = stage.replace(/[^a-zA-Z0-9_-]+/g, '_');
  const outPath = path.join(snapshotDir, `${ts}-${safeStage}.html`);
  fs.mkdirSync(snapshotDir, { recursive: true });
  const html = await page.content();
  const meta = [
    '<!--',
    `captured_at: ${nowIsoLabel()}`,
    `url: ${page.url()}`,
    `stage: ${stage}`,
    '-->',
    '',
  ].join('\n');
  fs.writeFileSync(outPath, meta + html, 'utf-8');
  return outPath;
}

async function firstVisible(page: Page, selectors: string[]): Promise<Locator | null> {
  for (const selector of selectors) {
    const locator = page.locator(selector).first();
    const visible = await locator.isVisible().catch(() => false);
    if (visible) return locator;
  }
  return null;
}

async function clickFirstVisible(page: Page, selectors: string[]): Promise<boolean> {
  const locator = await firstVisible(page, selectors);
  if (!locator) return false;
  await locator.click({ timeout: 5_000 });
  return true;
}

async function isLoginPage(page: Page): Promise<boolean> {
  const url = page.url();
  if (/\/login/i.test(url)) return true;
  const hint = await firstVisible(page, LOGIN_HINT_SELECTORS);
  return Boolean(hint);
}

async function waitForLogin(page: Page, timeoutMs: number): Promise<void> {
  if (!(await isLoginPage(page))) return;

  console.log('[info] 检测到登录页，请在浏览器中扫码登录视频号助手...');
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    await page.waitForTimeout(1500);
    if (!(await isLoginPage(page))) {
      console.log('[info] 登录完成。');
      return;
    }
  }
  throw new Error(`Login timeout after ${Math.round(timeoutMs / 1000)}s`);
}

async function fillBySelectors(page: Page, selectors: string[], value: string): Promise<boolean> {
  if (!value.trim()) return false;
  for (const selector of selectors) {
    const locator = page.locator(selector).first();
    const visible = await locator.isVisible().catch(() => false);
    if (!visible) continue;

    await locator.click({ timeout: 5_000 }).catch(() => undefined);
    const isContentEditable = await locator.evaluate((el) => (el as HTMLElement).isContentEditable).catch(() => false);
    if (isContentEditable) {
      const written = await locator.evaluate((el, text) => {
        const node = el as HTMLElement;
        node.focus();
        node.innerText = text;
        node.dispatchEvent(new Event('input', { bubbles: true }));
        node.dispatchEvent(new Event('change', { bubbles: true }));
        return (node.innerText || '').trim() === text.trim();
      }, value).catch(() => false);
      if (written) return true;
    }

    try {
      await locator.fill(value, { timeout: 5_000 });
      return true;
    } catch {
      await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A').catch(() => undefined);
      await page.keyboard.type(value, { delay: 20 });
      return true;
    }
  }
  return false;
}

async function fillShortTitle(page: Page, value: string): Promise<boolean> {
  if (!value.trim()) return false;
  if (await fillBySelectors(page, TITLE_SELECTORS, value)) return true;

  const fallback = page.locator('.short-title-wrap input').first();
  const visible = await fallback.isVisible().catch(() => false);
  if (!visible) return false;
  await fallback.fill(value).catch(() => undefined);
  return true;
}

async function fillDescription(page: Page, value: string): Promise<boolean> {
  if (!value.trim()) return false;
  if (await fillBySelectors(page, DESCRIPTION_SELECTORS, value)) return true;

  const fallback = page.locator('.post-desc-box .input-editor[contenteditable="true"]').first();
  const visible = await fallback.isVisible().catch(() => false);
  if (!visible) return false;
  const ok = await fallback.evaluate((el, text) => {
    const node = el as HTMLElement;
    node.focus();
    node.innerText = text;
    node.dispatchEvent(new Event('input', { bubbles: true }));
    node.dispatchEvent(new Event('change', { bubbles: true }));
    return (node.innerText || '').trim().length > 0;
  }, value).catch(() => false);
  return Boolean(ok);
}

async function uploadVideoWithRetry(page: Page, videoPath: string, timeoutMs: number): Promise<void> {
  const uploadSelectors = [
    '.post-edit-wrap input[type="file"][accept*="video"]',
    'input[type="file"][accept*="video"]',
    'input[type="file"]',
  ];

  let lastError: Error | null = null;
  for (let attempt = 1; attempt <= 8; attempt += 1) {
    for (const selector of uploadSelectors) {
      const locator = page.locator(selector).first();
      const count = await locator.count().catch(() => 0);
      if (!count) continue;
      try {
        await locator.setInputFiles(videoPath, { timeout: timeoutMs });
        return;
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
      }
    }
    await page.waitForTimeout(700);
  }
  throw lastError || new Error('Unable to locate/attach video file input');
}

async function uploadCoverWithRetry(page: Page, coverPath: string, timeoutMs: number): Promise<boolean> {
  const coverAbs = path.resolve(coverPath);
  if (!fs.existsSync(coverAbs) || !fs.statSync(coverAbs).isFile()) return false;
  if (!isImageFile(coverAbs)) return false;

  await clickFirstVisible(page, COVER_EDIT_ENTRY_SELECTORS).catch(() => undefined);
  await page.waitForTimeout(600);

  let uploaded = false;
  let lastError: Error | null = null;
  for (let attempt = 1; attempt <= 6; attempt += 1) {
    for (const selector of COVER_UPLOAD_INPUT_SELECTORS) {
      const locator = page.locator(selector).first();
      const count = await locator.count().catch(() => 0);
      if (!count) continue;
      try {
        await locator.setInputFiles(coverAbs, { timeout: timeoutMs });
        uploaded = true;
        break;
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
      }
    }
    if (uploaded) break;
    await page.waitForTimeout(800);
  }
  if (!uploaded) {
    throw lastError || new Error('cover setInputFiles failed');
  }

  await page.waitForTimeout(900);
  await clickFirstVisible(page, COVER_CONFIRM_SELECTORS).catch(() => undefined);
  await page.waitForTimeout(900);
  return true;
}

async function ensureDeclareOriginalChecked(page: Page): Promise<{ checked: boolean; dialogHandled: boolean }> {
  const row = await firstVisible(page, DECLARE_ORIGINAL_ROW_SELECTORS);
  if (!row) return { checked: false, dialogHandled: false };

  const isChecked = async (): Promise<boolean> => page.evaluate(() => {
    const wrapper = document.querySelector('.declare-original-checkbox label.ant-checkbox-wrapper');
    if (!wrapper) return false;
    if (wrapper.classList.contains('ant-checkbox-wrapper-checked')) return true;
    const input = wrapper.querySelector('input[type="checkbox"]') as HTMLInputElement | null;
    return Boolean(input?.checked);
  }).catch(() => false);

  if (!(await isChecked())) {
    await row.click({ timeout: 5_000 }).catch(() => undefined);
    await page.waitForTimeout(600);
  }

  let dialogHandled = false;
  const dialog = await firstVisible(page, DECLARE_ORIGINAL_DIALOG_SELECTORS);
  if (dialog) {
    const protoAgree = page.locator('.original-proto-wrapper label.ant-checkbox-wrapper').first();
    const agreeVisible = await protoAgree.isVisible().catch(() => false);
    if (agreeVisible) {
      const agreed = await protoAgree.evaluate((el) => {
        if (el.classList.contains('ant-checkbox-wrapper-checked')) return true;
        const input = el.querySelector('input[type="checkbox"]') as HTMLInputElement | null;
        return Boolean(input?.checked);
      }).catch(() => false);
      if (!agreed) {
        await protoAgree.click({ timeout: 5_000 }).catch(() => undefined);
      }
    }

    const confirm = await firstVisible(page, DECLARE_ORIGINAL_CONFIRM_SELECTORS);
    if (confirm) {
      await confirm.click({ timeout: 10_000 }).catch(() => undefined);
      await page.waitForTimeout(700);
      dialogHandled = true;
    }
  }

  return { checked: await isChecked(), dialogHandled };
}

async function waitForDraftButtonEnabled(page: Page, timeoutMs: number): Promise<Locator> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    for (const selector of SAVE_DRAFT_SELECTORS) {
      const locator = page.locator(selector).first();
      const visible = await locator.isVisible().catch(() => false);
      if (!visible) continue;

      const disabledAttr = await locator.getAttribute('disabled').catch(() => null);
      const ariaDisabled = await locator.getAttribute('aria-disabled').catch(() => null);
      const className = (await locator.getAttribute('class').catch(() => '')) || '';
      const enabled = await locator.isEnabled().catch(() => false);
      const hasDisabledClass = /disabled|is-disabled|btn_disabled|forbid/i.test(className);

      if (enabled && !disabledAttr && ariaDisabled !== 'true' && !hasDisabledClass) {
        return locator;
      }
    }
    await page.waitForTimeout(1500);
  }
  throw new Error(`"保存草稿" button not ready after ${Math.round(timeoutMs / 1000)}s`);
}

async function waitForSaveSuccess(page: Page, timeoutMs: number): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    for (const text of SAVE_SUCCESS_TEXTS) {
      const locator = page.getByText(text, { exact: false }).first();
      const visible = await locator.isVisible().catch(() => false);
      if (visible) return true;
    }
    await page.waitForTimeout(500);
  }
  return false;
}

async function run(): Promise<void> {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.help) {
    printHelp();
    return;
  }

  const videoPath = path.resolve(opts.videoPath);
  ensureFileExists(videoPath, 'Video file');
  const coverPath = inferCoverPath(videoPath, opts.coverPath);

  const title = (opts.title || inferTitle(videoPath)).trim();
  const descriptionBase = (opts.description || title).trim();
  const description = appendTopicsToDescription(descriptionBase, opts.topics);
  const htmlSnapshotDir = path.resolve(opts.htmlSnapshotDir || DEFAULT_HTML_SNAPSHOT_DIR);

  const profile = resolveProfileDir(opts.profileDir, opts.profileName);
  const outDir = path.resolve(opts.outputDir || path.join(os.tmpdir(), `wechat-channels-draft-${nowLabel()}`));
  ensureDir(outDir);

  console.log(`[info] video: ${videoPath}`);
  console.log(`[info] cover: ${coverPath || '(auto-detect failed / skipped)'}`);
  console.log(`[info] profile: ${profile.userDataDir}${profile.profileName ? ` (profile=${profile.profileName})` : ''}`);
  console.log(`[info] output: ${outDir}`);

  const context = await chromium.launchPersistentContext(profile.userDataDir, {
    channel: 'chrome',
    ignoreDefaultArgs: ['--enable-automation'],
    headless: opts.headless,
    viewport: { width: 1440, height: 960 },
    args: [
      '--disable-blink-features=AutomationControlled',
      '--disable-infobars',
      '--start-maximized',
      ...(profile.profileName ? [`--profile-directory=${profile.profileName}`] : []),
    ],
  });

  const page = context.pages()[0] || await context.newPage();
  bringChromeToFront();
  page.setDefaultTimeout(opts.actionTimeoutMs);
  page.setDefaultNavigationTimeout(Math.max(opts.actionTimeoutMs, 90_000));

  try {
    const htmlSnapshots: string[] = [];

    console.log(`[info] opening creator page: ${CHANNELS_CREATE_URL}`);
    await page.goto(CHANNELS_CREATE_URL, { waitUntil: 'domcontentloaded' });
    bringChromeToFront();
    await waitForLogin(page, opts.loginTimeoutMs);
    await page.goto(CHANNELS_CREATE_URL, { waitUntil: 'domcontentloaded' });
    bringChromeToFront();
    await page.waitForLoadState('networkidle').catch(() => undefined);

    await safeScreenshot(page, outDir, '01_page_opened.png');
    if (opts.enableHtmlSnapshot) {
      const htmlPath = await saveHtmlSnapshot(page, 'post_create_loaded', htmlSnapshotDir);
      htmlSnapshots.push(htmlPath);
    }

    await clickFirstVisible(page, UPLOAD_ENTRY_SELECTORS).catch(() => undefined);
    console.log('[info] uploading video...');
    await uploadVideoWithRetry(page, videoPath, Math.max(8_000, opts.actionTimeoutMs));
    await safeScreenshot(page, outDir, '02_video_selected.png');

    let coverUploaded = false;
    if (coverPath) {
      try {
        coverUploaded = await uploadCoverWithRetry(page, coverPath, Math.max(8_000, opts.actionTimeoutMs));
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        console.log(`[warn] 封面上传失败: ${msg}`);
      }
      await safeScreenshot(page, outDir, coverUploaded ? '02b_cover_uploaded.png' : '02b_cover_skipped.png');
    } else {
      await safeScreenshot(page, outDir, '02b_cover_not_found.png');
    }

    const titleFilled = await fillShortTitle(page, title);
    const descriptionFilled = await fillDescription(page, description);
    if (!titleFilled) console.log('[warn] 标题输入框未识别，已跳过标题填写。');
    if (!descriptionFilled) console.log('[warn] 描述输入框未识别，已跳过描述填写。');

    if (opts.enableHtmlSnapshot) {
      const htmlPath = await saveHtmlSnapshot(page, 'post_create_after_fill', htmlSnapshotDir);
      htmlSnapshots.push(htmlPath);
    }

    let declareOriginalChecked = false;
    let declareOriginalDialogHandled = false;
    if (opts.declareOriginal) {
      const declareResult = await ensureDeclareOriginalChecked(page);
      declareOriginalChecked = declareResult.checked;
      declareOriginalDialogHandled = declareResult.dialogHandled;
      if (!declareOriginalChecked) {
        console.log('[warn] "声明原创" 勾选未确认，请人工检查。');
      }
    }

    console.log('[info] waiting for draft button to be enabled...');
    const draftButton = await waitForDraftButtonEnabled(page, opts.uploadTimeoutMs);
    await safeScreenshot(page, outDir, '03_ready_to_save.png');

    console.log('[info] clicking "保存草稿"...');
    await draftButton.click({ timeout: 10_000 });

    const saved = await waitForSaveSuccess(page, 20_000);
    await safeScreenshot(page, outDir, saved ? '04_saved_success.png' : '04_saved_uncertain.png');

    const result = {
      action: 'save_draft_only',
      publish_clicked: false,
      draft_save_confirmed: saved,
      video: videoPath,
      cover_path: coverPath || '',
      cover_uploaded: coverUploaded,
      title,
      description,
      topics: opts.topics.map((x) => normalizeTopic(x)).filter(Boolean),
      short_title_filled: titleFilled,
      description_filled: descriptionFilled,
      declare_original_enabled: opts.declareOriginal,
      declare_original_checked: declareOriginalChecked,
      declare_original_dialog_handled: declareOriginalDialogHandled,
      html_snapshot_enabled: opts.enableHtmlSnapshot,
      html_snapshot_dir: opts.enableHtmlSnapshot ? htmlSnapshotDir : '',
      html_snapshots: htmlSnapshots,
      output_dir: outDir,
      timestamp: new Date().toISOString(),
    };
    console.log(JSON.stringify(result, null, 2));

    if (opts.keepOpen) {
      console.log('[info] browser kept open. Press Ctrl+C to exit.');
      await new Promise<void>(() => undefined);
    }
  } catch (error) {
    const errPath = path.join(outDir, '99_error.png');
    await page.screenshot({ path: errPath, fullPage: true }).catch(() => undefined);
    throw error;
  } finally {
    if (!opts.keepOpen) {
      await context.close().catch(() => undefined);
    }
  }
}

run().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`[error] ${message}`);
  if (message.includes('ProcessSingleton')) {
    console.error('[hint] Chrome profile is already in use. Close all Chrome windows or switch to a dedicated --profile-dir.');
  }
  process.exit(1);
});
