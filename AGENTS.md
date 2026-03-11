# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

Repository of Aki-focused automation and content skills. The codebase contains mixed runtimes (TypeScript/Bun, Python, and shell scripts) for writing, publishing, scraping, and media workflows.

## Architecture

```
skills/
├── aki-content-pipeline-pro/  # Multi-stage content production pipeline
├── aki-context-to-html/       # Article/text -> styled HTML
├── aki-post-to-wechat/        # WeChat browser publishing
├── aki-wechat-fetcher/        # WeChat article fetching
├── aki-image-article-video/   # Script + image -> JianYing draft pipeline
└── ...                        # Additional domain skills
```

Each skill contains:
- `SKILL.md` - YAML front matter (name, description) + documentation
- `scripts/` - TypeScript implementations
- `prompts/system.md` - AI generation guidelines (optional)

## Running Skills

TypeScript scripts are usually run via Bun:

```bash
npx -y bun skills/<skill>/scripts/<script>.ts [options]
```

Examples:
```bash
# WeChat fetch
npx -y bun skills/aki-wechat-fetcher/scripts/fetch.ts --url "<wechat-article-url>"

# WeChat publish
npx -y bun skills/aki-post-to-wechat/scripts/wechat-browser.ts --markdown article.md --images ./images
```

## Key Dependencies

- **Bun**: TypeScript runtime (via `npx -y bun`)
- **Python 3**: Many skills expose Python scripts
- **Chrome**: Required by browser-automation skills

## Plugin Configuration

`.claude-plugin/marketplace.json` defines plugin metadata and skill paths.

## Adding New Skills

**IMPORTANT**: Prefer `aki-` prefix for repository-owned skills.

1. Create `skills/aki-<name>/SKILL.md` with YAML front matter
   - Directory name: `aki-<name>`
   - SKILL.md `name` field: `aki-<name>`
2. Add scripts in `skills/aki-<name>/scripts/` (TypeScript/Python/Shell as needed)
3. Add prompt templates in `skills/aki-<name>/prompts/` if needed
4. Register in `.claude-plugin/marketplace.json` under `plugins[0].skills`

## Code Style

- TypeScript throughout, no comments
- Async/await patterns
- Short variable names
- Type-safe interfaces
