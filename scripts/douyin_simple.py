#!/usr/bin/env python3
"""
Simplified Douyin Downloader - No browser window
Uses Playwright headless mode
"""

import asyncio
import argparse
import subprocess
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Error: playwright not installed")
    print("Run: pip install playwright && playwright install chromium")
    sys.exit(1)


async def download_douyin(url: str, output: str = ".") -> str:
    """Download douyin video using headless browser"""

    async with async_playwright() as p:
        # Headless mode - no visible window
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Set longer timeout
        print(f"Fetching: {url}")
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
        except:
            await page.goto(url, timeout=60000)

        # Wait for video with retry
        for _ in range(3):
            try:
                await page.wait_for_selector('video', timeout=10000)
                break
            except:
                await page.wait_for_timeout(2000)

        # Get video URL
        video_url = await page.evaluate('''() => {
            const video = document.querySelector('video');
            return video?.currentSrc || video?.src;
        }''')

        if not video_url:
            await browser.close()
            raise Exception("No video found")

        # Get title
        title = await page.evaluate('''() => {
            const el = document.querySelector('[class*="title"]') || document.querySelector('h1');
            return el?.textContent?.trim()?.slice(0, 50) || 'video';
        }''')

        await browser.close()

        # Download
        safe_title = "".join(c for c in title if c.isalnum() or c in ' -_').strip()
        output_path = Path(output) / f"{safe_title}.mp4"

        print(f"Downloading to: {output_path}")

        # Use curl for download
        cmd = ['curl', '-L', '-H', 'Referer: https://www.douyin.com/',
               '-o', str(output_path), video_url]
        subprocess.run(cmd, check=True)

        return str(output_path)


def main():
    parser = argparse.ArgumentParser(description='Download Douyin videos')
    parser.add_argument('url', help='Douyin video URL')
    parser.add_argument('-o', '--output', default='.', help='Output directory')

    args = parser.parse_args()

    try:
        path = asyncio.run(download_douyin(args.url, args.output))
        print(f"\n✓ Downloaded: {path}")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
