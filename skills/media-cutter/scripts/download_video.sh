#!/bin/bash

# Download video from URL (supports Bilibili, YouTube, etc.)
# Usage: download_video.sh <URL> [output_filename]

if [ -z "$1" ]; then
    echo "Usage: $0 <URL> [output_filename]"
    exit 1
fi

URL="$1"
OUTPUT_DIR="/root/.openclaw/workspace/media-output"
mkdir -p "$OUTPUT_DIR"

if [ -n "$2" ]; then
    OUTPUT="--output \"$OUTPUT_DIR/$2.%(ext)s\""
else
    OUTPUT="--output \"$OUTPUT_DIR/%(title)s.%(ext)s\""
fi

echo "Downloading from: $URL"
echo "Output directory: $OUTPUT_DIR"

# Use yt-dlp with output template
if [ -n "$2" ]; then
    yt-dlp -o "$OUTPUT_DIR/$2.%(ext)s" "$URL"
else
    yt-dlp -o "$OUTPUT_DIR/%(title)s.%(ext)s" "$URL"
fi

echo "Done! Video saved to: $OUTPUT_DIR"
