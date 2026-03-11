# Next Optimization Plan

## Context Saved

- Coze reference draft ID: `704fa4c4-0a62-4510-8ff0-df9ecf5446ff`
- User target: article + images -> script + voiced JianYing draft, reusable as a skill

## Priority 1: Voice Quality and Voice Identity

Goal: support user-requested voice identity more precisely than current Edge TTS mapping.

Planned tracks:

1. MiniMax TTS integration (official API path)
- Use HTTP or WebSocket speech synthesis API.
- Manage speaker selection (`voice_id` or cloned voice IDs).
- Support speed and emotion controls.
- Save returned audio URL/file and inject into draft local assets.

2. Fallback strategy
- If API quota/auth fails, fallback to Edge TTS voice map.

## Priority 2: Subtitle-Audio Alignment

Problem: current subtitle timing can drift because durations are estimated by text length.

Planned tracks:

1. Forced alignment
- Preferred: call alignment API/plugin after TTS to get segment timestamps.
- Candidate: Coze workflow plugin `align_text_to_audio` pattern.

2. Segment-level TTS
- Split script into lines first, synthesize per line, build exact cumulative timeline.
- Use real audio duration per segment from `ffprobe`.

3. Quality gate
- Add timing checks: total subtitle end time ~= audio duration (threshold <= 150ms).

## Priority 3: Coze Workflow Interop

Goal: reuse useful nodes from existing Coze workflow as reference.

Planned extraction:

1. Audio synth node config (voice, speed, output link)
2. Text-to-audio alignment node config (`align_text_to_audio`)
3. Caption conversion node logic (`caption_infos` equivalent data contract)

## Priority 4: Operational Reliability

1. Add preflight checks (`edge-tts`, `ffmpeg`, JianYing root path).
2. Add `--dry-run` and `--verbose` in pipeline script.
3. Emit machine-readable run report (`json`) for debugging.
