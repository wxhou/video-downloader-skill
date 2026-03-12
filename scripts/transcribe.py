#!/usr/bin/env python3
"""
Video Transcription Tool
Extract audio and transcribe video content to text using Whisper
"""

import argparse
import subprocess
import sys
from pathlib import Path

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    print("Error: whisper not installed")
    print("Install with: pip install openai-whisper")
    sys.exit(1)


def extract_audio(video_path: str, output_path: str = None) -> str:
    """Extract audio from video using ffmpeg"""
    video_path = Path(video_path)

    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)

    if output_path is None:
        audio_path = video_path.with_suffix('.m4a')
    else:
        audio_path = Path(output_path)

    print(f"Extracting audio to: {audio_path}")

    cmd = [
        'ffmpeg', '-i', str(video_path),
        '-vn', '-acodec', 'copy',
        '-y', str(audio_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        # Try with re-encoding
        cmd = [
            'ffmpeg', '-i', str(video_path),
            '-vn', '-acodec', 'aac',
            '-y', str(audio_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Error extracting audio: {result.stderr}")
            sys.exit(1)

    return str(audio_path)


def transcribe(audio_path: str, model: str = 'base', language: str = 'zh') -> dict:
    """Transcribe audio using Whisper"""
    print(f"Loading Whisper {model} model...")
    whisper_model = whisper.load_model(model)

    print("Transcribing...")
    result = whisper_model.transcribe(audio_path, language=language)

    return result


def main():
    parser = argparse.ArgumentParser(description='Transcribe video to text')
    parser.add_argument('video', help='Video file path')
    parser.add_argument('-o', '--output', help='Output file path (default: video.txt)')
    parser.add_argument('-m', '--model', default='medium',
                        choices=['tiny', 'base', 'small', 'medium', 'large'],
                        help='Whisper model size (default: base)')
    parser.add_argument('-l', '--language', default='zh',
                        help='Language code (default: zh for Chinese)')
    parser.add_argument('--no-audio-extract', action='store_true',
                        help='Skip audio extraction (use existing audio file)')

    args = parser.parse_args()

    video_path = Path(args.video)

    # Extract audio if needed
    if args.no_audio_extract:
        audio_path = args.video
    else:
        audio_path = extract_audio(args.video, args.output.with_suffix('.m4a') if args.output else None)

    # Transcribe
    result = transcribe(audio_path, args.model, args.language)

    # Save transcript
    output_path = args.output or video_path.with_suffix('.txt')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(result['text'])

    print(f"\n✓ Transcript saved to: {output_path}")
    print(f"\n--- Transcript ---")
    print(result['text'])


if __name__ == '__main__':
    main()
