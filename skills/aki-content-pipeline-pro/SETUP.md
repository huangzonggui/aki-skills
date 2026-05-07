# Setup Guide

## Prerequisites

### Everyone needs:

- **Python 3.10+** — [python.org](https://python.org)
- **Comfly API key** — sign up at https://ai.comfly.chat (free credits available)

### Optional (for video/publish):

- **ffmpeg** (video export) — `brew install ffmpeg` (Mac) / [ffmpeg.org](https://ffmpeg.org) (Windows)
- **Jianying Pro** (video drafts) — [剪映专业版](https://www.capcut.cn)
- **WeChat Official Account** (publish) — `WECHAT_APP_ID` + `WECHAT_APP_SECRET`

---

## macOS

```bash
# 1. Check Python
python3 --version  # need 3.10+

# 2. Install Pillow (recommended)
pip3 install Pillow

# 3. Create config
cp config/keys.env.example ~/.config/ai/keys.env
# Edit ~/.config/ai/keys.env with your COMFLY_API_KEY

# 4. Verify
python3 scripts/check_env.py
```

## Windows

```powershell
# 1. Install Python from python.org (check "Add to PATH")

# 2. Install Pillow
pip install Pillow

# 3. Create config
copy config\keys.env.example %USERPROFILE%\.config\ai\keys.env
# Edit with Notepad, add your COMFLY_API_KEY

# 4. Verify
python scripts\check_env.py
```

## Linux

```bash
# 1. Python 3.10+ (usually pre-installed)
python3 --version

# 2. Install Pillow
pip3 install Pillow

# 3. Create config
cp config/keys.env.example ~/.config/ai/keys.env

# 4. Verify
python3 scripts/check_env.py
```

---

## Get a Comfly API Key

1. Visit https://ai.comfly.chat
2. Sign up / log in
3. Get your API key from the dashboard
4. Put it in `~/.config/ai/keys.env`:
   ```
   COMFLY_API_KEY=sk-your-actual-key
   ```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `sips: command not found` (Windows/Linux) | `pip install Pillow` |
| `COMFLY_API_KEY missing` | Create `~/.config/ai/keys.env` with your key |
| `ffprobe not found` (video only) | Install ffmpeg or skip video steps |
| `No module named 'PIL'` | `pip install Pillow` |
