import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import process from 'node:process';
import { launchChrome, getPageSession, waitForNewTab, clickElement, typeText, evaluate, sleep, type ChromeSession, type CdpConnection } from './cdp.ts';

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

const WECHAT_URL = 'https://mp.weixin.qq.com/';
const DEFAULT_ORIGINAL_AUTHOR = (process.env.WECHAT_ORIGINAL_AUTHOR || 'Aki聊AI').trim();

interface ImageInfo {
  placeholder: string;
  localPath: string;
  originalPath: string;
}

interface ArticleOptions {
  title: string;
  content?: string;
  htmlFile?: string;
  markdownFile?: string;
  theme?: string;
  author?: string;
  summary?: string;
  images?: string[];
  contentImages?: ImageInfo[];
  submit?: boolean;
  profileDir?: string;
  skipTitle?: boolean;
  manualPaste?: boolean;
  useAI?: boolean;
}

async function isLoggedIn(session: ChromeSession): Promise<boolean> {
  return await evaluate<boolean>(session, `
    (function() {
      const url = window.location.href || '';
      const isLoginUrl = url.includes('/cgi-bin/login') || url.includes('/cgi-bin/loginpage') || url.includes('/safe');
      if (!isLoginUrl && url.includes('/cgi-bin/')) return true;
      if (document.querySelector('.new-creation__menu')) return true;
      if (document.querySelector('.weui-desktop-menu__item')) return true;
      return false;
    })()
  `);
}

async function waitForLogin(session: ChromeSession, timeoutMs = 120_000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await isLoggedIn(session)) return true;
    await sleep(2000);
  }
  return false;
}

async function ensureHome(session: ChromeSession): Promise<void> {
  const homeUrl = 'https://mp.weixin.qq.com/cgi-bin/home?t=home/index';
  const url = await evaluate<string>(session, 'window.location.href');
  if (!url.includes('/cgi-bin/home')) {
    await evaluate(session, `window.location.href = ${JSON.stringify(homeUrl)}`);
    await sleep(3000);
  }

  for (let i = 0; i < 20; i++) {
    const hasMenu = await evaluate<boolean>(session, '!!document.querySelector(".new-creation__menu")');
    if (hasMenu) return;
    await sleep(500);
  }
  throw new Error('Home page not ready: creation menu not found');
}

async function getWeChatSession(cdp: CdpConnection): Promise<ChromeSession> {
  const targets = await cdp.send<{ targetInfos: Array<{ targetId: string; url: string; type: string }> }>('Target.getTargets');
  const pages = targets.targetInfos.filter((t) => t.type === 'page' && t.url.includes('mp.weixin.qq.com'));
  const preferred = pages.find((t) => t.url.includes('/cgi-bin/home'))
    || pages.find((t) => t.url.includes('/cgi-bin/'))
    || pages[0];
  if (!preferred) throw new Error('Page not found: mp.weixin.qq.com');

  const { sessionId } = await cdp.send<{ sessionId: string }>('Target.attachToTarget', { targetId: preferred.targetId, flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  await cdp.send('DOM.enable', {}, { sessionId });
  return { cdp, sessionId, targetId: preferred.targetId };
}

async function openWeChatHome(cdp: CdpConnection): Promise<ChromeSession> {
  const { targetId } = await cdp.send<{ targetId: string }>('Target.createTarget', { url: WECHAT_URL });
  const { sessionId } = await cdp.send<{ sessionId: string }>('Target.attachToTarget', { targetId, flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  await cdp.send('DOM.enable', {}, { sessionId });
  return { cdp, sessionId, targetId };
}

async function clickMenuByText(session: ChromeSession, text: string): Promise<void> {
  console.log(`[wechat] Clicking "${text}" menu...`);
  const posResult = await session.cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const items = document.querySelectorAll('.new-creation__menu .new-creation__menu-item');
        for (const item of items) {
          const title = item.querySelector('.new-creation__menu-title');
          if (title && title.textContent?.trim() === '${text}') {
            item.scrollIntoView({ block: 'center' });
            const rect = item.getBoundingClientRect();
            return JSON.stringify({ x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 });
          }
        }
        return 'null';
      })()
    `,
    returnByValue: true,
  }, { sessionId: session.sessionId });

  if (posResult.result.value === 'null') throw new Error(`Menu "${text}" not found`);
  const pos = JSON.parse(posResult.result.value);

  await session.cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: pos.x, y: pos.y, button: 'left', clickCount: 1 }, { sessionId: session.sessionId });
  await sleep(100);
  await session.cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: pos.x, y: pos.y, button: 'left', clickCount: 1 }, { sessionId: session.sessionId });
}

async function copyImageToClipboard(imagePath: string): Promise<void> {
  const scriptDir = path.dirname(new URL(import.meta.url).pathname);
  const copyScript = path.join(scriptDir, './copy-to-clipboard.ts');
  const bunBin = process.env.BUN_BIN || process.env.BUN_PATH || 'bun';
  const result = spawnSync(bunBin, [copyScript, 'image', imagePath], { stdio: 'inherit' });
  if (result.status !== 0) throw new Error(`Failed to copy image: ${imagePath}`);
}

async function copyHtmlToClipboard(htmlPath: string): Promise<void> {
  const scriptDir = path.dirname(new URL(import.meta.url).pathname);
  const copyScript = path.join(scriptDir, './copy-to-clipboard.ts');
  const bunBin = process.env.BUN_BIN || process.env.BUN_PATH || 'bun';
  const result = spawnSync(bunBin, [copyScript, 'html', '--file', htmlPath], { stdio: 'inherit' });
  if (result.status !== 0) throw new Error(`Failed to copy HTML: ${htmlPath}`);
}

function extractHtmlBody(htmlPath: string): string {
  const html = fs.readFileSync(htmlPath, 'utf-8');
  const match = html.match(/<div id=["']output["'][^>]*>([\s\S]*?)<\/div>/i);
  return match ? match[1] : html;
}

async function insertHtmlDirect(session: ChromeSession, htmlPath: string): Promise<boolean> {
  const content = extractHtmlBody(htmlPath);
  return await evaluate<boolean>(session, `
    (function() {
      const editor = document.querySelector('.ProseMirror');
      if (!editor) return false;
      editor.focus();
      const range = document.createRange();
      range.selectNodeContents(editor);
      range.collapse(true);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      try {
        return document.execCommand('insertHTML', false, ${JSON.stringify(content)});
      } catch (err) {
        return false;
      }
    })()
  `);
}

async function activateChrome(): Promise<void> {
  if (process.platform === 'darwin') {
    spawnSync('osascript', ['-e', 'tell application "Google Chrome" to activate']);
  }
}

async function focusEditor(session: ChromeSession): Promise<void> {
  await session.cdp.send('Page.bringToFront', {}, { sessionId: session.sessionId });
  await clickElement(session, '.ProseMirror');
  await evaluate(session, 'document.querySelector(".ProseMirror")?.focus()');
  await activateChrome();
  await sleep(300);
}

async function waitForEnter(prompt: string): Promise<void> {
  if (!process.stdin.isTTY) return;
  process.stdout.write(prompt);
  await new Promise<void>((resolve) => {
    process.stdin.setEncoding('utf8');
    process.stdin.resume();
    process.stdin.once('data', () => {
      process.stdin.pause();
      resolve();
    });
  });
}

async function pasteInEditor(session: ChromeSession): Promise<void> {
  const modifiers = process.platform === 'darwin' ? 4 : 2;
  await session.cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'v', code: 'KeyV', modifiers, windowsVirtualKeyCode: 86 }, { sessionId: session.sessionId });
  await sleep(50);
  await session.cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'v', code: 'KeyV', modifiers, windowsVirtualKeyCode: 86 }, { sessionId: session.sessionId });
}

async function copyHtmlFromBrowser(cdp: CdpConnection, htmlFilePath: string): Promise<void> {
  const absolutePath = path.isAbsolute(htmlFilePath) ? htmlFilePath : path.resolve(process.cwd(), htmlFilePath);
  const fileUrl = `file://${absolutePath}`;

  console.log(`[wechat] Opening HTML file in new tab: ${fileUrl}`);

  const { targetId } = await cdp.send<{ targetId: string }>('Target.createTarget', { url: fileUrl });
  const { sessionId } = await cdp.send<{ sessionId: string }>('Target.attachToTarget', { targetId, flatten: true });

  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  await sleep(2000);

  console.log('[wechat] Selecting #output content...');
  await cdp.send<{ result: { value: unknown } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const output = document.querySelector('#output') || document.body;
        const range = document.createRange();
        range.selectNodeContents(output);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        return true;
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  await sleep(300);

  const copyResult = await cdp.send<{ result: { value: boolean } }>('Runtime.evaluate', {
    expression: `
      (function() {
        try {
          return document.execCommand('copy');
        } catch (err) {
          return false;
        }
      })()
    `,
    returnByValue: true,
  }, { sessionId });

  if (!copyResult.result.value) {
    console.log('[wechat] Copying with system Cmd+C...');
    if (process.platform === 'darwin') {
      spawnSync('osascript', ['-e', 'tell application "System Events" to keystroke "c" using command down']);
    } else {
      spawnSync('xdotool', ['key', 'ctrl+c']);
    }
    await sleep(1000);
  } else {
    console.log('[wechat] Copied via document.execCommand.');
    await sleep(500);
  }

  console.log('[wechat] Closing HTML tab...');
  await cdp.send('Target.closeTarget', { targetId });
}

async function pasteFromClipboardInEditor(): Promise<void> {
  if (process.platform === 'darwin') {
    spawnSync('osascript', ['-e', 'tell application "System Events" to keystroke "v" using command down']);
  } else {
    spawnSync('xdotool', ['key', 'ctrl+v']);
  }
  await sleep(1000);
}

async function parseMarkdownWithPlaceholders(markdownPath: string, theme?: string, useAI?: boolean): Promise<{ title: string; author: string; summary: string; htmlPath: string; contentImages: ImageInfo[] }> {
  const scriptDir = path.dirname(new URL(import.meta.url).pathname);
  const scriptName = useAI ? 'md-to-wechat-ai.ts' : 'md-to-wechat.ts';
  const mdToWechatScript = path.join(scriptDir, scriptName);
  const bunBin = process.env.BUN_BIN || process.env.BUN_PATH || 'bun';
  const args = [mdToWechatScript, markdownPath];
  if (theme && !useAI) args.push('--theme', theme);
  if (useAI) console.error('[wechat] Using AI-powered styling (aki-context-to-html)...');
  const result = spawnSync(bunBin, args, { stdio: ['inherit', 'pipe', 'pipe'] });
  if (result.status !== 0) {
    const stderr = result.stderr?.toString() || '';
    throw new Error(`Failed to parse markdown: ${stderr}`);
  }

  const output = result.stdout.toString();
  return JSON.parse(output);
}

function parseHtmlMeta(htmlPath: string): { title: string; author: string; summary: string } {
  const content = fs.readFileSync(htmlPath, 'utf-8');

  let title = '';
  const titleMatch = content.match(/<title>([^<]+)<\/title>/i);
  if (titleMatch) title = titleMatch[1]!;

  let author = '';
  const authorMatch = content.match(/<meta\s+name=["']author["']\s+content=["']([^"']+)["']/i);
  if (authorMatch) author = authorMatch[1]!;

  let summary = '';
  const descMatch = content.match(/<meta\s+name=["']description["']\s+content=["']([^"']+)["']/i);
  if (descMatch) summary = descMatch[1]!;

  if (!summary) {
    const firstPMatch = content.match(/<p[^>]*>([^<]+)<\/p>/i);
    if (firstPMatch) {
      const text = firstPMatch[1]!.replace(/<[^>]+>/g, '').trim();
      if (text.length > 20) {
        summary = text.length > 120 ? text.slice(0, 117) + '...' : text;
      }
    }
  }

  return { title, author, summary };
}

async function selectAndReplacePlaceholder(session: ChromeSession, placeholder: string): Promise<boolean> {
  const result = await session.cdp.send<{ result: { value: boolean } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const editor = document.querySelector('.ProseMirror');
        if (!editor) return false;

        const normalize = (value) => (value || '').replace(/[^a-zA-Z0-9]+/g, '').toLowerCase();
        const needle = normalize(${JSON.stringify(placeholder)});
        const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT, null, false);
        let node;

        while ((node = walker.nextNode())) {
          const text = node.textContent || '';
          const idx = text.indexOf(${JSON.stringify(placeholder)});
          if (idx !== -1) {
            node.parentElement.scrollIntoView({ behavior: 'smooth', block: 'center' });

            editor.focus();
            const range = document.createRange();
            range.setStart(node, idx);
            range.setEnd(node, idx + ${placeholder.length});
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            return sel.toString() === ${JSON.stringify(placeholder)};
          }

          const normalized = normalize(text);
          const normIdx = needle ? normalized.indexOf(needle) : -1;
          if (normIdx !== -1) {
            let rawStart = -1;
            let rawEnd = -1;
            let count = 0;
            for (let i = 0; i < text.length; i++) {
              const ch = text[i];
              if (/[a-zA-Z0-9]/.test(ch)) {
                if (count === normIdx && rawStart === -1) rawStart = i;
                if (count === normIdx + needle.length - 1) {
                  rawEnd = i + 1;
                  break;
                }
                count++;
              }
            }
            if (rawStart !== -1 && rawEnd !== -1) {
              node.parentElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
              editor.focus();
              const range = document.createRange();
              range.setStart(node, rawStart);
              range.setEnd(node, rawEnd);
              const sel = window.getSelection();
              sel.removeAllRanges();
              sel.addRange(range);
              return normalize(sel.toString()) === needle;
            }
          }
        }
        return false;
      })()
    `,
    returnByValue: true,
  }, { sessionId: session.sessionId });

  return result.result.value;
}

async function deleteSelectedText(session: ChromeSession): Promise<void> {
  await session.cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        try {
          document.execCommand('delete');
        } catch (err) {}
        return true;
      })()
    `,
    returnByValue: true,
  }, { sessionId: session.sessionId });
}

async function pressDeleteKey(session: ChromeSession): Promise<void> {
  await session.cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8 }, { sessionId: session.sessionId });
  await sleep(50);
  await session.cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8 }, { sessionId: session.sessionId });
}

async function isOriginalDialogVisible(session: ChromeSession): Promise<boolean> {
  return await evaluate<boolean>(session, `
    (function() {
      const isVisible = (el) => {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        if (!r || r.width < 2 || r.height < 2) return false;
        const st = window.getComputedStyle(el);
        return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
      };
      const dialogs = Array.from(document.querySelectorAll('.weui-desktop-dialog')).filter(isVisible);
      return dialogs.some((d) => ((d.querySelector('.weui-desktop-dialog__title')?.textContent || d.textContent || '').replace(/\\s+/g, '').includes('原创')));
    })()
  `);
}

async function clickPrimaryButtonInDialog(session: ChromeSession, labels: string[] = ['确定', '确认', '完成']): Promise<boolean> {
  return await evaluate<boolean>(session, `
    (function() {
      const labels = ${JSON.stringify(labels)};
      const norm = (s) => (s || '').replace(/\\s+/g, '').trim();
      const isVisible = (el) => {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        if (!r || r.width < 2 || r.height < 2) return false;
        const st = window.getComputedStyle(el);
        return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
      };
      const dialogs = Array.from(document.querySelectorAll('.weui-desktop-dialog,[role="dialog"]')).filter(isVisible);
      for (const dialog of dialogs) {
        const buttons = Array.from(dialog.querySelectorAll('button,a,.weui-desktop-btn'));
        for (const btn of buttons) {
          if (!isVisible(btn)) continue;
          const t = norm(btn.textContent);
          if (!t || t.includes('取消')) continue;
          if (labels.some((l) => t === norm(l))) {
            btn.click();
            return true;
          }
        }
        const primary = dialog.querySelector('.weui-desktop-btn_primary');
        if (primary && isVisible(primary)) {
          primary.click();
          return true;
        }
      }
      return false;
    })()
  `);
}

async function handleOriginalDialogIfPresent(session: ChromeSession, authorName: string): Promise<boolean> {
  const exists = await isOriginalDialogVisible(session);
  if (!exists) return false;

  await evaluate(session, `
    (function() {
      const isVisible = (el) => {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        if (!r || r.width < 2 || r.height < 2) return false;
        const st = window.getComputedStyle(el);
        return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
      };
      const dialogs = Array.from(document.querySelectorAll('.weui-desktop-dialog')).filter(isVisible);
      const dialog = dialogs.find((d) => ((d.querySelector('.weui-desktop-dialog__title')?.textContent || d.textContent || '').replace(/\\s+/g, '').includes('原创')));
      if (!dialog) return false;

      const pickVisible = (arr) => arr.find((el) => isVisible(el) && !el.disabled);
      const typeRadio = pickVisible(Array.from(dialog.querySelectorAll('input.js_original_type_radio[value="0"]')));
      if (typeRadio && !typeRadio.checked) {
        const label = typeRadio.closest('label') || typeRadio;
        label.click();
      }

      const authorInputs = Array.from(dialog.querySelectorAll(
        '.js_customerauthor_container input.js_author, .js_customerauthor_container input, input[placeholder*="作者"], input.js_author'
      ));
      const authorInput = pickVisible(authorInputs);
      if (authorInput) {
        authorInput.focus();
        authorInput.value = ${JSON.stringify(authorName)};
        authorInput.dispatchEvent(new Event('input', { bubbles: true }));
        authorInput.dispatchEvent(new Event('change', { bubbles: true }));
      }

      const agreement = pickVisible(Array.from(dialog.querySelectorAll('.original_agreement input[type="checkbox"], .original_agreement .weui-desktop-form__checkbox')));
      if (agreement && !agreement.checked) {
        const label = agreement.closest('label') || agreement;
        label.click();
      }
      return true;
    })()
  `);

  await sleep(250);
  await clickPrimaryButtonInDialog(session, ['确定', '确认']);

  for (let i = 0; i < 24; i++) {
    if (!(await isOriginalDialogVisible(session))) break;
    await sleep(250);
  }

  console.log(`[wechat] Original dialog handled with author: ${authorName}`);
  return true;
}

export async function postArticle(options: ArticleOptions): Promise<void> {
  const { title, content, htmlFile, markdownFile, theme, author, summary, images = [], submit = false, profileDir, skipTitle = false, manualPaste = false, useAI = false } = options;
  let { contentImages = [] } = options;
  let effectiveTitle = title || '';
  let effectiveAuthor = author || DEFAULT_ORIGINAL_AUTHOR;
  let effectiveSummary = summary || '';
  let effectiveHtmlFile = htmlFile;

  if (markdownFile) {
    console.log(`[wechat] Parsing markdown: ${markdownFile}`);
    const parsed = await parseMarkdownWithPlaceholders(markdownFile, theme, useAI);
    effectiveTitle = effectiveTitle || parsed.title;
    effectiveAuthor = effectiveAuthor || parsed.author;
    effectiveSummary = effectiveSummary || parsed.summary;
    effectiveHtmlFile = parsed.htmlPath;
    contentImages = parsed.contentImages;
    console.log(`[wechat] Title: ${effectiveTitle || '(empty)'}`);
    console.log(`[wechat] Author: ${effectiveAuthor || '(empty)'}`);
    console.log(`[wechat] Summary: ${effectiveSummary || '(empty)'}`);
    console.log(`[wechat] Found ${contentImages.length} images to insert`);
  } else if (htmlFile && fs.existsSync(htmlFile)) {
    console.log(`[wechat] Parsing HTML: ${htmlFile}`);
    const meta = parseHtmlMeta(htmlFile);
    effectiveTitle = effectiveTitle || meta.title;
    effectiveAuthor = effectiveAuthor || meta.author;
    effectiveSummary = effectiveSummary || meta.summary;
    effectiveHtmlFile = htmlFile;
    console.log(`[wechat] Title: ${effectiveTitle || '(empty)'}`);
    console.log(`[wechat] Author: ${effectiveAuthor || '(empty)'}`);
    console.log(`[wechat] Summary: ${effectiveSummary || '(empty)'}`);
  }

  if (effectiveTitle && effectiveTitle.length > 64) throw new Error(`Title too long: ${effectiveTitle.length} chars (max 64)`);
  if (!content && !effectiveHtmlFile) throw new Error('Either --content, --html, or --markdown is required');

  const { cdp } = await launchChrome(WECHAT_URL, profileDir);

  try {
    console.log('[wechat] Waiting for page load...');
    await sleep(3000);

    let session: ChromeSession;
    try {
      session = await getWeChatSession(cdp);
    } catch (err) {
      console.warn(`[wechat] No existing WeChat tab, opening a new one: ${err instanceof Error ? err.message : String(err)}`);
      session = await openWeChatHome(cdp);
      await sleep(2000);
    }

    const loggedIn = await isLoggedIn(session);
    if (!loggedIn) {
      console.log('[wechat] Not logged in. Please scan QR code...');
      const ok = await waitForLogin(session);
      if (!ok) throw new Error('Login timeout');
    }
    console.log('[wechat] Logged in.');
    await sleep(1000);
    await ensureHome(session);

    const targets = await cdp.send<{ targetInfos: Array<{ targetId: string; url: string; type: string }> }>('Target.getTargets');
    const initialIds = new Set(targets.targetInfos.map(t => t.targetId));

    await clickMenuByText(session, '文章');
    await sleep(3000);

    const editorTargetId = await waitForNewTab(cdp, initialIds, 'mp.weixin.qq.com');
    console.log('[wechat] Editor tab opened.');

    const { sessionId } = await cdp.send<{ sessionId: string }>('Target.attachToTarget', { targetId: editorTargetId, flatten: true });
    session = { cdp, sessionId, targetId: editorTargetId };

    await cdp.send('Page.enable', {}, { sessionId });
    await cdp.send('Runtime.enable', {}, { sessionId });
    await cdp.send('DOM.enable', {}, { sessionId });

    await sleep(3000);

    if (effectiveTitle && !skipTitle) {
      console.log('[wechat] Filling title...');
      await evaluate(session, `document.querySelector('#title').value = ${JSON.stringify(effectiveTitle)}; document.querySelector('#title').dispatchEvent(new Event('input', { bubbles: true }));`);
    }

    if (effectiveAuthor) {
      console.log('[wechat] Filling author...');
      await evaluate(session, `document.querySelector('#author').value = ${JSON.stringify(effectiveAuthor)}; document.querySelector('#author').dispatchEvent(new Event('input', { bubbles: true }));`);
    }

    console.log('[wechat] Clicking on editor...');
    await clickElement(session, '.ProseMirror');
    await sleep(500);

    if (effectiveHtmlFile && fs.existsSync(effectiveHtmlFile)) {
      console.log(`[wechat] Copying HTML content from: ${effectiveHtmlFile}`);
      try {
        await copyHtmlToClipboard(effectiveHtmlFile);
      } catch (err) {
        console.warn(`[wechat] Clipboard HTML copy failed, falling back to browser selection: ${err instanceof Error ? err.message : String(err)}`);
        await copyHtmlFromBrowser(cdp, effectiveHtmlFile);
      }
      await sleep(500);
      console.log('[wechat] Refocusing editor...');
      await focusEditor(session);

      if (manualPaste) {
        console.log('[wechat] Manual paste mode. Paste now (Cmd+V) in the editor.');
        await waitForEnter('[wechat] Press Enter after paste... ');
      } else {
        console.log('[wechat] Pasting into editor...');
        await pasteFromClipboardInEditor();
        await sleep(3000);

        const contentLength = await evaluate<number>(session, 'document.querySelector(".ProseMirror")?.textContent?.trim().length || 0');
        if (contentLength < 10) {
          console.warn('[wechat] Editor still empty after paste, retrying with CDP paste...');
          await focusEditor(session);
          await pasteInEditor(session);
          await sleep(3000);
          const retryLength = await evaluate<number>(session, 'document.querySelector(".ProseMirror")?.textContent?.trim().length || 0');
          if (retryLength < 10) {
            throw new Error('Paste failed: editor still empty after retry. Try keeping the editor in the foreground.');
          }
        }
      }

      const ensureLength = await evaluate<number>(session, 'document.querySelector(".ProseMirror")?.textContent?.trim().length || 0');
      if (ensureLength < 10) {
        throw new Error('Editor is empty. Please paste content before continuing.');
      }

      if (contentImages.length > 0) {
        console.log(`[wechat] Inserting ${contentImages.length} images...`);
        for (let i = 0; i < contentImages.length; i++) {
          const img = contentImages[i]!;
          console.log(`[wechat] [${i + 1}/${contentImages.length}] Processing: ${img.placeholder}`);

          const found = await selectAndReplacePlaceholder(session, img.placeholder);
          if (!found) {
            console.warn(`[wechat] Placeholder not found: ${img.placeholder}`);
            continue;
          }

          await sleep(500);

          console.log(`[wechat] Copying image: ${path.basename(img.localPath)}`);
          await copyImageToClipboard(img.localPath);
          await sleep(300);

          console.log('[wechat] Deleting placeholder...');
          await deleteSelectedText(session);
          await sleep(200);

          console.log('[wechat] Pasting image...');
          await activateChrome();
          await pasteFromClipboardInEditor();
          await sleep(3000);
          const imageCount = await evaluate<number>(session, 'document.querySelectorAll(".ProseMirror img").length');
          console.log(`[wechat] Image count now: ${imageCount}`);
        }
        console.log('[wechat] All images inserted.');
      }
    } else if (content) {
      for (const img of images) {
        if (fs.existsSync(img)) {
          console.log(`[wechat] Pasting image: ${img}`);
          await copyImageToClipboard(img);
          await sleep(500);
          await pasteInEditor(session);
          await sleep(2000);
        }
      }

      console.log('[wechat] Typing content...');
      await typeText(session, content);
      await sleep(1000);
    }

    if (effectiveSummary) {
      console.log(`[wechat] Filling summary: ${effectiveSummary}`);
      await evaluate(session, `document.querySelector('#js_description').value = ${JSON.stringify(effectiveSummary)}; document.querySelector('#js_description').dispatchEvent(new Event('input', { bubbles: true }));`);
    }

    await handleOriginalDialogIfPresent(session, effectiveAuthor || DEFAULT_ORIGINAL_AUTHOR);
    console.log('[wechat] Saving as draft...');
    await evaluate(session, `document.querySelector('#js_submit button').click()`);
    await sleep(3000);

    if (await isOriginalDialogVisible(session)) {
      console.log('[wechat] Original dialog shown after save click, handling...');
      await handleOriginalDialogIfPresent(session, effectiveAuthor || DEFAULT_ORIGINAL_AUTHOR);
      await sleep(600);
      await evaluate(session, `document.querySelector('#js_submit button').click()`);
      await sleep(2500);
    }

    const saved = await evaluate<boolean>(session, `!!document.querySelector('.weui-desktop-toast')`);
    if (saved) {
      console.log('[wechat] Draft saved successfully!');
    } else {
      console.log('[wechat] Waiting for save confirmation...');
      await sleep(5000);
    }

    console.log('[wechat] Done. Browser window left open.');
  } finally {
    cdp.close();
  }
}

function printUsage(): never {
  console.log(`Post article to WeChat Official Account

Usage:
  npx -y bun wechat-article.ts [options]

Options:
  --title <text>     Article title (auto-extracted from markdown)
  --content <text>   Article content (use with --image)
  --html <path>      HTML file to paste (alternative to --content)
  --markdown <path>  Markdown file to convert and post (recommended)
  --theme <name>     Theme for markdown (default, grace, simple, huasheng)
  --ai               Use AI-powered styling (aki-context-to-html GLM model)
  --author <name>    Author name (default: Aki聊AI)
  --summary <text>   Article summary
  --image <path>     Content image, can repeat (only with --content)
  --skip-title       Skip auto-filling the title
  --manual-paste     Pause for manual paste before inserting images
  --submit           Save as draft
  --profile <dir>    Chrome profile directory

Examples:
  npx -y bun wechat-article.ts --markdown article.md
  npx -y bun wechat-article.ts --markdown article.md --theme grace --submit
  npx -y bun wechat-article.ts --markdown article.md --ai --submit
  npx -y bun wechat-article.ts --title "标题" --content "内容" --image img.png
  npx -y bun wechat-article.ts --title "标题" --html article.html --submit
  npx -y bun wechat-article.ts --markdown article.md --skip-title
  npx -y bun wechat-article.ts --markdown article.md --manual-paste

Markdown mode:
  Images in markdown are converted to placeholders. After pasting HTML,
  each placeholder is selected, scrolled into view, deleted, and replaced
  with the actual image via paste.

AI mode (--ai):
  Uses aki-context-to-html with GLM AI model for intelligent styling:
  - Smart highlights: <mark> for key insights, <em> for terms
  - Better typography: 20px font, Noto Serif SC
  - Semantic formatting based on content understanding
`);
  process.exit(0);
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  if (args.includes('--help') || args.includes('-h')) printUsage();

  const images: string[] = [];
  let title: string | undefined;
  let content: string | undefined;
  let htmlFile: string | undefined;
  let markdownFile: string | undefined;
  let theme: string = 'huasheng';  // Default to huasheng theme
  let author: string | undefined;
  let summary: string | undefined;
  let submit = false;
  let skipTitle = false;
  let manualPaste = false;
  let profileDir: string | undefined;
  let useAI = false;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i]!;
    if (arg === '--title' && args[i + 1]) title = args[++i];
    else if (arg === '--content' && args[i + 1]) content = args[++i];
    else if (arg === '--html' && args[i + 1]) htmlFile = args[++i];
    else if (arg === '--markdown' && args[i + 1]) markdownFile = args[++i];
    else if (arg === '--theme' && args[i + 1]) theme = args[++i];
    else if (arg === '--author' && args[i + 1]) author = args[++i];
    else if (arg === '--summary' && args[i + 1]) summary = args[++i];
    else if (arg === '--image' && args[i + 1]) images.push(args[++i]!);
    else if (arg === '--skip-title') skipTitle = true;
    else if (arg === '--manual-paste') manualPaste = true;
    else if (arg === '--submit') submit = true;
    else if (arg === '--profile' && args[i + 1]) profileDir = args[++i];
    else if (arg === '--ai') useAI = true;
  }

  if (!markdownFile && !htmlFile && !title) { console.error('Error: --title is required (or use --markdown/--html)'); process.exit(1); }
  if (!markdownFile && !htmlFile && !content) { console.error('Error: --content, --html, or --markdown is required'); process.exit(1); }

  await postArticle({ title: title || '', content, htmlFile, markdownFile, theme, author, summary, images, submit, profileDir, skipTitle, manualPaste, useAI });
}

await main().catch((err) => {
  console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
  process.exit(1);
});
