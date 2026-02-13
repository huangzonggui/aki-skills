---
name: aki-article-transformer
description: "Transform articles for different platforms. Mode 1: Rewrite with 30% information variation for other platforms. Mode 2: Generate 20-second video script (口播文案). Use when asked to transform, rewrite, or create video scripts from articles."
---

# Aki Article Transformer

Transform existing articles into different formats for multi-platform content distribution.

## Quick Start

```bash
# ONE-TIME SETUP: Create user-level provider config
mkdir -p ~/.config/comfly
cat > ~/.config/comfly/config <<'EOF'
COMFLY_API_KEY=your-api-key-here
COMFLY_API_BASE_URL=https://ai.comfly.chat
COMFLY_CHAT_MODEL=gpt-4o-mini
EOF

# Mode 1: Rewrite article for other platform (30% information variation)
npx -y bun ${SKILL_DIR}/scripts/transform.ts article.md --mode rewrite

# Mode 2: Generate 20-second video script
npx -y bun ${SKILL_DIR}/scripts/transform.ts article.md --mode script
```

**Auto-Detection**: The skill automatically detects:
- `~/.config/comfly/config` (user-level provider config)
- `ANTHROPIC_BASE_URL` and `ANTHROPIC_MODEL` from your IDE environment
- Falls back to environment variables if needed

> **Note**: `${SKILL_DIR}` represents this skill's installation directory. Agent replaces with actual path at runtime.

## Transformation Modes

### Mode 1: Article Rewrite (`--mode rewrite`)

Rewrite the article for other platforms with **30% information variation**:
- Change examples, analogies, and supporting details
- Keep core message and main points
- Adjust tone for broader audience appeal
- Add fresh perspectives while maintaining original intent

**Use Cases**:
- Cross-platform content distribution (Xiaohongshu, Zhihu, Toutiao, etc.)
- Content variation for SEO
- A/B testing different versions

### Mode 2: Video Script (`--mode script`)

Generate a **20-second video script** (口播文案) optimized for short video platforms:
- Extract key message in conversational tone
- Optimize for speaking pace (~3-4 characters per second)
- Include hook, core content, and call-to-action
- Natural, engaging delivery style

**Use Cases**:
- Douyin (TikTok) videos
- Video accounts on WeChat
- Short video content creation
- Livestream talking points

## Script Reference

| Script | Purpose |
|--------|---------|
| `scripts/transform.ts` | Main transformation script |

## Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `<input>` | Input article file path (markdown) | Required |
| `--mode <mode>` | Transformation mode: `rewrite` or `script` | Required |
| `--output <path>` | Output file path | `<input-dir>/transformed-<mode>.md` |
| `--platform <name>` | Target platform (for rewrite mode): `xiaohongshu`, `zhihu`, `toutiao`, `generic` | `generic` |
| `--duration <seconds>` | Target duration (for script mode) | `20` |
| `--api-key <key>` | Override API key | From config |
| `--model <name>` | Override model name | `glm-4-flash` |

## Examples

```bash
# Rewrite for Xiaohongshu
npx -y bun ${SKILL_DIR}/scripts/transform.ts article.md --mode rewrite --platform xiaohongshu

# Generate 30-second video script
npx -y bun ${SKILL_DIR}/scripts/transform.ts article.md --mode script --duration 30

# Specify output path
npx -y bun ${SKILL_DIR}/scripts/transform.ts article.md --mode rewrite --output ./rewritten.md
```

## API Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `COMFLY_API_KEY` | API key (preferred) | **Required** |
| `COMFLY_API_BASE_URL` | API base URL | Optional |
| `COMFLY_CHAT_MODEL` | Model name | Optional |
| `CLOUD_CODE_API_KEY` | Legacy fallback | Optional |
| `CLOUD_CODE_API_URL` | API endpoint | GLM API |
| `CLOUD_CODE_MODEL` | Model name | `glm-4-flash` |

### Alternative Variables (for compatibility)

```
GLM_API_KEY, OPENAI_API_KEY, API_KEY
GLM_API_URL, OPENAI_API_URL
GLM_MODEL, MODEL
```

### Supported APIs

| API | API URL | Model |
|-----|---------|-------|
| **GLM (智谱)** | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | `glm-4-flash` |
| **OpenAI** | `https://api.openai.com/v1/chat/completions` | `gpt-4o-mini` |
| **DeepSeek** | `https://api.deepseek.com/v1/chat/completions` | `deepseek-chat` |

## Output Format

### Rewrite Mode Output
- Markdown format preserving original structure
- 30% varied content (examples, analogies, details)
- Platform-optimized tone when specified

### Script Mode Output
- Plain text script optimized for speaking
- Estimated character count (~60-80 characters for 20 seconds)
- Natural phrasing with pauses marked
- Hook + Core + CTA structure

## Troubleshooting

- **API Key not found**: Set `COMFLY_API_KEY` or create `~/.config/comfly/config`
- **API request failed**: Check API key and URL are correct
- **Script too long/short**: Adjust `--duration` parameter
- **Rewrite not different enough**: The 30% variation is intentional to preserve core message
