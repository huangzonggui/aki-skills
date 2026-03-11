#!/bin/bash
# Download music playlist/album

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-/root/.openclaw/workspace/music-output}"

# Create output directory
mkdir -p "$OUTPUT_DIR"

if [ -z "$1" ]; then
    echo "Usage: $0 <playlist_url> [output_directory]"
    echo ""
    echo "Example:"
    echo "  $0 \"https://www.youtube.com/playlist?list=PLAYLIST_ID\" my_album/"
    echo "  $0 \"https://soundcloud.com/artist/sets/album\" album/"
    echo ""
    echo "Options:"
    echo "  -I 1-5    Download only tracks 1-5"
    echo "  --reverse Download in reverse order"
    exit 1
fi

PLAYLIST_URL="$1"
OUTPUT_SUBDIR="$2"
shift

# Parse optional arguments
YTDL_ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        -I)
            YTDL_ARGS+=("-I" "$2")
            shift 2
            ;;
        --reverse)
            YTDL_ARGS+=("--playlist-reverse")
            shift
            ;;
        *)
            shift
            ;;
    esac
done

echo "=== Playlist Downloader ==="
echo "URL: $PLAYLIST_URL"

if [ -n "$OUTPUT_SUBDIR" ]; then
    WORK_DIR="$OUTPUT_DIR/$OUTPUT_SUBDIR"
    mkdir -p "$WORK_DIR"
    echo "Output: $WORK_DIR"
else
    WORK_DIR="$OUTPUT_DIR"
    echo "Output: $WORK_DIR"
fi

echo ""

cd "$WORK_DIR"

# Download playlist
yt-dlp -x --audio-format mp3 --audio-quality 0 -f "bestaudio/best" \
    -o "%(playlist_index)03d - %(artist)s - %(title)s.%(ext)s" \
    "${YTDL_ARGS[@]}" \
    "$PLAYLIST_URL"

echo ""
echo "Done! Files saved in: $WORK_DIR"
