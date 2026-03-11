---
name: aki-obsidian-brain
description: Aki 的个人 Obsidian 总控技能。以 /Users/aki/Documents/ObsidianVaults/Aki数字资产 为唯一中枢，统一记录与查询任务、灵感、选题、个人资料、创作积累、多媒体索引。适用于“记任务/记灵感/记选题/随手记/todo/图度/待办还有哪些/最重要待办/可写选题/追溯选题”等自然语言请求，并复用 obsidian-cli 的命令能力。
---

# Aki Obsidian Brain

这是 Aki 的个人总控技能。它负责：
- 解析自然语言一句话意图。
- 把内容按固定规范写入 Obsidian Vault。
- 查询任务与选题并按约定排序返回。
- 在需要时给出 `obsidian-cli` 的打开/搜索命令。

## 默认中枢

- Vault 路径：`/Users/aki/Documents/ObsidianVaults/Aki数字资产`
- Vault 名：`Aki数字资产`
- 内容系统目录：`00-Aki第二大脑/`

配置文件：`config.json`
写入前规则源：`00-Aki第二大脑/工具与服务/Obsidian智能写入规则.md`

## 触发场景

- 记录类：`记任务`、`记待办`、`todo`、`图度`、`记灵感`、`记想法`、`随手记`、`记选题`
- 查询类：`待办还有哪些`、`还有哪些没做`、`最重要待办`、`最重要的todo`、`可写选题`、`还有哪些话题没写`
- 追溯类：`追溯选题 xxx`

## 写入规范

- 任务清单：`00-Aki第二大脑/任务清单.md`
  - `- [ ] [Q1] 任务内容｜记录: YYYY-MM-DD HH:MM｜标签: #todo #q1`
- 灵感池：`00-Aki第二大脑/灵感池.md`
  - `- [ ] 灵感内容｜记录: ...｜标签: #idea`
- 选题库：`00-Aki第二大脑/选题库.md`
  - `- [ ] 话题标题｜记录: ...｜标签: #topic #ai-tech｜引用: [原文链接](URL)`
  - 可选补充：`｜动机: ...`
- 不写入任何 `来源: 飞书/OpenClaw` 之类的输入端标记。
- 不创建 `移动采集_*` 或单独收件箱中转文件。

## 任务四象限映射

- 重要且紧急 -> `Q1`
- 重要不紧急 -> `Q2`
- 紧急不重要 -> `Q3`
- 不紧急不重要 -> `Q4`
- 未提供时默认：`Q2`

## 去重与更新

选题库按“标题精确匹配”去重。
- 已存在同标题：不新增重复条目。
- 新请求带来源链接：补到原条目。
- 新请求带动机：补到原条目。

## 查询输出规则

- `还有哪些没做`：按 `Q1 -> Q2 -> Q3 -> Q4` 分组。
- `最重要的待办`：优先 `Q1`，其次 `Q2`，默认前 10 条。
- `还有哪些话题没写`：输出选题库未勾选条目。
- `追溯选题 X`：返回标题、记录时间、动机、来源。

## 低置信度处理

如果输入无法明确路由到任务/灵感/选题/查询，必须先确认，不要盲写。
第一版不要自动猜测“观点”或“个人生活”目标文件。

## 脚本入口

使用脚本执行统一解析与读写：

```bash
python3 ./scripts/brain_router.py --input "记个选题：OpenClaw 龙虾大热话题 来源 https://example.com"
```

可选参数：

```bash
python3 ./scripts/brain_router.py --config ./config.json --input "还有哪些没做"
python3 ./scripts/brain_router.py --init-only
```

## 与 obsidian-cli 协作

本技能负责路径、格式、规则；`obsidian-cli` 负责 vault 内操作命令参考。

常用命令模板：

```bash
obsidian vault="Aki数字资产" search query="OpenClaw"
obsidian vault="Aki数字资产" read path="00-Aki第二大脑/选题库.md"
obsidian vault="Aki数字资产" open path="00-Aki第二大脑/任务清单.md"
```

如果系统提示 CLI 未启用：
- 打开 Obsidian -> `Settings > General > Advanced` -> 开启 `Command line interface`。

## 参考文档

- `references/templates.md`
- `references/parsing-rules.md`

## 日常调用提示词

- `记个任务：今晚发布稿子，重要且紧急`
- `我有个todo：研究露营气垫，重要不紧急`
- `记个灵感：OpenClaw 可以做 5 集系列`
- `记个选题：OpenClaw 龙虾大热话题 来源 https://... 动机: ...`
- `还有哪些没做`
- `最重要的待办`
- `还有哪些话题没写`
- `追溯选题 OpenClaw 龙虾大热话题`
