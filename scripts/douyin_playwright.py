#!/usr/bin/env python3
"""
Douyin video downloader - iesdouyin.com API (no browser needed) + Playwright fallback

Usage: python douyin_playwright.py "https://v.douyin.com/xxxxx" -o ~/Downloads/
"""

import asyncio
import argparse
import re
import subprocess
import urllib.request
from pathlib import Path


async def download_douyin(url: str, output_dir: str = '.') -> dict:
    """Download douyin video: iesdouyin API first, Playwright fallback"""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Step 1: Resolve video ID
    video_id = None
    resolved_url = url

    if 'v.douyin.com' in url:
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
            })
            with urllib.request.urlopen(req, timeout=10) as response:
                resolved_url = response.url
        except Exception as e:
            print(f"URL resolution failed: {e}")

    match = re.search(r'/video/(\d{16,})', resolved_url)
    if match:
        video_id = match.group(1)

    if not video_id:
        match = re.search(r'/video/(\d{16,})', url)
        if match:
            video_id = match.group(1)

    if not video_id:
        return {'success': False, 'error': f'Could not extract video ID from: {url}'}

    print(f"Video ID: {video_id}")

    # Step 2: iesdouyin.com API (no browser, no login)
    share_url = f'https://www.iesdouyin.com/share/video/{video_id}/'
    try:
        req = urllib.request.Request(share_url, headers={
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Referer': 'https://www.iesdouyin.com/',
        })
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8', errors='ignore')

        # Extract video_id from play_addr in page source
        play_match = re.search(r'video_id=([^&"<>]+)', html)
        if play_match:
            vid_id = play_match.group(1)
            no_wm_url = f'https://aweme.snssdk.com/aweme/v1/play/?video_id={vid_id}&ratio=1080p&line=0'
            output_file = output_path / f'douyin_{video_id}.mp4'

            print(f"Using iesdouyin API (no browser, no login)...")
            cmd_str = (
                f'wget -c -O "{output_file}" '
                f'-H "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1" '
                f'-H "Referer: https://www.douyin.com/" '
                f'"{no_wm_url}"'
            )
            result = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
            if result.returncode == 0 and output_file.exists() and output_file.stat().st_size > 10000:
                print(f"Downloaded: {output_file} ({output_file.stat().st_size // 1024 // 1024}MB)")
                return {'success': True, 'video_path': str(output_file), 'video_id': video_id}
            else:
                print(f"API download failed: {result.stderr[:200] if result.stderr else 'unknown'}")
        else:
            print("Could not find video_id in page, trying Playwright...")

    except Exception as e:
        print(f"iesdouyin API failed: {e}, trying Playwright...")

    # Step 3: Playwright fallback
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {'success': False, 'error': 'Playwright not installed. Run: pip install playwright && playwright install chromium'}

    print("Trying Playwright browser fallback...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            print(f"Opening: {url}")
            await page.goto(url)
            await page.wait_for_timeout(3000)

            video = await page.query_selector('video')
            if video:
                video_src = await video.get_attribute('src')
                if video_src:
                    async with page.context.request.fetch(video_src) as response:
                        if response.status == 200:
                            video_path = output_path / f"douyin_{video_id}.mp4"
                            content = await response.body()
                            with open(video_path, 'wb') as f:
                                f.write(content)
                            print(f"Downloaded (Playwright): {video_path}")
                            await browser.close()
                            return {'success': True, 'video_path': str(video_path)}

            await browser.close()
            return {'success': False, 'error': 'Video not found in page'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def main():
    parser = argparse.ArgumentParser(description='Download Douyin video (iesdouyin API + Playwright fallback)')
    parser.add_argument('url', help='Douyin URL')
    parser.add_argument('-o', '--output', default='.', help='Output directory')
    args = parser.parse_args()

    result = await download_douyin(args.url, args.output)
    print(result)


if __name__ == '__main__':
    asyncio.run(main())
