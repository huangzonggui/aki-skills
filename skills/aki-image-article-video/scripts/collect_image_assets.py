#!/usr/bin/env python3
"""
Collect ordered image assets for storyboard/video assembly.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List


def pick_assets(base: Path, max_images: int) -> List[Path]:
    cover = base / '0-cover.png'
    results: List[Path] = []

    if cover.exists():
        results.append(cover)

    numbered: List[tuple[int, Path]] = []
    for p in base.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
            continue
        m = re.fullmatch(r"(\d+)\.(png|jpg|jpeg|webp)", p.name, re.IGNORECASE)
        if not m:
            continue
        idx = int(m.group(1))
        if idx == 0:
            continue
        numbered.append((idx, p))

    for _, p in sorted(numbered, key=lambda x: x[0]):
        results.append(p)
        if len(results) >= max_images:
            break

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description='Collect ordered image assets')
    parser.add_argument('--assets-dir', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--max-images', type=int, default=4)
    parser.add_argument('--storyboard-json', help='optional storyboard to derive durations')
    args = parser.parse_args()

    base = Path(args.assets_dir).expanduser().resolve()
    out = Path(args.output).expanduser().resolve()

    if not base.exists():
        raise FileNotFoundError(f'assets dir not found: {base}')

    assets = pick_assets(base, args.max_images)
    if not assets:
        raise RuntimeError(f'no image assets found in {base}')

    durations = None
    if args.storyboard_json:
        sb = json.loads(Path(args.storyboard_json).expanduser().resolve().read_text(encoding='utf-8'))
        tl = sb.get('timeline', [])
        durations = [float(x.get('duration', 0)) for x in tl[:len(assets)]]
        if len(durations) < len(assets):
            durations.extend([0.0] * (len(assets) - len(durations)))

    payload = {
        'assets_dir': str(base),
        'assets': [str(x) for x in assets],
        'assets_csv': ','.join(str(x) for x in assets),
        'durations': durations,
        'durations_csv': ','.join(str(x) for x in durations) if durations else None,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'✅ assets written: {out}')
    print(payload['assets_csv'])
    if payload['durations_csv']:
        print(payload['durations_csv'])


if __name__ == '__main__':
    main()
