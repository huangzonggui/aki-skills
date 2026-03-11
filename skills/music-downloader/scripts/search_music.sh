#!/bin/bash
# Search for music on YouTube and get links

if [ -z "$1" ]; then
    echo "Usage: $0 \"歌手名 歌名\""
    echo ""
    echo "Example:"
    echo "  $0 \"田园 后来的后来\""
    echo "  $0 \"周杰伦 晴天\""
    exit 1
fi

QUERY="$1"

echo "=== Music Search ==="
echo "Query: $QUERY"
echo ""

# Search YouTube
yt-dlp "ytsearch10:$QUERY" --get-id --get-title --get-url --flat-playlist 2>/dev/null | \
    paste - - - | \
    awk 'BEGIN {FS="\t"} {printf "%3d. %s\n    URL: https://www.youtube.com/watch?v=%s\n", NR, $1, $2}'

echo ""
echo "Use download_music.sh to download:"
echo "  download_music.sh \"https://www.youtube.com/watch?v=<VIDEO_ID>\""
