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
import urllib.request
from pathlib import Path


def detect_platform(url: str) -> str:
    """Detect platform from URL"""
    url_lower = url.lower()
    if 'douyin.com' in url_lower or 'v.douyin.com' in url_lower:
        return 'douyin'
    elif 'bilibili.com' in url_lower or 'b23.tv' in url_lower:
        return 'bilibili'
    elif 'xiaohongshu.com' in url_lower:
        return 'xiaohongshu'
    elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        return 'youtube'
    elif 'twitter.com' in url_lower or 'x.com' in url_lower:
        return 'twitter'
    return 'unknown'


def parse_douyin_share(url: str) -> str:
    """Parse douyin share URL to get video ID"""
    # Handle redirect URLs like https://v.douyin.com/xxxxx
    if 'v.douyin.com' in url:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.url
        except:
            pass
    return url


def download_douyin(url: str, output_dir: str = '.') -> dict:
    """Download douyin video using third-party API"""
    # Try multiple APIs
    apis = [
        f"https://api.leping.fun/dy/?url={url}",
        f"https://min.taoanlife.com/dy?url={url}",
    ]

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.douyin.com/'
    }

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for api_url in apis:
        try:
            print(f"Trying API: {api_url[:50]}...")
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))

                if data.get('code') == 0 or data.get('status') == 'success':
                    video_url = data.get('data', {}).get('play_addr') or \
                               data.get('data', {}).get('video') or \
                               data.get('url')

                    if video_url:
                        # Download video
                        video_path = output_path / f"douyin_video.mp4"
                        urllib.request.urlretrieve(video_url, video_path)

                        return {
                            'success': True,
                            'platform': 'douyin',
                            'video_path': str(video_path),
                            'title': data.get('data', {}).get('title', 'douyin_video'),
                            'author': data.get('data', {}).get('author', 'unknown')
                        }
        except Exception as e:
            print(f"API failed: {e}")
            continue

    return {'success': False, 'error': 'All APIs failed'}


def download_video(url: str, output_dir: str = '.', extract_metadata: bool = True) -> dict:
    """Download video using appropriate method"""

    platform = detect_platform(url)

    # Special handling for Douyin
    if platform == 'douyin':
        result = download_douyin(url, output_dir)
        if result['success']:
            return result

    # Use yt-dlp for other platforms
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    output_template = str(output_path / '%(title)s_%(uploader)s.%(ext)s')

    cmd = [
        'yt-dlp',
        '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        '--output', output_template,
    ]

    if extract_metadata:
        cmd.extend(['--write-info-json'])

    cmd.append(url)

    print(f"Downloading: {url}")
    print(f"Platform: {platform}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("Download completed!")
        return {
            'success': True,
            'url': url,
            'platform': platform,
            'output_dir': str(output_path)
        }
    except subprocess.CalledProcessError as e:
        return {
            'success': False,
            'url': url,
            'error': e.stderr
        }


def main():
    parser = argparse.ArgumentParser(description='Download videos from social platforms')
    parser.add_argument('url', help='Video URL')
    parser.add_argument('-o', '--output', default='.', help='Output directory')
    parser.add_argument('--no-metadata', action='store_true', help='Skip metadata')

    args = parser.parse_args()

    result = download_video(
        args.url,
        args.output,
        extract_metadata=not args.no_metadata
    )

    if result['success']:
        print(f"\n✓ Success! Platform: {result['platform']}")
        if result.get('video_path'):
            print(f"Video: {result['video_path']}")
        sys.exit(0)
    else:
        print(f"\n✗ Failed: {result.get('error', 'Unknown error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
