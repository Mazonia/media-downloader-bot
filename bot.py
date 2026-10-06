"""
Telegram Media Downloader Bot with Pre-Download 100MB File Size Threshold Check.
If estimated file size > 100MB, prompts user BEFORE downloading to choose PC storage vs Phone delivery.
"""

import os
import re
import html
import ctypes
import uuid
from pathlib import Path
from loguru import logger
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import config
from downloader import MediaDownloader

# Set Windows Console Title for Task Manager identification
try:
    if os.name == "nt":
        ctypes.windll.kernel32.SetConsoleTitleW("Telegram-Media-Downloader")
except Exception:
    pass

url_cache = {}

def is_url(text: str) -> bool:
    pattern = re.compile(
        r"^(?:http|ftp)s?://" +
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|" +
        r"localhost|" +
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})" +
        r"(?::\d+)?" +
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return bool(pattern.match(text.strip()))

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "Friend"
    text = (
        f"👋 <b>Welcome {html.escape(user_name)}!</b>\n\n"
        "🎬 <b>All-in-One Social Media Downloader Bot</b>\n\n"
        "Just send me any link from:\n"
        "• 🎵 <b>TikTok</b> (No watermark)\n"
        "• 📸 <b>Instagram</b> (Reels, Posts, Carousels)\n"
        "• ▶️ <b>YouTube</b> (Shorts, 1080p, 2K, 4K, 8K)\n"
        "• 🐦 <b>X / Twitter & Reddit</b>\n"
        "• 📌 <b>Pinterest, Facebook & 1000+ sites</b>\n\n"
        "⚙️ <b>Smart Download Control:</b>\n"
        "• Pick exact resolution (480p up to 8K) or MP3 audio.\n"
        "• For files crossing <b>100 MB</b>, the bot prompts you <i>before downloading</i> "
        "to confirm whether to store on your PC or stream to your phone!"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def handle_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text.strip()
    if not is_url(msg_text):
        await update.message.reply_text("⚠️ Please send a valid media URL link (e.g., YouTube, TikTok, Instagram, X).")
        return

    msg = await update.message.reply_text("🔍 <b>Probing media formats and file sizes...</b>", parse_mode="HTML")

    data = MediaDownloader.get_info_and_resolutions(msg_text)
    req_id = uuid.uuid4().hex[:8]

    if not data:
        title = "Media Video"
        uploader = "Unknown"
        duration_str = "Unknown"
        resolutions = [
            {"height": 480, "label": "480p (SD)", "est_mb": 30},
            {"height": 720, "label": "720p (HD)", "est_mb": 65},
            {"height": 1080, "label": "1080p (Full HD)", "est_mb": 140},
        ]
        audio_est_mb = 10
    else:
        title = data["title"]
        uploader = data["uploader"]
        dur = data["duration"]
        minutes, seconds = divmod(dur, 60)
        duration_str = f"{minutes}:{seconds:02d}" if dur else "Reel/Short"
        resolutions = data["resolutions"]
        audio_est_mb = data["audio_est_mb"]

    res_map = {str(r["height"]): r.get("est_mb", 50) for r in resolutions}
    url_cache[req_id] = {
        "url": msg_text,
        "title": title,
        "res_map": res_map,
        "audio_est_mb": audio_est_mb,
    }

    button_rows = []
    current_row = []
    for res in resolutions:
        est = res.get("est_mb", 0)
        est_txt = f" (~{est} MB)" if est > 0 else ""
        btn_label = f"🎬 {res['label']}{est_txt}"
        btn = InlineKeyboardButton(btn_label, callback_data=f"dl_{res['height']}_{req_id}")
        current_row.append(btn)
        if len(current_row) == 2:
            button_rows.append(current_row)
            current_row = []
    if current_row:
        button_rows.append(current_row)

    audio_label = f"🎵 Extract Audio (MP3 320k) (~{audio_est_mb} MB)"
    button_rows.append([InlineKeyboardButton(audio_label, callback_data=f"dl_mp3_{req_id}")])

    keyboard = InlineKeyboardMarkup(button_rows)
    card_text = (
        f"🎬 <b>{html.escape(title[:60])}</b>\n"
        f"👤 <b>Creator:</b> {html.escape(uploader)}\n"
        f"⏱ <b>Duration:</b> {duration_str}\n\n"
        "<i>Select your preferred resolution or audio format:</i>"
    )

    await msg.edit_text(card_text, reply_markup=keyboard, parse_mode="HTML")

async def deliver_to_phone(query, file_path: Path, title: str, size_mb: int):
    """Deliver file to phone; if > 50MB, splits into parts for Telegram Bot API compliance."""
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
            f"<i>Splitting and delivering {size_mb} MB to your phone in sequential parts...</i>",
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

async def execute_download_and_store(query, url: str, res_type: str, dest_target: str, title: str):
    """Executes the download and handles PC storage vs Phone delivery."""
    is_video = res_type != "mp3"
    label = f"{res_type}p Video" if is_video else "MP3 Audio"

    if dest_target == "server":
        await query.edit_message_text(
            f"⏳ <b>Downloading {label} to PC storage...</b>\n"
            "<i>Saving directly to your computer hard drive without mobile data...</i>",
            parse_mode="HTML"
        )
        if is_video:
            file_path, d_title, size_mb = MediaDownloader.download_video_at_resolution(url, int(res_type))
        else:
            file_path, d_title, size_mb = MediaDownloader.download_audio(url)

        if not file_path or not file_path.exists():
            await query.edit_message_text(f"❌ Download failed: {d_title}")
            return

        await query.edit_message_text(
            "✅ <b>Saved to PC / Server Storage!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎬 <b>Title:</b> {html.escape(d_title[:60])}\n"
            f"📊 <b>Quality:</b> {label}\n"
            f"📦 <b>Actual Size:</b> <code>{size_mb} MB</code>\n"
            f"📁 <b>Local Path:</b>\n<code>{file_path}</code>\n\n"
            "💾 <i>Media is stored safely on your PC disk. No phone data was consumed.</i>",
            parse_mode="HTML"
        )

    elif dest_target == "phone":
        await query.edit_message_text(
            f"⏳ <b>Downloading {label}...</b>\n"
            "<i>Will prepare and deliver to your phone once downloaded...</i>",
            parse_mode="HTML"
        )
        if is_video:
            file_path, d_title, size_mb = MediaDownloader.download_video_at_resolution(url, int(res_type))
            if not file_path or not file_path.exists():
                await query.edit_message_text(f"❌ Download failed: {d_title}")
                return
            await deliver_to_phone(query, file_path, d_title, size_mb)
        else:
            file_path, d_title, size_mb = MediaDownloader.download_audio(url)
            if not file_path or not file_path.exists():
                await query.edit_message_text(f"❌ Extraction failed: {d_title}")
                return
            if size_mb <= 50:
                await query.edit_message_text("📤 <b>Uploading MP3 audio to Telegram...</b>", parse_mode="HTML")
                with open(file_path, "rb") as f:
                    await query.message.reply_audio(
                        audio=f,
                        title=d_title[:40],
                        caption=f"🎵 <b>{html.escape(d_title[:60])}</b>\n📦 Size: {size_mb} MB",
                        parse_mode="HTML"
                    )
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            else:
                await deliver_to_phone(query, file_path, d_title, size_mb)

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data
    parts = data.split("_")
    action_type = parts[0]

    # 1. PRE-DOWNLOAD CONFIRMATION (User clicked Server, Phone, or Cancel for >100MB file)
    if action_type == "pconf":
        choice = parts[1]  # pc, phone, or cancel
        req_id = parts[2]
        cached = url_cache.get(req_id)
        if not cached:
            await query.edit_message_text("⚠️ Selection session expired. Please send the link again.")
            return

        if choice == "cancel":
            await query.edit_message_text("❌ <i>Download cancelled. No files were downloaded to PC or phone.</i>", parse_mode="HTML")
            return

        res_type = parts[3]  # 720, 1080, 2160, mp3
        dest_target = "server" if choice == "pc" else "phone"
        await execute_download_and_store(query, cached["url"], res_type, dest_target, cached["title"])
        return

    # 2. RESOLUTION SELECTION
    if action_type == "dl":
        res_type = parts[1]
        req_id = parts[2]
        cached = url_cache.get(req_id)
        if not cached:
            await query.message.reply_text("⚠️ Link session expired. Please paste the link again.")
            return

        url = cached["url"]
        title = cached["title"]

        if res_type == "mp3":
            est_mb = cached.get("audio_est_mb", 10)
            label = "MP3 Audio"
        else:
            est_mb = cached.get("res_map", {}).get(res_type, 60)
            label = f"{res_type}p Video"

        # PRE-DOWNLOAD 100MB THRESHOLD INTERCEPTOR
        if est_mb > config.DELIVERY_THRESHOLD_MB:
            # DO NOT DOWNLOAD! Prompt user first!
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💾 Save on PC / Server Only", callback_data=f"pconf_pc_{req_id}_{res_type}")],
                [InlineKeyboardButton("📱 Download & Send to Phone", callback_data=f"pconf_phone_{req_id}_{res_type}")],
                [InlineKeyboardButton("❌ Cancel Download", callback_data=f"pconf_cancel_{req_id}")],
            ])
            card = (
                f"⚠️ <b>LARGE FILE CONFIRMATION (~{est_mb} MB)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🎬 <b>Title:</b> {html.escape(title[:60])}\n"
                f"📊 <b>Selected Quality:</b> {label}\n"
                f"📦 <b>Estimated Size:</b> <code>~{est_mb} MB</code> <i>(Exceeds {config.DELIVERY_THRESHOLD_MB} MB limit)</i>\n\n"
                "<b>Before downloading, where do you want this file?</b>\n"
                "• <b>Save to PC:</b> Downloads to PC disk; consumes zero phone data.\n"
                "• <b>Send to Phone:</b> Downloads & streams to your phone chat."
            )
            await query.edit_message_text(card, reply_markup=keyboard, parse_mode="HTML")
            return

        # ESTIMATED <= 100MB: Proceed with download and deliver to phone
        await execute_download_and_store(query, url, res_type, "phone", title)
        return

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
    logger.info("🎬 Media Downloader Bot is running (Pre-download 100MB Threshold Guard active)...")
    app.run_polling()

if __name__ == "__main__":
    main()
