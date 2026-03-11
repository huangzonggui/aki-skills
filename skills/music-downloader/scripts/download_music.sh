#!/bin/bash
# Download music from URL and convert to MP3

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-/root/.openclaw/workspace/music-output}"

# Create output directory
mkdir -p "$OUTPUT_DIR"

if [ -z "$1" ]; then
    echo "Usage: $0 <url> [output_filename.mp3] [--audio-quality 0|1|2]"
    echo ""
    echo "Example:"
    echo "  $0 \"https://www.youtube.com/watch?v=VIDEO_ID\""
    echo "  $0 \"https://www.youtube.com/watch?v=VIDEO_ID\" song.mp3"
    echo "  $0 \"https://soundcloud.com/artist/track\" track.mp3"
    echo ""
    echo "Quality options (optional):"
    echo "  0 = best (default)"
    echo "  1 = good"
    echo "  2 = smaller"
    exit 1
fi

URL="$1"
OUTPUT_FILE="$2"
AUDIO_QUALITY="0"

# Parse optional arguments
shift 2
while [ $# -gt 0 ]; do
    case "$1" in
        --audio-quality)
            AUDIO_QUALITY="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Map quality to yt-dlp format
case "$AUDIO_QUALITY" in
    0) FORMAT="bestaudio/best" ;;
    1) FORMAT="bestaudio[abr<=192]/bestaudio" ;;
    2) FORMAT="bestaudio[abr<=128]/bestaudio" ;;
    *) FORMAT="bestaudio/best" ;;
esac

echo "=== Music Downloader ==="
echo "URL: $URL"
echo "Format: $FORMAT"
echo "Output dir: $OUTPUT_DIR"
echo ""

cd "$OUTPUT_DIR"

# Download and convert to MP3
if [ -n "$OUTPUT_FILE" ]; then
    # Custom filename
    yt-dlp -x --audio-format mp3 --audio-quality 0 -f "$FORMAT" -o "$OUTPUT_FILE" "$URL"
else
    # Auto-generate filename from metadata
    yt-dlp -x --audio-format mp3 --audio-quality 0 -f "$FORMAT" -o "%(artist)s - %(title)s.%(ext)s" "$URL"
fi

echo ""
echo "Done! Files saved in: $OUTPUT_DIR"
