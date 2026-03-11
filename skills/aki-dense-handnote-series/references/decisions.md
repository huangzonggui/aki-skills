# Long-term Decisions

## 2026-03-05 OpenClaw 案例驱动改造

### 触发案例

- 话题根目录：`/Users/aki/Downloads/Browsers/自媒体/1. AI个人IP话题/11. 00-20260304-2141-OpenClaw龙虾大热：底层生态改写与安全裸奔`
- 核心稿：`/Users/aki/Downloads/Browsers/自媒体/1. AI个人IP话题/11. 00-20260304-2141-OpenClaw龙虾大热：底层生态改写与安全裸奔/mp_weixin/article/core_note.md`
- 复盘结论：旧逻辑 `max_chars=1200`，chunk 约 1056，导致系列图仅 1 张；并且 `series_01_prompt` 与 `cover_prompt` 内容高度重叠。

### 锁定产品决策（不可回退）

1. 图像链路改为单一技能调用：pipeline 只调 `generate_handnote_bundle.py`。
2. 内容页口径固定为 2-4 张（不含封面）。
3. 结尾页策略默认 `adaptive`，仅在有明确总结/CTA 时生成。
4. 逻辑识别采用 `hybrid`：规则优先，LLM 兜底。
5. 封面/系列强差异约束：系列页禁止封面化单中心超大标题，必须信息结构化（分区/步骤/对比）。

### 实施约束

1. 输出目录契约保持不变：
   - `images/cover/cover_01.png`
   - `images/series/*.png`
   - `prompts/cover_prompt.md`
   - `prompts/series_XX_prompt.md`
   - `images/series/outline.md`
2. 双平台（公众号/小红书）使用同一拆分与生成策略，不做分叉逻辑。
3. 在 `logic-mode=hybrid|rule` 下仍需保证内容页不低于 2；不得静默退化为 1 页。

### 后续观察指标

1. 每篇平均内容页数（仅内容页，不含封面）。
2. “封面与系列图过于相似”的投诉次数（每周）。
3. 触发 LLM 兜底占比（`fallback_used=true` 的比例）。
