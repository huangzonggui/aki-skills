# Aki Obsidian Brain

在 OpenClaw 工作区中使用这项技能处理 Aki 的 Obsidian 写入与查询。

## 什么时候用

- `记个任务`
- `记个待办`
- `todo`
- `图度`
- `记个灵感`
- `记个想法`
- `随手记`
- `记个选题`
- `还有哪些没做`
- `最重要的待办`
- `可写选题`
- `追溯选题 xxx`

## 固定流程

1. 先读取：
   `/srv/aki/obsidian/Aki数字资产/00-Aki第二大脑/工具与服务/Obsidian智能写入规则.md`
2. 不要直接编辑 Markdown。
3. 统一调用：

```bash
/root/.openclaw/workspace/scripts/run_obsidian_brain.sh --input "原始用户输入"
```

4. 如果脚本返回 `need_confirmation`，只追问一句最短澄清。
5. 如果脚本返回写入或查询结果，简短回复结果，不要写输入来源。

## 约束

- 只写入 `任务清单.md`、`灵感池.md`、`选题库.md`
- 不创建 `移动采集_*`
- 不创建单独收件箱
- 不写 `飞书`、`OpenClaw` 等来源标识
- 第一版不要自动猜测“观点”或“个人生活”
