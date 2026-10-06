# 🎬 All-in-One Social Media Video & Audio Downloader Bot

A high-performance Telegram bot that extracts and downloads ultra-high-definition videos (480p up to 8K UHD) and crystal-clear MP3 audio (320 kbps) from virtually any social media link.

Features an intelligent **Pre-Download 100MB File Size Guard**: files exceeding 100 MB trigger an interactive prompt *before anything is saved to disk*, allowing you to choose whether to store the media on your PC hard drive (zero mobile data used) or chunk and deliver it to your phone.

---

## ✨ Key Features
- **🌐 Universal Platform Support**: YouTube (Shorts & 4K/8K Videos), TikTok (watermark-free), Instagram (Reels, Carousels, Posts), X/Twitter, Reddit (with synced audio), Facebook, Pinterest, Vimeo, and 1000+ sites powered by yt-dlp.
- **📊 Dynamic Resolution Ladder**: Automatically probes media streams and displays buttons for available source qualities: `480p`, `720p`, `1080p`, `1440p (2K)`, `2160p (4K)`, and `4320p (8K)`.
- **🎵 Studio Quality Audio Extraction**: Convert any video to high-bitrate MP3 (320 kbps) with embedded metadata.
- **🛡️ Pre-Download 100MB Threshold Guard**: Calculates estimated file size *before* downloading. If estimated size > 100MB, the bot asks you:
  - 💾 **Save to PC / Server Only**: Saves to local `downloads/` folder; leaves your mobile data untouched.
  - 📱 **Download & Send to Phone**: Downloads and delivers directly to Telegram chat.
  - ❌ **Cancel Download**: Aborts without writing any file.
- **🧩 Automatic Chunk Splitter**: Bypasses Telegram's 50MB single-file bot limit by automatically splitting large mobile deliveries into sequential 48MB parts.
- **🏷️ Dedicated Windows Process Name**: Runs as `media-downloader.exe` with console title `Telegram-Media-Downloader` for easy identification in Windows Task Manager.

---

## 📋 Prerequisites & Setup Guide

### 1. Getting a Telegram Bot Token (Step-by-Step)
1. Open Telegram and search for the official **[@BotFather](https://t.me/BotFather)** (look for the verified blue checkmark).
2. Start the chat by pressing **Start** or typing `/start`.
3. Send the command `/newbot`.
4. Choose a friendly display name for your bot (e.g. `My Media Downloader`).
5. Choose a unique username ending in `bot` (e.g. `john_media_dl_bot`).
6. BotFather will reply with congratulations and provide your **HTTP API Token**:
   ```
   123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```
7. Copy this token. You will paste it into your `.env` file.

### 2. Finding Your Telegram User ID
1. In Telegram, search for **[@userinfobot](https://t.me/userinfobot)**.
2. Send `/start`.
3. The bot will reply with your numeric **Id** (e.g., `987654321`).

### 3. Installing FFmpeg (Crucial for 1080p+, 4K & MP3)
`yt-dlp` requires FFmpeg to merge high-resolution video streams with separate high-quality audio streams.
- **Windows (Recommended via Winget)**:
  ```powershell
  winget install Gyan.FFmpeg
  ```
- **Windows (Chocolatey)**:
  ```powershell
  choco install ffmpeg
  ```
- **Manual**: Download the release archive from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/), extract it, and add the `bin` folder to your Windows System `PATH`.
- Verify installation in PowerShell:
  ```powershell
  ffmpeg -version
  ```

---

## 🚀 Installation & Running

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Mazonia/media-downloader-bot.git
   cd media-downloader-bot
   ```

2. **Create and configure your `.env` file**:
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your favorite text editor:
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   DELIVERY_THRESHOLD_MB=100
   DOWNLOAD_DIR=./downloads
   ```

3. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch the bot**:
   - **Option A (Recommended)**: Double-click `run.bat` or run:
     ```powershell
     .\run.bat
     ```
     *(This launches under `media-downloader.exe` in Windows Task Manager)*
   - **Option B**:
     ```powershell
     python bot.py
     ```

5. **Using the Bot**:
   - Send `/start` in your Telegram chat with the bot.
   - Paste any video link (YouTube, TikTok, Instagram, X, etc.).
   - Choose your desired resolution or MP3 audio from the interactive buttons!

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
