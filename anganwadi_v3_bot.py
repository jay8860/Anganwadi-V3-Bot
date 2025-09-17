import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)

# --------------- CONFIG -----------------
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
VIDEO_FILE = "video_links.txt"
INDEX_FILE = "video_index.json"
IST = ZoneInfo("Asia/Kolkata")
TRIGGER_COMMAND = "video"  # will work as /video
# ----------------------------------------

# Load all YouTube links from file
def load_video_links():
    with open(VIDEO_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]

# Load last video index from file (or default to 0)
def load_video_index(chat_id):
    if not os.path.exists(INDEX_FILE):
        return 0
    with open(INDEX_FILE, "r") as f:
        data = json.load(f)
    return data.get(str(chat_id), 0)

# Save updated index after sending video
def save_video_index(chat_id, index):
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "r") as f:
            data = json.load(f)
    else:
        data = {}
    data[str(chat_id)] = index
    with open(INDEX_FILE, "w") as f:
        json.dump(data, f)

# --------------- COMMAND HANDLER -----------------
async def send_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return

    chat_id = chat.id
    videos = load_video_links()

    # Load last sent index
    index = load_video_index(chat_id)

    if index >= len(videos):
        await context.bot.send_message(chat_id=chat_id, text="🎬 आज के लिए कोई नया वीडियो उपलब्ध नहीं है।")
        return

    video_link = videos[index]
    now = datetime.now(tz=IST).strftime("%d-%m-%Y %I:%M %p")

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"📅 *{now}*\n🎥 आज की ECCE गतिविधि:\n{video_link}",
        parse_mode="Markdown"
    )

    save_video_index(chat_id, index + 1)

# --------------- MAIN -----------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    # Register the trigger command
    app.add_handler(CommandHandler(TRIGGER_COMMAND, send_video))

    print("Bot is running and waiting for /video command...")
    app.run_polling()
