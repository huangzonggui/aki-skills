---
name: media-cutter
description: Download videos from platforms (Bilibili, YouTube, etc.), extract audio, and split media files into segments. Use when user needs to: (1) Download videos from URLs, (2) Split long videos into multiple parts (e.g., separate songs from a music video), (3) Extract audio from video, (4) Save both video and audio clips separately.
---

# Media Cutter

Download videos, split media files into segments, and extract audio.

## Quick Start

### Download Video

```bash
yt-dlp -o "%(title)s.%(ext)s" <URL>
```

### Split Video by Time

Split first 60 seconds:
```bash
ffmpeg -i input.mp4 -t 60 -c copy output_part1.mp4
```

Split from 00:01:00 to 00:02:00:
```bash
ffmpeg -i input.mp4 -ss 00:01:00 -to 00:02:00 -c copy output_segment.mp4
```

### Extract Audio

```bash
ffmpeg -i input.mp4 -vn -acodec libmp3lame output.mp3
```

### Split Audio into Multiple Parts

Split every 3 minutes:
```bash
# Use the split_audio.sh script
/root/.openclaw/workspace/aki-skills/skills/media-cutter/scripts/split_audio.sh input.mp3 180
```

## Scripts

### split_video.sh

Split video into segments by duration.

```bash
split_video.sh <input_video> <segment_duration_seconds> [output_prefix]
```

Example:
```bash
split_video.sh video.mp4 180 song
# Creates: song_001.mp4, song_002.mp4, ...
```

### split_audio.sh

Split audio into segments by duration (fixed time intervals).

```bash
split_audio.sh <input_audio> <segment_duration_seconds> [output_prefix]
```

Example:
```bash
split_audio.sh audio.mp3 180 song
# Creates: song_001.mp3, song_002.mp3, ...
```

### split_audio_smart.sh (Recommended for Music Videos)

Split audio by detecting silence between songs.

```bash
split_audio_smart.sh <input_audio> <output_prefix> [min_silence_sec=2] [silence_threshold=-50dB]
```

Example:
```bash
split_audio_smart.sh audio.mp3 song
# Creates: song_001.mp3, song_002.mp3, ...

# More strict splitting (3 seconds of silence, -40dB threshold):
split_audio_smart.sh audio.mp3 song 3 -40
```

How it works:
- Detects silent sections between songs
- Cuts at the midpoint of each silence
- Prevents cutting songs in half
- Adjust `min_silence_sec` (lower = more splits) and `silence_threshold` (higher = more strict) as needed

### extract_audio.sh

Extract audio from video file.

```bash
extract_audio.sh <input_video> [output_audio]
```

Example:
```bash
extract_audio.sh video.mp4 audio.mp3
```

### download_video.sh

Download video from URL (supports Bilibili, YouTube, etc.).

```bash
download_video.sh <URL> [output_filename]
```

Example:
```bash
download_video.sh "https://www.bilibili.com/video/BV1VbBVBsE1g"
```

## Workflow: Split Music Video into Songs

**Option 1: Smart Split (Recommended)**
Detects silence between songs automatically.

```bash
# 1. Download video
download_video.sh "<BILIBILI_URL>"

# 2. Extract audio
extract_audio.sh video.mp4 audio.mp3

# 3. Smart split by silence
split_audio_smart.sh audio.mp3 song

# Optional: Create corresponding video segments
# (Need to manually sync split points or use fixed duration for video)
```

**Option 2: Fixed Duration Split**
Cuts by fixed time intervals.

```bash
# 1. Download video
download_video.sh "<BILIBILI_URL>"

# 2. Extract audio
extract_audio.sh video.mp4 audio.mp3

# 3. Split into songs (e.g., 3.5 minutes per song)
split_audio.sh audio.mp3 210 song

# 4. If you want video segments too:
split_video.sh video.mp4 210 song_video
```

## Tips

- `-c copy` in ffmpeg is fast (no re-encoding) but requires cutting at keyframes
- For precise cuts, remove `-c copy` but it will be slower
- Use `-t` for duration, `-to` for end time
- Bilibili URLs work directly with yt-dlp
- Output directory: `/root/.openclaw/workspace/media-output/` (create if needed)

## Dependencies

- `ffmpeg` - Required (should be installed)
- `yt-dlp` - Install via `pip install yt-dlp`
