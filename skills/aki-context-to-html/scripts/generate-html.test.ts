import { describe, expect, test } from 'bun:test';
import { decorateGuideSections, preConvertMarkdownToHtml } from './generate-html.ts';

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
