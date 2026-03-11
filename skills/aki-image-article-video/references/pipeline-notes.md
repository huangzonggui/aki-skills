# Pipeline Notes

## Proven Stable Path

1. Build draft with `builder=scratch` (do not clone template project).
2. Use ordered image assets as timeline segments (cover + section images).
3. Generate subtitles from script (`script_to_srt.py`).
4. Generate TTS audio.
5. Convert audio to local `m4a` and write inside `draft/local_assets`.
6. Patch audio track in `draft_content.json` and mirror to `draft_info.json`.
7. Move draft entry to top in `root_meta_info.json`.

## Why This Works Better

- Avoids stale media references from old templates.
- Avoids macOS folder permission issues with external media paths.
- Avoids fragile tone/effect chain that can cause silent audio in some drafts.
- Keeps JSON-level control for deterministic output.

## Known Failure Modes

- `libmediainfo` read failures on some audio/path combinations.
- Audio exists but app plays silence when audio track metadata is inconsistent.
- Subtitle timing drift when timing is only proportional by character length.

## First-line Fixes

- Convert audio to `m4a` (AAC, 48kHz, stereo).
- Keep audio path under project `local_assets`.
- Reset to a single explicit audio segment (`0s` to target duration).
- Clear `materials.audio_effects` when stability is priority.
