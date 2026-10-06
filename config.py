"""
Configuration for Telegram Media Downloader
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
# 100MB delivery threshold as requested
DELIVERY_THRESHOLD_MB = int(os.getenv("DELIVERY_THRESHOLD_MB", "100"))
DOWNLOAD_DIR = BASE_DIR / os.getenv("DOWNLOAD_DIR", "downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
