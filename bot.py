"""
Telegram Media Downloader Bot — 100MB Threshold Edition
Prompts user to choose Server vs Phone when crossing 100MB.
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

# Set Windows console and Task Manager title
try:
    ctypes.windll.kernel32.SetConsoleTitleW("Media-Downloader-Bot")
except Exception:
    pass

URL_REGEX = re.compile(r'https?://(?:www\.)?[a-zA-Z0-9./?=_&%#~+-]+')
url_cache: dict[str, str] = {}
# Holds pending files that crossed 100MB: {job_id: {"file_path": Path, "title": str, "size_mb": int}}
pending_delivery: dict[str, dict] = {}


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎬 <b>MULTI-RESOLUTION MEDIA DOWNLOADER</b> 🚀\n\n"
        "Send or forward me any video link from:\n"
        "• <b>YouTube</b>, <b>TikTok</b>, <b>Instagram</b>, <b>X / Twitter</b>, <b>Reddit</b> & 1000+ sites\n\n"
        "<b>Features:</b>\n"
        "• Quality from <b>480p up to 4K / 8K UHD</b>\n"
        "• <b>100MB Threshold Guard:</b> If a video crosses 100MB, you decide whether to keep it on your PC Server or send to your Phone!\n\n"
        "<i>Paste a link below to get started:</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def handle_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    matches = URL_REGEX.findall(text)
    if not matches:
        return

    url = matches[0]
    import uuid
    req_id = uuid.uuid4().hex[:8]
    url_cache[req_id] = url

    msg = await update.message.reply_text("🔍 <i>Inspecting video source for resolutions...</i>", parse_mode="HTML")

    data = MediaDownloader.get_info_and_resolutions(url)
    if not data:
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

    button_rows.append([InlineKeyboardButton("🎵 Extract Audio (MP3 320k)", callback_data=f"dl_mp3_{req_id}")])

    keyboard = InlineKeyboardMarkup(button_rows)
    card_text = (
        f"📹 <b>{html.escape(title[:60])}</b>\n"
        f"👤 <b>Creator:</b> {html.escape(uploader)}\n"
        f"⏱️ <b>Duration:</b> {duration_str}\n\n"
        f"<i>Select your preferred download resolution:</i>"
    )

    await msg.edit_text(card_text, reply_markup=keyboard, parse_mode="HTML")


async def deliver_to_phone(query, file_path: Path, title: str, size_mb: int):
    """Deliver file to phone; if > 50MB, splits into parts so Telegram allows it."""
    if size_mb <= 50:
        await query.edit_message_text(f"📤 <b>Uploading video ({size_mb} MB) to your phone...</b>", parse_mode="HTML")
        with open(file_path, "rb") as f:
            await query.message.reply_video(
                video=f,
                caption=f"🎬 <b>{html.escape(title[:60])}</b>\n📦 Size: {size_mb} MB",
                parse_mode="HTML",
                supports_streaming=True
            )
        try:
            os.remove(file_path)
        except Exception:
            pass
    else:
        await query.edit_message_text(
            f"📤 <b>File is {size_mb} MB (>50MB Telegram single upload limit)</b>\n"
            f"<i>Splitting and uploading {size_mb} MB to your phone in parts...</i>",
            parse_mode="HTML"
        )
        parts = MediaDownloader.split_file_for_telegram(file_path, max_part_size_mb=48)
        for idx, part_p in enumerate(parts, 1):
            with open(part_p, "rb") as f:
                await query.message.reply_document(
                    document=f,
                    caption=f"📦 <b>{html.escape(title[:45])}</b> — Part {idx}/{len(parts)}",
                    parse_mode="HTML"
                )
            try:
                os.remove(part_p)
            except Exception:
                pass
        try:
            os.remove(file_path)
        except Exception:
            pass


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data
    parts = data.split("_")

    # Handle Server vs Phone choice for files > 100MB
    if parts[0] == "dest":
        choice = parts[1]  # 'server' or 'phone'
        job_id = parts[2]
        item = pending_delivery.get(job_id)
        if not item:
            await query.edit_message_text("⚠️ Selection expired.")
            return

        file_p = item["file_path"]
        title = item["title"]
        size_mb = item["size_mb"]

        if choice == "server":
            await query.edit_message_text(
                f"✅ <b>Kept on PC / Server ({size_mb} MB)!</b>\n\n"
                f"<b>Title:</b> {html.escape(title)}\n"
                f"<b>Local Path:</b>\n<code>{file_p}</code>\n\n"
                f"💾 <i>File is safely saved on your PC storage without using mobile data.</i>",
                parse_mode="HTML"
            )
            del pending_delivery[job_id]
        elif choice == "phone":
            await deliver_to_phone(query, file_p, title, size_mb)
            if job_id in pending_delivery:
                del pending_delivery[job_id]
        return

    # Regular download trigger
    if len(parts) < 3:
        return

    res_type = parts[1]  # '480', '720', '1080', '2160', 'mp3'
    req_id = parts[2]
    url = url_cache.get(req_id)
    if not url:
        await query.message.reply_text("⚠️ Link expired. Please paste the link again.")
        return

    label = f"{res_type}p Video" if res_type.isdigit() else "MP3 Audio"
    await query.edit_message_text(f"⏳ <b>Downloading {label}...</b>\n<i>Fetching media stream...</i>", parse_mode="HTML")

    if res_type.isdigit():
        target_h = int(res_type)
        file_path, title, size_mb = MediaDownloader.download_video_at_resolution(url, target_h)
        if not file_path or not file_path.exists():
            await query.edit_message_text(f"❌ {title}")
            return

        # ── 100MB THRESHOLD CHECK ──────────────────────────────────────
        if size_mb > config.DELIVERY_THRESHOLD_MB:
            import uuid
            job_id = uuid.uuid4().hex[:8]
            pending_delivery[job_id] = {
                "file_path": file_path,
                "title": title,
                "size_mb": size_mb,
            }

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💾 Keep on PC / Server", callback_data=f"dest_server_{job_id}"),
                    InlineKeyboardButton("📱 Send to Phone", callback_data=f"dest_phone_{job_id}"),
                ]
            ])

            await query.edit_message_text(
                f"📦 <b>FILE SIZE NOTICE: {size_mb} MB</b>\n"
                f"{'━' * 28}\n\n"
                f"<b>Title:</b> {html.escape(title[:60])}\n"
                f"<b>Quality:</b> {target_h}p\n"
                f"<b>Size:</b> <code>{size_mb} MB</code> (Exceeds {config.DELIVERY_THRESHOLD_MB} MB threshold)\n\n"
                f"<b>Where would you like to deliver this media?</b>",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return

        # File is <= 100MB: Deliver directly to phone
        await deliver_to_phone(query, file_path, title, size_mb)

    elif res_type == "mp3":
        file_path, title, size_mb = MediaDownloader.download_audio(url)
        if file_path and file_path.exists():
            await query.edit_message_text("📤 <b>Uploading MP3 audio to Telegram...</b>", parse_mode="HTML")
            with open(file_path, "rb") as f:
                await query.message.reply_audio(
                    audio=f,
                    title=title[:40],
                    caption=f"🎵 <b>{html.escape(title[:60])}</b>\n📦 Size: {size_mb} MB",
                    parse_mode="HTML"
                )
            try:
                os.remove(file_path)
            except Exception:
                pass
        else:
            await query.edit_message_text(f"❌ {title}")


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
    logger.info("🎬 Media Downloader Bot is running (100MB Threshold Edition)...")
    app.run_polling()


if __name__ == "__main__":
    main()
