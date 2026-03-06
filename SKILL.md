---
name: video-summary
description: 视频内容总结技能 - 从 YouTube / Bilibili 视频中提取字幕文本，用于 AI 总结。支持自动/手动字幕、多语言字幕、yt-dlp 兜底。用法: /vsummary <视频URL>
---

# Video Summary

从视频中提取字幕/转录文本，让 AI 总结视频内容。

## 核心功能

- **YouTube 字幕提取**: 自动获取手动/自动生成字幕，支持中英日韩多语言
- **Bilibili CC 字幕提取**: 获取 B 站 CC 字幕（需视频有字幕）
- **yt-dlp 兜底**: 其他平台通过 yt-dlp 提取字幕
- **智能语言选择**: 优先中文 → 英文 → 日文 → 韩文

## 使用方式

### 聊天命令

```
/vsummary https://www.youtube.com/watch?v=dQw4w9WgXcQ
/vsummary https://www.bilibili.com/video/BV1xx411c7XW
```

### 命令行

```bash
python3 {baseDir}/scripts/transcript.py "https://youtube.com/watch?v=xxx"
python3 {baseDir}/scripts/transcript.py "https://bilibili.com/video/BVxxx" --json
```

## 依赖

- `youtube-transcript-api` — YouTube 字幕提取（核心）
- `aiohttp` — 异步 HTTP 请求
- `yt-dlp` — 通用兜底方案（可选）

```bash
pip install youtube-transcript-api aiohttp yt-dlp
```

## 支持的 URL 格式

| 平台 | 格式 |
|------|------|
| YouTube | `youtube.com/watch?v=xxx`, `youtu.be/xxx`, `youtube.com/shorts/xxx` |
| Bilibili | `bilibili.com/video/BVxxx`, `bilibili.com/video/avxxx`, `b23.tv/xxx` |

## 限制

- **无字幕 = 无法提取**: 本技能依赖视频字幕，没有字幕的视频无法处理
- **Bilibili 成功率较低**: B 站大部分视频没有 CC 字幕
- **字幕质量**: 自动生成字幕可能有错误，特别是专业术语
