#!/usr/bin/env python3
"""
Video Downloader - Download videos from multiple platforms
Supports: Douyin, X/Twitter, Bilibili, YouTube, Xiaohongshu
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def detect_platform(url: str) -> str:
    """Detect platform from URL"""
    url_lower = url.lower()

    if 'douyin.com' in url_lower:
        return 'douyin'
    elif 'bilibili.com' in url_lower or 'b23.tv' in url_lower:
        return 'bilibili'
    elif 'xiaohongshu.com' in url_lower:
        return 'xiaohongshu'
    elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        return 'youtube'
    elif 'twitter.com' in url_lower or 'x.com' in url_lower:
        return 'twitter'
    else:
        return 'unknown'


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for filesystem"""
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    return filename


def download_video(url: str, output_dir: str = '.', extract_metadata: bool = True) -> dict:
    """Download video using yt-dlp"""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # yt-dlp template for output
    output_template = str(output_path / '%(title)s_%(uploader)s.%(ext)s')

    cmd = [
        'yt-dlp',
        '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        '--output', output_template,
    ]

    if extract_metadata:
        cmd.extend(['--write-info-json', '--print', 'after_move:{"video":"%(filepath)s","title":"%(title)s","uploader":"%(uploader)s","upload_date":"%(upload_date)s","duration":"%(duration)s","like_count":"%(like_count)s","comment_count":"%(comment_count)s"}'])

    cmd.append(url)

    print(f"Downloading: {url}")
    print(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        print("Download completed!")
        print(result.stdout)

        # Parse metadata from output
        metadata = {}
        for line in result.stdout.split('\n'):
            if line.startswith('{') and 'video' in line:
                try:
                    metadata = json.loads(line)
                except json.JSONDecodeError:
                    pass

        return {
            'success': True,
            'url': url,
            'platform': detect_platform(url),
            'metadata': metadata,
            'output_dir': str(output_path)
        }

    except subprocess.CalledProcessError as e:
        print(f"Error: {e.stderr}", file=sys.stderr)
        return {
            'success': False,
            'url': url,
            'error': e.stderr
        }


def main():
    parser = argparse.ArgumentParser(
        description='Download videos from social platforms'
    )
    parser.add_argument('url', help='Video URL')
    parser.add_argument('-o', '--output', default='.', help='Output directory')
    parser.add_argument('--no-metadata', action='store_true', help='Skip metadata extraction')

    args = parser.parse_args()

    result = download_video(
        args.url,
        args.output,
        extract_metadata=not args.no_metadata
    )

    if result['success']:
        print("\n=== Result ===")
        print(f"Platform: {result['platform']}")
        print(f"Output: {result['output_dir']}")
        if result.get('metadata'):
            print(f"Title: {result['metadata'].get('title', 'N/A')}")
            print(f"Video: {result['metadata'].get('video', 'N/A')}")
        sys.exit(0)
    else:
        print(f"\nFailed: {result.get('error', 'Unknown error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
