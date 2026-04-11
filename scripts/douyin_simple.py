#!/usr/bin/env python3
"""
Douyin Downloader - Stealth headless mode
"""

import asyncio
import argparse
import subprocess
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth
except ImportError:
    print("Error: Required packages not installed")
    print("Run: pip install playwright playwright-stealth && playwright install chromium")
    sys.exit(1)


async def download_douyin(url: str, output: str = ".") -> str:
    """Download douyin video using stealth headless browser"""

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ]
        )

        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        )

        page = await context.new_page()

        # Apply stealth patches
        stealth = Stealth()
        await stealth.apply_stealth_async(page)

        print(f"Fetching: {url}")

        try:
            await page.goto(url, wait_until='networkidle', timeout=90000)
        except:
            await page.goto(url, timeout=90000)

        # Wait for video to load
        await page.wait_for_timeout(3000)

        # Try to get video URL
        video_url = None
        for attempt in range(3):
            video_url = await page.evaluate('''() => {
                const video = document.querySelector('video');
                if (video) {
                    return video.currentSrc || video.src || null;
                }
                return null;
            }''')

            if video_url:
                break
            print(f"Attempt {attempt + 1}: waiting...")
            await page.wait_for_timeout(2000)

        if not video_url:
            await browser.close()
            raise Exception("No video found")

        # Get title
        title = await page.evaluate('''() => {
            const el = document.querySelector('[class*="title"]') ||
                       document.querySelector('h1') ||
                       document.title;
            return el?.textContent?.trim()?.slice(0, 50) || 'video';
        }''')

        await browser.close()

        # Download
        safe_title = "".join(c for c in title if c.isalnum() or c in ' -_').strip()
        output_path = Path(output) / f"{safe_title}.mp4"

        print(f"Downloading: {safe_title}.mp4")

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
