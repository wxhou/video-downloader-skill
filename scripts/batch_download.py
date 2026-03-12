#!/usr/bin/env python3
"""
Batch video downloader - download multiple videos from a list
"""

import argparse
import sys
from pathlib import Path
from download import download_video, detect_platform


def read_urls(file_path: str) -> list:
    """Read URLs from file (one per line)"""
    urls = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)
    return urls


def main():
    parser = argparse.ArgumentParser(description='Batch download videos')
    parser.add_argument('file', help='File containing URLs (one per line)')
    parser.add_argument('-o', '--output', default='./downloads', help='Output directory')
    parser.add_argument('--continue', action='store_true', help='Continue on errors')

    args = parser.parse_args()

    urls = read_urls(args.file)
    print(f"Found {len(urls)} URLs to download")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    fail_count = 0

    for i, url in enumerate(urls, 1):
        print(f"\n[{i}/{len(urls)}] Processing: {url}")

        result = download_video(url, str(output_dir))

        if result['success']:
            success_count += 1
            print(f"  ✓ Success - {result['platform']}")
        else:
            fail_count += 1
            print(f"  ✗ Failed")

            if not args.continue:
                print("Stopping due to error (use --continue to ignore errors)")
                break

    print(f"\n=== Summary ===")
    print(f"Total: {len(urls)}")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == '__main__':
    main()
