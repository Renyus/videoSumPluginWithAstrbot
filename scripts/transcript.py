#!/usr/bin/env python3
"""
Video Transcript CLI - 从视频中提取字幕文本
用法: python -m scripts.transcript <video_url> [--json]
     python scripts/transcript.py <video_url> [--json]
"""

import asyncio
import json
import os
import sys


async def main():
    if len(sys.argv) < 2:
        print("Usage: transcript.py <video_url> [--json]", file=sys.stderr)
        print("", file=sys.stderr)
        print("Supported platforms:", file=sys.stderr)
        print("  - YouTube (youtube.com, youtu.be)", file=sys.stderr)
        print("  - Bilibili (bilibili.com, b23.tv)", file=sys.stderr)
        print("", file=sys.stderr)
        print("Options:", file=sys.stderr)
        print("  --json    Output as JSON", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    output_json = "--json" in sys.argv

    # 尝试导入 main.py 中的 TranscriptExtractor
    # 支持两种运行方式:
    # 1. python -m scripts.transcript (从插件根目录运行，使用包导入)
    # 2. python scripts/transcript.py (直接运行)
    TranscriptExtractor = None
    try:
        # 方式 1: 作为包模块运行 (python -m scripts.transcript)
        from main import TranscriptExtractor
    except ImportError:
        try:
            # 方式 2: 直接运行时，将插件根目录加入搜索路径
            plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if plugin_root not in sys.path:
                sys.path.append(plugin_root)  # append 而非 insert，避免覆盖优先级
            from main import TranscriptExtractor
        except ImportError:
            print(
                "Error: Cannot import TranscriptExtractor. "
                "Please run from the plugin root directory:\n"
                "  cd <plugin_dir> && python -m scripts.transcript <url>",
                file=sys.stderr,
            )
            sys.exit(1)

    # 读取环境变量中的 SESSDATA
    bili_sessdata = os.environ.get("BILIBILI_SESSDATA", "")
    extractor = TranscriptExtractor(bili_sessdata=bili_sessdata)
    try:
        result = await extractor.extract(url)
    finally:
        await extractor.close()

    if output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            if result.get("title"):
                print(f"# {result['title']}")
            print(f"# Platform: {result['platform']}")
            print(f"# Source: {result['source']}")
            if result["language"]:
                print(f"# Language: {result['language']}")
            print()
            print(result["transcript"])
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
