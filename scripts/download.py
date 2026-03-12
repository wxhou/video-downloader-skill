#!/usr/bin/env python3
"""
Video Downloader - Download videos from multiple platforms
Supports: Douyin, X/Twitter, Bilibili, YouTube, Xiaohongshu
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


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


async def download_douyin_async(url: str, output_dir: str = '.') -> dict:
    """Download douyin video using Playwright (browser automation)"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not PLAYWRIGHT_AVAILABLE:
        return {'success': False, 'error': 'Playwright not installed. Run: pip install playwright && playwright install chromium'}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            print(f"Opening: {url}")
            await page.goto(url, wait_until='networkidle')

            # Wait for video element to be present
            await page.wait_for_selector('video', timeout=10000)

            # Extract video URL using JavaScript
            video_info = await page.evaluate('''() => {
                const video = document.querySelector('video');
                if (!video) return { error: 'No video element found' };
                return {
                    url: video.currentSrc || video.src,
                    duration: video.duration,
                    width: video.videoWidth,
                    height: video.videoHeight
                };
            }''')

            if video_info.get('error'):
                await browser.close()
                return {'success': False, 'error': video_info['error']}

            video_url = video_info.get('url')
            if not video_url:
                await browser.close()
                return {'success': False, 'error': 'No video URL found'}

            print(f"Found video URL: {video_url[:80]}...")

            # Download the video
            async with page.context.request.fetch(video_url) as response:
                if response.status == 200:
                    content = await response.body()

                    # Try to get title/author from page
                    title_info = await page.evaluate('''() => {
                        const titleEl = document.querySelector('[class*="title"]') ||
                                       document.querySelector('h1') ||
                                       document.querySelector('[data-e2e="video-detail"]');
                        const authorEl = document.querySelector('[class*="author"]') ||
                                        document.querySelector('[data-e2e="video-author"]') ||
                                        document.querySelector('a[href*="/user/"]');
                        return {
                            title: titleEl ? titleEl.textContent?.trim() : 'douyin_video',
                            author: authorEl ? authorEl.textContent?.trim() : 'unknown'
                        };
                    }''')

                    # Sanitize filename
                    title = title_info.get('title', 'douyin_video')[:50]
                    author = title_info.get('author', 'unknown')[:20]
                    safe_title = re.sub(r'[^\w\s-]', '', title).strip()
                    safe_author = re.sub(r'[^\w\s-]', '', author).strip()

                    video_path = output_path / f"{safe_title}_{safe_author}.mp4"
                    with open(video_path, 'wb') as f:
                        f.write(content)

                    print(f"Downloaded: {video_path}")
                    await browser.close()
                    return {
                        'success': True,
                        'platform': 'douyin',
                        'video_path': str(video_path),
                        'title': safe_title,
                        'author': safe_author
                    }

            await browser.close()
            return {'success': False, 'error': 'Failed to download video'}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def download_douyin(url: str, output_dir: str = '.') -> dict:
    """Download douyin video - async wrapper"""
    return asyncio.run(download_douyin_async(url, output_dir))


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
