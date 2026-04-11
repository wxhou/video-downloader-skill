#!/usr/bin/env python3
"""
Video Downloader - Download videos from multiple platforms
Supports: Douyin, X/Twitter, Bilibili, YouTube, Xiaohongshu
Features:
  - Extract ALL videos from a tweet (supports multiple videos per post)
  - Save to downloaded_videos/ subfolder in current project
  - Report metadata: path, filename, duration, resolution, size
  - Fallback chain: yt-dlp -> Playwright -> curl/wget
  - Audio transcription support (OpenAI Whisper)
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

def detect_platform(url: str) -> str:
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


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = re.sub(r'\s+', '_', name)
    name = name[:100].strip('._')
    return name or 'video'


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f}MB"
    else:
        return f"{size_bytes / 1024 / 1024 / 1024:.2f}GB"


def format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "N/A"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def get_video_info(filepath: str) -> dict:
    """Get video metadata using ffprobe"""
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', filepath]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        video_stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
        format_info = data.get('format', {})
        if not video_stream:
            return {}
        return {
            'duration': float(format_info.get('duration', 0)),
            'resolution': f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}",
            'codec': video_stream.get('codec_name', 'unknown'),
            'bitrate': format_info.get('bit_rate', 'unknown'),
            'size_bytes': int(format_info.get('size', 0)),
        }
    except Exception:
        return {}


def ensure_output_dir(project_dir: Path = None) -> Path:
    """Create downloaded_videos subfolder in project directory"""
    if project_dir is None:
        project_dir = Path.cwd()
    output_dir = project_dir / 'downloaded_videos'
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# ────────────────────────────────────────────────────────────────
# Twitter / X Downloader (multi-video support)
# ────────────────────────────────────────────────────────────────

async def _extract_twitter_videos_via_browser(tweet_url: str) -> list[dict]:
    """Extract video URLs from tweet using Playwright browser"""
    if not PLAYWRIGHT_AVAILABLE:
        return []

    videos = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                locale='zh-CN',
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            await page.goto(tweet_url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)

            # Extract video elements and metadata
            js_code = """
            (function() {
                var videos = [];
                var seenUrls = {};

                // Method 1: video elements
                document.querySelectorAll('video').forEach(function(v) {
                    var src = v.currentSrc || v.src || '';
                    if (src && src.startsWith('http') && !seenUrls[src]) {
                        seenUrls[src] = true;
                        videos.push({ url: src, type: 'element' });
                    }
                });

                // Method 2: og:video meta tags
                document.querySelectorAll('meta[property="og:video"]').forEach(function(m) {
                    var url = m.getAttribute('content') || '';
                    if (url && url.startsWith('http') && !seenUrls[url]) {
                        seenUrls[url] = true;
                        videos.push({ url: url, type: 'meta' });
                    }
                });

                // Method 3: script JSON with video URLs
                var scripts = document.querySelectorAll('script');
                for (var i = 0; i < scripts.length; i++) {
                    var text = scripts[i].textContent || '';
                    var re = /(?:video_url|contentUrl|src)\\s*:\\s*["']([^"']+\\.(?:mp4|webm|m3u8)[^"']*)["']/gi;
                    var m;
                    while ((m = re.exec(text)) !== null) {
                        var url = m[1];
                        if (!seenUrls[url]) {
                            seenUrls[url] = true;
                            videos.push({ url: url, type: 'script' });
                        }
                    }
                }

                // Get author and tweet text from tweet article
                var author = 'unknown';
                var tweetText = '';
                var article = document.querySelector('[data-testid="tweet"]') ||
                              document.querySelector('article') ||
                              document.querySelector('[role="article"]');
                if (article) {
                    var authorEl = article.querySelector('[data-testid="User-Name"] a[href*="/"]') ||
                                   article.querySelector('a[tabindex="0"][role="link"]');
                    author = authorEl ? authorEl.textContent.replace(/@/g, '').trim() : 'unknown';
                    var textEl = article.querySelector('[data-testid="tweetText"]') ||
                                 article.querySelector('div[lang]');
                    tweetText = textEl ? textEl.textContent.trim().slice(0, 80) : '';
                }

                return { videos: videos, author: author, tweetText: tweetText };
            })();
            """
            video_data = await page.evaluate(js_code)

            await browser.close()

            if video_data.get('videos'):
                for i, v in enumerate(video_data['videos']):
                    v['index'] = i + 1
                    v['author'] = video_data.get('author', 'unknown')
                    v['tweet_text'] = video_data.get('tweetText', '')
                return video_data['videos']

            return []

    except Exception as e:
        print(f"  Browser extraction failed: {e}")
        return []


def _get_browsers_to_try() -> list[str]:
    """Return list of browsers to try for cookie extraction, in priority order"""
    return ['chrome', 'chromium', 'edge', 'firefox', 'safari']


def _download_via_ytdlp(url: str, output_dir: Path, index: int = None, tweet_text: str = '', use_cookies: bool = True) -> dict:
    """Download single video using yt-dlp, with optional browser cookie auth"""
    tweet_id = re.search(r'/status/(\d+)', url)
    tweet_id = tweet_id.group(1) if tweet_id else 'video'

    base_name = sanitize_filename(tweet_text) if tweet_text else tweet_id
    if index:
        output_template = str(output_dir / f'{base_name}_%(playlist_index)s.%(ext)s')
    else:
        output_template = str(output_dir / f'{base_name}.%(ext)s')

    # Try with browser cookies first (handles age-restricted content)
    if use_cookies:
        for browser in _get_browsers_to_try():
            print(f"  [yt-dlp + {browser} cookies] {url[:70]}...")
            cmd = ['yt-dlp', '--output', output_template, '--no-playlist',
                   f'--cookies-from-browser={browser}', url]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode == 0:
                    # Find downloaded file
                    for pattern in [f'{base_name}_*', f'{tweet_id}*']:
                        for f in sorted(output_dir.glob(pattern)):
                            if f.suffix.lower() in ['.mp4', '.webm', '.mkv', '.mov', '.m4v']:
                                info = get_video_info(str(f))
                                return {
                                    'success': True,
                                    'method': f'yt-dlp + {browser} cookies',
                                    'video_path': str(f),
                                    'filename': f.name,
                                    'duration': info.get('duration', 0),
                                    'resolution': info.get('resolution', 'unknown'),
                                    'size': info.get('size_bytes', f.stat().st_size),
                                }
                    return {'success': True, 'method': f'yt-dlp + {browser} cookies'}
                else:
                    err = result.stderr[-300:]
                    if 'not found' in err.lower() or 'no cookies' in err.lower() or 'profile' in err.lower():
                        print(f"    {browser} cookies unavailable, trying next...")
                        continue
                    # Browser found but download failed for other reason
                    print(f"    {browser} failed: {err[:100]}, trying next...")
                    continue
            except subprocess.TimeoutExpired:
                print(f"    {browser} timeout, trying next...")
                continue
            except FileNotFoundError:
                print(f"    yt-dlp not found")
                break
            except Exception as e:
                print(f"    {browser} error: {e}")
                continue

        print(f"  No browser cookies available, trying without...")

    # Fallback: yt-dlp without cookies
    cmd = ['yt-dlp', '--output', output_template, '--no-playlist', url]
    print(f"  [yt-dlp] {url[:70]}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            for pattern in [f'{base_name}_*', f'{tweet_id}*']:
                for f in sorted(output_dir.glob(pattern)):
                    if f.suffix.lower() in ['.mp4', '.webm', '.mkv', '.mov', '.m4v']:
                        info = get_video_info(str(f))
                        return {
                            'success': True,
                            'method': 'yt-dlp',
                            'video_path': str(f),
                            'filename': f.name,
                            'duration': info.get('duration', 0),
                            'resolution': info.get('resolution', 'unknown'),
                            'size': info.get('size_bytes', f.stat().st_size),
                        }
            return {'success': True, 'method': 'yt-dlp'}
        else:
            return {'success': False, 'method': 'yt-dlp', 'error': result.stderr[-500:]}
    except subprocess.TimeoutExpired:
        return {'success': False, 'method': 'yt-dlp', 'error': 'Timeout'}
    except FileNotFoundError:
        return {'success': False, 'method': 'yt-dlp', 'error': 'yt-dlp not found'}
    except Exception as e:
        return {'success': False, 'method': 'yt-dlp', 'error': str(e)}


def _download_via_curl(video_url: str, output_dir: Path, filename: str = None) -> dict:
    """Download video using curl"""
    if not filename:
        match = re.search(r'/([^/]+\.mp4)', video_url)
        filename = match.group(1) if match else f'video_{int(time.time())}.mp4'
    filepath = output_dir / filename

    cmd = ['curl', '-L', '-C', '-', '-o', str(filepath),
           '-A', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
           '--referer', 'https://x.com/', video_url]
    print(f"  [curl] {video_url[:70]}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and filepath.exists() and filepath.stat().st_size > 1000:
            info = get_video_info(str(filepath))
            return {
                'success': True,
                'method': 'curl',
                'video_path': str(filepath),
                'filename': filepath.name,
                'duration': info.get('duration', 0),
                'resolution': info.get('resolution', 'unknown'),
                'size': info.get('size_bytes', filepath.stat().st_size),
            }
        else:
            return {'success': False, 'method': 'curl', 'error': result.stderr[-300:] or 'Download failed'}
    except subprocess.TimeoutExpired:
        return {'success': False, 'method': 'curl', 'error': 'Timeout'}
    except FileNotFoundError:
        return {'success': False, 'method': 'curl', 'error': 'curl not found'}
    except Exception as e:
        return {'success': False, 'method': 'curl', 'error': str(e)}


def _extract_twitter_via_vxtwitter(tweet_url: str) -> list[dict]:
    """Extract video URLs from tweet via vxtwitter API (no auth required)"""
    import urllib.request
    import json

    # Extract tweet ID and construct API URL
    match = re.search(r'/status/(\d+)', tweet_url)
    if not match:
        return []

    api_url = f"https://api.vxtwitter.com{tweet_url}"
    print(f"  [vxtwitter] {api_url}")

    try:
        req = urllib.request.Request(api_url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))

        if not data.get('hasMedia') or not data.get('mediaURLs'):
            return []

        videos = []
        for i, media in enumerate(data.get('media_extended', [])):
            if media.get('type') == 'video':
                videos.append({
                    'url': media.get('url', ''),
                    'author': data.get('user_name', 'unknown'),
                    'author_handle': data.get('user_screen_name', ''),
                    'tweet_text': data.get('text', '')[:200],
                    'duration_millis': media.get('duration_millis', 0),
                    'width': media.get('size', {}).get('width', 0),
                    'height': media.get('size', {}).get('height', 0),
                    'thumbnail': media.get('thumbnail_url', ''),
                })

        # Also add mediaURLs that might not be in media_extended
        for i, video_url in enumerate(data.get('mediaURLs', [])):
            if not any(v['url'] == video_url for v in videos):
                videos.append({
                    'url': video_url,
                    'author': data.get('user_name', 'unknown'),
                    'author_handle': data.get('user_screen_name', ''),
                    'tweet_text': data.get('text', '')[:200],
                    'duration_millis': 0,
                    'width': 0,
                    'height': 0,
                    'thumbnail': '',
                })

        print(f"  [vxtwitter] Found {len(videos)} video(s) via API")
        return videos

    except Exception as e:
        print(f"  [vxtwitter] Failed: {e}")
        return []


def _download_single_video(video_url: str, output_dir: Path, filename: str) -> dict:
    """Download a single video URL using curl"""
    filepath = output_dir / filename

    cmd = ['curl', '-L', '-C', '-', '-o', str(filepath),
           '-A', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
           '--referer', 'https://x.com/', video_url]
    print(f"  [curl] {video_url[:70]}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and filepath.exists() and filepath.stat().st_size > 1000:
            info = get_video_info(str(filepath))
            return {
                'success': True,
                'method': 'curl',
                'video_path': str(filepath),
                'filename': filepath.name,
                'duration': info.get('duration', 0),
                'resolution': info.get('resolution', 'unknown'),
                'size': info.get('size_bytes', filepath.stat().st_size),
            }
        else:
            return {'success': False, 'method': 'curl', 'error': result.stderr[-300:] or 'Download failed'}
    except subprocess.TimeoutExpired:
        return {'success': False, 'method': 'curl', 'error': 'Timeout'}
    except FileNotFoundError:
        return {'success': False, 'method': 'curl', 'error': 'curl not found'}
    except Exception as e:
        return {'success': False, 'method': 'curl', 'error': str(e)}


async def download_twitter_async(url: str) -> list[dict]:
    """Download all videos from an X/Twitter post"""
    output_dir = ensure_output_dir()
    results = []

    # Normalize to x.com
    url = re.sub(r'twitter\.com', 'x.com', url)

    print(f"\n{'='*50}")
    print(f"X/Twitter Video Downloader")
    print(f"{'='*50}")
    print(f"URL: {url}")
    print(f"Output: {output_dir}")

    # Step 0: Try vxtwitter API (no auth required, fastest)
    print(f"\n[0] Trying vxtwitter API (no auth)...")
    video_urls = _extract_twitter_via_vxtwitter(url)

    if video_urls:
        print(f"  Found {len(video_urls)} video(s) via vxtwitter")
        for i, v in enumerate(video_urls):
            video_url = v['url']
            author = v.get('author', 'unknown')
            tweet_text = v.get('tweet_text', '')

            safe_author = sanitize_filename(author)
            safe_text = sanitize_filename(tweet_text)[:40] if tweet_text else f'tweet_{i+1}'
            filename = f"{safe_text}_{safe_author}_{i+1}.mp4"

            print(f"\n[0] Downloading video {i+1}/{len(video_urls)}: {filename}")
            dl = _download_single_video(video_url, output_dir, filename)
            dl['url'] = video_url
            if dl['success']:
                results.append(dl)
            else:
                print(f"  curl failed: {dl.get('error', '')[:200]}")
                # Fallback to yt-dlp for this video
                dl = _download_via_ytdlp(video_url, output_dir, i + 1, tweet_text)
                if dl['success']:
                    dl['url'] = video_url
                    results.append(dl)
                else:
                    results.append({'success': False, 'url': video_url, 'error': dl.get('error', 'unknown')})

        if results:
            return results

    # Step 1: Try yt-dlp with browser cookies (handles age-restricted content)
    print(f"\n[1] Trying yt-dlp with browser cookies...")
    dl = _download_via_ytdlp(url, output_dir, tweet_text=url)
    dl['url'] = url
    if dl['success']:
        results.append(dl)
        return results
    else:
        print(f"  yt-dlp failed: {dl.get('error', 'unknown')[:200]}")

    # Step 2: Try Playwright to extract video URLs
    print(f"\n[2] Extracting videos via browser...")
    video_urls = await _extract_twitter_videos_via_browser(url)

    if not video_urls:
        print("  No videos found via browser.")
        results.append(dl)  # Already tried yt-dlp, already failed
        return results

    print(f"  Found {len(video_urls)} video(s)")

    # Step 3: Download each video
    for i, v in enumerate(video_urls):
        video_url = v['url']
        author = v.get('author', 'unknown')
        tweet_text = v.get('tweet_text', '')

        # Generate filename
        safe_author = sanitize_filename(author)
        safe_text = sanitize_filename(tweet_text) if tweet_text else f'tweet_{i+1}'
        filename = f"{safe_text}_{safe_author}_{i+1}.mp4"

        print(f"\n[2] Downloading video {i+1}/{len(video_urls)}: {filename}")

        # Try curl first (direct URL from browser)
        dl = _download_via_curl(video_url, output_dir, filename)
        if dl['success']:
            dl['url'] = video_url
            results.append(dl)
            continue

        print(f"  curl failed, trying yt-dlp...")
        dl = _download_via_ytdlp(video_url, output_dir, i + 1, tweet_text)
        if dl['success']:
            dl['url'] = video_url
            results.append(dl)
            continue

        print(f"  yt-dlp also failed: {dl.get('error', 'unknown')[:200]}")
        results.append({'success': False, 'url': video_url, 'error': dl.get('error', 'unknown')})

    return results


def download_twitter(url: str) -> list[dict]:
    return asyncio.run(download_twitter_async(url))


# ────────────────────────────────────────────────────────────────
# Douyin Downloader (existing logic)
# ────────────────────────────────────────────────────────────────

def parse_douyin_share(url: str) -> str:
    if 'v.douyin.com' in url:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                resolved_url = response.url
                match = re.search(r'/video/(\d+)', resolved_url)
                if match:
                    return match.group(1)
                return resolved_url
        except:
            pass
    match = re.search(r'/video/(\d+)', url)
    if match:
        return match.group(1)
    return url


async def download_douyin_async(url: str, output_dir: str = '.') -> dict:
    import re as re_module
    import urllib.request as urllib_req
    import subprocess as subproc

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    video_id = None
    resolved_url = url

    if 'v.douyin.com' in url:
        try:
            req = urllib_req.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
            })
            with urllib_req.urlopen(req, timeout=10) as response:
                resolved_url = response.url
        except Exception as e:
            print(f"Redirect follow failed: {e}")

    match = re_module.search(r'/video/(\d{16,})', resolved_url)
    if match:
        video_id = match.group(1)
    if not video_id:
        match = re_module.search(r'/video/(\d{16,})', url)
        if match:
            video_id = match.group(1)

    if not video_id:
        return {'success': False, 'error': f'Could not extract video ID from: {url}'}

    print(f"Video ID: {video_id}")

    # Try iesdouyin.com API
    share_url = f'https://www.iesdouyin.com/share/video/{video_id}/'
    try:
        req = urllib_req.Request(share_url, headers={
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Referer': 'https://www.iesdouyin.com/',
        })
        with urllib_req.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8', errors='ignore')

        render_match = re_module.search(r'"play_addr"\s*:\s*\{[^}]*"uri"\s*:\s*"([^"]+)"', html)
        if render_match:
            video_uri = render_match.group(1)
            play_match = re_module.search(r'video_id=([^&"]+)', html)
            vid_id = play_match.group(1) if play_match else video_uri
            no_wm_url = f'https://aweme.snssdk.com/aweme/v1/play/?video_id={vid_id}&ratio=1080p&line=0'

            safe_name = f'douyin_{video_id}'
            output_file = output_path / f'{safe_name}.mp4'

            cmd_str = f'wget -c -O "{output_file}" ' \
                      f'-H "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1" ' \
                      f'-H "Referer: https://www.douyin.com/" ' \
                      f'"{no_wm_url}"'

            print(f"Downloading via iesdouyin API...")
            result = subproc.run(cmd_str, shell=True, capture_output=True, text=True)

            if result.returncode == 0 and output_file.exists() and output_file.stat().st_size > 10000:
                info = get_video_info(str(output_file))
                return {
                    'success': True,
                    'platform': 'douyin',
                    'video_path': str(output_file),
                    'title': safe_name,
                    'video_id': video_id,
                    'method': 'iesdouyin_api',
                    'duration': info.get('duration', 0),
                    'resolution': info.get('resolution', 'unknown'),
                    'size': info.get('size_bytes', output_file.stat().st_size),
                }
            else:
                print(f"wget failed: {result.stderr[:200] if result.stderr else 'unknown'}")

    except Exception as e:
        print(f"iesdouyin API failed: {e}, trying Playwright...")

    # Playwright fallback
    if not PLAYWRIGHT_AVAILABLE:
        return {'success': False, 'error': 'iesdouyin API failed and Playwright not installed'}

    print("Trying Playwright fallback...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until='networkidle')
            await page.wait_for_selector('video', timeout=10000)

            video_info = await page.evaluate('''() => {
                const video = document.querySelector('video');
                if (!video) return { error: 'No video element' };
                return { url: video.currentSrc || video.src, duration: video.duration,
                         width: video.videoWidth, height: video.videoHeight };
            }''')

            if video_info.get('error'):
                await browser.close()
                return {'success': False, 'error': video_info['error']}

            video_url = video_info.get('url')
            if not video_url:
                await browser.close()
                return {'success': False, 'error': 'No video URL found'}

            async with page.context.request.fetch(video_url) as response:
                if response.status == 200:
                    content = await response.body()
                    title_info = await page.evaluate('''() => {
                        const titleEl = document.querySelector('[class*="title"]') || document.querySelector('h1');
                        const authorEl = document.querySelector('[class*="author"]') || document.querySelector('a[href*="/user/"]');
                        return {
                            title: titleEl ? titleEl.textContent?.trim() : 'douyin_video',
                            author: authorEl ? authorEl.textContent?.trim() : 'unknown'
                        };
                    }''')
                    title = title_info.get('title', 'douyin_video')[:50]
                    author = title_info.get('author', 'unknown')[:20]
                    safe_title = re_module.sub(r'[^\w\s-]', '', title).strip()
                    safe_author = re_module.sub(r'[^\w\s-]', '', author).strip()
                    video_path = output_path / f"{safe_title}_{safe_author}.mp4"
                    with open(video_path, 'wb') as f:
                        f.write(content)
                    info = get_video_info(str(video_path))
                    await browser.close()
                    return {
                        'success': True,
                        'platform': 'douyin',
                        'video_path': str(video_path),
                        'title': safe_title,
                        'author': safe_author,
                        'method': 'playwright',
                        'duration': info.get('duration', 0),
                        'resolution': info.get('resolution', 'unknown'),
                        'size': info.get('size_bytes', video_path.stat().st_size),
                    }
            await browser.close()
            return {'success': False, 'error': 'Failed to download video'}
    except Exception as e:
        return {'success': False, 'error': f'Both iesdouyin API and Playwright failed: {str(e)}'}


def download_douyin(url: str, output_dir: str = '.') -> dict:
    return asyncio.run(download_douyin_async(url, output_dir))


# ────────────────────────────────────────────────────────────────
# Generic download (yt-dlp for Bilibili, YouTube, etc.)
# ────────────────────────────────────────────────────────────────

def download_generic(url: str, output_dir: str = '.') -> dict:
    platform = detect_platform(url)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    safe_name = f'{platform}_video'
    output_template = str(output_path / f'{safe_name}.%(ext)s')

    cmd = ['yt-dlp', '--output', output_template, '--write-info-json', url]
    print(f"Downloading: {url}")
    print(f"Platform: {platform}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            # Find downloaded file
            for f in output_path.glob(f'{safe_name}.*'):
                if f.suffix.lower() in ['.mp4', '.webm', '.mkv', '.mov', '.m4v']:
                    info = get_video_info(str(f))
                    # Find metadata JSON
                    json_file = f.with_suffix('.info.json')
                    metadata = {}
                    if json_file.exists():
                        try:
                            with open(json_file) as jf:
                                metadata = json.load(jf)
                        except:
                            pass
                    return {
                        'success': True,
                        'platform': platform,
                        'video_path': str(f),
                        'filename': f.name,
                        'title': metadata.get('title', f.stem),
                        'author': metadata.get('uploader', 'unknown'),
                        'duration': info.get('duration', 0) or metadata.get('duration', 0),
                        'resolution': info.get('resolution', 'unknown'),
                        'size': info.get('size_bytes', f.stat().st_size),
                        'method': 'yt-dlp',
                    }
            return {'success': True, 'platform': platform}
        else:
            return {'success': False, 'platform': platform, 'error': result.stderr[-500:]}
    except subprocess.TimeoutExpired:
        return {'success': False, 'platform': platform, 'error': 'Timeout'}
    except FileNotFoundError:
        return {'success': False, 'platform': platform, 'error': 'yt-dlp not found. Run: pip install yt-dlp'}
    except Exception as e:
        return {'success': False, 'platform': platform, 'error': str(e)}


# ────────────────────────────────────────────────────────────────
# Audio extraction & transcription
# ────────────────────────────────────────────────────────────────

def extract_audio(video_path: str, output_dir: str = '.') -> str:
    video_path = Path(video_path)
    output_path = Path(output_dir)
    audio_path = output_path / f"{video_path.stem}.m4a"

    for codec in ['copy', 'aac']:
        cmd = ['ffmpeg', '-i', str(video_path), '-vn']
        if codec == 'copy':
            cmd.extend(['-acodec', 'copy'])
        else:
            cmd.extend(['-acodec', 'aac'])
        cmd.extend(['-y', str(audio_path)])
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            return str(audio_path)
        except subprocess.CalledProcessError:
            continue
    return ''


def transcribe_audio(audio_path: str, model: str = 'base') -> dict:
    if not WHISPER_AVAILABLE:
        return {'success': False, 'error': 'whisper not installed. Run: pip install openai-whisper'}
    try:
        print(f"Loading Whisper {model} model...")
        whisper_model = whisper.load_model(model)
        print("Transcribing audio...")
        result = whisper_model.transcribe(audio_path, language='zh')
        return {'success': True, 'text': result['text'], 'language': result.get('language', 'zh')}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def transcribe_video(video_path: str, output_dir: str = '.', model: str = 'medium') -> dict:
    video_path = Path(video_path)
    if not video_path.exists():
        return {'success': False, 'error': 'Video file not found'}

    print(f"Extracting audio from {video_path.name}...")
    audio_path = extract_audio(str(video_path), output_dir)
    if not audio_path:
        return {'success': False, 'error': 'Failed to extract audio'}

    result = transcribe_audio(audio_path, model)
    if result.get('success'):
        transcript_path = Path(output_dir) / f"{video_path.stem}.txt"
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(result['text'])
        result['transcript_path'] = str(transcript_path)
        print(f"Transcript saved to: {transcript_path}")
    return result


# ────────────────────────────────────────────────────────────────
# Main entry
# ────────────────────────────────────────────────────────────────

def download_video(url: str, output_dir: str = None, extract_metadata: bool = True) -> list[dict]:
    """Download video(s). Returns a list of result dicts."""
    platform = detect_platform(url)

    if platform == 'twitter':
        # Twitter may have multiple videos
        output_path = ensure_output_dir(Path(output_dir) if output_dir else None)
        results = download_twitter(url)
        # Attach output path to results
        for r in results:
            r['output_dir'] = str(output_path)
            r['platform'] = 'twitter'
        return results

    elif platform == 'douyin':
        output_path = ensure_output_dir(Path(output_dir) if output_dir else None)
        result = download_douyin(url, str(output_path))
        result['output_dir'] = str(output_path)
        return [result]

    else:
        output_path = ensure_output_dir(Path(output_dir) if output_dir else None)
        result = download_generic(url, str(output_path))
        result['output_dir'] = str(output_path)
        return [result]


def print_results(results: list[dict]):
    """Print formatted download results"""
    print(f"\n{'='*50}")
    print(f"Download Summary")
    print(f"{'='*50}")

    success_count = sum(1 for r in results if r.get('success'))
    total = len(results)
    print(f"Total videos: {total}")
    print(f"Successful: {success_count}")
    print(f"Failed: {total - success_count}")

    for i, r in enumerate(results):
        print(f"\n--- Video {i+1} ---")
        if r.get('success'):
            size = format_size(r.get('size', 0))
            duration = format_duration(r.get('duration', 0))
            print(f"  Status: SUCCESS")
            print(f"  File: {r.get('video_path', r.get('filename', 'unknown'))}")
            print(f"  Resolution: {r.get('resolution', 'N/A')}")
            print(f"  Duration: {duration}")
            print(f"  Size: {size}")
            print(f"  Method: {r.get('method', 'N/A')}")
            print(f"  Output: {r.get('output_dir', 'N/A')}")
        else:
            print(f"  Status: FAILED")
            print(f"  Error: {r.get('error', 'unknown')[:200]}")


def main():
    parser = argparse.ArgumentParser(description='Download videos from social platforms')
    parser.add_argument('url', help='Video URL')
    parser.add_argument('-o', '--output', default=None, help='Output directory (default: ./downloaded_videos)')
    parser.add_argument('--no-metadata', action='store_true', help='Skip metadata')
    parser.add_argument('--transcribe', action='store_true', help='Transcribe video to text')
    parser.add_argument('--model', default='medium', choices=['medium', 'large'],
                        help='Whisper model size (default: medium)')

    args = parser.parse_args()

    results = download_video(args.url, args.output, extract_metadata=not args.no_metadata)
    print_results(results)

    success_count = sum(1 for r in results if r.get('success'))

    # Transcribe if requested
    if args.transcribe and success_count > 0:
        print(f"\n{'='*50}")
        print("Transcription")
        print(f"{'='*50}")
        for r in results:
            if r.get('success') and r.get('video_path'):
                print(f"\nTranscribing: {r.get('filename', 'video')}...")
                transcribe_result = transcribe_video(r['video_path'], r.get('output_dir', '.'), args.model)
                if transcribe_result.get('success'):
                    print(f"  Transcript ({len(transcribe_result['text'])} chars): {transcribe_result['text'][:200]}...")
                    print(f"  Saved to: {transcribe_result.get('transcript_path')}")
                else:
                    print(f"  Failed: {transcribe_result.get('error')}")

    sys.exit(0 if success_count > 0 else 1)


if __name__ == '__main__':
    main()
