#!/usr/bin/env python3
"""
下载 YouTube 视频和字幕
使用 yt-dlp 下载视频（最高 1080p）和英文字幕
"""

import sys
import json
import os
import re
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    print("❌ Error: yt-dlp not installed")
    print("Please install: pip install yt-dlp")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from utils import (
    validate_url,
    sanitize_filename,
    format_file_size,
    get_video_duration_display,
    ensure_directory
)

def _parse_cookies_from_browser(spec: str):
    """
    Parse cookies-from-browser spec into yt-dlp tuple form.
    Format: BROWSER[+KEYRING][:PROFILE][::CONTAINER]
    Example: "chrome", "chrome:Default", "chrome+KEYRING:Profile 1", "firefox::container"
    """
    if not spec:
        return None
    mobj = re.fullmatch(r'''(?x)
        (?P<name>[^+:]+)
        (?:\s*\+\s*(?P<keyring>[^:]+))?
        (?:\s*:\s*(?!:)(?P<profile>.+?))?
        (?:\s*::\s*(?P<container>.+))?
    ''', spec)
    if mobj is None:
        raise ValueError(f'invalid cookies-from-browser spec: {spec}')
    browser_name, keyring, profile, container = mobj.group('name', 'keyring', 'profile', 'container')
    return (browser_name.lower(), profile, keyring.upper() if keyring else None, container)


def download_video(url: str, output_dir: str = None) -> dict:
    """
    下载 YouTube 视频和字幕

    Args:
        url: YouTube URL
        output_dir: 输出目录，默认为当前目录

    Returns:
        dict: {
            'video_path': 视频文件路径,
            'subtitle_path': 字幕文件路径,
            'title': 视频标题,
            'duration': 视频时长（秒）,
            'file_size': 文件大小（字节）
        }

    Raises:
        ValueError: 无效的 URL
        Exception: 下载失败
    """
    # 验证 URL
    if not validate_url(url):
        raise ValueError(f"Invalid YouTube URL: {url}")

    # 设置输出目录
    if output_dir is None:
        output_dir = Path.cwd()
    else:
        output_dir = Path(output_dir)

    output_dir = ensure_directory(output_dir)

    print(f"🎬 开始下载视频...")
    print(f"   URL: {url}")
    print(f"   输出目录: {output_dir}")

    # Load .env if available
    if load_dotenv:
        load_dotenv()

    cookies_from_browser = os.getenv("YT_DLP_COOKIES_FROM_BROWSER")
    cookie_file = os.getenv("YT_DLP_COOKIE_FILE")
    ydl_proxy = os.getenv("YT_DLP_PROXY")
    ydl_rate_limit = os.getenv("YT_DLP_RATE_LIMIT")
    ydl_format = os.getenv("YT_DLP_FORMAT")
    ydl_player_client = os.getenv("YT_DLP_PLAYER_CLIENT")
    ydl_impersonate = os.getenv("YT_DLP_IMPERSONATE")
    ydl_force_ipv4 = os.getenv("YT_DLP_FORCE_IPV4")
    max_video_height = os.getenv("MAX_VIDEO_HEIGHT")

    # 配置 yt-dlp 选项
    height = int(max_video_height) if max_video_height and max_video_height.isdigit() else 1080
    format_selector = ydl_format or f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]/best'
    ydl_opts = {
        # 视频格式：最高 1080p，优先 mp4（可用 YT_DLP_FORMAT 覆盖）
        'format': format_selector,

        # 输出模板：包含视频 ID（避免特殊字符问题）
        'outtmpl': str(output_dir / '%(id)s.%(ext)s'),

        # 下载字幕
        'writesubtitles': True,
        'writeautomaticsub': True,  # 自动字幕作为备选
        'subtitleslangs': ['en'],   # 英文字幕
        'subtitlesformat': 'vtt',   # VTT 格式

        # 不下载缩略图
        'writethumbnail': False,

        # 静默模式（减少输出）
        'quiet': False,
        'no_warnings': False,

        # 进度钩子
        'progress_hooks': [_progress_hook],
    }

    # Optional cookies support for bot-check gated videos
    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file
    if cookies_from_browser:
        ydl_opts['cookiesfrombrowser'] = _parse_cookies_from_browser(cookies_from_browser)
    if ydl_proxy:
        ydl_opts['proxy'] = ydl_proxy
    if ydl_rate_limit:
        ydl_opts['ratelimit'] = ydl_rate_limit
    if ydl_player_client:
        clients = [c.strip() for c in ydl_player_client.split(',') if c.strip()]
        if clients:
            ydl_opts['extractor_args'] = {'youtube': {'player_client': clients}}
    if ydl_impersonate is not None and ydl_impersonate != "":
        try:
            from yt_dlp.networking.impersonate import ImpersonateTarget
            ydl_opts['impersonate'] = ImpersonateTarget.from_str(ydl_impersonate)
        except Exception as e:
            print(f"⚠️  无法解析 YT_DLP_IMPERSONATE={ydl_impersonate}: {e}")
    if ydl_force_ipv4 and ydl_force_ipv4.lower() in ("1", "true", "yes"):
        ydl_opts['source_address'] = '0.0.0.0'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 提取信息
            print("\n📊 获取视频信息...")
            info = ydl.extract_info(url, download=False)

            title = info.get('title', 'Unknown')
            duration = info.get('duration', 0)
            video_id = info.get('id', 'unknown')

            print(f"   标题: {title}")
            print(f"   时长: {get_video_duration_display(duration)}")
            print(f"   视频ID: {video_id}")

            # 下载视频
            print(f"\n📥 开始下载...")
            info = ydl.extract_info(url, download=True)

            # 获取下载的文件路径
            video_filename = ydl.prepare_filename(info)
            video_path = Path(video_filename)

            # 查找字幕文件
            subtitle_path = None
            subtitle_exts = ['.en.vtt', '.vtt']
            for ext in subtitle_exts:
                potential_sub = video_path.with_suffix(ext)
                # 处理带语言代码的字幕文件
                if not potential_sub.exists():
                    # 尝试 <filename>.en.vtt 格式
                    stem = video_path.stem
                    potential_sub = video_path.parent / f"{stem}.en.vtt"

                if potential_sub.exists():
                    subtitle_path = potential_sub
                    break

            # 获取文件大小
            file_size = video_path.stat().st_size if video_path.exists() else 0

            # 验证下载结果
            if not video_path.exists():
                raise Exception("Video file not found after download")

            print(f"\n✅ 视频下载完成: {video_path.name}")
            print(f"   大小: {format_file_size(file_size)}")

            if subtitle_path and subtitle_path.exists():
                print(f"✅ 字幕下载完成: {subtitle_path.name}")
            else:
                print(f"⚠️  未找到英文字幕")
                print(f"   提示：某些视频可能没有字幕或需要自动生成")

            return {
                'video_path': str(video_path),
                'subtitle_path': str(subtitle_path) if subtitle_path else None,
                'title': title,
                'duration': duration,
                'file_size': file_size,
                'video_id': video_id
            }

    except Exception as e:
        print(f"\n❌ 下载失败: {str(e)}")
        raise


def _progress_hook(d):
    """下载进度回调"""
    if d['status'] == 'downloading':
        # 显示下载进度
        if 'downloaded_bytes' in d and 'total_bytes' in d and d['total_bytes']:
            percent = d['downloaded_bytes'] / d['total_bytes'] * 100
            downloaded = format_file_size(d['downloaded_bytes'])
            total = format_file_size(d['total_bytes'])
            speed = d.get('speed', 0)
            speed_str = format_file_size(speed) + '/s' if speed else 'N/A'

            # 使用 \r 实现进度条覆盖
            bar_length = 30
            filled = int(bar_length * percent / 100)
            bar = '█' * filled + '░' * (bar_length - filled)

            print(f"\r   [{bar}] {percent:.1f}% - {downloaded}/{total} - {speed_str}", end='', flush=True)
        elif 'downloaded_bytes' in d:
            # 无总大小信息时，只显示已下载
            downloaded = format_file_size(d['downloaded_bytes'])
            speed = d.get('speed', 0)
            speed_str = format_file_size(speed) + '/s' if speed else 'N/A'
            print(f"\r   下载中... {downloaded} - {speed_str}", end='', flush=True)

    elif d['status'] == 'finished':
        print()  # 换行


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("Usage: python download_video.py <youtube_url> [output_dir]")
        print("\nExample:")
        print("  python download_video.py https://youtube.com/watch?v=Ckt1cj0xjRM")
        print("  python download_video.py https://youtube.com/watch?v=Ckt1cj0xjRM ~/Downloads")
        sys.exit(1)

    url = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        result = download_video(url, output_dir)

        # 输出 JSON 结果（供其他脚本使用）
        print("\n" + "="*60)
        print("下载结果 (JSON):")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"\n❌ 错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
