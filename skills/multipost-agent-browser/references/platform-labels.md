# 平台标签映射

在 MultiPost 页面中优先用这些文案做首轮文本匹配。

| 平台 | 候选标签 |
|---|---|
| Weibo | `微博`, `Weibo` |
| Jike | `即刻`, `Jike` |
| X | `X`, `Twitter` |
| Xiaohongshu | `小红书`, `Xiaohongshu`, `RED` |
| Zhihu | `知乎` |
| WeChat Official Account | `微信公众号`, `WeChat` |
| Douyin | `抖音`, `Douyin`, `TikTok` |
| Video Account | `视频号` |
| Kuaishou | `快手` |
| Douban | `豆瓣` |
| Toutiao | `微头条`, `头条`, `Toutiao` |
| Baijiahao | `百家号` |
| Bilibili | `B站`, `哔哩哔哩`, `Bilibili` |
| Xueqiu | `雪球` |
| Dedao | `得到` |
| Maimai | `脉脉` |
| Juejin | `掘金`, `沸点` |
| Feishu/WeCom/DingTalk | `飞书`, `企微`, `企业微信`, `钉钉` |
| LinkedIn | `LinkedIn` |
| Facebook | `Facebook` |
| Instagram | `Instagram` |
| Threads | `Threads` |
| Reddit | `Reddit` |
| Bluesky | `Bsky`, `Bluesky` |
| Substack | `Substack` |

若未匹配到标签：

1. 运行 `agent-browser --session multipost snapshot -i -c`
2. 用 `agent-browser find text "<keyword>"` 在附近文案中查找
3. 回退到 `snapshot` 输出中的 `@e*` 引用
