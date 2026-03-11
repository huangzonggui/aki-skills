---
name: music-downloader
description: Download music from free music platforms (YouTube Music, SoundCloud, Jamendo, Bandcamp, Free Music Archive). Use when user wants to download songs, albums, or playlists from these sources.
---

# Music Downloader

Download music from free and legal music platforms.

## Supported Platforms

| Platform | Type | Notes |
|----------|------|-------|
| YouTube Music | Video/Audio | Unlimited, mixed quality |
| SoundCloud | Audio | Many free tracks |
| Jamendo | Audio | 100% free, CC licensed |
| Bandcamp | Audio | Free/name-your-price |
| Free Music Archive | Audio | Curated free music |

## Quick Start

### Download Single Song

```bash
# YouTube
download_music.sh "https://www.youtube.com/watch?v=VIDEO_ID" song.mp3

# SoundCloud
download_music.sh "https://soundcloud.com/artist/track" track.mp3

# Jamendo
download_music.sh "https://www.jamendo.com/track/12345" track.mp3
```

### Download Playlist/Album

```bash
# YouTube Music playlist
download_playlist.sh "https://www.youtube.com/playlist?list=PLAYLIST_ID" album/

# SoundCloud set
download_playlist.sh "https://soundcloud.com/artist/sets/album" album/
```

## Scripts

### download_music.sh

Download single track and convert to MP3.

```bash
download_music.sh <url> [output_filename.mp3]
```

Example:
```bash
# Auto-generate filename
download_music.sh "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Custom filename
download_music.sh "https://www.youtube.com/watch?v=dQw4w9WgXcQ" rick_roll.mp3
```

### download_playlist.sh

Download entire playlist/album.

```bash
download_playlist.sh <url> [output_directory]
```

Example:
```bash
download_playlist.sh "https://www.youtube.com/playlist?list=PLrAXtmRdnEQy7i4q5XK9z5Z4d5qX5qX5q" my_playlist/
```

### search_music.sh

Search for music on YouTube and get links.

```bash
search_music.sh "歌手名 歌名"
```

Example:
```bash
search_music.sh "田园 后来的后来"
search_music.sh "周杰伦 晴天"
```

## Quality Options

### Audio Quality

Add `--audio-quality` flag:
- `0` = best (default)
- `1` = good
- `2` = smaller

```bash
download_music.sh --audio-quality 1 "URL" song.mp3
```

### Format Options

- MP3 (default) - `-x --audio-format mp3`
- M4A (AAC) - `-x --audio-format m4a`
- WAV (uncompressed) - `-x --audio-format wav`

## Platform-Specific Notes

### YouTube Music

- Best for: Popular songs, covers, remixes
- Quality: Variable (depends on source)
- Tip: Add "audio only" to search for better rips

### SoundCloud

- Best for: Independent artists, electronic music
- Note: Some tracks are download-protected
- Tip: Look for "Free Download" badge

### Jamendo

- Best for: Royalty-free, background music
- License: Creative Commons
- Great for: Videos, podcasts, commercial use

### Bandcamp

- Best for: Independent artists
- Note: Only free/name-your-price tracks downloadable
- Tip: Use search with "free" filter

### Free Music Archive

- Best for: Curated legal free music
- Quality: Varies
- Great for: Documentaries, educational content

## Output Location

Default: `/root/.openclaw/workspace/music-output/`

## Dependencies

- `yt-dlp` (for YouTube, SoundCloud)
- `ffmpeg` (for audio conversion)

## Tips

1. **Batch download**: Put URLs in a text file (one per line) and loop through them
2. **Metadata**: yt-dlp automatically fetches metadata (title, artist, album)
3. **Playlists**: Use `-I 1-5` to download only first 5 tracks from playlist
4. **Retry failed downloads**: yt-dlp has built-in retry mechanism

## Legal Note

- Only download music you have rights to use
- Respect artists' licenses
- Support creators when possible (buy/stream officially)
