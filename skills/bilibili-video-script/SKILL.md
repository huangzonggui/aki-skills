---
name: bilibili-video-script
description: Generate Bilibili-style short video scripts (30-60 seconds) based on AI/Tech news. Use when user wants to create short video scripts in the style of Bilibili tech news accounts like 新智元AIEra. Triggers on: video script generation, Bilibili content creation, short video outline, 30-second video script, tech news video.
---

# Bilibili 视频脚本生成

基于新智元AIEra等B站科技资讯账号风格的短视频脚本生成。

## 参考风格

请阅读 `references/xinzhiyuan_analysis.md` 了解详细的脚本公式和风格指南。

## 快速公式

### 标题公式
```
[数字/情绪词] + [核心事件] + [悬念/对比]
```
示例：
- "AMD豪掷6GW+1.6亿股！为什么Meta抢了头条？"
- "老黄封神！单季度681亿营收炸场"

### 脚本公式（30秒）
1. **开场 (5秒)**：抛出最大亮点/悬念
2. **正文 (20秒)**：核心事件 + 关键数据 + 原因分析
3. **结尾 (5秒)**：一句话观点 + 引导互动

### 脚本公式（60秒）
1. **开场 (5秒)**：热点切入 + 悬念
2. **背景 (10秒)**：事件详情 + 数据
3. **分析 (30秒)**：多角度解读 + 对比/案例
4. **收尾 (15秒)**：观点总结 + 行业展望

## 使用方法

1. **用户提供素材**：新闻链接、热点事件、产品发布等
2. **提取关键信息**：
   - 核心事件/产品
   - 关键数据（金额、用户数、百分比）
   - 涉及的公司/人物
   - 行业影响
3. **生成脚本**：按照上述公式生成
4. **输出格式**：使用 `templates/script_template.md` 格式输出

## 关键要素

必须包含：
- ✅ 核心热点事件/产品
- ✅ 至少1个具体数据
- ✅ 行业影响/意义
- ✅ 悬念或对比元素

标题技巧：
- ✅ 使用数字（金额、百分比）
- ✅ 热点人物/公司名称
- ✅ 悬念词（为什么？是什么？）

## 输出示例

参考 `references/example_scripts.md` 中的完整示例。

## 注意事项

- 时长控制在60-120秒
- 开头3秒必须抓住注意力
- 每10秒一个爆点
- 结尾给出观点/洞察而非简单总结
