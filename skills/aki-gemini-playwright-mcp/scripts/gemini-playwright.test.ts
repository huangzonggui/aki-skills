import { describe, expect, test } from 'bun:test';
import { pickBestVisualCandidate, type VisualCandidate } from './gemini-playwright.ts';

describe('pickBestVisualCandidate', () => {
  test('prefers a fresh blob image over Gemini placeholder SVG assets', () => {
    const beforeKeys = new Set<string>([
      'img:https://www.gstatic.com/lamda/images/gemini_sparkle_aurora_33f86dc0c0257da337c63.svg|765x1024',
    ]);
    const candidates: VisualCandidate[] = [
      {
        key: 'img:https://www.gstatic.com/lamda/images/gemini_sparkle_aurora_33f86dc0c0257da337c63.svg|765x1024',
        src: 'https://www.gstatic.com/lamda/images/gemini_sparkle_aurora_33f86dc0c0257da337c63.svg',
        score: 765 * 1024,
        y: 2400,
      },
      {
        key: 'img:blob:https://gemini.google.com/generated-1|765x1024',
        src: 'blob:https://gemini.google.com/generated-1',
        score: 765 * 1024,
        y: 2200,
      },
    ];

    expect(pickBestVisualCandidate(candidates, beforeKeys)?.src).toBe(
      'blob:https://gemini.google.com/generated-1'
    );
  });

  test('falls back to the largest fresh raster image when no blob exists', () => {
    const beforeKeys = new Set<string>();
    const candidates: VisualCandidate[] = [
      {
        key: 'img:https://example.com/preview-small.png|320x320',
        src: 'https://example.com/preview-small.png',
        score: 320 * 320,
        y: 2000,
      },
      {
        key: 'img:https://example.com/generated-large.webp|1024x1365',
        src: 'https://example.com/generated-large.webp',
        score: 1024 * 1365,
        y: 2100,
      },
    ];

    expect(pickBestVisualCandidate(candidates, beforeKeys)?.src).toBe(
      'https://example.com/generated-large.webp'
    );
  });
});
