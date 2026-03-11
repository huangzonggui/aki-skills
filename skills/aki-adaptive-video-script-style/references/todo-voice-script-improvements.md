# Voice Script Logic TODO (Long-Term)

Last updated: 2026-03-04

## Scope

Skill: `aki-adaptive-video-script-style`  
Pipeline caller: `aki-content-pipeline-pro` -> `derive_platform_copies` -> `generate_script.py`

## This Round (User-Confirmed Improvements)

1. Remove duration title line:
   - Do not output heading like `# 视频口播脚本（约XX秒）`.
   - Reason: downstream video generation may treat this line as body text.

2. First 3 seconds must deliver the core爆点:
   - No warm-up or abstract opening.
   - Lead with the strongest fact/judgment immediately.

3. Sentence 2-3 must stay on the same爆点 thread:
   - No detours.
   - Explain why this爆点 matters for non-technical audience.
   - Specifically explain why key professional terms matter in plain language.

4. Keep language sharp and non-draggy:
   - Maintain “震惊级信号” intensity.
   - Highlight narrative such as:
     - software底层逻辑在变
     - 行业正在重新洗牌

5. Fixed/templated ending:
   - Use CTA style like `对此你怎么看？评论区聊聊。`
   - Allow controlled variants, but keep intent stable.

## Future Refactor TODO

1. Add explicit prompt constraints in `scripts/generate_script.py`:
   - Hook-first opening policy.
   - No duration heading policy.
   - Early-line audience adaptation policy.
   - Ending CTA policy.

2. Add output guardrails (post-check):
   - Reject if line 1 is not爆点.
   - Reject if heading contains duration pattern.
   - Reject if first 3 lines do not mention “why this matters”.

3. Add regression examples:
   - Save good/fail script snapshots for A/B comparison.
   - Keep sample from current topic as baseline.

## Baseline Reference (Current Topic)

- `/Users/aki/Downloads/Browsers/自媒体/1. AI个人IP话题/11. 00-20260304-2141-OpenClaw龙虾大热：底层生态改写与安全裸奔/mp_weixin/article/core_note.md`
- `/Users/aki/Downloads/Browsers/自媒体/1. AI个人IP话题/11. 00-20260304-2141-OpenClaw龙虾大热：底层生态改写与安全裸奔/channels_weixin/script/voice_script.md`
