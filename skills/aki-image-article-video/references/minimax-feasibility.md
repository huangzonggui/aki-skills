# MiniMax Feasibility (2026-03-01)

## Conclusion

MiniMax can be used for "specified voice" audio generation, but not through the Coding Plan endpoint itself.

- Coding Plan in MiniMax docs is for coding-oriented chat models and API-key setup, not direct TTS generation.
- TTS/voice capabilities are exposed by speech endpoints (text_to_speech, voice clone, voice list, transcription).

## Practical Direction

1. Keep current draft builder unchanged.
2. Replace TTS stage only:
- call MiniMax `text_to_speech`
- choose `voice_id` for system voice or custom cloned voice
- store audio in `draft/local_assets`
- patch draft audio track as done now

3. Alignment upgrade:
- Option A: split script into short lines and synthesize line-by-line
- Option B: synthesize full audio then run transcription/alignment to recover timestamps
- Build subtitle timeline from real audio timestamps instead of text-length heuristics

## Risks and Checks

- API quota and billing control
- Voice authorization/compliance for cloned voices
- Retry/backoff for network calls
- Local fallback to Edge TTS when MiniMax fails

## Candidate APIs to Verify in POC

- Text to speech (`text_to_speech`)
- Voice clone (`voice_clone`)
- List voices (`list_voices`)
- File transcription (`file_transcription`)
