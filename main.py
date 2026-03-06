#!/usr/bin/env python3
"""
AstrBot Video Summary Plugin
视频内容总结插件 - 从视频中提取字幕/转录文本
支持平台: YouTube, Bilibili
兜底方案: yt-dlp
"""

import asyncio
import json
import os
import re
import urllib.parse
from typing import Optional

import aiohttp
from astrbot.api import logger
from astrbot.api.all import (
    AstrMessageEvent,
    MessageEventResult,
    Star,
    register,
)
from astrbot.api.event import filter
from astrbot.api.star import Context

# ==================== 配置 ====================
REQUEST_TIMEOUT = 30
MAX_TRANSCRIPT_LENGTH = 15000  # 字幕文本最大长度（字符），防止过长

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# YouTube 字幕语言偏好（按优先级）
YOUTUBE_LANG_PRIORITY = ["zh-Hans", "zh-CN", "zh", "zh-Hant", "zh-TW", "en", "ja", "ko"]

# Bilibili API
BILIBILI_VIDEO_INFO_API = "https://api.bilibili.com/x/web-interface/view"
BILIBILI_PLAYER_API = "https://api.bilibili.com/x/player/wbi/v2"

# Bilibili SESSDATA Cookie（从环境变量读取，用于获取 AI 生成字幕）
# 设置方式: export BILIBILI_SESSDATA="你的SESSDATA值"
BILIBILI_SESSDATA = os.environ.get("BILIBILI_SESSDATA", "")


# ==================== URL 解析 ====================


def parse_video_url(url: str) -> tuple[str, str]:
    """
    解析视频 URL，返回 (platform, video_id)

    支持格式:
    - YouTube: youtube.com/watch?v=xxx, youtu.be/xxx, youtube.com/shorts/xxx
    - Bilibili: bilibili.com/video/BVxxx, b23.tv/xxx

    Returns:
        ("youtube", "dQw4w9WgXcQ") 或 ("bilibili", "BV1xx411c7XW") 或 ("unknown", url)
    """
    url = url.strip()

    # YouTube
    yt_patterns = [
        r"(?:youtube\.com/watch\?.*[?&]v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in yt_patterns:
        match = re.search(pattern, url)
        if match:
            return "youtube", match.group(1)

    # Bilibili
    bili_patterns = [
        r"bilibili\.com/video/(BV[a-zA-Z0-9]+)",
        r"bilibili\.com/video/av(\d+)",
        r"b23\.tv/([a-zA-Z0-9]+)",
    ]
    for pattern in bili_patterns:
        match = re.search(pattern, url)
        if match:
            return "bilibili", match.group(1)

    return "unknown", url


# ==================== 字幕提取 ====================


class TranscriptExtractor:
    """视频字幕/转录提取器"""

    def __init__(self, bili_sessdata: str = ""):
        self._session: Optional[aiohttp.ClientSession] = None
        self._bili_sessdata = bili_sessdata or BILIBILI_SESSDATA

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                headers={"User-Agent": DEFAULT_USER_AGENT},
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def extract(self, url: str) -> dict:
        """
        从视频 URL 提取字幕文本

        Returns:
            {
                "success": bool,
                "platform": str,
                "video_id": str,
                "title": str,
                "transcript": str,
                "language": str,
                "source": str,       # "subtitle" / "auto-generated" / "yt-dlp"
                "error": str | None,
            }
        """
        platform, video_id = parse_video_url(url)

        if platform == "youtube":
            return await self._extract_youtube(video_id)
        elif platform == "bilibili":
            return await self._extract_bilibili(video_id)
        else:
            # 尝试 yt-dlp 兜底
            return await self._extract_ytdlp(url)

    # -------------------- YouTube --------------------

    async def _extract_youtube(self, video_id: str) -> dict:
        """从 YouTube 提取字幕（使用 youtube-transcript-api）"""
        base_result = {
            "platform": "youtube",
            "video_id": video_id,
            "title": "",
            "language": "",
            "source": "",
        }

        try:
            # 尝试使用 youtube-transcript-api
            from youtube_transcript_api import YouTubeTranscriptApi

            ytt_api = YouTubeTranscriptApi()

            # 尝试获取字幕列表（同步操作，放入线程池）
            transcript_list = await asyncio.to_thread(ytt_api.list, video_id)

            # 按语言偏好选择字幕
            transcript = None
            source = "subtitle"

            # 先尝试手动字幕
            for lang in YOUTUBE_LANG_PRIORITY:
                for t in transcript_list:
                    if t.language_code.startswith(lang) and not t.is_generated:
                        transcript = t
                        break
                if transcript:
                    break

            # 再尝试自动生成字幕
            if not transcript:
                for lang in YOUTUBE_LANG_PRIORITY:
                    for t in transcript_list:
                        if t.language_code.startswith(lang) and t.is_generated:
                            transcript = t
                            source = "auto-generated"
                            break
                    if transcript:
                        break

            # 如果还没找到，取第一个可用的
            if not transcript:
                for t in transcript_list:
                    transcript = t
                    source = "auto-generated" if t.is_generated else "subtitle"
                    break

            if not transcript:
                return {
                    **base_result,
                    "success": False,
                    "transcript": "",
                    "error": "该视频没有可用的字幕",
                }

            # 获取字幕内容（同步操作，放入线程池）
            fetched = await asyncio.to_thread(transcript.fetch)
            lines = []
            for snippet in fetched:
                text = snippet.text.strip()
                if text:
                    lines.append(text)

            transcript_text = "\n".join(lines)

            # 截断过长文本
            if len(transcript_text) > MAX_TRANSCRIPT_LENGTH:
                transcript_text = (
                    transcript_text[:MAX_TRANSCRIPT_LENGTH]
                    + f"\n\n> ... 字幕已截断 (超过 {MAX_TRANSCRIPT_LENGTH} 字符)"
                )

            return {
                **base_result,
                "success": True,
                "transcript": transcript_text,
                "language": transcript.language_code,
                "source": source,
                "error": None,
            }

        except ImportError:
            # youtube-transcript-api 未安装，尝试 yt-dlp 兜底
            return await self._extract_ytdlp(
                f"https://www.youtube.com/watch?v={video_id}"
            )
        except Exception as e:
            error_msg = str(e)
            # 常见错误友好提示
            if "Subtitles are disabled" in error_msg:
                error_msg = "该视频已禁用字幕"
            elif "Video unavailable" in error_msg:
                error_msg = "视频不可用（可能是私密视频或已删除）"
            elif "Too Many Requests" in error_msg:
                error_msg = "请求过于频繁，请稍后再试"

            logger.error(f"YouTube 字幕提取失败: {error_msg}")
            return {
                **base_result,
                "success": False,
                "transcript": "",
                "error": f"YouTube 字幕提取失败: {error_msg}",
            }

    # -------------------- Bilibili --------------------

    async def _extract_bilibili(self, video_id: str) -> dict:
        """从 Bilibili 提取 CC 字幕"""
        base_result = {
            "platform": "bilibili",
            "video_id": video_id,
            "title": "",
            "language": "",
            "source": "subtitle",
        }

        session = await self._get_session()
        # 构建 Bilibili 请求用的 Cookie
        bili_cookies = None
        if self._bili_sessdata:
            bili_cookies = {"SESSDATA": self._bili_sessdata}

        try:
            # 1. 获取视频基本信息 (bvid → aid + cid)
            params = {}
            if video_id.startswith("BV"):
                params["bvid"] = video_id
            elif video_id.startswith("av") or video_id.isdigit():
                params["aid"] = video_id.replace("av", "")
            else:
                # 可能是 b23.tv 短链，先解析
                resolved = await self._resolve_b23(video_id)
                if resolved:
                    _, video_id = parse_video_url(resolved)
                    if video_id.startswith("BV"):
                        params["bvid"] = video_id
                    else:
                        return {
                            **base_result,
                            "success": False,
                            "transcript": "",
                            "error": "无法解析 B 站短链接",
                        }
                else:
                    return {
                        **base_result,
                        "success": False,
                        "transcript": "",
                        "error": "无法解析 B 站短链接",
                    }

            async with session.get(
                BILIBILI_VIDEO_INFO_API, params=params, cookies=bili_cookies
            ) as resp:
                if resp.status != 200:
                    return {
                        **base_result,
                        "success": False,
                        "transcript": "",
                        "error": f"获取视频信息失败: HTTP {resp.status}",
                    }
                data = await resp.json()

            if data.get("code") != 0:
                return {
                    **base_result,
                    "success": False,
                    "transcript": "",
                    "error": f"获取视频信息失败: {data.get('message', '未知错误')}",
                }

            video_data = data["data"]
            aid = video_data["aid"]
            cid = video_data["cid"]
            title = video_data.get("title", "")
            base_result["title"] = title

            # 2. 获取字幕信息
            player_params = {"aid": aid, "cid": cid}
            async with session.get(
                BILIBILI_PLAYER_API, params=player_params, cookies=bili_cookies
            ) as resp:
                if resp.status != 200:
                    return {
                        **base_result,
                        "success": False,
                        "transcript": "",
                        "error": f"获取字幕信息失败: HTTP {resp.status}",
                    }
                player_data = await resp.json()

            if player_data.get("code") != 0:
                return {
                    **base_result,
                    "success": False,
                    "transcript": "",
                    "error": "获取字幕信息失败",
                }

            # 提取字幕 URL
            subtitle_info = (
                player_data.get("data", {}).get("subtitle", {}).get("subtitles", [])
            )

            if not subtitle_info:
                if not self._bili_sessdata:
                    hint = (
                        "该视频没有公开字幕。"
                        "设置 BILIBILI_SESSDATA 环境变量后可获取 AI 生成字幕。"
                        "获取方式: 浏览器登录B站 → F12 → Application → Cookies → SESSDATA"
                    )
                else:
                    hint = "该视频没有可用字幕（已使用登录 Cookie，但仍未找到字幕）"
                return {
                    **base_result,
                    "success": False,
                    "transcript": "",
                    "error": hint,
                }

            # 选择字幕：优先 AI 生成的中文，其次手动中文，最后取第一个
            selected = subtitle_info[0]
            for sub in subtitle_info:
                lang = sub.get("lan", "")
                if lang.startswith("zh"):
                    selected = sub
                    break

            # 判断是 AI 字幕还是创作者上传
            sub_type = selected.get("type", 0)
            if sub_type == 1:
                base_result["source"] = "ai-generated"
            else:
                base_result["source"] = "subtitle"

            subtitle_url = selected.get("subtitle_url", "")
            if subtitle_url.startswith("//"):
                subtitle_url = "https:" + subtitle_url

            base_result["language"] = selected.get("lan", "unknown")

            # 3. 下载字幕内容
            async with session.get(subtitle_url) as resp:
                if resp.status != 200:
                    return {
                        **base_result,
                        "success": False,
                        "transcript": "",
                        "error": f"下载字幕失败: HTTP {resp.status}",
                    }
                subtitle_data = await resp.json()

            # 解析字幕 JSON (Bilibili 格式: {"body": [{"content": "...", "from": 0.0, "to": 1.0}]})
            body = subtitle_data.get("body", [])
            if not body:
                return {
                    **base_result,
                    "success": False,
                    "transcript": "",
                    "error": "字幕内容为空",
                }

            lines = [item.get("content", "").strip() for item in body if item.get("content")]
            transcript_text = "\n".join(lines)

            if len(transcript_text) > MAX_TRANSCRIPT_LENGTH:
                transcript_text = (
                    transcript_text[:MAX_TRANSCRIPT_LENGTH]
                    + f"\n\n> ... 字幕已截断 (超过 {MAX_TRANSCRIPT_LENGTH} 字符)"
                )

            return {
                **base_result,
                "success": True,
                "transcript": transcript_text,
                "error": None,
            }

        except Exception as e:
            logger.error(f"Bilibili 字幕提取失败: {type(e).__name__}: {e}")
            return {
                **base_result,
                "success": False,
                "transcript": "",
                "error": f"Bilibili 字幕提取失败: {type(e).__name__}: {e}",
            }

    async def _resolve_b23(self, short_id: str) -> Optional[str]:
        """解析 b23.tv 短链接"""
        session = await self._get_session()
        try:
            async with session.get(
                f"https://b23.tv/{short_id}", allow_redirects=False
            ) as resp:
                if resp.status in (301, 302):
                    return resp.headers.get("Location")
        except Exception:
            logger.warning(f"b23.tv 短链接解析失败: {short_id}")
            pass
        return None

    # -------------------- yt-dlp 兜底 --------------------

    async def _extract_ytdlp(self, url: str) -> dict:
        """使用 yt-dlp 提取字幕（通用兜底方案）"""
        base_result = {
            "platform": "unknown",
            "video_id": url,
            "title": "",
            "language": "",
            "source": "yt-dlp",
        }

        try:
            import yt_dlp
        except ImportError:
            return {
                **base_result,
                "success": False,
                "transcript": "",
                "error": "yt-dlp 未安装。请运行: pip install yt-dlp",
            }

        try:
            # 在线程中运行 yt-dlp（它是同步的）
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._ytdlp_extract_sync, url)
            return {**base_result, **result}
        except Exception as e:
            return {
                **base_result,
                "success": False,
                "transcript": "",
                "error": f"yt-dlp 提取失败: {type(e).__name__}: {e}",
            }

    @staticmethod
    def _ytdlp_extract_sync(url: str) -> dict:
        """yt-dlp 同步提取字幕"""
        import tempfile
        import glob
        import os
        import yt_dlp

        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["zh-Hans", "zh-CN", "zh", "en", "ja"],
                "subtitlesformat": "json3",
                "outtmpl": os.path.join(tmpdir, "%(id)s"),
                "quiet": True,
                "no_warnings": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", "")

            # 查找生成的字幕文件
            sub_files = glob.glob(os.path.join(tmpdir, "*.json3"))
            if not sub_files:
                # 尝试其他格式
                sub_files = glob.glob(os.path.join(tmpdir, "*.vtt"))
                if not sub_files:
                    sub_files = glob.glob(os.path.join(tmpdir, "*.srt"))

            if not sub_files:
                return {
                    "success": False,
                    "title": title,
                    "transcript": "",
                    "error": "yt-dlp 未能提取到字幕",
                }

            # 读取字幕
            sub_file = sub_files[0]
            lang = ""

            # 从文件名提取语言
            basename = os.path.basename(sub_file)
            parts = basename.rsplit(".", 2)
            if len(parts) >= 3:
                lang = parts[-2]

            with open(sub_file, "r", encoding="utf-8") as f:
                content = f.read()

            # 尝试解析 json3 格式
            if sub_file.endswith(".json3"):
                try:
                    data = json.loads(content)
                    events = data.get("events", [])
                    lines = []
                    for event in events:
                        segs = event.get("segs", [])
                        text = "".join(s.get("utf8", "") for s in segs).strip()
                        if text and text != "\n":
                            lines.append(text)
                    transcript_text = "\n".join(lines)
                except json.JSONDecodeError:
                    transcript_text = content
            else:
                # VTT/SRT: 简单提取文本行
                lines = []
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.isdigit() or "-->" in line or line.startswith("WEBVTT"):
                        continue
                    # 去除 HTML 标签
                    line = re.sub(r"<[^>]+>", "", line)
                    if line:
                        lines.append(line)
                transcript_text = "\n".join(lines)

            if len(transcript_text) > MAX_TRANSCRIPT_LENGTH:
                transcript_text = (
                    transcript_text[:MAX_TRANSCRIPT_LENGTH]
                    + f"\n\n> ... 字幕已截断 (超过 {MAX_TRANSCRIPT_LENGTH} 字符)"
                )

            return {
                "success": True,
                "title": title,
                "transcript": transcript_text,
                "language": lang,
                "error": None,
            }


# ==================== AstrBot 插件 ====================


@register("astrbot_plugin_video_summary", "视频内容总结", "一个可以提取B站，油管视频的cc字幕或ai字幕（需cookie）并总结视频内容最后给出观点分析的插件", "1.0.0")
class VideoSummaryPlugin(Star):
    """AstrBot 视频内容总结插件"""

    def __init__(self, context: Context, config=None):
        super().__init__(context)
        # 优先从 AstrBot 插件配置读取，其次从环境变量读取
        bili_sessdata = ""
        if config:
            bili_sessdata = config.get("bilibili_sessdata", "")
        if not bili_sessdata:
            bili_sessdata = os.environ.get("BILIBILI_SESSDATA", "")
        self.extractor = TranscriptExtractor(bili_sessdata=bili_sessdata)

    async def terminate(self):
        """插件卸载时清理资源"""
        await self.extractor.close()

    @filter.command("vsummary")
    async def handle_vsummary(self, event: AstrMessageEvent):
        """
        处理 /vsummary 命令
        用法: /vsummary <视频URL>
        """
        message = event.message_str.strip()
        parts = message.split(None, 1)

        if len(parts) < 2:
            yield event.plain_result(
                "视频内容总结\n\n"
                "用法: `/vsummary <视频URL>`\n\n"
                "支持平台:\n"
                "• YouTube (youtube.com, youtu.be)\n"
                "• Bilibili (bilibili.com, b23.tv)\n\n"
                "示例:\n"
                "• `/vsummary https://www.youtube.com/watch?v=dQw4w9WgXcQ`\n"
                "• `/vsummary https://www.bilibili.com/video/BV1xx411c7XW`"
            )
            return

        url = parts[1].strip()

        # 补全 scheme
        if not url.startswith(("http://", "https://")):
            url = "https://" + url



        result = await self.extractor.extract(url)

        if not result["success"]:
            yield event.plain_result(f"提取失败: {result['error']}")
            return

        transcript = result["transcript"]
        title = result.get("title") or "未知标题"

        source_label = {
            "subtitle": "人工字幕",
            "auto-generated": "自动生成字幕",
            "ai-generated": "B站 AI 字幕",
            "yt-dlp": "yt-dlp 提取",
        }.get(result["source"], result["source"])



        # 调用 LLM 进行总结
        # 获取当前会话信息，以便准确获取其对应的人格
        conv_mgr = self.context.conversation_manager
        umo = event.unified_msg_origin
        cid = await conv_mgr.get_curr_conversation_id(umo)
        conversation = await conv_mgr.get_conversation(umo, cid) if cid else None
        conversation_persona_id = conversation.persona_id if conversation else None
        
        cfg = self.context.get_config(umo=umo).get("provider_settings", {})

        # 获取当前生效的人格设定
        (
            _,
            persona,
            _,
            _,
        ) = await self.context.persona_manager.resolve_selected_persona(
            umo=umo,
            conversation_persona_id=conversation_persona_id,
            platform_name=event.get_platform_name(),
            provider_settings=cfg,
        )
        
        persona_prompt = persona.get("prompt", "") if persona else ""

        # 视频分析专项指令
        # 视频分析专项指令
        video_task = (
            "用户给你发了一段视频的字幕文本，请你看完后告诉用户视频讲了什么，并发表你的看法。\n"
            "要求：\n"
            "1. 拒绝机械的格式（不要用“视频概括”、“关键要点”、“个人观点”这种死板的标题）。\n"
            "2. 把内容总结和你的吐槽/观点自然地融合在一起，就像和朋友聊天一样。\n"
            "3. 保持你的人格设定（如果有），语气要生动、有个性。\n"
            "4. 回答要有重点，不要像报流水账一样复述所有废话。"
        )

        # 合并人格设定与任务指令
        if persona_prompt:
            system_prompt = f"{persona_prompt}\n\n---\n\n{video_task}"
        else:
            system_prompt = video_task

        prompt = f"视频标题: {title}\n\n以下是视频字幕内容:\n\n{transcript}"

        try:
            provider_id = await self.context.get_current_chat_provider_id(
                umo=event.unified_msg_origin
            )
            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                system_prompt=system_prompt,
            )

            # 构建最终回复
            header = f"**{title}**\n"
            header += f"字幕来源: {source_label}"
            if result["language"]:
                header += f" ({result['language']})"
            header += "\n\n---\n\n"

            # 提取 LLM 回复文本
            ai_summary = ""
            if llm_resp and llm_resp.completion_text:
                ai_summary = llm_resp.completion_text
            else:
                ai_summary = "AI 未能生成总结内容。"

            yield event.plain_result(header + ai_summary)

        except Exception as e:
            # LLM 调用失败，降级返回原始字幕
            yield event.plain_result(
                f"AI 总结失败 ({type(e).__name__}: {e})，以下是原始字幕:\n\n"
                f"{transcript[:3000]}"
            )

