#!/usr/bin/env python3
"""
Video Transcript CLI - 从视频中提取字幕文本
用法: python transcript.py <video_url> [--json]
"""

import asyncio
import json
import sys
import os

# 将父目录加入 path，复用 main.py 中的 TranscriptExtractor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    if len(sys.argv) < 2:
        print("Usage: transcript.py <video_url> [--json]", file=sys.stderr)
        print("", file=sys.stderr)
        print("Supported platforms:", file=sys.stderr)
        print("  • YouTube (youtube.com, youtu.be)", file=sys.stderr)
        print("  • Bilibili (bilibili.com, b23.tv)", file=sys.stderr)
        print("", file=sys.stderr)
        print("Options:", file=sys.stderr)
        print("  --json    Output as JSON", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    output_json = "--json" in sys.argv

    # 尝试从 main.py 导入，如果失败则使用独立实现
    try:
        from main import TranscriptExtractor
    except ImportError:
        print(
            "Error: Cannot import TranscriptExtractor. "
            "Please run from the plugin directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    extractor = TranscriptExtractor()
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
