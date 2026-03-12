#!/bin/bash
# Setup script for video downloader

echo "Installing video downloader dependencies..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required"
    exit 1
fi

# Install yt-dlp
echo "Installing yt-dlp..."
pip install yt-dlp

# Install Playwright (for Douyin download)
echo "Installing Playwright..."
pip install playwright
playwright install chromium

# Install ffmpeg (required for merging video/audio)
if command -v brew &> /dev/null; then
    echo "Installing ffmpeg via Homebrew..."
    brew install ffmpeg
elif command -v apt-get &> /dev/null; then
    echo "Installing ffmpeg via apt..."
    sudo apt-get install -y ffmpeg
fi

echo ""
echo "Setup complete!"
echo "Usage:"
echo "  python scripts/download.py \"VIDEO_URL\" -o ./downloads"
echo ""
