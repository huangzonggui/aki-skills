#!/usr/bin/env bash
set -euo pipefail

DEFAULT_THEME="lapis"
DEFAULT_HIGHLIGHT="solarized-light"
TOOLS_MD="$HOME/.openclaw/workspace/TOOLS.md"
WECHAT_CONFIG="$HOME/.config/wechat/config"

print_help() {
  cat <<USAGE
Usage:
  $0 --dir <image-dir> --title <title> [--cover <cover-path>] [--out <markdown-path>] [--theme <theme>] [--highlight <highlight>] [--publish]

Examples:
  $0 --dir ./imgs --title "春晚机器人：4张图看懂趋势"
  $0 --dir ./imgs --title "春晚机器人：4张图看懂趋势" --publish
USAGE
}

read_config_value() {
  local file="$1"
  local keys="$2"
  awk -v keys="$keys" '
    BEGIN {
      n = split(keys, arr, ",")
      for (i = 1; i <= n; i++) allow[arr[i]] = 1
    }
    /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
    {
      line = $0
      sub(/^[[:space:]]*export[[:space:]]+/, "", line)
      eq = index(line, "=")
      if (eq == 0) next
      k = substr(line, 1, eq - 1)
      v = substr(line, eq + 1)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", k)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
      gsub(/^["'\'']|["'\'']$/, "", v)
      if (allow[k]) {
        print v
        exit
      }
    }
  ' "$file"
}

load_credentials_from_files() {
  local appid="${WECHAT_APP_ID:-}"
  local secret="${WECHAT_APP_SECRET:-}"
  local file

  for file in "$WECHAT_CONFIG" "$TOOLS_MD"; do
    [[ -f "$file" ]] || continue

    if [[ -z "$appid" ]]; then
      appid="$(read_config_value "$file" "WECHAT_APP_ID,WECHAT_ID,APPID,APP_ID")"
    fi
    if [[ -z "$secret" ]]; then
      secret="$(read_config_value "$file" "WECHAT_APP_SECRET,WECHAT_TOKEN,APPSECRET,APP_SECRET,SECRET,TOKEN")"
    fi
  done

  if [[ -n "$appid" ]]; then
    export WECHAT_APP_ID="$appid"
    export WECHAT_ID="$appid"
  fi
  if [[ -n "$secret" ]]; then
    export WECHAT_APP_SECRET="$secret"
    export WECHAT_TOKEN="$secret"
  fi
}

ensure_wenyan() {
  if ! command -v wenyan >/dev/null 2>&1; then
    echo "wenyan-cli 未安装，正在安装 @wenyan-md/cli..."
    npm install -g @wenyan-md/cli
  fi
}

require_publish_credentials() {
  load_credentials_from_files
  if [[ -z "${WECHAT_APP_ID:-}" || -z "${WECHAT_APP_SECRET:-}" ]]; then
    echo "缺少 WECHAT_APP_ID 或 WECHAT_APP_SECRET。"
    echo "请先配置环境变量，或在 $WECHAT_CONFIG（推荐）/ $TOOLS_MD 中添加配置。"
    exit 1
  fi
}

IMAGE_DIR=""
TITLE=""
COVER=""
OUT_MD=""
THEME="$DEFAULT_THEME"
HIGHLIGHT="$DEFAULT_HIGHLIGHT"
DO_PUBLISH="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      IMAGE_DIR="$2"
      shift 2
      ;;
    --title)
      TITLE="$2"
      shift 2
      ;;
    --cover)
      COVER="$2"
      shift 2
      ;;
    --out)
      OUT_MD="$2"
      shift 2
      ;;
    --theme)
      THEME="$2"
      shift 2
      ;;
    --highlight)
      HIGHLIGHT="$2"
      shift 2
      ;;
    --publish)
      DO_PUBLISH="true"
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo "未知参数: $1"
      print_help
      exit 1
      ;;
  esac
done

if [[ -z "$IMAGE_DIR" || -z "$TITLE" ]]; then
  echo "--dir 和 --title 是必填参数"
  print_help
  exit 1
fi

if [[ ! -d "$IMAGE_DIR" ]]; then
  echo "图片目录不存在: $IMAGE_DIR"
  exit 1
fi

IMAGE_DIR_ABS="$(cd "$IMAGE_DIR" && pwd)"
if [[ -z "$OUT_MD" ]]; then
  OUT_MD="$IMAGE_DIR_ABS/wechat-image-post.md"
fi

IMAGES=()
while IFS= read -r img; do
  IMAGES+=("$img")
done < <(find "$IMAGE_DIR_ABS" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.webp" \) | sort)

if [[ ${#IMAGES[@]} -eq 0 ]]; then
  echo "目录中没有图片文件: $IMAGE_DIR_ABS"
  exit 1
fi

if [[ -z "$COVER" ]]; then
  COVER="${IMAGES[0]}"
fi

if [[ ! -f "$COVER" ]]; then
  echo "封面图不存在: $COVER"
  exit 1
fi

{
  echo "---"
  echo "title: $TITLE"
  echo "cover: $COVER"
  echo "---"
  echo
  echo "# $TITLE"
  echo
  idx=1
  for img in "${IMAGES[@]}"; do
    echo "![图$idx]($img)"
    echo
    idx=$((idx + 1))
  done
} > "$OUT_MD"

echo "已生成图文 Markdown: $OUT_MD"
echo "图片数量: ${#IMAGES[@]}"

if [[ "$DO_PUBLISH" == "true" ]]; then
  require_publish_credentials
  ensure_wenyan
  echo "开始发布到微信公众号草稿箱..."
  wenyan publish -f "$OUT_MD" -t "$THEME" -h "$HIGHLIGHT"
  echo "发布请求完成。请到公众号后台草稿箱检查。"
else
  echo "未执行发布（未传 --publish）。"
fi
