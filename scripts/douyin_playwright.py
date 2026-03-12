#!/usr/bin/env python3
"""
Douyin video downloader using Playwright
"""

import asyncio
import argparse
from pathlib import Path
from playwright.async_api import async_playwright


async def download_douyin(url: str, output_dir: str = '.') -> dict:
    """Download douyin video using Playwright"""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print(f"Opening: {url}")
        await page.goto(url)

        # Wait for video to load
        await page.wait_for_timeout(3000)

        # Find video element
        video = await page.query_selector('video')

        if video:
            video_src = await video.get_attribute('src')
            print(f"Video src: {video_src}")

            if video_src:
                # Download video
                async with page.context.request.fetch(video_src) as response:
                    if response.status == 200:
                        video_path = output_path / "douyin_video.mp4"
                        content = await response.body()
                        with open(video_path, 'wb') as f:
                            f.write(content)
                        print(f"Downloaded: {video_path}")
                        await browser.close()
                        return {'success': True, 'video_path': str(video_path)}

        # Try alternative method - get from page
        content = await page.content()

        # Look for play_addr in page source
        if 'playaddr' in content.lower() or 'aweme' in content.lower():
            print("Found video data in page")

        await browser.close()
        return {'success': False, 'error': 'Video not found'}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('url', help='Douyin URL')
    parser.add_argument('-o', '--output', default='.', help='Output directory')
    args = parser.parse_args()

    result = await download_douyin(args.url, args.output)
    print(result)


if __name__ == '__main__':
    asyncio.run(main())
