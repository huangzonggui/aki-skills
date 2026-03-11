---
name: aki-image-article-video
description: Natural-language image/article-to-JianYing draft pipeline. Keeps provided script text unchanged, uses real audio duration, ASR-first subtitles, configurable voice profiles, and cache-based BGM selection.
---

# AKI Image Article Video (V3)

This skill is designed for CC/Codex natural-language orchestration.
Primary entrypoint is:

`scripts/nl_entrypoint.py`

## Natural-language intents

1. `generate_draft` (default)
- Input minimum: `project_dir`
- Optional: `voice_name`, `speed_override`, `subtitle_mode`, `subtitle_engine`, `subtitle_qa_policy`, `subtitle_font`, `subtitle_max_chars`, `subtitle_max_duration`, `script_editor_cmd`, `script_editor_timeout_sec`, `bgm_mode`, `bgm_min_duration_sec`, `new_name`
- Output: structured JSON with draft/audio/srt/cpm/speed/subtitle/bgm/warnings

2. `register_voice_profile`
- Register/update local voice profile in `.local/voice_profiles.json`
- Supports provider/model/ref audio/default speed/voice_uri

3. `bgm_feedback`
- Mark a picked BGM as `tech_like` or `dislike` (history learning)

## Behavior contract

1. Script rule:
- If a script file exists (filename contains `口播稿` or `script`), use it directly (verbatim).
- If no script exists, merge markdown files and generate script from article content.
- Optional `script_editor_cmd` can post-edit generated script before TTS/subtitle.
- Command placeholders: `{input}` `{output}` `{workdir}`.

2. Timeline rule:
- Audio is generated first.
- Draft duration follows real audio duration.
- No hard 30s truncation.

3. Subtitle rule:
- Default `subtitle_engine=stable_regroup`: whisper word timestamps + regroup segmentation + QA report.
- `legacy` mode keeps old ASR/heuristic + script-text rewrite path.
- Fallback to heuristic when ASR path fails.

4. Voice/speed rule:
- Priority: `speed_override` > profile `default_speed` > fallback defaults.
- global fallback default speed is `1.0`.
- `日常松弛男` fallback default speed is `1.3` when profile has no speed configured.
- `speed_override` can override run-time speed.

5. CPM rule:
- Report only, no hard validation.

6. Image rule:
- Use all images in the directory recursively (`png/jpg/jpeg/webp/bmp`).

7. Animation rule:
- Default preset `flip_zoom` (page-turn transition + lightweight zoom handling).
- Transition falls back to `叠化` automatically when `翻页` is unavailable.

8. BGM rule:
- Source: JianYing cache pool.
- Independent BGM track.
- Default priority: `剪映收藏 + 已购(可商用代理信号)` tracks first (when locally resolvable to cache mp3).
- `auto_tech_from_jy_cache` prefers `tech_like` history from music-category tracks.
- Supports `music_only` policy to force music-category filtering.
- `bgm_min_duration_sec` can reject short clips (default `45.0`).

## Config model

Committed defaults:
- `config/defaults.json`
- `config/voice_profiles.example.json`

Private local state (gitignored):
- `.local/voice_profiles.json`
- `.local/voice_refs/`
- `.local/bgm_history.json`
- `.local/runtime_reports/`

Environment overrides:
- `JY_PROJECTS_ROOT`
- `AI_KEYS_ENV_PATH`
- `VOICE_PROFILE_PATH`
- `JY_CACHE_MUSIC_DIR`
- `RUNTIME_REPORTS_DIR`

## Internal scripts

- `scripts/nl_entrypoint.py` - natural-language entry
- `scripts/build_video_from_article_assets.py` - core builder (compatible CLI retained)
- `scripts/voice_registry.py` - voice profile CRUD and voice_uri update
- `scripts/bgm_selector.py` - BGM pick + feedback learning
- `scripts/draft_enhancer.py` - draft animation + BGM track injection

## Command examples (for agent execution)

Generate draft:

```bash
python /Users/aki/Development/code/aki-skills/skills/aki-image-article-video/scripts/nl_entrypoint.py \
  --project-dir "/abs/project_dir" \
  --intent generate_draft \
  --voice-name "日常松弛男"
```

Register voice profile:

```bash
python /Users/aki/Development/code/aki-skills/skills/aki-image-article-video/scripts/nl_entrypoint.py \
  --project-dir "/abs/project_dir" \
  --intent register_voice_profile \
  --voice-name "知性女声" \
  --voice-provider siliconflow \
  --voice-model "IndexTeam/IndexTTS-2" \
  --voice-ref-audio "/abs/ref.mp3" \
  --voice-default-speed 1.28
```

BGM feedback:

```bash
python /Users/aki/Development/code/aki-skills/skills/aki-image-article-video/scripts/nl_entrypoint.py \
  --project-dir "/abs/project_dir" \
  --intent bgm_feedback \
  --bgm-track-path "/abs/bgm.mp3" \
  --bgm-feedback "加入科技池"
```
