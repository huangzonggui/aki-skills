import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import { mkdir, readdir } from 'node:fs/promises';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';

const WECHAT_URL = 'https://mp.weixin.qq.com/';
const DEBUG_UPLOAD = process.env.WECHAT_BROWSER_DEBUG_UPLOAD === '1';
const DEFAULT_ORIGINAL_AUTHOR = (process.env.WECHAT_ORIGINAL_AUTHOR || 'Aki聊AI').trim();

interface MarkdownMeta {
  title: string;
  author: string;
  content: string;
}

function parseMarkdownFile(filePath: string): MarkdownMeta {
  const text = fs.readFileSync(filePath, 'utf-8');
  let title = '';
  let author = '';
  let content = '';

  const fmMatch = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (fmMatch) {
    const fm = fmMatch[1]!;
    const titleMatch = fm.match(/^title:\s*(.+)$/m);
    if (titleMatch) title = titleMatch[1]!.trim().replace(/^["']|["']$/g, '');
    const authorMatch = fm.match(/^author:\s*(.+)$/m);
    if (authorMatch) author = authorMatch[1]!.trim().replace(/^["']|["']$/g, '');
  }

  const bodyText = fmMatch ? text.slice(fmMatch[0].length) : text;

  if (!title) {
    const h1Match = bodyText.match(/^#\s+(.+)$/m);
    if (h1Match) title = h1Match[1]!.trim();
  }

  const lines = bodyText.split('\n');
  const outLines: string[] = [];
  let lastWasBlank = true;
  let approxLen = 0;
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('![') || trimmed.startsWith('---')) continue;

    if (!trimmed) {
      if (!lastWasBlank) {
        outLines.push('');
        approxLen += 1;
        lastWasBlank = true;
      }
      continue;
    }

    // Keep heading semantics but remove markdown marker for plain-text posting.
    const normalized = trimmed.startsWith('#')
      ? trimmed.replace(/^#+\s*/, '')
      : trimmed;
    outLines.push(normalized);
    approxLen += normalized.length + 1;
    lastWasBlank = false;
    if (approxLen > 1200) break;
  }
  content = outLines.join('\n').trim();

  return { title, author, content };
}

function compressTitle(title: string, maxLen = 20): string {
  if (title.length <= maxLen) return title;

  const prefixes = ['如何', '为什么', '什么是', '怎样', '怎么', '关于'];
  let t = title;
  for (const p of prefixes) {
    if (t.startsWith(p) && t.length > maxLen) {
      t = t.slice(p.length);
      if (t.length <= maxLen) return t;
    }
  }

  const fillers = ['的', '了', '在', '是', '和', '与', '以及', '或者', '或', '还是', '而且', '并且', '但是', '但', '因为', '所以', '如果', '那么', '虽然', '不过', '然而', '——', '…'];
  for (const f of fillers) {
    if (t.length <= maxLen) break;
    t = t.replace(new RegExp(f, 'g'), '');
  }

  if (t.length > maxLen) t = t.slice(0, maxLen);

  return t;
}

function compressContent(content: string, maxLen = 1000): string {
  if (content.length <= maxLen) return content;

  const lines = content.split('\n');
  const result: string[] = [];
  let len = 0;

  for (const line of lines) {
    if (len + line.length + 1 > maxLen) {
      const remaining = maxLen - len - 1;
      if (remaining > 20) result.push(line.slice(0, remaining - 3) + '...');
      break;
    }
    result.push(line);
    len += line.length + 1;
  }

  return result.join('\n');
}

async function loadImagesFromDir(dir: string): Promise<string[]> {
  const entries = await readdir(dir);
  const images = entries
    .filter(f => /\.(png|jpg|jpeg|gif|webp)$/i.test(f))
    .sort()
    .map(f => path.join(dir, f));
  return images;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function pasteImageViaClipboard(imagePath: string): boolean {
  try {
    const scriptDir = path.dirname(new URL(import.meta.url).pathname);
    const bunBin = process.execPath || 'bun';
    const copyScript = path.join(scriptDir, 'copy-to-clipboard.ts');
    const pasteScript = path.join(scriptDir, 'paste-from-clipboard.ts');

    const copy = spawnSync(bunBin, [copyScript, 'image', imagePath], { stdio: 'inherit' });
    if ((copy.status ?? 1) !== 0) {
      console.warn('[wechat-browser] Clipboard fallback failed at copy-to-clipboard');
      return false;
    }

    const paste = spawnSync(bunBin, [pasteScript, '--app', 'Google Chrome', '--retries', '5', '--delay', '350'], { stdio: 'inherit' });
    if ((paste.status ?? 1) !== 0) {
      console.warn('[wechat-browser] Clipboard fallback failed at paste-from-clipboard');
      return false;
    }
    return true;
  } catch (err) {
    console.warn(`[wechat-browser] Clipboard fallback exception: ${err instanceof Error ? err.message : String(err)}`);
    return false;
  }
}

function pasteHtmlViaClipboard(html: string): boolean {
  try {
    const scriptDir = path.dirname(new URL(import.meta.url).pathname);
    const bunBin = process.execPath || 'bun';
    const copyScript = path.join(scriptDir, 'copy-to-clipboard.ts');
    const pasteScript = path.join(scriptDir, 'paste-from-clipboard.ts');

    const copy = spawnSync(bunBin, [copyScript, 'html'], {
      input: html,
      stdio: ['pipe', 'inherit', 'inherit'],
    });
    if ((copy.status ?? 1) !== 0) {
      console.warn('[wechat-browser] Clipboard HTML fallback failed at copy-to-clipboard');
      return false;
    }

    const paste = spawnSync(bunBin, [pasteScript, '--app', 'Google Chrome', '--retries', '5', '--delay', '350'], { stdio: 'inherit' });
    if ((paste.status ?? 1) !== 0) {
      console.warn('[wechat-browser] Clipboard HTML fallback failed at paste-from-clipboard');
      return false;
    }
    return true;
  } catch (err) {
    console.warn(`[wechat-browser] Clipboard HTML fallback exception: ${err instanceof Error ? err.message : String(err)}`);
    return false;
  }
}

async function waitForImagesUploaded(
  cdp: CdpConnection,
  sessionId: string,
  expectedCount: number,
  timeoutMs = 45_000,
): Promise<void> {
  const start = Date.now();
  const minWaitMs = 8_000;
  let bestCount = 0;

  while (Date.now() - start < timeoutMs) {
    const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
      expression: `
        (function() {
          const countBySelector = (selector) => {
            try { return document.querySelectorAll(selector).length; } catch { return 0; }
          };

          const possibleCounts = [
            countBySelector('.weui-desktop-uploader__file'),
            countBySelector('.weui-desktop-uploader__files li'),
            countBySelector('.js_upload_list li'),
            countBySelector('.js_img_list li'),
            countBySelector('.js_cover_preview img'),
            countBySelector('.weui-desktop-uploader img'),
            countBySelector('.js_appmsg_thumb img'),
            countBySelector('.js_appmsg_thumb_wrp img'),
            countBySelector('[class*="thumb"] img'),
          ];

          const uploading = [
            countBySelector('.weui-desktop-uploader__progress'),
            countBySelector('.is-uploading'),
            countBySelector('.uploading'),
            countBySelector('.weui-desktop-icon-loading'),
          ].reduce((a, b) => a + b, 0);

          const hasCoverStyle = !!Array.from(
            document.querySelectorAll('.js_cover_preview, .js_cover_preview_new, .js_appmsg_thumb_wrp, [class*="thumb"]')
          ).find((el) => {
            const inline = (el && el.style && el.style.cssText) ? el.style.cssText : '';
            const style = (el.getAttribute('style') || '') + ' ' + inline;
            const m = style.match(/background-image\\s*:\\s*url\\(([^)]+)\\)/i);
            if (!m) return false;
            const url = (m[1] || '').replace(/['"]/g, '').trim().toLowerCase();
            if (!url) return false;
            if (url.includes('undefined') || url.includes('null') || url.includes('about:blank')) return false;
            return true;
          });

          return JSON.stringify({
            count: Math.max(...possibleCounts),
            uploading,
            hasCoverStyle,
            raw: possibleCounts,
          });
        })()
      `,
      returnByValue: true,
    }, { sessionId });

    const parsed = JSON.parse(result.result.value) as {
      count: number;
      uploading: number;
      hasCoverStyle: boolean;
      raw: number[];
    };
    bestCount = Math.max(bestCount, parsed.count);
    const elapsed = Date.now() - start;
    const enoughWait = elapsed >= minWaitMs;
    const hasVisualSignal = parsed.count >= expectedCount || parsed.hasCoverStyle;

    if (enoughWait && hasVisualSignal && parsed.uploading === 0) {
      console.log(`[wechat-browser] Images upload likely complete: count=${parsed.count}, cover=${parsed.hasCoverStyle}`);
      return;
    }

    await sleep(800);
  }

  console.warn(`[wechat-browser] Images upload check timeout. expected=${expectedCount}, observed=${bestCount}. Continue after grace wait.`);
  await sleep(6_000);
}

async function detectImageUploadIssue(
  cdp: CdpConnection,
  sessionId: string,
): Promise<string | null> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const isVisible = (el) => {
          if (!el) return false;
          const r = el.getBoundingClientRect();
          if (!r || r.width < 2 || r.height < 2) return false;
          const st = window.getComputedStyle(el);
          return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
        };
        const coverError = document.querySelector('#js_cover_description_area .js_cover_error, #js_cover_error');
        if (coverError && isVisible(coverError)) {
          const msg = (coverError.textContent || '').trim();
          if (msg) return msg;
        }
        const selectors = [
          '.weui-desktop-toast',
          '.weui-desktop-tips',
          '.weui-desktop-dialog',
          '.weui-desktop-popover',
          '.weui-desktop-msg',
          '.weui-desktop-notification',
        ];
        const nodes = selectors.flatMap((s) => Array.from(document.querySelectorAll(s))).filter(isVisible);
        const visibleText = nodes
          .map((n) => (n && n.textContent ? n.textContent.trim() : ''))
          .filter(Boolean)
          .join('\\n');
        const haystack = visibleText.replace(/\\s+/g, ' ');
        const patterns = [
          /图片不能为空/i,
          /图片加载失败/i,
          /上传失败[^。\\n]*/i,
          /图片[^。\\n]{0,20}(失败|过大|超出|不支持|格式)/i,
          /(格式|大小|尺寸)[^。\\n]{0,20}(不支持|错误|失败)/i,
        ];
        for (const p of patterns) {
          const m = haystack.match(p);
          if (m) return m[0];
        }
        return '';
      })()
    `,
    returnByValue: true,
  }, { sessionId });

  const msg = (result.result.value || '').trim();
  return msg || null;
}

async function verifyCoverReady(cdp: CdpConnection, sessionId: string): Promise<boolean> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const area = document.querySelector('#js_cover_description_area');
        if (!area) return 'false';
        const err = document.querySelector('#js_cover_description_area .js_cover_error');
        if (err) {
          const st = window.getComputedStyle(err);
          const txt = (err.textContent || '').trim();
          if (st.display !== 'none' && txt) return 'false';
        }
        const isValidUrl = (raw) => {
          const url = (raw || '').replace(/['"]/g, '').trim().toLowerCase();
          if (!url) return false;
          if (url.includes('undefined') || url.includes('null') || url.includes('about:blank')) return false;
          return true;
        };
        const hasValidBg = (el) => {
          const st = (el.getAttribute('style') || '') + ' ' + (el.style?.cssText || '');
          const m = st.match(/background-image\\s*:\\s*url\\(([^)]+)\\)/i);
          return !!(m && isValidUrl(m[1] || ''));
        };
        const hasValidImg = (el) => {
          const imgs = Array.from(el.querySelectorAll('img'));
          for (const img of imgs) {
            const src = (img.getAttribute('src') || img.getAttribute('data-src') || '').trim();
            if (isValidUrl(src)) return true;
          }
          return false;
        };
        const cover = Array.from(document.querySelectorAll(
          '#js_cover_description_area .js_cover_preview_new, #js_cover_description_area .js_cover_preview, #js_cover_description_area .first_appmsg_cover, #js_cover_description_area [class*="cover"], #js_cover_description_area'
        ));
        for (const el of cover) {
          const r = el.getBoundingClientRect();
          const stMain = window.getComputedStyle(el);
          if (!r || r.width < 2 || r.height < 2) continue;
          if (stMain.display === 'none' || stMain.visibility === 'hidden' || stMain.opacity === '0') continue;
          if (hasValidBg(el) || hasValidImg(el)) return 'true';
        }
        return 'false';
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  return result.result.value === 'true';
}

async function hasLegacyCoverArea(cdp: CdpConnection, sessionId: string): Promise<boolean> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `document.querySelector('#js_cover_description_area') ? 'true' : 'false'`,
    returnByValue: true,
  }, { sessionId });
  return result.result.value === 'true';
}

async function verifyImageTextUploadReady(cdp: CdpConnection, sessionId: string): Promise<boolean> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const isVisible = (el) => {
          const r = el.getBoundingClientRect();
          if (!r || r.width < 2 || r.height < 2) return false;
          const st = window.getComputedStyle(el);
          return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
        };
        const isLikelyRealImage = (img) => {
          if (!img || !isVisible(img)) return false;
          const src = (img.getAttribute('src') || img.getAttribute('data-src') || '').toLowerCase();
          if (!src) return false;
          if (src.includes('icon') || src.includes('emoji') || src.includes('svg') || src.includes('base64')) return false;
          const r = img.getBoundingClientRect();
          const w = Math.max(r.width || 0, img.naturalWidth || 0);
          const h = Math.max(r.height || 0, img.naturalHeight || 0);
          return w >= 80 && h >= 80;
        };

        const imgSelectors = [
          '.weui-desktop-uploader__file img',
          '.weui-desktop-uploader__files img',
          '.js_upload_list img',
          '.js_img_list img',
          '[class*="upload"] img',
          '[class*="thumb"] img',
          '[class*="cover"] img',
          '.js_pmEditorArea img',
          '.ProseMirror img',
        ];
        const seen = new Set();
        for (const selector of imgSelectors) {
          const nodes = Array.from(document.querySelectorAll(selector));
          for (const img of nodes) {
            if (!isLikelyRealImage(img)) continue;
            const src = (img.getAttribute('src') || img.getAttribute('data-src') || '').trim();
            if (src) seen.add(src);
          }
        }
        if (seen.size > 0) return 'true';

        const nodes = Array.from(document.querySelectorAll('[style*="background-image"], [class*="thumb"], [class*="cover"], [class*="upload"]'));
        for (const el of nodes) {
          const r = el.getBoundingClientRect();
          if (!r || r.width < 2 || r.height < 2) continue;
          const stMain = window.getComputedStyle(el);
          if (stMain.display === 'none' || stMain.visibility === 'hidden' || stMain.opacity === '0') continue;
          const st = (el.getAttribute('style') || '') + ' ' + (el.style?.cssText || '');
          const m = st.match(/background-image\\s*:\\s*url\\(([^)]+)\\)/i);
          if (!m) continue;
          const url = (m[1] || '').replace(/['"]/g, '').trim().toLowerCase();
          if (!url || url.includes('undefined') || url.includes('null') || url.includes('about:blank')) continue;
          if (url.includes('icon') || url.includes('emoji') || url.includes('svg') || url.includes('base64')) continue;
          return 'true';
        }
        return 'false';
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  return result.result.value === 'true';
}

async function hasSelectedUploadFiles(cdp: CdpConnection, sessionId: string): Promise<boolean> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const inputs = Array.from(document.querySelectorAll('input[type=file]'));
        return inputs.some((input) => (input.files?.length || 0) > 0) ? 'true' : 'false';
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  return result.result.value === 'true';
}

async function findTopImageFileInputNodeIds(cdp: CdpConnection, sessionId: string): Promise<number[]> {
  const { root } = await cdp.send<{ root: { nodeId: number } }>('DOM.getDocument', {}, { sessionId });
  const selectors = [
    '#js_content_top .image-selector .js_upload_btn_container input[type=file]',
    '#js_content_top .js_upload_btn_container input[type=file]',
    '#js_content_top input[type=file]',
  ];
  for (const selector of selectors) {
    const { nodeIds } = await cdp.send<{ nodeIds: number[] }>('DOM.querySelectorAll', {
      nodeId: root.nodeId,
      selector,
    }, { sessionId });
    if (nodeIds.length > 0) {
      console.log(`[wechat-browser] Using top-image input selector: ${selector} (count=${nodeIds.length})`);
      return nodeIds;
    }
  }
  throw new Error('Top image uploader input not found under #js_content_top');
}

async function verifyTopImageReady(cdp: CdpConnection, sessionId: string): Promise<boolean> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const top = document.querySelector('#js_content_top');
        if (!top) return 'false';
        const isVisible = (el) => {
          if (!el) return false;
          const r = el.getBoundingClientRect();
          if (!r || r.width < 2 || r.height < 2) return false;
          const st = window.getComputedStyle(el);
          return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
        };
        const isValidUrl = (raw) => {
          const url = (raw || '').replace(/['"]/g, '').trim().toLowerCase();
          if (!url) return false;
          if (url.includes('undefined') || url.includes('null') || url.includes('about:blank')) return false;
          if (url.includes('icon') || url.includes('emoji') || url.includes('svg') || url.includes('base64')) return false;
          return true;
        };

        const err = top.querySelector('.js_content_top_error, .js_error_msg');
        if (err && isVisible(err)) {
          const txt = (err.textContent || '').replace(/\\s+/g, '');
          if (txt.includes('图片不能为空')) return 'false';
        }

        const imgs = Array.from(top.querySelectorAll('img'));
        for (const img of imgs) {
          if (!isVisible(img)) continue;
          const src = (img.getAttribute('src') || img.getAttribute('data-src') || '').trim();
          if (!isValidUrl(src)) continue;
          const r = img.getBoundingClientRect();
          const w = Math.max(r.width || 0, img.naturalWidth || 0);
          const h = Math.max(r.height || 0, img.naturalHeight || 0);
          if (w >= 80 && h >= 80) return 'true';
        }

        const bgNodes = Array.from(top.querySelectorAll('[style*="background-image"]'));
        for (const el of bgNodes) {
          if (!isVisible(el)) continue;
          const st = (el.getAttribute('style') || '') + ' ' + (el.style?.cssText || '');
          const m = st.match(/background-image\\s*:\\s*url\\(([^)]+)\\)/i);
          if (!m) continue;
          if (isValidUrl(m[1] || '')) return 'true';
        }

        const addArea = top.querySelector('.image-selector__add');
        if (addArea && !isVisible(addArea)) return 'true';

        return 'false';
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  return result.result.value === 'true';
}

async function waitForTopImageReady(cdp: CdpConnection, sessionId: string, timeoutMs = 20_000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await verifyTopImageReady(cdp, sessionId)) return true;
    await sleep(600);
  }
  return false;
}

async function countEditorImages(cdp: CdpConnection, sessionId: string): Promise<number> {
  const result = await cdp.send<{ result: { value: number } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const selectors = ['.js_pmEditorArea img', '.ProseMirror img', '#js_editor img', '.rich_media_content img'];
        const isVisible = (el) => {
          const r = el.getBoundingClientRect();
          if (!r || r.width < 2 || r.height < 2) return false;
          const st = window.getComputedStyle(el);
          return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
        };
        const seen = new Set();
        for (const s of selectors) {
          const nodes = Array.from(document.querySelectorAll(s));
          for (const img of nodes) {
            if (!isVisible(img)) continue;
            const src = (img.getAttribute('src') || img.getAttribute('data-src') || '').toLowerCase();
            if (!src || src.includes('icon') || src.includes('emoji') || src.includes('svg') || src.includes('base64')) continue;
            const r = img.getBoundingClientRect();
            const w = Math.max(r.width || 0, img.naturalWidth || 0);
            const h = Math.max(r.height || 0, img.naturalHeight || 0);
            if (w < 80 || h < 80) continue;
            seen.add(src);
          }
        }
        return seen.size;
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  return Number(result.result.value || 0);
}

async function clickVisibleByText(
  cdp: CdpConnection,
  sessionId: string,
  patterns: string[],
  options?: { exact?: boolean; prefix?: boolean; maxTextLen?: number },
): Promise<boolean> {
  const exact = options?.exact ?? false;
  const prefix = options?.prefix ?? false;
  const maxTextLen = options?.maxTextLen ?? 100;
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const patterns = ${JSON.stringify(patterns)};
        const exact = ${exact ? 'true' : 'false'};
        const prefix = ${prefix ? 'true' : 'false'};
        const maxTextLen = ${maxTextLen};
        const norm = (s) => (s || '').replace(/\\s+/g, '').trim();
        const isVisible = (el) => {
          const r = el.getBoundingClientRect();
          if (!r || r.width < 2 || r.height < 2) return false;
          const st = window.getComputedStyle(el);
          return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
        };
        const nodes = Array.from(document.querySelectorAll(
          'button,a,label,[role="button"],li,span,div,.weui-desktop-dialog__btn,.weui-desktop-dropdown__item'
        ));

        let best = null;
        let bestScore = Number.MAX_SAFE_INTEGER;
        for (const el of nodes) {
          if (!isVisible(el)) continue;
          const t = norm(el.textContent);
          if (!t || t.length > maxTextLen) continue;
          for (const p of patterns) {
            const np = norm(p);
            const matched = exact ? t === np : (prefix ? t.startsWith(np) : t.includes(np));
            if (!matched) continue;
            const score = t.length;
            if (score < bestScore) {
              bestScore = score;
              best = { el, t };
            }
          }
        }

        if (!best) return JSON.stringify({ ok: false });
        best.el.scrollIntoView({ block: 'center', inline: 'center' });
        best.el.click();
        return JSON.stringify({ ok: true, text: best.t });
      })()
    `,
    returnByValue: true,
  }, { sessionId });

  const parsed = JSON.parse(result.result.value) as { ok: boolean; text?: string };
  if (parsed.ok) {
    console.log(`[wechat-browser] Clicked by text: ${parsed.text ?? patterns.join('/')}`);
  } else {
    console.log(`[wechat-browser] Text not found: ${patterns.join('/')}`);
  }
  return parsed.ok;
}

async function setSwitchByRowLabel(
  cdp: CdpConnection,
  sessionId: string,
  patterns: string[],
  desiredOn = true,
): Promise<boolean> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const patterns = ${JSON.stringify(patterns)};
        const desiredOn = ${desiredOn ? 'true' : 'false'};
        const norm = (s) => (s || '').replace(/\\s+/g, '').trim().toLowerCase();
        const isVisible = (el) => {
          const r = el.getBoundingClientRect();
          if (!r || r.width < 2 || r.height < 2) return false;
          const st = window.getComputedStyle(el);
          return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
        };
        const matchText = (text) => {
          const t = norm(text);
          return patterns.some((p) => t.includes(norm(p)));
        };
        const stateOf = (el) => {
          if (!el) return false;
          if (typeof el.checked === 'boolean') return !!el.checked;
          if (el.getAttribute) {
            const aria = el.getAttribute('aria-checked');
            if (aria === 'true') return true;
            if (aria === 'false') return false;
          }
          const cls = (el.className || '').toString().toLowerCase();
          return /(active|checked|selected|on|open)/.test(cls);
        };

        const labels = Array.from(document.querySelectorAll('label,span,div,li'));
        for (const label of labels) {
          if (!isVisible(label)) continue;
          const txt = (label.textContent || '').trim();
          if (!txt || txt.length > 40) continue;
          if (!matchText(txt)) continue;

          let row = label;
          for (let i = 0; i < 6 && row; i++) {
            const s = row.querySelector('input[type="checkbox"],button[role="switch"],[role="switch"],.weui-desktop-switch,.switch,.weui-switch');
            if (s) {
              const current = stateOf(s);
              if (current !== desiredOn) s.click();
              return JSON.stringify({ ok: true, label: txt, changed: current !== desiredOn, currentAfter: desiredOn });
            }
            row = row.parentElement;
          }
        }

        return JSON.stringify({ ok: false });
      })()
    `,
    returnByValue: true,
  }, { sessionId });

  const parsed = JSON.parse(result.result.value) as {
    ok: boolean;
    label?: string;
    changed?: boolean;
    currentAfter?: boolean;
  };
  if (parsed.ok) {
    console.log(`[wechat-browser] Switch set by row: ${parsed.label} (changed=${parsed.changed})`);
    return true;
  }
  console.log(`[wechat-browser] Switch row not found: ${patterns.join('/')}`);
  return false;
}

async function openSettingRow(
  cdp: CdpConnection,
  sessionId: string,
  patterns: string[],
): Promise<boolean> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const patterns = ${JSON.stringify(patterns)};
        const norm = (s) => (s || '').replace(/\\s+/g, '').trim().toLowerCase();
        const isVisible = (el) => {
          const r = el.getBoundingClientRect();
          if (!r || r.width < 2 || r.height < 2) return false;
          const st = window.getComputedStyle(el);
          return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
        };
        const textMatch = (txt) => {
          const t = norm(txt);
          return patterns.some((p) => t.includes(norm(p)));
        };
        const labels = Array.from(document.querySelectorAll('label,span,div,li'));
        for (const lb of labels) {
          if (!isVisible(lb)) continue;
          const txt = (lb.textContent || '').trim();
          if (!txt || txt.length > 40) continue;
          if (!textMatch(txt)) continue;

          let row = lb;
          for (let i = 0; i < 6 && row; i++) {
            const iconBtn = row.querySelector(
              'button,a,[role="button"],.icon,[class*="icon"],[class*="edit"],[class*="arrow"],svg'
            );
            if (iconBtn && isVisible(iconBtn)) {
              iconBtn.click();
              return JSON.stringify({ ok: true, label: txt, via: 'icon' });
            }
            row = row.parentElement;
          }

          lb.click();
          return JSON.stringify({ ok: true, label: txt, via: 'label' });
        }
        return JSON.stringify({ ok: false });
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  const parsed = JSON.parse(result.result.value) as { ok: boolean; label?: string; via?: string };
  if (parsed.ok) {
    console.log(`[wechat-browser] Opened setting row: ${parsed.label} via ${parsed.via}`);
    return true;
  }
  console.log(`[wechat-browser] Setting row not found: ${patterns.join('/')}`);
  return false;
}

async function clickConfirmInDialog(cdp: CdpConnection, sessionId: string): Promise<boolean> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const norm = (s) => (s || '').replace(/\\s+/g, '').trim();
        const isVisible = (el) => {
          const r = el.getBoundingClientRect();
          if (!r || r.width < 2 || r.height < 2) return false;
          const st = window.getComputedStyle(el);
          return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
        };
        const dialogs = Array.from(document.querySelectorAll(
          '.weui-desktop-dialog,.weui-desktop-popover,.weui-desktop-modal,.weui-desktop-sheet,[role="dialog"]'
        )).filter(isVisible);
        if (!dialogs.length) return JSON.stringify({ ok: false });
        const good = ['确定', '确认', '完成', '我知道了'];
        for (const d of dialogs) {
          const nodes = Array.from(d.querySelectorAll('button,a,label,span,div'));
          for (const n of nodes) {
            if (!isVisible(n)) continue;
            const t = norm(n.textContent);
            if (!t || t.length > 12) continue;
            if (t.includes('草稿')) continue;
            if (good.some((g) => t.includes(g))) {
              n.click();
              return JSON.stringify({ ok: true, text: t });
            }
          }
        }
        return JSON.stringify({ ok: false });
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  const parsed = JSON.parse(result.result.value) as { ok: boolean; text?: string };
  if (parsed.ok) {
    console.log(`[wechat-browser] Clicked dialog confirm: ${parsed.text}`);
  }
  return parsed.ok;
}

async function clickPrimaryButtonInVisibleDialog(
  cdp: CdpConnection,
  sessionId: string,
  labels: string[] = ['确定', '确认', '完成'],
): Promise<boolean> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
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
        const dialogs = Array.from(document.querySelectorAll('.weui-desktop-dialog,[role="dialog"],.weui-desktop-modal')).filter(isVisible);
        for (const dialog of dialogs) {
          const buttons = Array.from(dialog.querySelectorAll('button,a,.weui-desktop-btn'));
          for (const btn of buttons) {
            if (!isVisible(btn)) continue;
            const t = norm(btn.textContent);
            if (!t || t.includes('取消')) continue;
            if (labels.some((l) => t === norm(l))) {
              btn.click();
              return JSON.stringify({ ok: true, text: t, via: 'label' });
            }
          }
          const primary = dialog.querySelector('.weui-desktop-btn_primary');
          if (primary && isVisible(primary)) {
            primary.click();
            return JSON.stringify({ ok: true, text: norm(primary.textContent || ''), via: 'primary-class' });
          }
        }
        return JSON.stringify({ ok: false });
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  const parsed = JSON.parse(result.result.value) as { ok: boolean; text?: string; via?: string };
  if (parsed.ok) {
    console.log(`[wechat-browser] Clicked dialog primary: ${parsed.text ?? ''} via ${parsed.via ?? ''}`);
  }
  return parsed.ok;
}

async function handleOriginalDialogIfPresent(
  cdp: CdpConnection,
  sessionId: string,
  authorName: string = DEFAULT_ORIGINAL_AUTHOR,
): Promise<boolean> {
  const prepared = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const norm = (s) => (s || '').replace(/\\s+/g, '').trim();
        const isVisible = (el) => {
          if (!el) return false;
          const r = el.getBoundingClientRect();
          if (!r || r.width < 2 || r.height < 2) return false;
          const st = window.getComputedStyle(el);
          return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
        };
        const dialogs = Array.from(document.querySelectorAll('.weui-desktop-dialog')).filter(isVisible);
        const dialog = dialogs.find((d) => {
          const title = norm(d.querySelector('.weui-desktop-dialog__title')?.textContent || d.textContent || '');
          return title.includes('原创');
        });
        if (!dialog) return JSON.stringify({ ok: false });

        const pickVisible = (arr) => arr.find((el) => isVisible(el) && !el.disabled);

        const textOriginal = pickVisible(Array.from(dialog.querySelectorAll('input.js_original_type_radio[value="0"]')));
        if (textOriginal && !textOriginal.checked) {
          const label = textOriginal.closest('label') || textOriginal;
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

        return JSON.stringify({ ok: true });
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  const parsed = JSON.parse(prepared.result.value) as { ok: boolean };
  if (!parsed.ok) return false;

  const confirmed = await clickPrimaryButtonInVisibleDialog(cdp, sessionId, ['确定', '确认']);
  if (!confirmed) return true;

  const start = Date.now();
  while (Date.now() - start < 6000) {
    const closed = await cdp.send<{ result: { value: boolean } }>('Runtime.evaluate', {
      expression: `
        (function() {
          const isVisible = (el) => {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            if (!r || r.width < 2 || r.height < 2) return false;
            const st = window.getComputedStyle(el);
            return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
          };
          const dialogs = Array.from(document.querySelectorAll('.weui-desktop-dialog')).filter(isVisible);
          const hit = dialogs.find((d) => ((d.querySelector('.weui-desktop-dialog__title')?.textContent || d.textContent || '').replace(/\\s+/g, '').includes('原创')));
          return !hit;
        })()
      `,
      returnByValue: true,
    }, { sessionId });
    if (closed.result.value) break;
    await sleep(250);
  }

  console.log(`[wechat-browser] Original dialog handled with author: ${authorName}`);
  return true;
}

async function debugDumpSettingTexts(cdp: CdpConnection, sessionId: string, stage: string): Promise<void> {
  if (!DEBUG_UPLOAD) return;
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const keys = ['原创','创作','来源','观点','参考','广告','合集','声明','程序化','AI','个人','情况'];
        const norm = (s) => (s || '').replace(/\\s+/g, '').trim();
        const isVisible = (el) => {
          const r = el.getBoundingClientRect();
          if (!r || r.width < 2 || r.height < 2) return false;
          const st = window.getComputedStyle(el);
          return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
        };
        const nodes = Array.from(document.querySelectorAll('label,button,a,li,span,div'));
        const texts = [];
        const seen = new Set();
        for (const n of nodes) {
          if (!isVisible(n)) continue;
          const t = norm(n.textContent);
          if (!t || t.length > 120) continue;
          if (!keys.some((k) => t.includes(k))) continue;
          if (seen.has(t)) continue;
          seen.add(t);
          texts.push(t);
          if (texts.length >= 40) break;
        }
        return JSON.stringify(texts);
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  const texts = JSON.parse(result.result.value) as string[];
  console.log(`[wechat-browser] Setting texts (${stage}): ${texts.join(' | ')}`);
}

async function debugDumpUploadArea(cdp: CdpConnection, sessionId: string, stage: string): Promise<void> {
  if (!DEBUG_UPLOAD) return;
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const isVisible = (el) => {
          const r = el.getBoundingClientRect();
          if (!r || r.width < 2 || r.height < 2) return false;
          const st = window.getComputedStyle(el);
          return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
        };
        const shortSel = (el) => {
          if (!el) return '';
          const id = el.id ? '#' + el.id : '';
          const cls = (el.className || '').toString().trim().split(/\\s+/).slice(0, 3).join('.');
          return (el.tagName || '').toLowerCase() + id + (cls ? '.' + cls : '');
        };
        const keyNodes = [];
        const nodes = Array.from(document.querySelectorAll('a,button,span,div,label,li'));
        for (const el of nodes) {
          const txt = (el.textContent || '').replace(/\\s+/g, '');
          if (!txt) continue;
          if (!/本地上传|图片库|扫码上传|AI配图|拖拽图片|选择或拖拽/.test(txt)) continue;
          const rect = el.getBoundingClientRect();
          keyNodes.push({
            sel: shortSel(el),
            text: txt.slice(0, 60),
            visible: isVisible(el),
            rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
          });
          if (keyNodes.length >= 20) break;
        }
        const fileInputs = Array.from(document.querySelectorAll('input[type=file]')).map((el) => {
          const rect = el.getBoundingClientRect();
          return {
            sel: shortSel(el),
            accept: el.accept || '',
            name: el.name || '',
            visible: isVisible(el),
            rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
          };
        });
        return JSON.stringify({ keyNodes, fileInputs });
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  console.log(`[wechat-browser] Upload area (${stage}): ${result.result.value}`);
}

async function clickBySelectors(
  cdp: CdpConnection,
  sessionId: string,
  selectors: string[],
  label: string,
): Promise<boolean> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const selectors = ${JSON.stringify(selectors)};
        const isVisible = (el) => {
          if (!el) return false;
          const r = el.getBoundingClientRect();
          if (!r || r.width < 2 || r.height < 2) return false;
          const st = window.getComputedStyle(el);
          return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
        };
        for (const selector of selectors) {
          const nodes = Array.from(document.querySelectorAll(selector));
          for (const el of nodes) {
            if (!isVisible(el)) continue;
            el.scrollIntoView({ block: 'center', inline: 'center' });
            el.click();
            return JSON.stringify({ ok: true, selector, text: (el.textContent || '').trim() });
          }
        }
        return JSON.stringify({ ok: false });
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  const parsed = JSON.parse(result.result.value) as { ok: boolean; selector?: string; text?: string };
  if (parsed.ok) {
    console.log(`[wechat-browser] Clicked ${label}: selector=${parsed.selector} text=${parsed.text ?? ''}`);
  } else {
    console.log(`[wechat-browser] Selector not found for ${label}`);
  }
  return parsed.ok;
}

async function pickAndFocusContentEditor(
  cdp: CdpConnection,
  sessionId: string,
  preferGuideEditor: boolean,
): Promise<string> {
  const primary = preferGuideEditor
    ? [
        '#guide_words_main .js_pmEditorArea .ProseMirror[contenteditable="true"]',
        '#guide_words_main .ProseMirror[contenteditable="true"]',
        '.share-text__input .ProseMirror[contenteditable="true"]',
      ]
    : [
        '#js_ueditor .rich_media_content .ProseMirror[contenteditable="true"]',
        '#js_ueditor .ProseMirror[contenteditable="true"]',
        '#ueditor_0 .rich_media_content .ProseMirror[contenteditable="true"]',
        '#ueditor_0 .ProseMirror[contenteditable="true"]',
        '.editor-v-root .rich_media_content .ProseMirror[contenteditable="true"]',
      ];
  const fallback = [
    '.js_pmEditorArea .ProseMirror[contenteditable="true"]',
    '.rich_media_content .ProseMirror[contenteditable="true"]',
    '.ProseMirror[contenteditable="true"]',
    '[contenteditable="true"]',
  ];
  const selectors = [...primary, ...fallback];

  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const selectors = ${JSON.stringify(selectors)};
        const isVisible = (el) => {
          if (!el) return false;
          const r = el.getBoundingClientRect();
          if (!r || r.width < 2 || r.height < 2) return false;
          const st = window.getComputedStyle(el);
          return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
        };
        for (const selector of selectors) {
          const el = document.querySelector(selector);
          if (!el || !isVisible(el)) continue;
          el.scrollIntoView({ block: 'center', inline: 'nearest' });
          el.focus();
          const range = document.createRange();
          range.selectNodeContents(el);
          range.collapse(false);
          const sel = window.getSelection();
          if (sel) {
            sel.removeAllRanges();
            sel.addRange(range);
          }
          return JSON.stringify({ ok: true, selector });
        }
        return JSON.stringify({ ok: false });
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  const parsed = JSON.parse(result.result.value) as { ok: boolean; selector?: string };
  if (!parsed.ok || !parsed.selector) {
    throw new Error('Content editor not found');
  }
  console.log(`[wechat-browser] Focused content editor: ${parsed.selector}`);
  return parsed.selector;
}

async function clearContentEditor(
  cdp: CdpConnection,
  sessionId: string,
  editorSelector: string,
): Promise<void> {
  await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const el = document.querySelector(${JSON.stringify(editorSelector)});
        if (!el) return false;
        el.focus();
        const sel = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(el);
        if (sel) {
          sel.removeAllRanges();
          sel.addRange(range);
        }
        try { document.execCommand('delete', false); } catch {}
        return true;
      })()
    `,
    returnByValue: true,
  }, { sessionId });
}

async function readContentEditorState(
  cdp: CdpConnection,
  sessionId: string,
  editorSelector: string,
): Promise<{ textLen: number; lineBreaks: number; blockCount: number; normalized: string; preview: string }> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const el = document.querySelector(${JSON.stringify(editorSelector)});
        if (!el) return JSON.stringify({ textLen: 0, lineBreaks: 0, blockCount: 0, normalized: '', preview: '' });
        const clone = el.cloneNode(true);
        const placeholders = clone.querySelectorAll('.editor_placeholder,.ProseMirror-widget,.tips_global,.placeholder_tips');
        placeholders.forEach((n) => n.remove());
        const txt = ((clone.innerText || clone.textContent || '') + '').replace(/\\u200b/g, '').trim();
        const normalized = txt.replace(/\\s+/g, '');
        const lineBreaks = (txt.match(/\\n/g) || []).length;
        const paragraphs = Array.from(clone.querySelectorAll('p'));
        const blockCount = paragraphs.length > 0
          ? paragraphs.filter((p) => ((p.innerText || p.textContent || '') + '').replace(/\\u200b/g, '').trim().length > 0).length
          : (txt.length > 0 ? 1 : 0);
        return JSON.stringify({
          textLen: txt.length,
          lineBreaks,
          blockCount,
          normalized,
          preview: txt.slice(0, 120),
        });
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  return JSON.parse(result.result.value) as { textLen: number; lineBreaks: number; blockCount: number; normalized: string; preview: string };
}

function isContentWritten(state: { textLen: number; normalized: string }, content: string): boolean {
  const expected = content.replace(/\s+/g, '');
  if (!expected) return true;
  const anchor = expected.slice(0, Math.min(12, expected.length));
  return state.textLen > 0 && state.normalized.includes(anchor);
}

function escapeHtml(input: string): string {
  return input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function buildEditorHtml(content: string): string {
  const lines = content.replace(/\r\n/g, '\n').split('\n');
  const html: string[] = [];
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      html.push('<p><br></p>');
      continue;
    }
    if (line.startsWith('#')) {
      const title = line.replace(/^#+\s*/, '');
      html.push(`<p><strong>${escapeHtml(title)}</strong></p>`);
      continue;
    }
    if (line.startsWith('- ')) {
      html.push(`<p>• ${escapeHtml(line.slice(2))}</p>`);
      continue;
    }
    html.push(`<p>${escapeHtml(line)}</p>`);
  }
  return html.join('');
}

async function insertContentAsHtml(
  cdp: CdpConnection,
  sessionId: string,
  editorSelector: string,
  content: string,
): Promise<boolean> {
  const html = buildEditorHtml(content);
  const result = await cdp.send<{ result: { value: boolean } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const editor = document.querySelector(${JSON.stringify(editorSelector)});
        if (!editor) return false;
        editor.focus();
        const sel = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(editor);
        range.collapse(false);
        if (sel) {
          sel.removeAllRanges();
          sel.addRange(range);
        }
        try {
          return document.execCommand('insertHTML', false, ${JSON.stringify(html)});
        } catch (err) {
          return false;
        }
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  return !!result.result.value;
}

async function insertContentLineByLine(
  cdp: CdpConnection,
  sessionId: string,
  content: string,
): Promise<void> {
  const lines = content.replace(/\r\n/g, '\n').split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!;
    if (line) {
      await cdp.send('Input.insertText', { text: line }, { sessionId });
    }
    if (i < lines.length - 1) {
      await cdp.send('Input.dispatchKeyEvent', {
        type: 'keyDown',
        key: 'Enter',
        code: 'Enter',
        windowsVirtualKeyCode: 13,
      }, { sessionId });
      await cdp.send('Input.dispatchKeyEvent', {
        type: 'keyUp',
        key: 'Enter',
        code: 'Enter',
        windowsVirtualKeyCode: 13,
      }, { sessionId });
    }
    await sleep(20);
  }
}

async function dumpComposeDiagnostics(cdp: CdpConnection, sessionId: string): Promise<void> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const pick = (selector) => {
          const el = document.querySelector(selector);
          if (!el) return null;
          const st = window.getComputedStyle(el);
          const r = el.getBoundingClientRect();
          const text = ((el.innerText || el.textContent || '') + '').replace(/\\s+/g, ' ').trim().slice(0, 160);
          return {
            selector,
            visible: st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0' && r.width > 2 && r.height > 2,
            rect: { w: Math.round(r.width), h: Math.round(r.height) },
            text,
            html: (el.outerHTML || '').slice(0, 600),
          };
        };
        return JSON.stringify({
          topError: pick('#js_content_top .js_content_top_error'),
          topUploader: pick('#js_content_top .image-selector'),
          guideEditor: pick('#guide_words_main .ProseMirror[contenteditable="true"]'),
          bodyEditor: pick('#js_ueditor .ProseMirror[contenteditable="true"]'),
        });
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  console.warn(`[wechat-browser] Compose diagnostics: ${result.result.value}`);
}

async function findBestFileInputNodeIds(cdp: CdpConnection, sessionId: string): Promise<number[]> {
  const marker = `codex-upload-target-${Date.now()}`;
  const markResult = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const marker = ${JSON.stringify(marker)};
        const nodes = Array.from(document.querySelectorAll('input[type=file]'));
        for (const n of nodes) n.removeAttribute('data-codex-upload-target');
        const isVisible = (el) => {
          if (!el) return false;
          const r = el.getBoundingClientRect();
          if (!r) return false;
          const st = window.getComputedStyle(el);
          if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
          return r.width > 1 && r.height > 1;
        };
        let best = null;
        let bestScore = -1;
        const snapshots = [];
        for (const input of nodes) {
          let score = 0;
          if (input.closest('#js_cover_description_area')) score += 140;
          if (input.closest('.select-cover,.first_appmsg_cover,.cover_drop_inner_wrp')) score += 100;
          if (input.closest('.weui-desktop-dialog,.weui-desktop-popover,[role="dialog"]')) score += 120;
          if ((input.accept || '').toLowerCase().includes('image')) score += 50;
          if (!input.disabled) score += 20;
          if (isVisible(input)) score += 40;
          if (input.multiple) score += 5;
          const rect = input.getBoundingClientRect();
          snapshots.push({
            score,
            accept: input.accept || '',
            id: input.id || '',
            name: input.name || '',
            className: input.className || '',
            inDialog: !!input.closest('.weui-desktop-dialog,.weui-desktop-popover,[role="dialog"]'),
            inCover: !!input.closest('#js_cover_description_area'),
            visible: isVisible(input),
            rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
          });
          if (score > bestScore) {
            best = input;
            bestScore = score;
          }
        }
        if (!best) return JSON.stringify({ ok: false, count: nodes.length, snapshots });
        best.setAttribute('data-codex-upload-target', marker);
        const attrs = ['class', 'accept', 'name', 'id'];
        const info = {};
        for (const k of attrs) info[k] = best.getAttribute(k) || '';
        return JSON.stringify({
          ok: true,
          score: bestScore,
          multiple: !!best.multiple,
          info,
          count: nodes.length,
          inDialog: !!best.closest('.weui-desktop-dialog,.weui-desktop-popover,[role="dialog"]'),
          inCover: !!best.closest('#js_cover_description_area'),
          snapshots,
        });
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  if (DEBUG_UPLOAD) {
    try {
      console.log(`[wechat-browser] Upload input mark: ${markResult.result.value}`);
    } catch {}
  }

  const { root } = await cdp.send<{ root: { nodeId: number } }>('DOM.getDocument', {}, { sessionId });
  const marked = await cdp.send<{ nodeIds: number[] }>('DOM.querySelectorAll', {
    nodeId: root.nodeId,
    selector: `[data-codex-upload-target="${marker}"]`,
  }, { sessionId });
  if (marked.nodeIds.length > 0) {
    const markedHtml = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
      expression: `
        (function() {
          const el = document.querySelector('[data-codex-upload-target="${marker}"]');
          return el ? (el.outerHTML || '').slice(0, 300) : '';
        })()
      `,
      returnByValue: true,
    }, { sessionId });
    if (DEBUG_UPLOAD && markedHtml.result.value) {
      console.log(`[wechat-browser] Marked upload input html: ${markedHtml.result.value}`);
    }
    console.log(`[wechat-browser] Using marked upload input (count=${marked.nodeIds.length})`);
    return marked.nodeIds;
  }

  const selectors = [
    '#js_cover_description_area input[type=file]',
    '.select-cover input[type=file]',
    '.weui-desktop-dialog input[type=file]',
    '.weui-desktop-uploader input[type=file]',
    'input[type=file][accept*="image"]',
    'input[type=file]',
  ];
  for (const selector of selectors) {
    const { nodeIds } = await cdp.send<{ nodeIds: number[] }>('DOM.querySelectorAll', {
      nodeId: root.nodeId,
      selector,
    }, { sessionId });
    if (nodeIds.length > 0) {
      console.log(`[wechat-browser] Using upload input selector fallback: ${selector} (count=${nodeIds.length})`);
      return nodeIds;
    }
  }
  throw new Error('File input not found');
}

async function findAllFileInputNodeIds(cdp: CdpConnection, sessionId: string): Promise<number[]> {
  const { root } = await cdp.send<{ root: { nodeId: number } }>('DOM.getDocument', {}, { sessionId });
  const { nodeIds } = await cdp.send<{ nodeIds: number[] }>('DOM.querySelectorAll', {
    nodeId: root.nodeId,
    selector: 'input[type=file]',
  }, { sessionId });
  if (!nodeIds.length) throw new Error('No file input found for fallback upload');
  console.log(`[wechat-browser] Fallback: use all file inputs (count=${nodeIds.length})`);
  return nodeIds;
}

async function setCheckboxInRow(
  cdp: CdpConnection,
  sessionId: string,
  rowSelector: string,
  checkboxSelector: string,
  desiredOn = true,
): Promise<boolean> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const row = document.querySelector(${JSON.stringify(rowSelector)});
        if (!row) return JSON.stringify({ ok: false, reason: 'row-not-found' });
        const st = window.getComputedStyle(row);
        if (st.display === 'none' || st.visibility === 'hidden') return JSON.stringify({ ok: false, reason: 'row-hidden' });
        const checkbox = row.querySelector(${JSON.stringify(checkboxSelector)});
        if (!checkbox) return JSON.stringify({ ok: false, reason: 'checkbox-not-found' });
        const desiredOn = ${desiredOn ? 'true' : 'false'};
        const current = !!checkbox.checked;
        if (current !== desiredOn) {
          const clickTarget = row.querySelector('label,.setting-group__switch,.allow_click_opr,input[type="checkbox"]') || checkbox;
          clickTarget.click();
        }
        return JSON.stringify({ ok: true, changed: current !== desiredOn, after: desiredOn });
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  const parsed = JSON.parse(result.result.value) as { ok: boolean; reason?: string; changed?: boolean };
  if (parsed.ok) {
    console.log(`[wechat-browser] Checkbox set on row ${rowSelector} (changed=${parsed.changed})`);
    return true;
  }
  console.log(`[wechat-browser] Checkbox row set failed: ${rowSelector}, reason=${parsed.reason}`);
  return false;
}

async function openRowById(
  cdp: CdpConnection,
  sessionId: string,
  rowSelector: string,
): Promise<boolean> {
  const result = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
    expression: `
      (function() {
        const row = document.querySelector(${JSON.stringify(rowSelector)});
        if (!row) return JSON.stringify({ ok: false, reason: 'row-not-found' });
        const st = window.getComputedStyle(row);
        if (st.display === 'none' || st.visibility === 'hidden') return JSON.stringify({ ok: false, reason: 'row-hidden' });
        const candidates = [
          '.allow_click_opr',
          '.setting-group__switch',
          '.js_claim_source_desc',
          '.js_article_tags_label',
          '.read-more__icon__more',
          'label',
        ];
        for (const selector of candidates) {
          const el = row.querySelector(selector);
          if (!el) continue;
          el.click();
          return JSON.stringify({ ok: true, via: selector });
        }
        row.click();
        return JSON.stringify({ ok: true, via: 'row' });
      })()
    `,
    returnByValue: true,
  }, { sessionId });
  const parsed = JSON.parse(result.result.value) as { ok: boolean; reason?: string; via?: string };
  if (parsed.ok) {
    console.log(`[wechat-browser] Opened row ${rowSelector} via ${parsed.via}`);
    return true;
  }
  console.log(`[wechat-browser] Open row failed: ${rowSelector}, reason=${parsed.reason}`);
  return false;
}

async function dispatchFileInputChange(cdp: CdpConnection, sessionId: string): Promise<void> {
  await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const inputs = Array.from(document.querySelectorAll('input[type=file]'));
        let fired = 0;
        for (const input of inputs) {
          const count = input.files ? input.files.length : 0;
          if (count <= 0) continue;
          try { input.dispatchEvent(new Event('input', { bubbles: true })); } catch {}
          try { input.dispatchEvent(new Event('change', { bubbles: true })); } catch {}
          fired++;
        }
        return fired;
      })()
    `,
    returnByValue: true,
  }, { sessionId });
}

async function applyPreSubmitSettings(cdp: CdpConnection, sessionId: string): Promise<void> {
  console.log('[wechat-browser] Applying pre-submit settings...');
  const scrollToBottom = async () => {
    await cdp.send('Runtime.evaluate', {
      expression: 'window.scrollTo(0, document.body.scrollHeight); true;',
      returnByValue: true,
    }, { sessionId });
  };

  await scrollToBottom();
  await sleep(400);
  // 某些账号需要先展开底部设置区
  await clickVisibleByText(cdp, sessionId, ['更多设置', '声明与权益', '声明与话题', '内容声明', '创作声明'], { maxTextLen: 24 });
  await sleep(500);
  await debugDumpSettingTexts(cdp, sessionId, 'before');

  // 1) 开启原创（可用时）
  await scrollToBottom();
  const originalOpenedById = await setCheckboxInRow(cdp, sessionId, '#js_original', '.js_ori_setting_checkbox', true);
  if (!originalOpenedById) {
    const originalOpenedByText = await setSwitchByRowLabel(cdp, sessionId, ['声明原创', '原创声明', '原创'], true);
    if (!originalOpenedByText) {
      await clickVisibleByText(cdp, sessionId, ['声明原创', '原创声明', '原创'], { maxTextLen: 24 });
    }
  }
  await sleep(500);
  await handleOriginalDialogIfPresent(cdp, sessionId, DEFAULT_ORIGINAL_AUTHOR);
  await sleep(350);

  // 2) 创作来源 -> 个人观点 + 情况参考
  await scrollToBottom();
  let sourceOpened = await openRowById(cdp, sessionId, '#js_claim_source_area');
  if (!sourceOpened) {
    sourceOpened = await openSettingRow(cdp, sessionId, ['创作来源', '创作类型', '内容来源']);
  }
  await sleep(500);
  if (sourceOpened) {
    await debugDumpSettingTexts(cdp, sessionId, 'source-opened');
    await clickVisibleByText(cdp, sessionId, ['个人观点', '观点'], { maxTextLen: 120 });
    await sleep(300);
    await clickVisibleByText(cdp, sessionId, ['情况参考', '参考情况', '资料参考', '参考'], { maxTextLen: 120 });
    await sleep(300);
    await clickPrimaryButtonInVisibleDialog(cdp, sessionId, ['确定', '确认']);
    await handleOriginalDialogIfPresent(cdp, sessionId, DEFAULT_ORIGINAL_AUTHOR);
    await sleep(500);
  }

  // 3) 开启赞赏
  await scrollToBottom();
  const rewardOpenedById = await setCheckboxInRow(cdp, sessionId, '#js_reward_setting_area', '.js_reward_setting_checkbox', true);
  if (!rewardOpenedById) {
    const rewardOpenedById2 = await setCheckboxInRow(cdp, sessionId, '#reward_setting_area', '.js_reward_setting', true);
    if (!rewardOpenedById2) {
      const rewardOpenedByText = await setSwitchByRowLabel(cdp, sessionId, ['赞赏'], true);
      if (!rewardOpenedByText) {
        await clickVisibleByText(cdp, sessionId, ['赞赏'], { maxTextLen: 24 });
      }
    }
  }
  await sleep(500);

  // 4) 开启程序化广告
  await scrollToBottom();
  const adOpenedById = await setCheckboxInRow(cdp, sessionId, '#js_insert_ad_area', '.js_auto_insert_ad', true);
  if (!adOpenedById) {
    const adOpenedByText = await setSwitchByRowLabel(cdp, sessionId, ['程序化广告', '广告'], true);
    if (!adOpenedByText) {
      await clickVisibleByText(cdp, sessionId, ['程序化广告', '广告'], { maxTextLen: 24 });
    }
  }
  await sleep(500);

  // 5) 加入合集 -> AI
  await scrollToBottom();
  let collectionOpened = await openRowById(cdp, sessionId, '#js_article_tags_area');
  if (!collectionOpened) {
    await clickBySelectors(cdp, sessionId, ['#js_article_tags_area .js_article_tags_label', '#js_article_tags_area .allow_click_opr'], 'collection entry');
    collectionOpened = await openSettingRow(cdp, sessionId, ['添加合集', '加入合集', '合集']);
  }
  await sleep(500);
  if (collectionOpened) {
    await debugDumpSettingTexts(cdp, sessionId, 'collection-opened');
    const picked = await clickVisibleByText(cdp, sessionId, ['AI合集', 'AIGC', 'AI'], { prefix: true, maxTextLen: 40 });
    if (!picked) {
      await clickVisibleByText(cdp, sessionId, ['人工智能', '科技'], { prefix: true, maxTextLen: 40 });
    }
    await sleep(300);
    await clickPrimaryButtonInVisibleDialog(cdp, sessionId, ['确定', '确认', '完成']);
    await handleOriginalDialogIfPresent(cdp, sessionId, DEFAULT_ORIGINAL_AUTHOR);
  }
  await sleep(500);
}

async function getFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (!address || typeof address === 'string') {
        server.close(() => reject(new Error('Unable to allocate a free TCP port.')));
        return;
      }
      const port = address.port;
      server.close((err) => {
        if (err) reject(err);
        else resolve(port);
      });
    });
  });
}

function findChromeExecutable(): string | undefined {
  const override = process.env.WECHAT_BROWSER_CHROME_PATH?.trim();
  if (override && fs.existsSync(override)) return override;

  const candidates: string[] = [];
  switch (process.platform) {
    case 'darwin':
      candidates.push(
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
        '/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta',
        '/Applications/Chromium.app/Contents/MacOS/Chromium',
        '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
      );
      break;
    case 'win32':
      candidates.push(
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
        'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
      );
      break;
    default:
      candidates.push(
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/snap/bin/chromium',
        '/usr/bin/microsoft-edge',
      );
      break;
  }

  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return undefined;
}

function getDefaultProfileDir(): string {
  const base = process.env.XDG_DATA_HOME || path.join(os.homedir(), '.local', 'share');
  return path.join(base, 'wechat-browser-profile');
}

async function fetchJson<T = unknown>(url: string): Promise<T> {
  const res = await fetch(url, { redirect: 'follow' });
  if (!res.ok) throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

async function waitForChromeDebugPort(port: number, timeoutMs: number): Promise<string> {
  const start = Date.now();
  let lastError: unknown = null;

  while (Date.now() - start < timeoutMs) {
    try {
      const version = await fetchJson<{ webSocketDebuggerUrl?: string }>(`http://127.0.0.1:${port}/json/version`);
      if (version.webSocketDebuggerUrl) return version.webSocketDebuggerUrl;
      lastError = new Error('Missing webSocketDebuggerUrl');
    } catch (error) {
      lastError = error;
    }
    await sleep(200);
  }

  throw new Error(`Chrome debug port not ready: ${lastError instanceof Error ? lastError.message : String(lastError)}`);
}

class CdpConnection {
  private ws: WebSocket;
  private nextId = 0;
  private pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> | null }>();
  private eventHandlers = new Map<string, Set<(params: unknown) => void>>();

  private constructor(ws: WebSocket) {
    this.ws = ws;
    this.ws.addEventListener('message', (event) => {
      try {
        const data = typeof event.data === 'string' ? event.data : new TextDecoder().decode(event.data as ArrayBuffer);
        const msg = JSON.parse(data) as { id?: number; method?: string; params?: unknown; result?: unknown; error?: { message?: string } };

        if (msg.method) {
          const handlers = this.eventHandlers.get(msg.method);
          if (handlers) handlers.forEach((h) => h(msg.params));
        }

        if (msg.id) {
          const pending = this.pending.get(msg.id);
          if (pending) {
            this.pending.delete(msg.id);
            if (pending.timer) clearTimeout(pending.timer);
            if (msg.error?.message) pending.reject(new Error(msg.error.message));
            else pending.resolve(msg.result);
          }
        }
      } catch {}
    });

    this.ws.addEventListener('close', () => {
      for (const [id, pending] of this.pending.entries()) {
        this.pending.delete(id);
        if (pending.timer) clearTimeout(pending.timer);
        pending.reject(new Error('CDP connection closed.'));
      }
    });
  }

  static async connect(url: string, timeoutMs: number): Promise<CdpConnection> {
    const ws = new WebSocket(url);
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('CDP connection timeout.')), timeoutMs);
      ws.addEventListener('open', () => { clearTimeout(timer); resolve(); });
      ws.addEventListener('error', () => { clearTimeout(timer); reject(new Error('CDP connection failed.')); });
    });
    return new CdpConnection(ws);
  }

  on(method: string, handler: (params: unknown) => void): void {
    if (!this.eventHandlers.has(method)) this.eventHandlers.set(method, new Set());
    this.eventHandlers.get(method)!.add(handler);
  }

  async send<T = unknown>(method: string, params?: Record<string, unknown>, options?: { sessionId?: string; timeoutMs?: number }): Promise<T> {
    const id = ++this.nextId;
    const message: Record<string, unknown> = { id, method };
    if (params) message.params = params;
    if (options?.sessionId) message.sessionId = options.sessionId;

    const timeoutMs = options?.timeoutMs ?? 15_000;

    const result = await new Promise<unknown>((resolve, reject) => {
      const timer = timeoutMs > 0 ? setTimeout(() => { this.pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, timeoutMs) : null;
      this.pending.set(id, { resolve, reject, timer });
      this.ws.send(JSON.stringify(message));
    });

    return result as T;
  }

  close(): void {
    try { this.ws.close(); } catch {}
  }
}

interface WeChatBrowserOptions {
  title?: string;
  content?: string;
  images?: string[];
  imagesDir?: string;
  markdownFile?: string;
  submit?: boolean;
  preSubmitSettings?: boolean;
  timeoutMs?: number;
  profileDir?: string;
  chromePath?: string;
}

export async function postToWeChat(options: WeChatBrowserOptions): Promise<void> {
  const { submit = false, preSubmitSettings = true, timeoutMs = 120_000, profileDir = getDefaultProfileDir() } = options;

  let title = options.title || '';
  let content = options.content || '';
  let images = options.images || [];

  if (options.markdownFile) {
    const absPath = path.isAbsolute(options.markdownFile) ? options.markdownFile : path.resolve(process.cwd(), options.markdownFile);
    if (!fs.existsSync(absPath)) throw new Error(`Markdown file not found: ${absPath}`);
    const meta = parseMarkdownFile(absPath);
    if (!title) title = meta.title;
    if (!content) content = meta.content;
    console.log(`[wechat-browser] Parsed markdown: title="${meta.title}", content=${meta.content.length} chars`);
  }

  if (options.imagesDir) {
    const absDir = path.isAbsolute(options.imagesDir) ? options.imagesDir : path.resolve(process.cwd(), options.imagesDir);
    if (!fs.existsSync(absDir)) throw new Error(`Images directory not found: ${absDir}`);
    images = await loadImagesFromDir(absDir);
    console.log(`[wechat-browser] Found ${images.length} images in ${absDir}`);
  }

  if (title.length > 20) {
    const original = title;
    title = compressTitle(title, 20);
    console.log(`[wechat-browser] Title compressed: "${original}" → "${title}"`);
  }

  if (content.length > 1000) {
    const original = content.length;
    content = compressContent(content, 1000);
    console.log(`[wechat-browser] Content compressed: ${original} → ${content.length} chars`);
  }

  if (!title) throw new Error('Title is required (use --title or --markdown)');
  if (!content) throw new Error('Content is required (use --content or --markdown)');
  if (images.length === 0) throw new Error('At least one image is required (use --image or --images)');

  for (const img of images) {
    if (!fs.existsSync(img)) throw new Error(`Image not found: ${img}`);
  }

  const chromePath = options.chromePath ?? findChromeExecutable();
  if (!chromePath) throw new Error('Chrome not found. Set WECHAT_BROWSER_CHROME_PATH env var.');

  await mkdir(profileDir, { recursive: true });

  const port = await getFreePort();
  console.log(`[wechat-browser] Launching Chrome (profile: ${profileDir})`);

  const chrome = spawn(chromePath, [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-blink-features=AutomationControlled',
    '--start-maximized',
    WECHAT_URL,
  ], { stdio: 'ignore' });

  let cdp: CdpConnection | null = null;

  try {
    const wsUrl = await waitForChromeDebugPort(port, 30_000);
    cdp = await CdpConnection.connect(wsUrl, 30_000);

    const targets = await cdp.send<{ targetInfos: Array<{ targetId: string; url: string; type: string }> }>('Target.getTargets');
    let pageTarget = targets.targetInfos.find((t) => t.type === 'page' && t.url.includes('mp.weixin.qq.com'));

    if (!pageTarget) {
      const { targetId } = await cdp.send<{ targetId: string }>('Target.createTarget', { url: WECHAT_URL });
      pageTarget = { targetId, url: WECHAT_URL, type: 'page' };
    }

    let { sessionId } = await cdp.send<{ sessionId: string }>('Target.attachToTarget', { targetId: pageTarget.targetId, flatten: true });

    await cdp.send('Page.enable', {}, { sessionId });
    await cdp.send('Runtime.enable', {}, { sessionId });
    await cdp.send('DOM.enable', {}, { sessionId });

    console.log('[wechat-browser] Waiting for page load...');
    await sleep(3000);

    const checkLoginStatus = async (): Promise<boolean> => {
      const result = await cdp!.send<{ result: { value: string } }>('Runtime.evaluate', {
        expression: `window.location.href`,
        returnByValue: true,
      }, { sessionId });
      return result.result.value.includes('/cgi-bin/home');
    };

    const waitForLogin = async (): Promise<boolean> => {
      const start = Date.now();
      while (Date.now() - start < timeoutMs) {
        if (await checkLoginStatus()) return true;
        await sleep(2000);
      }
      return false;
    };

    let isLoggedIn = await checkLoginStatus();
    if (!isLoggedIn) {
      console.log('[wechat-browser] Not logged in. Please scan QR code to log in...');
      isLoggedIn = await waitForLogin();
      if (!isLoggedIn) throw new Error('Timed out waiting for login. Please log in first.');
    }
    console.log('[wechat-browser] Logged in.');

    await sleep(2000);

    const imageTextMenuLabels = ['图文', '贴图'];
    console.log(`[wechat-browser] Looking for image-text menu: ${imageTextMenuLabels.join('/')}`);
    const menuResult = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
      expression: `
        const menuItems = document.querySelectorAll('.new-creation__menu .new-creation__menu-item');
        const count = menuItems.length;
        const texts = Array.from(menuItems).map(m => m.querySelector('.new-creation__menu-title')?.textContent?.trim() || m.textContent?.trim() || '');
        JSON.stringify({ count, texts });
      `,
      returnByValue: true,
    }, { sessionId });
    console.log(`[wechat-browser] Menu items: ${menuResult.result.value}`);

    const getTargets = async () => {
      return await cdp!.send<{ targetInfos: Array<{ targetId: string; url: string; type: string }> }>('Target.getTargets');
    };

    const initialTargets = await getTargets();
    const initialIds = new Set(initialTargets.targetInfos.map(t => t.targetId));
    console.log(`[wechat-browser] Initial targets count: ${initialTargets.targetInfos.length}`);

    console.log(`[wechat-browser] Finding image-text menu position: ${imageTextMenuLabels.join('/')}`);
    const menuPos = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
      expression: `
        (function() {
          const isVisible = (el) => {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            if (!rect || rect.width < 2 || rect.height < 2) return false;
            const st = window.getComputedStyle(el);
            return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
          };
          const menuItems = document.querySelectorAll('.new-creation__menu .new-creation__menu-item');
          console.log('Found menu items:', menuItems.length);
          for (const item of menuItems) {
            const title = item.querySelector('.new-creation__menu-title');
            const text = title?.textContent?.trim() || '';
            console.log('Menu item text:', text);
            if (${JSON.stringify(['图文', '贴图'])}.includes(text) && isVisible(item)) {
              item.scrollIntoView({ block: 'center' });
              const rect = item.getBoundingClientRect();
              console.log('Found image-text menu item, rect:', JSON.stringify(rect));
              const anchor = item.querySelector('a');
              const href = anchor?.getAttribute('href') || item.getAttribute('href') || item.getAttribute('data-href') || '';
              return JSON.stringify({
                label: text,
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                width: rect.width,
                height: rect.height,
                href,
              });
            }
          }
          return 'null';
        })()
      `,
      returnByValue: true,
    }, { sessionId });
    console.log(`[wechat-browser] Menu position: ${menuPos.result.value}`);

    const pos = menuPos.result.value !== 'null' ? JSON.parse(menuPos.result.value) : null;
    if (!pos) throw new Error('Image-text menu not found or not visible (expected 图文/贴图)');
    const selectedMenuLabel = String(pos.label || '');
    const menuHref = String(pos.href || '').trim();
    if (menuHref) {
      console.log(`[wechat-browser] Menu href detected: ${menuHref}`);
    }

    if (menuHref && /^https?:\/\//i.test(menuHref)) {
      console.log('[wechat-browser] Navigating directly via menu href...');
      await cdp.send('Page.navigate', { url: menuHref }, { sessionId });
      await sleep(1200);
    } else {

      const menuClickResult = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
        expression: `
          (function() {
            const labels = ${JSON.stringify(imageTextMenuLabels)};
            const isVisible = (el) => {
              if (!el) return false;
              const rect = el.getBoundingClientRect();
              if (!rect || rect.width < 2 || rect.height < 2) return false;
              const st = window.getComputedStyle(el);
              return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
            };
            const items = Array.from(document.querySelectorAll('.new-creation__menu .new-creation__menu-item'));
            for (const item of items) {
              if (!isVisible(item)) continue;
              const title = (item.querySelector('.new-creation__menu-title')?.textContent || item.textContent || '').trim();
              if (!labels.includes(title)) continue;
              const target = item.querySelector('a,button,[role="button"]') || item;
              ['mouseover', 'mouseenter', 'mousedown', 'mouseup', 'click'].forEach((type) => {
                target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, composed: true, button: 0 }));
              });
              try { target.click(); } catch {}
              return JSON.stringify({ ok: true, title });
            }
            return JSON.stringify({ ok: false });
          })()
        `,
        returnByValue: true,
      }, { sessionId });
      const menuClicked = JSON.parse(menuClickResult.result.value) as { ok: boolean; title?: string };
      if (!menuClicked.ok) {
        console.log('[wechat-browser] Fallback to coordinate click for image-text menu...');
        await cdp.send('Input.dispatchMouseEvent', {
          type: 'mousePressed',
          x: pos.x,
          y: pos.y,
          button: 'left',
          clickCount: 1,
        }, { sessionId });
        await sleep(100);
        await cdp.send('Input.dispatchMouseEvent', {
          type: 'mouseReleased',
          x: pos.x,
          y: pos.y,
          button: 'left',
          clickCount: 1,
        }, { sessionId });
      } else {
        console.log(`[wechat-browser] Clicked creation menu: ${menuClicked.title}`);
      }
    }

    console.log('[wechat-browser] Waiting for editor...');
    await sleep(3000);

    const waitForEditor = async (): Promise<{ targetId: string; isNewTab: boolean } | null> => {
      const start = Date.now();
      let attemptedDirectNav = false;

      while (Date.now() - start < 30_000) {
        const targets = await getTargets();
        const pageTargets = targets.targetInfos.filter(t => t.type === 'page');

        for (const t of pageTargets) {
          console.log(`[wechat-browser] Target: ${t.url}`);
        }

        const newTab = pageTargets.find(t => !initialIds.has(t.targetId) && t.url.includes('mp.weixin.qq.com'));
        if (newTab) {
          console.log(`[wechat-browser] Found new tab: ${newTab.url}`);
          return { targetId: newTab.targetId, isNewTab: true };
        }

        const editorTab = pageTargets.find(t => t.url.includes('appmsg'));
        if (editorTab) {
          console.log(`[wechat-browser] Found editor tab: ${editorTab.url}`);
          return { targetId: editorTab.targetId, isNewTab: !initialIds.has(editorTab.targetId) };
        }

        const currentUrl = await cdp!.send<{ result: { value: string } }>('Runtime.evaluate', {
          expression: `window.location.href`,
          returnByValue: true,
        }, { sessionId });
        console.log(`[wechat-browser] Current page URL: ${currentUrl.result.value}`);

        const inlineEditor = await cdp!.send<{ result: { value: boolean } }>('Runtime.evaluate', {
          expression: `
            (function() {
              const candidates = [
                '#js_appmsg_editor',
                '#appmsg_content',
                '#js_content_top .image-selector',
                '#title',
              ];
              return candidates.some((s) => !!document.querySelector(s));
            })()
          `,
          returnByValue: true,
        }, { sessionId });
        if (inlineEditor.result.value) {
          console.log('[wechat-browser] Inline editor detected in current page');
          return { targetId: pageTarget!.targetId, isNewTab: false };
        }

        if (currentUrl.result.value.includes('appmsg')) {
          console.log(`[wechat-browser] Current page navigated to editor`);
          return { targetId: pageTarget!.targetId, isNewTab: false };
        }

        if (!attemptedDirectNav && Date.now() - start > 9_000) {
          attemptedDirectNav = true;
          const tokenMatch = currentUrl.result.value.match(/[?&]token=(\d+)/);
          const token = tokenMatch?.[1] || '';
          if (token) {
            const candidateUrls = [
              `https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=8&lang=zh_CN&token=${token}`,
              `https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=10&lang=zh_CN&token=${token}`,
              `https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&isNew=1&type=8&lang=zh_CN&token=${token}`,
              `https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&isNew=1&type=10&lang=zh_CN&token=${token}`,
            ];
            for (const url of candidateUrls) {
              try {
                console.log(`[wechat-browser] Direct editor navigate attempt: ${url}`);
                await cdp!.send('Page.navigate', { url }, { sessionId });
                await sleep(1400);
                const check = await cdp!.send<{ result: { value: boolean } }>('Runtime.evaluate', {
                  expression: `
                    (function() {
                      return !!(document.querySelector('#js_appmsg_editor') || document.querySelector('#appmsg_content') || document.querySelector('#title'));
                    })()
                  `,
                  returnByValue: true,
                }, { sessionId });
                if (check.result.value) {
                  console.log('[wechat-browser] Direct editor navigation succeeded');
                  return { targetId: pageTarget!.targetId, isNewTab: false };
                }
              } catch (err) {
                console.warn(`[wechat-browser] Direct navigate failed: ${err instanceof Error ? err.message : String(err)}`);
              }
            }
          }
        }

        await sleep(1000);
      }
      return null;
    };

    const editorInfo = await waitForEditor();
    if (!editorInfo) {
      const finalTargets = await getTargets();
      console.log(`[wechat-browser] Final targets: ${finalTargets.targetInfos.filter(t => t.type === 'page').map(t => t.url).join(', ')}`);
      throw new Error('Editor not found.');
    }

    if (editorInfo.isNewTab) {
      console.log('[wechat-browser] Switching to editor tab...');
      const editorSession = await cdp.send<{ sessionId: string }>('Target.attachToTarget', { targetId: editorInfo.targetId, flatten: true });
      sessionId = editorSession.sessionId;

      await cdp.send('Page.enable', {}, { sessionId });
      await cdp.send('Runtime.enable', {}, { sessionId });
      await cdp.send('DOM.enable', {}, { sessionId });
    } else {
      console.log('[wechat-browser] Editor opened in current page');
    }

    await cdp.send('Page.enable', {}, { sessionId });
    await cdp.send('Runtime.enable', {}, { sessionId });
    await cdp.send('DOM.enable', {}, { sessionId });

    await sleep(2000);

    console.log('[wechat-browser] Uploading all images at once...');
    const absolutePaths = images.map(p => path.isAbsolute(p) ? p : path.resolve(process.cwd(), p));
    console.log(`[wechat-browser] Images: ${absolutePaths.join(', ')}`);
    await debugDumpUploadArea(cdp, sessionId, 'before-click');
    const flowDetect = await cdp.send<{ result: { value: string } }>('Runtime.evaluate', {
      expression: `
        (function() {
          const topImage = !!document.querySelector('#js_content_top .image-selector, #js_content_top input[type=file]');
          const legacyCover = !!document.querySelector('#js_cover_description_area');
          const editorInsert = !!document.querySelector('#js_editor_insertimage, .jsInsertIcon, #js_editor');
          return JSON.stringify({ topImage, legacyCover, editorInsert });
        })()
      `,
      returnByValue: true,
    }, { sessionId });
    const flow = JSON.parse(flowDetect.result.value) as { topImage: boolean; legacyCover: boolean; editorInsert: boolean };
    const isStickerFlow = flow.topImage;
    console.log(`[wechat-browser] Flow detection: menu=${selectedMenuLabel}, topImage=${flow.topImage}, legacyCover=${flow.legacyCover}, editorInsert=${flow.editorInsert}`);

    if (isStickerFlow) {
      // 贴图页面：图片必须通过 #js_content_top 的 image-selector 上传。
      await clickBySelectors(cdp, sessionId, [
        '#js_content_top .image-selector .js_upload_btn_container',
        '#js_content_top .image-selector .pop-opr__button',
        '#js_content_top .js_upload_btn_container',
      ], 'top image upload entry');
      await clickVisibleByText(cdp, sessionId, ['本地上传'], { exact: true, maxTextLen: 12 });
      await clickVisibleByText(cdp, sessionId, ['本地上传'], { maxTextLen: 32 });
      await sleep(300);
    } else {
      // 图文页面：先激活编辑器，再点击图片入口并选择本地上传。
      await clickBySelectors(cdp, sessionId, [
        '.js_pmEditorArea',
        '.ProseMirror',
        '[contenteditable="true"]',
        '#js_editor',
      ], 'editor area');
      await sleep(250);
      await clickBySelectors(cdp, sessionId, [
        '#js_editor_insertimage',
        '.jsInsertIcon',
        '.icon20_common.add_image',
        '.js_editor_insertphoto',
        '.js_upload_btn_container',
      ], 'insert image entry');
      await sleep(300);

      await clickBySelectors(cdp, sessionId, [
        '#js_cover_description_area .js_cover_btn_area',
        '#js_cover_description_area .select-cover__btn',
        '#js_cover_description_area .js_chooseCover',
        '#js_cover_description_area .js_modifyCover',
        '.js_cover_btn_area',
        '.select-cover__btn',
      ], 'cover entry');
      await sleep(350);
      await clickBySelectors(cdp, sessionId, [
        '#js_cover_description_area .js_imagedialog',
        '.js_cover_opr .js_imagedialog',
        '.js_imagedialog',
      ], 'cover image dialog');
      await sleep(350);
      await clickVisibleByText(cdp, sessionId, ['本地上传'], { exact: true, maxTextLen: 12 });
      await clickVisibleByText(cdp, sessionId, ['本地上传'], { maxTextLen: 32 });
      await sleep(350);
    }
    await debugDumpUploadArea(cdp, sessionId, 'after-click');

    let uploadInputNodeIds = isStickerFlow
      ? await findTopImageFileInputNodeIds(cdp, sessionId)
      : await findBestFileInputNodeIds(cdp, sessionId);
    for (const nodeId of uploadInputNodeIds) {
      await cdp.send('DOM.setFileInputFiles', {
        nodeId,
        files: isStickerFlow ? [absolutePaths[0]!] : absolutePaths,
      }, { sessionId });
    }
    await dispatchFileInputChange(cdp, sessionId);

    console.log('[wechat-browser] Waiting for image upload to complete...');
    if (isStickerFlow) {
      await sleep(1200);
    } else {
      await waitForImagesUploaded(cdp, sessionId, absolutePaths.length);
    }
    let uploadIssue = await detectImageUploadIssue(cdp, sessionId);
    let coverReady = await verifyCoverReady(cdp, sessionId);
    let topImageReady = isStickerFlow ? await waitForTopImageReady(cdp, sessionId, 18_000) : false;
    if (uploadIssue) {
      console.warn(`[wechat-browser] Upload warning detected: ${uploadIssue}. Retrying upload once...`);
      if (isStickerFlow) {
        await clickBySelectors(cdp, sessionId, [
          '#js_content_top .image-selector .js_upload_btn_container',
          '#js_content_top .image-selector .pop-opr__button',
          '#js_content_top .js_upload_btn_container',
        ], 'top image upload entry retry');
        await clickVisibleByText(cdp, sessionId, ['本地上传'], { exact: true, maxTextLen: 12 });
        await clickVisibleByText(cdp, sessionId, ['本地上传'], { maxTextLen: 32 });
        await sleep(300);
        uploadInputNodeIds = await findTopImageFileInputNodeIds(cdp, sessionId);
      } else {
        await clickBySelectors(cdp, sessionId, [
          '#js_editor_insertimage',
          '.jsInsertIcon',
          '.icon20_common.add_image',
          '.js_editor_insertphoto',
          '.js_upload_btn_container',
          '#js_cover_description_area .js_cover_btn_area',
          '#js_cover_description_area .select-cover__btn',
          '#js_cover_description_area .js_chooseCover',
          '#js_cover_description_area .js_modifyCover',
          '.js_cover_btn_area',
          '.select-cover__btn',
        ], 'cover entry retry');
        await sleep(300);
        await clickBySelectors(cdp, sessionId, [
          '#js_cover_description_area .js_imagedialog',
          '.js_cover_opr .js_imagedialog',
          '.js_imagedialog',
        ], 'cover image dialog retry');
        await sleep(300);
        await clickVisibleByText(cdp, sessionId, ['本地上传'], { exact: true, maxTextLen: 12 });
        await clickVisibleByText(cdp, sessionId, ['本地上传'], { maxTextLen: 32 });
        await sleep(300);
        uploadInputNodeIds = await findAllFileInputNodeIds(cdp, sessionId);
      }
      for (const nodeId of uploadInputNodeIds) {
        await cdp.send('DOM.setFileInputFiles', {
          nodeId,
          files: isStickerFlow ? [absolutePaths[0]!] : absolutePaths,
        }, { sessionId });
      }
      await dispatchFileInputChange(cdp, sessionId);
      if (isStickerFlow) {
        await sleep(1200);
      } else {
        await waitForImagesUploaded(cdp, sessionId, absolutePaths.length, 30_000);
      }
      uploadIssue = await detectImageUploadIssue(cdp, sessionId);
      coverReady = await verifyCoverReady(cdp, sessionId);
      topImageReady = isStickerFlow ? await waitForTopImageReady(cdp, sessionId, 12_000) : false;
    }
    if (!isStickerFlow && !coverReady && absolutePaths.length > 0) {
      console.warn('[wechat-browser] File-input upload not ready, trying clipboard paste fallback...');
      await cdp.send('Page.bringToFront', {}, { sessionId });
      await clickBySelectors(cdp, sessionId, [
        '#js_cover_description_area .js_cover_preview_new',
        '#js_cover_description_area .js_cover_preview',
        '#js_cover_description_area .js_cover_btn_area',
        '#js_cover_description_area .select-cover__btn',
        '#js_cover_description_area .js_chooseCover',
        '.js_cover_btn_area',
        '.select-cover__btn',
      ], 'cover area for clipboard fallback');
      await sleep(300);
      const pasted = pasteImageViaClipboard(absolutePaths[0]!);
      if (pasted) {
        await sleep(2500);
        uploadIssue = await detectImageUploadIssue(cdp, sessionId);
        coverReady = await verifyCoverReady(cdp, sessionId);
      }
    }
    const hasUploadSelection = await hasSelectedUploadFiles(cdp, sessionId);
    if (!coverReady) {
      // Give dynamic uploader UI a second chance to render previews.
      await sleep(1200);
    }
    const isLegacyCoverFlow = selectedMenuLabel === '图文' && await hasLegacyCoverArea(cdp, sessionId);
    const imageTextUploadReady = await verifyImageTextUploadReady(cdp, sessionId);
    const editorImageCount = await countEditorImages(cdp, sessionId);
    console.log(`[wechat-browser] Upload verification: menu=${selectedMenuLabel || 'unknown'}, flow=${isLegacyCoverFlow ? 'legacy-cover' : 'image-text'}, coverReady=${coverReady}, topImageReady=${topImageReady}, imageTextUploadReady=${imageTextUploadReady}, hasUploadSelection=${hasUploadSelection}, editorImageCount=${editorImageCount}, issue=${uploadIssue ?? 'none'}`);
    const uploadOk = isLegacyCoverFlow
      ? coverReady
      : (isStickerFlow ? topImageReady : imageTextUploadReady);
    if (uploadIssue || !uploadOk) {
      await dumpComposeDiagnostics(cdp, sessionId);
      throw new Error(`Image upload failed${uploadIssue ? `: ${uploadIssue}` : ''}`);
    }

    console.log('[wechat-browser] Filling title...');
    await cdp.send('Runtime.evaluate', {
      expression: `
        const titleInput = document.querySelector('#title');
        if (titleInput) {
          titleInput.value = ${JSON.stringify(title)};
          titleInput.dispatchEvent(new Event('input', { bubbles: true }));
        } else {
          throw new Error('Title input not found');
        }
      `,
    }, { sessionId });
    await sleep(500);

    console.log('[wechat-browser] Preparing content editor...');
    // Always prefer the real body editor; only fallback to guide text when body is unavailable.
    const editorSelector = await pickAndFocusContentEditor(cdp, sessionId, false);
    await sleep(200);

    const normalizedContent = content.replace(/\r\n/g, '\n');
    await clearContentEditor(cdp, sessionId, editorSelector);
    await sleep(120);
    await pickAndFocusContentEditor(cdp, sessionId, false);
    console.log('[wechat-browser] Inserting content line-by-line...');
    await insertContentLineByLine(cdp, sessionId, normalizedContent);
    await sleep(350);

    let editorState = await readContentEditorState(cdp, sessionId, editorSelector);
    const expectedLineBreaks = (normalizedContent.match(/\n/g) || []).length;
    const lineBreakMissing = expectedLineBreaks > 0 && editorState.lineBreaks === 0 && editorState.blockCount <= 1;
    if (!isContentWritten(editorState, normalizedContent) || lineBreakMissing) {
      if (lineBreakMissing) {
        console.warn(`[wechat-browser] Line-break check failed: expected>=${expectedLineBreaks}, actual=${editorState.lineBreaks}. Retrying with clipboard HTML paste...`);
      } else {
        console.warn('[wechat-browser] Line-by-line insertion check failed, retrying with HTML insertion...');
      }
      await clearContentEditor(cdp, sessionId, editorSelector);
      await sleep(120);
      await pickAndFocusContentEditor(cdp, sessionId, false);
      let recovered = false;
      if (lineBreakMissing) {
        await cdp.send('Page.bringToFront', {}, { sessionId });
        const pasted = pasteHtmlViaClipboard(`<div>${buildEditorHtml(normalizedContent)}</div>`);
        recovered = pasted;
      }
      if (!recovered) {
        await insertContentAsHtml(cdp, sessionId, editorSelector, normalizedContent);
      }
      await sleep(400);
      editorState = await readContentEditorState(cdp, sessionId, editorSelector);
    }

    if (!isContentWritten(editorState, normalizedContent)) {
      await dumpComposeDiagnostics(cdp, sessionId);
      throw new Error('Content insert failed: editor text not detected after retries');
    }
    if (expectedLineBreaks > 0 && editorState.lineBreaks === 0 && editorState.blockCount <= 1) {
      await dumpComposeDiagnostics(cdp, sessionId);
      throw new Error(`Content insert failed: expected multi-line content but detected lineBreaks=0 (expected>=${expectedLineBreaks})`);
    }
    console.log(`[wechat-browser] Content inserted and verified (len=${editorState.textLen}, lineBreaks=${editorState.lineBreaks}, blockCount=${editorState.blockCount}, preview="${editorState.preview}")`);
    await sleep(500);

    if (submit) {
      if (preSubmitSettings) {
        await applyPreSubmitSettings(cdp, sessionId);
      } else {
        console.log('[wechat-browser] Skipping pre-submit settings (use --pre-submit-settings to enable).');
      }
      console.log('[wechat-browser] Saving as draft...');
      await cdp.send('Runtime.evaluate', {
        expression: `document.querySelector('#js_submit')?.click()`,
      }, { sessionId });
      await sleep(3000);
      console.log('[wechat-browser] Draft saved!');
    } else {
      console.log('[wechat-browser] Article composed (preview mode). Add --submit to save as draft.');
    }
  } finally {
    if (cdp) {
      cdp.close();
    }
    console.log('[wechat-browser] Done. Browser window left open.');
  }
}

function printUsage(): never {
  console.log(`Post image-text (图文) to WeChat Official Account

Usage:
  npx -y bun wechat-browser.ts [options]

Options:
  --markdown <path>  Markdown file for title/content extraction
  --images <dir>     Directory containing images (PNG/JPG)
  --title <text>     Article title (max 20 chars, auto-compressed)
  --content <text>   Article content (max 1000 chars, auto-compressed)
  --image <path>     Add image (can be repeated)
  --submit           Save as draft (default: preview only)
  --pre-submit-settings  Apply extra settings (原创/创作来源/赞赏/广告/合集) before saving (default: on)
  --skip-pre-submit-settings  Skip extra settings and only fill title/content/image
  --profile <dir>    Chrome profile directory
  --help             Show this help

Examples:
  npx -y bun wechat-browser.ts --markdown article.md --images ./photos/
  npx -y bun wechat-browser.ts --title "测试" --content "内容" --image ./photo.png
  npx -y bun wechat-browser.ts --markdown article.md --images ./photos/ --submit
`);
  process.exit(0);
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  if (args.includes('--help') || args.includes('-h')) printUsage();

  const images: string[] = [];
  let submit = false;
  let preSubmitSettings = true;
  let profileDir: string | undefined;
  let title: string | undefined;
  let content: string | undefined;
  let markdownFile: string | undefined;
  let imagesDir: string | undefined;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i]!;
    if (arg === '--image' && args[i + 1]) {
      images.push(args[++i]!);
    } else if (arg === '--images' && args[i + 1]) {
      imagesDir = args[++i];
    } else if (arg === '--title' && args[i + 1]) {
      title = args[++i];
    } else if (arg === '--content' && args[i + 1]) {
      content = args[++i];
    } else if (arg === '--markdown' && args[i + 1]) {
      markdownFile = args[++i];
    } else if (arg === '--submit') {
      submit = true;
    } else if (arg === '--pre-submit-settings') {
      preSubmitSettings = true;
    } else if (arg === '--skip-pre-submit-settings') {
      preSubmitSettings = false;
    } else if (arg === '--profile' && args[i + 1]) {
      profileDir = args[++i];
    }
  }

  if (!markdownFile && !title) {
    console.error('Error: --title or --markdown is required');
    process.exit(1);
  }
  if (!markdownFile && !content) {
    console.error('Error: --content or --markdown is required');
    process.exit(1);
  }
  if (images.length === 0 && !imagesDir) {
    console.error('Error: --image or --images is required');
    process.exit(1);
  }

  await postToWeChat({
    title,
    content,
    images: images.length > 0 ? images : undefined,
    imagesDir,
    markdownFile,
    submit,
    preSubmitSettings,
    profileDir,
  });
}

await main().catch((err) => {
  console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
  process.exit(1);
});
