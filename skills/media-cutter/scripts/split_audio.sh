#!/bin/bash

# Split audio into segments by duration
# Usage: split_audio.sh <input_audio> <segment_duration_seconds> [output_prefix]

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <input_audio> <segment_duration_seconds> [output_prefix]"
    exit 1
fi

INPUT="$1"
DURATION="$2"
PREFIX="${3:-segment}"

# Create output directory
OUTPUT_DIR="/root/.openclaw/workspace/media-output"
mkdir -p "$OUTPUT_DIR"

# Get input filename without extension
BASENAME=$(basename "$INPUT")
EXT="${BASENAME##*.}"
BASENAME="${BASENAME%.*}"

# Calculate audio duration
TOTAL_DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$INPUT")
TOTAL_DURATION=${TOTAL_DURATION%.*}  # Remove decimal part

echo "Total duration: ${TOTAL_DURATION}s"
echo "Segment duration: ${DURATION}s"

# Split audio
CURRENT_TIME=0
COUNTER=1

while [ $((CURRENT_TIME)) -lt $((TOTAL_DURATION)) ]; do
    OUTPUT_FILE="$OUTPUT_DIR/${PREFIX}_$(printf "%03d" $COUNTER).$EXT"

    echo "Creating segment $COUNTER: $OUTPUT_FILE (${CURRENT_TIME}s - $((CURRENT_TIME + DURATION))s)"

    ffmpeg -i "$INPUT" -ss $CURRENT_TIME -t $DURATION -c copy "$OUTPUT_FILE" -y -loglevel error

    CURRENT_TIME=$((CURRENT_TIME + DURATION))
    COUNTER=$((COUNTER + 1))
done

echo "Done! Segments saved to: $OUTPUT_DIR"
