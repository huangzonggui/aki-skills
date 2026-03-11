#!/bin/bash
# 智能音频分割 - 通过检测静音段自动分割歌曲
# 使用 ffmpeg 的 silencedetect 滤镜

if [ $# -lt 2 ]; then
    echo "Usage: $0 <input_file> <output_prefix> [min_silence_sec=2] [silence_threshold=-50dB]"
    echo ""
    echo "Example:"
    echo "  $0 audio.mp3 song"
    echo "  $0 audio.mp3 song 3 -40  # 更严格（3秒静音，-40dB阈值）"
    exit 1
fi

INPUT_FILE="$1"
OUTPUT_PREFIX="$2"
MIN_SILENCE="${3:-2}"           # 最小静音时长（秒）
SILENCE_THRESHOLD="${4:--50dB}"  # 静音阈值（负数，值越大越严格）

if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: File '$INPUT_FILE' not found"
    exit 1
fi

echo "=== Smart Audio Split ==="
echo "Input: $INPUT_FILE"
echo "Prefix: $OUTPUT_PREFIX"
echo "Min silence: ${MIN_SILENCE}s"
echo "Threshold: $SILENCE_THRESHOLD"
echo ""

# 1. 检测静音段（获取静音开始和结束的时间戳）
# 输出格式：
# [silencedetect @ ...] silence_start: 123.45
# [silencedetect @ ...] silence_end: 130.67
# [silencedetect @ ...] silence_duration: 8.22

echo "Detecting silence segments..."
SILENCE_DATA=$(ffmpeg -i "$INPUT_FILE" -af "silencedetect=noise=$SILENCE_THRESHOLD:d=$MIN_SILENCE" -f null - 2>&1 | grep "silence_")

# 解析静音数据
SILENCE_START_TIMES=$(echo "$SILENCE_DATA" | grep "silence_start:" | grep -oE "[0-9]+\.[0-9]+")
SILENCE_END_TIMES=$(echo "$SILENCE_DATA" | grep "silence_end:" | grep -oE "[0-9]+\.[0-9]+")

# 将静音段转换为分割点（每段静音的中间时间点）
# 例如： silence_start=123.45, silence_end=130.67，分割点 = (123.45 + 130.67) / 2 = 127.06

# 创建临时文件存储分割点
SPLITS_FILE=$(mktemp)
> "$SPLITS_FILE"

if [ -z "$SILENCE_START_TIMES" ]; then
    echo "Warning: No silence segments detected. Output will be the whole file."
    echo "Try reducing min_silence_sec or silence_threshold."
    SPLIT_POINTS=()
else
    echo "Found $(echo "$SILENCE_START_TIMES" | wc -l) silence segments"

    # 计算分割点
    echo "$SILENCE_START_TIMES" | while read -r start; do
        # 找到对应的 end
        end=$(echo "$SILENCE_END_TIMES" | head -n 1)
        SILENCE_END_TIMES=$(echo "$SILENCE_END_TIMES" | tail -n +1)

        # 计算分割点（静音中间）
        split_point=$(echo "scale=2; ($start + $end) / 2" | bc)
        echo "$split_point" >> "$SPLITS_FILE"
    done

    SPLIT_POINTS=$(sort -n "$SPLITS_FILE")
    echo "Split points: $SPLIT_POINTS"
fi

rm "$SPLITS_FILE"

# 2. 添加开头和结尾
DURATION=$(ffprobe -i "$INPUT_FILE" -show_entries format=duration -v quiet -of csv="p=0")
DURATION=$(echo "$DURATION" | cut -d'.' -f1)

ALL_POINTS="0"
if [ -n "$SPLIT_POINTS" ]; then
    ALL_POINTS="$ALL_POINTS $SPLIT_POINTS"
fi
ALL_POINTS="$ALL_POINTS $DURATION"

# 3. 分割音频
echo ""
echo "Splitting audio into segments..."

COUNT=1
echo "$ALL_POINTS" | tr ' ' '\n' | while read -r point; do
    [ -z "$point" ] && continue

    # 读取下一点作为结束时间
    next_point=$(echo "$ALL_POINTS" | tr ' ' '\n' | grep -A 1 "^${point}$" | tail -n 1)

    if [ -n "$next_point" ] && [ "$next_point" != "$point" ]; then
        duration_sec=$(echo "$next_point - $point" | bc)

        # 格式化序号（001, 002, ...）
        NUM=$(printf "%03d" $COUNT)

        OUTPUT_FILE="${OUTPUT_PREFIX}_${NUM}.mp3"

        echo "Segment $COUNT: ${point}s -> ${next_point}s (${duration_sec}s) -> $OUTPUT_FILE"

        ffmpeg -ss "$point" -i "$INPUT_FILE" -t "$duration_sec" -c copy "$OUTPUT_FILE" -y -loglevel error

        COUNT=$((COUNT + 1))
    fi
done

echo ""
echo "Done! Segments saved as ${OUTPUT_PREFIX}_*.mp3"
