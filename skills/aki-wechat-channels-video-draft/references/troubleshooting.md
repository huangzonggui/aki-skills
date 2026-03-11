# Troubleshooting

## 1) 卡在登录页

- 现象：脚本日志持续提示需要扫码登录。
- 处理：
  - 不要加 `--headless`，保证可以看到浏览器窗口。
  - 在窗口里用微信扫码登录后再等待脚本继续。
  - 如登录态经常失效，显式指定稳定目录：

```bash
--profile-name zimeiti-publisher
```

## 2) 找不到视频上传控件

- 现象：报错 `Unable to locate video file input on page`。
- 处理：
  - 确认页面是 `channels.weixin.qq.com/platform/post/create`。
  - 手动刷新一次后重跑。
  - 若微信改版，更新 `UPLOAD_ENTRY_SELECTORS` 与 `findVideoInput` 的 `accept` 判定。

## 3) “保存草稿”按钮长时间不可点击

- 现象：报错 `"保存草稿" button not ready...`。
- 常见原因：
  - 视频上传或转码尚未完成；
  - 视频编码不兼容，需要转码后再上传。
- 处理：
  - 增大等待时间：`--upload-timeout-sec 1800`
  - 先用本地播放器确认视频可正常播放，再重试。

## 4) 未识别标题/描述输入框

- 现象：日志提示“标题输入框未识别”或“描述输入框未识别”。
- 处理：
  - 页面改版后，补充 `TITLE_SELECTORS` / `DESCRIPTION_SELECTORS`。
  - 先保证草稿保存链路可用，再按当前页面结构调整表单定位。

## 5) 报 `ProcessSingleton`（配置目录被占用）

- 现象：使用系统 Chrome profile 时，启动失败并提示 `ProcessSingleton`。
- 处理：
  - 关闭所有 Chrome 窗口后重试；
  - 或改用独立目录：`--profile-name zimeiti-publisher`（或显式 `--profile-dir`）。

## 6) 标题超过 16 字限制

- 现象：视频号标题输入后，页面提示标题超过 16 字，导致标题不符合发布要求。
- 当前状态：
  - 脚本会按传入 `--title` 或文件名填写标题；
  - 目前没有针对视频号 16 字上限做自动截断、压缩改写或回退短标题策略。
- 下次迭代建议：
  - 在填写前先做长度校验；
  - 超限时优先使用用户显式提供的短标题；
  - 若未提供，则自动生成/截断到 16 字以内，并在日志里输出原始标题与最终标题。
- 英文一个字母就算一个，例如这个是17个字：九个强烈推荐小龙虾技能skills 而这个是16个字：九个强烈推荐小龙虾技能skill
