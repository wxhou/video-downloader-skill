---
name: video-downloader
description: Download videos from social platforms without watermarks. Use when user wants to download videos from Douyin (抖音), X (Twitter), Bilibili (B站), YouTube, or Xiaohongshu (小红书). Supports MP4 video download and extracting video metadata (title, description, author). Triggers for: "下载视频", "download video", "无水印下载", "抖音视频", "B站视频", "YouTube视频", "小红书视频", "X视频", "Twitter视频", or any request involving these platforms.
---

# Video Downloader Skill

Download videos from major social platforms in MP4 format with metadata extraction.

## Supported Platforms

- Douyin (抖音)
- X / Twitter (推特)
- Bilibili (B站)
- YouTube (油管)
- Xiaohongshu (小红书)

## Quick Start

### Installation

Install required dependencies:

```bash
pip install yt-dlp playwright playwright-stealth
playwright install chromium
```

Or use the included setup script:
```bash
bash scripts/setup.sh
```

### Download a Video

```bash
# Basic download (saves to current directory)
python scripts/download.py "VIDEO_URL"

# Specify output directory
python scripts/download.py "VIDEO_URL" -o /path/to/save

# Download with metadata (JSON)
python scripts/download.py "VIDEO_URL" -o /path/to/save --metadata
```

### Supported URL Formats

| Platform | Example URL |
|----------|-------------|
| Douyin | `https://www.douyin.com/video/123456789` or `https://v.douyin.com/xxxxx` |
| X/Twitter | `https://x.com/user/status/123456789` or `https://twitter.com/user/status/123456789` |
| Bilibili | `https://www.bilibili.com/video/BVxxxxxx` or `https://b23.tv/xxxxx` |
| YouTube | `https://www.youtube.com/watch?v=xxxxx` or `https://youtu.be/xxxxx` |
| Xiaohongshu | `https://www.xiaohongshu.com/discovery/item/xxxxx` |

## Usage Patterns

### Interactive Download

When user provides a URL:
1. Detect platform from URL
2. Run appropriate downloader
3. Save video as `{title}_{author}.mp4`
4. Extract metadata to `{title}_{author}.json`

### Batch Download

```bash
# Download from file (one URL per line)
python scripts/batch_download.py urls.txt -o ./downloads
```

### Metadata Output

By default, saves metadata as JSON:
```json
{
  "title": "视频标题",
  "description": "视频描述",
  "author": "作者昵称",
  "author_id": "作者ID",
  "upload_date": "2024-01-01",
  "duration": 120,
  "likes": 10000,
  "comments": 500,
  "shares": 100,
  "url": "原始URL",
  "video_path": "本地视频路径"
}
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/download.py` | Single video download with optional transcription |
| `scripts/transcribe.py` | Standalone video transcription |
| `scripts/batch_download.py` | Batch download from URL list |
| `scripts/setup.sh` | Install dependencies |

## Error Handling

Common errors and solutions:

| Error | Solution |
|-------|----------|
| "No video found" | URL may be invalid or private |
| "Cookie required" | Some platforms need authentication |
| "Network error" | Check proxy settings |

## Platform Notes

- **YouTube**: Best quality, may need proxy
- **Bilibili**: Works well, supports series
- **Douyin (抖音)**: Uses Playwright browser automation - no cookies needed!
- **Xiaohongshu (小红书)**: May require cookies
- **X/Twitter**: Some videos require authentication

## 抖音下载 (无需Cookies)

现在使用 Playwright 浏览器自动化技术，无需 cookies 即可下载抖音视频：

```bash
# 自动提取无水印视频
python scripts/download.py "https://www.douyin.com/video/123456789"
```

## 视频转录 (语音转文字)

使用 OpenAI Whisper 进行语音转文字，默认输出**简体中文**。

### 安装转录依赖

```bash
pip install openai-whisper
```

### ⚠️ 重要：模型要求

**必须使用 medium 或 large 模型**，tiny/base/small 模型识别效果差。

```bash
# 下载 medium 模型 (约 1.4GB)
# 首次运行时会自动下载

# 转录视频
python scripts/transcribe.py video.mp4 -m medium

# 下载+转录
python scripts/download.py "VIDEO_URL" --transcribe --model medium
```

### Whisper 模型对比

| 模型 | 大小 | 准确率 | 推荐 |
|------|------|--------|------|
| tiny/base/small | ~40-240MB | 较低 | ❌ 不推荐 |
| **medium** | 1.4GB | 较高 | ✅ 推荐 |
| large | 2.9GB | 最高 | 可选 |

### 使用示例

```bash
# 单独转录
python scripts/transcribe.py ~/Downloads/video.mp4 -m medium

# 下载抖音视频并转录
python scripts/download.py "https://v.douyin.com/xxxxx" --transcribe --model medium
```

## Implementation

This skill uses `yt-dlp` as the core engine with platform-specific extractors. The downloader automatically handles:
- URL parsing and validation
- Video format selection (prefers no-watermark)
- Metadata extraction
- Filename sanitization
- Error retry logic
