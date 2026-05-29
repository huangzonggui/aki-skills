import { describe, expect, test } from 'bun:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { decorateGuideSections, inlineLocalImagesInHtml, preConvertMarkdownToHtml } from './generate-html.ts';

describe('decorateGuideSections', () => {
  test('renders numbered part-guide headings without PART label', () => {
    const html = decorateGuideSections('<h2 class="section-title">Claude Code 的六个工程护城河</h2>');

    expect(html).toContain('<span class="section-number">01</span>');
    expect(html).toContain('<span class="section-main">Claude Code 的六个工程护城河</span>');
    expect(html).not.toContain('section-part');
    expect(html).not.toContain('PART');
  });
});

describe('preConvertMarkdownToHtml', () => {
  test('converts markdown images into img tags instead of plain paragraphs', () => {
    const html = preConvertMarkdownToHtml('![](./images/demo.png)');

    expect(html).toContain('<img src="./images/demo.png" alt="">');
    expect(html).not.toContain('<p>![](./images/demo.png)</p>');
  });
});

describe('inlineLocalImagesInHtml', () => {
  test('embeds local relative images as data urls for canvas export', () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'aki-context-to-html-'));
    try {
      const copiesDir = path.join(root, 'copies');
      const assetsDir = path.join(root, 'assets');
      fs.mkdirSync(copiesDir, { recursive: true });
      fs.mkdirSync(assetsDir, { recursive: true });
      fs.writeFileSync(
        path.join(assetsDir, 'demo.png'),
        Buffer.from(
          'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=',
          'base64',
        ),
      );

      const html = inlineLocalImagesInHtml('<img src="../assets/demo.png" alt="demo">', copiesDir);

      expect(html).toContain('src="data:image/png;base64,');
      expect(html).toContain('alt="demo"');
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  });

  test('keeps remote images unchanged', () => {
    const html = inlineLocalImagesInHtml('<img src="https://example.com/demo.png">', '/tmp');

    expect(html).toContain('src="https://example.com/demo.png"');
  });
});

describe('part-guide export template', () => {
  test('uses export-time highlight overlays instead of cross-line mark backgrounds', () => {
    const scriptDir = path.dirname(fileURLToPath(import.meta.url));
    const template = fs.readFileSync(path.join(scriptDir, 'template-part-guide.html'), 'utf-8');

    expect(template).toContain('decorateMarkBackgroundsForExport');
    expect(template).toContain('export-highlight-bg');
    expect(template).toContain('allowTaint: false');
    expect(template).toContain('canvasLooksBlank');
    expect(template).toContain('const points = [');
    expect(template).not.toContain('allowTaint: true');
  });
});
