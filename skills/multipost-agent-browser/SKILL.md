---
name: multipost-agent-browser
description: 使用 agent-browser 操作 multipost.app，自动填写发布表单、勾选目标平台、上传素材，并执行发布或保存草稿。适用于用户要求自动化 MultiPost 控制台分发发布的场景。
allowed-tools: Bash(agent-browser:*)
---

# MultiPost 网页发布（agent-browser）

通过 `agent-browser` 自动化操作 `https://multipost.app` 的发布流程。

## 适用场景

当用户提出以下需求时使用本技能：

- 在 MultiPost 网页控制台发布内容
- 一次填写内容并分发到多个平台
- 在 `multipost.app/dashboard/publish` 做批量或重复发布

## 脚本目录

本技能脚本位于 `scripts/` 目录。

| 脚本 | 作用 |
|---|---|
| `scripts/bootstrap-session.sh` | 首次手动登录并保存登录态 |
| `scripts/open-publish.sh` | 恢复登录态并打开发布页 |

## 输入参数

开始操作前请准备以下字段：

- `title`（必填）
- `content`（必填，可为文本或文件内容）
- `platforms`（必填，目标平台列表）
- `media_files`（可选，素材绝对路径）
- `mode`（可选：`draft` 或 `publish`，默认 `draft`）
- `schedule_time`（可选，仅用户明确要求定时发布时使用）

如果 `content` 是文件路径，先读取文件全文，再填入发布内容。

## 安全规则

- 默认使用 `draft`（保存草稿）模式。
- 没有用户在当前会话中的明确确认，不得点击最终发布按钮。
- 提交前必须先截图并给出预检摘要。

## 核心流程

### 1) 启动会话

复用名为 `multipost` 的持久化会话：

```bash
SKILL_DIR="/Users/aki/Development/code/aki-skills/skills/multipost-agent-browser"
bash "${SKILL_DIR}/scripts/open-publish.sh" multipost
```

如果没有登录态文件（或登录态失效），执行：

```bash
bash "${SKILL_DIR}/scripts/bootstrap-session.sh" multipost
bash "${SKILL_DIR}/scripts/open-publish.sh" multipost
```

### 2) 校验当前页面为发布页

```bash
agent-browser --session multipost get url
agent-browser --session multipost snapshot -i -c
```

若被重定向到登录页，重新执行 bootstrap。

### 3) 填写标题与正文

优先使用语义定位；失败后再使用最新 `snapshot` 的 `@e*` 引用。

```bash
# 标题
agent-browser --session multipost find label "Title" fill "$TITLE" || \
agent-browser --session multipost find label "标题" fill "$TITLE" || \
agent-browser --session multipost find placeholder "Title" fill "$TITLE" || \
agent-browser --session multipost find placeholder "标题" fill "$TITLE"

# 正文
agent-browser --session multipost find label "Content" fill "$CONTENT" || \
agent-browser --session multipost find label "内容" fill "$CONTENT" || \
agent-browser --session multipost find placeholder "Write" fill "$CONTENT" || \
agent-browser --session multipost find placeholder "写点什么" fill "$CONTENT"
```

若上述定位失败：

1. 执行 `agent-browser --session multipost snapshot -i`
2. 在输出中定位正文编辑器引用
3. 使用 `agent-browser --session multipost fill @eN "$CONTENT"` 填充

### 4) 选择目标平台

优先使用 `references/platform-labels.md` 里的候选标签。

对每个目标平台执行：

```bash
agent-browser --session multipost find text "<platform_label>" click
```

选择完成后：

```bash
agent-browser --session multipost snapshot -i -c
```

### 5) 上传素材（可选）

1. 先执行 `snapshot -i`，定位上传控件引用。
2. 上传文件：

```bash
agent-browser --session multipost upload @eN /absolute/path/a.png /absolute/path/b.png
```

3. 等待并校验：

```bash
agent-browser --session multipost wait --load networkidle
agent-browser --session multipost screenshot /tmp/multipost-media-check.png
```

### 6) 定时发布（可选）

仅当用户明确要求定时发布时执行：

1. 按页面文案定位并点击“定时”相关控件
2. 填写日期与时间
3. 提交前校验时区与时间是否正确

### 7) 预检与提交

提交前必须先产出预检截图：

```bash
agent-browser --session multipost screenshot /tmp/multipost-preflight.png
```

然后按模式执行：

- `mode=draft`：点击 `Save Draft` / `保存草稿`
- `mode=publish`：仅在用户明确确认后点击 `Publish` / `发布`

示例：

```bash
agent-browser --session multipost find text "Save Draft" click || \
agent-browser --session multipost find text "保存草稿" click
```

```bash
agent-browser --session multipost find text "Publish" click || \
agent-browser --session multipost find text "发布" click
```

### 8) 回传结果

返回以下信息：

- 最终 URL（`agent-browser --session multipost get url`）
- 实际动作（`draft` 或 `published`）
- 目标平台列表
- 截图路径（`/tmp/multipost-preflight.png` 与最终确认截图）

## 常见问题排查

- 找不到元素：重新 `snapshot -i` 并使用新引用。
- 页面语言变化：按参考表尝试中英文标签。
- 登录态过期：重新执行 `bootstrap-session.sh`。
- 检查页面 JS 错误：

```bash
agent-browser --session multipost errors
agent-browser --session multipost console
```
