# video-summary

AstrBot 视频内容总结插件 — 提取视频字幕，AI 自动分析总结。

## 功能

- 支持 **YouTube** 和 **Bilibili** 视频
- 自动提取字幕（手动字幕 / 自动生成字幕 / B站 AI 字幕）
- 完美融合 AstrBot 人格设定，AI 的总结语气会根据你配置的人格自动调整
- 调用 LLM 对字幕内容进行分析总结，输出观点
- 其他平台通过 yt-dlp 兜底提取

## 使用

```
/vsummary <视频URL>
```

示例：
```
/vsummary https://www.youtube.com/watch?v=dQw4w9WgXcQ
/vsummary https://www.bilibili.com/video/BV1F1PwzNE99
/vsummary https://b23.tv/xxxxx
```

## 安装

1. 将插件目录放入 AstrBot 的 `data/plugins/`
2. 安装依赖：
   ```bash
   pip install youtube-transcript-api aiohttp
   # 可选，用于其他平台兜底
   pip install yt-dlp
   ```
3. 重启 AstrBot

## 配置

在 AstrBot 管理面板 → 插件配置 → 视频内容总结 中填写：

| 配置项 | 说明 |
|--------|------|
| `bilibili_sessdata` | B站登录 Cookie，用于获取 AI 生成字幕。不填则只能获取创作者上传的 CC 字幕。 |

### 获取 SESSDATA

1. 浏览器登录 bilibili.com
2. F12 → Application → Cookies → `https://www.bilibili.com`
3. 找到 `SESSDATA`，复制其值粘贴到插件配置中

> SESSDATA 有效期约 1 个月，过期后需重新获取。

## 支持的 URL 格式

| 平台 | 格式 |
|------|------|
| YouTube | `youtube.com/watch?v=xxx`、`youtu.be/xxx`、`youtube.com/shorts/xxx` |
| Bilibili | `bilibili.com/video/BVxxx`、`bilibili.com/video/avxxx`、`b23.tv/xxx` |

## 字幕语言优先级

中文(简) → 中文(繁) → 英文 → 日文 → 韩文

## 限制

- 依赖字幕，无字幕的视频无法处理
- B站大部分视频无公开 CC 字幕，需配置 SESSDATA 获取 AI 字幕
- 自动生成字幕可能存在识别错误

## 文件结构

```
video_summary_1_0_0/
├── main.py              # AstrBot 插件主文件
├── scripts/
│   └── transcript.py    # CLI 字幕提取工具
├── _conf_schema.json    # 插件配置定义
├── metadata.yaml        # AstrBot 插件元数据
├── SKILL.md             # Skill 说明
└── README.md
```

## CLI 使用（独立于 AstrBot）

```bash
python scripts/transcript.py "https://youtube.com/watch?v=xxx"
python scripts/transcript.py "https://bilibili.com/video/BVxxx" --json
```
