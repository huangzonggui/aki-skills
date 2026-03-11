#!/bin/bash

# Extract audio from video file
# Usage: extract_audio.sh <input_video> [output_audio]

if [ -z "$1" ]; then
    echo "Usage: $0 <input_video> [output_audio]"
    exit 1
fi

INPUT="$1"
OUTPUT="${2:-${1%.*}.mp3}"

# Create output directory if needed
OUTPUT_DIR=$(dirname "$OUTPUT")
mkdir -p "$OUTPUT_DIR"

echo "Extracting audio from: $INPUT"
echo "Output: $OUTPUT"

ffmpeg -i "$INPUT" -vn -acodec libmp3lame -q:a 2 "$OUTPUT" -y -loglevel error

echo "Done! Audio saved to: $OUTPUT"
