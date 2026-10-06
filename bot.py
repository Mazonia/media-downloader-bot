"""
Telegram Media Downloader Bot — Multi-Resolution Edition (480p to 4K/8K)
"""

import os
import re
import html
import ctypes
import asyncio
from pathlib import Path
from loguru import logger

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    BotCommand,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
from downloader import MediaDownloader

# Set distinct Windows console and task manager title
try:
    ctypes.windll.kernel32.SetConsoleTitleW("Media-Downloader-Bot")
except Exception:
    pass

URL_REGEX = re.compile(r'https?://(?:www\.)?[a-zA-Z0-9./?=_&%#~+-]+')
url_cache: dict[str, str] = {}


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome and instructions."""
    text = (
        "🎬 <b>MULTI-RESOLUTION MEDIA DOWNLOADER</b> 🚀\n\n"
        "Send or forward me any video link from:\n"
        "• <b>YouTube</b>, <b>TikTok</b>, <b>Instagram</b>, <b>X / Twitter</b>, <b>Reddit</b> & 1000+ sites\n\n"
        "I will detect the video's quality and let you pick your exact resolution from <b>480p up to 4K / 8K UHD</b>!\n\n"
        "<i>Paste a link below to get started:</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def handle_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detect link, extract resolution ladder, and prompt user."""
    text = update.message.text or ""
    matches = URL_REGEX.findall(text)
    if not matches:
        return

    url = matches[0]
    import uuid
    req_id = uuid.uuid4().hex[:8]
    url_cache[req_id] = url

    msg = await update.message.reply_text("🔍 <i>Detecting available resolutions...</i>", parse_mode="HTML")

    data = MediaDownloader.get_info_and_resolutions(url)
    if not data:
        # Fallback choices if extraction had warnings
        title = "Video Link"
        uploader = "Creator"
        duration_str = "Clip"
        resolutions = [
            {"height": 480, "label": "480p (SD)"},
            {"height": 720, "label": "720p (HD)"},
            {"height": 1080, "label": "1080p (Full HD)"},
        ]
    else:
        title = data["title"]
        uploader = data["uploader"]
        dur = data["duration"]
        minutes, seconds = divmod(dur, 60)
        duration_str = f"{minutes}:{seconds:02d}" if dur else "Reel/Short"
        resolutions = data["resolutions"]

    # Build buttons for each detected resolution
    button_rows = []
    current_row = []
    for res in resolutions:
        btn = InlineKeyboardButton(f"📺 {res['label']}", callback_data=f"dl_{res['height']}_{req_id}")
        current_row.append(btn)
        if len(current_row) == 2:
            button_rows.append(current_row)
            current_row = []
    if current_row:
        button_rows.append(current_row)

    # Audio option
    button_rows.append([InlineKeyboardButton("🎵 Extract Audio (MP3 320k)", callback_data=f"dl_mp3_{req_id}")])

    keyboard = InlineKeyboardMarkup(button_rows)

    card_text = (
        f"📹 <b>{html.escape(title[:60])}</b>\n"
        f"👤 <b>Creator:</b> {html.escape(uploader)}\n"
        f"⏱️ <b>Duration:</b> {duration_str}\n\n"
        f"<i>Select your preferred download resolution:</i>"
    )

    await msg.edit_text(card_text, reply_markup=keyboard, parse_mode="HTML")


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle resolution click and start download."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data
    parts = data.split("_")
    if len(parts) < 3:
        return

    res_type = parts[1]  # '480', '720', '1080', '2160', 'mp3'
    req_id = parts[2]
    url = url_cache.get(req_id)
    if not url:
        await query.message.reply_text("⚠️ Link expired. Please paste the link again.")
        return

    label = f"{res_type}p Video" if res_type.isdigit() else "MP3 Audio"
    await query.edit_message_text(f"⏳ <b>Downloading in {label}...</b>\n<i>Streaming high-quality segments...</i>", parse_mode="HTML")

    downloaded_file = None
    try:
        if res_type.isdigit():
            target_h = int(res_type)
            file_path, title, size_mb = MediaDownloader.download_video_at_resolution(url, target_h)
            if file_path and file_path.exists():
                downloaded_file = file_path

                if size_mb > 50:
                    # Inform user file is saved locally due to Telegram Bot API 50MB direct upload cap
                    await query.edit_message_text(
                        f"✅ <b>Downloaded in {target_h}p ({size_mb} MB)!</b>\n\n"
                        f"<b>Title:</b> {html.escape(title)}\n"
                        f"<b>Saved on PC:</b>\n<code>{file_path}</code>\n\n"
                        f"ℹ️ <i>Telegram Bot API limits direct chat uploads to 50MB. Your full-resolution {size_mb}MB file is saved safely on your PC!</i>",
                        parse_mode="HTML"
                    )
                    return

                await query.edit_message_text(f"📤 <b>Uploading {target_h}p video ({size_mb} MB) to Telegram...</b>", parse_mode="HTML")
                with open(file_path, "rb") as f:
                    await query.message.reply_video(
                        video=f,
                        caption=f"🎬 <b>{html.escape(title[:60])}</b>\n📺 Quality: {target_h}p | {size_mb} MB",
                        parse_mode="HTML",
                        supports_streaming=True
                    )
            else:
                await query.edit_message_text(f"❌ {title}")

        elif res_type == "mp3":
            file_path, title, size_mb = MediaDownloader.download_audio(url)
            if file_path and file_path.exists():
                downloaded_file = file_path
                await query.edit_message_text("📤 <b>Uploading MP3 audio to Telegram...</b>", parse_mode="HTML")
                with open(file_path, "rb") as f:
                    await query.message.reply_audio(
                        audio=f,
                        title=title[:40],
                        caption=f"🎵 <b>{html.escape(title[:60])}</b>\n📦 Size: {size_mb} MB",
                        parse_mode="HTML"
                    )
            else:
                await query.edit_message_text(f"❌ {title}")

    except Exception as e:
        logger.error(f"Download flow failed: {e}")
        await query.message.reply_text(f"⚠️ Error: {e}")
    finally:
        # Auto clean up files <= 50MB that were delivered
        if downloaded_file and downloaded_file.exists() and downloaded_file.stat().st_size <= 50 * 1024 * 1024:
            try:
                os.remove(downloaded_file)
            except Exception:
                pass


def main():
    if not config.BOT_TOKEN:
        print("\n⚠️ Error: TELEGRAM_BOT_TOKEN is not set in .env file!\n")
        return

    app = ApplicationBuilder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler(["start", "help"], handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_message))
    app.add_handler(CallbackQueryHandler(callback_router))

    async def post_init(application):
        try:
            await application.bot.set_my_commands([
                BotCommand("start", "Help & Supported Platforms"),
            ])
        except Exception:
            pass

    app.post_init = post_init
    logger.info("🎬 Media Downloader Bot is running (Multi-Resolution Edition)...")
    app.run_polling()


if __name__ == "__main__":
    main()
