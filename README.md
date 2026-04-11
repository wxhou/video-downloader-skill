# Video Downloader

全平台视频下载工具，支持无水印下载。

## 支持平台

- 抖音 (Douyin)
- X / Twitter (推特)
- B站 (Bilibili)
- YouTube (油管)
- 小红书 (Xiaohongshu)

## 安装

```bash
# 安装依赖
pip install yt-dlp playwright
playwright install chromium

# macOS 安装 ffmpeg
brew install ffmpeg

# Linux
sudo apt-get install ffmpeg
```

或使用一键安装脚本：
```bash
bash scripts/setup.sh
```

## 使用方法

### 下载单个视频

```bash
# 基本用法
python scripts/download.py "视频URL"

# 指定输出目录
python scripts/download.py "视频URL" -o ./downloads

# 不保存元数据
python scripts/download.py "视频URL" --no-metadata
```

### 批量下载

```bash
# 创建URL列表文件（每行一个URL）
python scripts/batch_download.py urls.txt -o ./downloads
```

## 支持的URL格式

| 平台 | 示例 |
|------|------|
| 抖音 | `https://www.douyin.com/video/123456789` |
| X/Twitter | `https://x.com/user/status/123456789` |
| B站 | `https://www.bilibili.com/video/BVxxxxxx` |
| YouTube | `https://www.youtube.com/watch?v=xxxxx` |
| 小红书 | `https://www.xiaohongshu.com/discovery/item/xxxxx` |

## 输出文件

- 视频文件：`{标题}_{作者}.mp4`
- 元数据：`{标题}_{作者}.json`

## 注意事项

- 部分平台可能需要代理
- 部分视频需要登录才能下载
- 请遵守平台服务条款
