# 👇 Full bot code with video posting feature
# ------- All imports remain the same -------
import os
import json
import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from telegram import Update, ChatMemberUpdated
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)

# ---------- Config ----------
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
IST = ZoneInfo("Asia/Kolkata")

_raw_ids = os.environ.get("ALLOWED_CHAT_IDS")
if _raw_ids:
    ALLOWED_CHAT_IDS = {int(x.strip()) for x in _raw_ids.split(",") if x.strip()}
else:
    ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID", "0"))
    ALLOWED_CHAT_IDS = set() if ALLOWED_CHAT_ID == 0 else {ALLOWED_CHAT_ID}

print("TOKEN_FINGERPRINT:", hashlib.sha256(TOKEN.encode()).hexdigest()[:12])
print("ALLOWED_CHAT_IDS:", sorted(list(ALLOWED_CHAT_IDS)) if ALLOWED_CHAT_IDS else "ANY (setup mode)")

# ---------- In-memory State ----------
submissions = defaultdict(lambda: defaultdict(dict))
streaks = defaultdict(lambda: defaultdict(int))
last_submission_date = defaultdict(dict)
known_users = defaultdict(dict)
media_group_seen = set()

def today_str():
    return datetime.now(tz=IST).strftime("%Y-%m-%d")

def is_allowed_chat(chat_id: int) -> bool:
    return True if not ALLOWED_CHAT_IDS else chat_id in ALLOWED_CHAT_IDS

# ---------- State Persistence ----------
STATE_FILE = "bot_state.json"
VIDEO_INDEX_FILE = "video_index.json"

def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump({
            "submissions": submissions,
            "streaks": streaks,
            "last_submission_date": last_submission_date,
            "known_users": known_users
        }, f, default=dict)

def load_state():
    global submissions, streaks, last_submission_date, known_users
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            submissions.update({int(k): defaultdict(dict, v) for k, v in data.get("submissions", {}).items()})
            streaks.update({int(k): defaultdict(int, v) for k, v in data.get("streaks", {}).items()})
            last_submission_date.update({int(k): v for k, v in data.get("last_submission_date", {}).items()})
            known_users.update({int(k): v for k, v in data.get("known_users", {}).items()})
    except Exception as e:
        print(f"[INFO] No previous state loaded: {e}")

# ---------- New: Video Posting ----------
def get_today_video_link():
    try:
        with open("video_links.txt", "r") as f:
            video_links = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return "⚠️ वीडियो लिस्ट नहीं मिली (video_links.txt)."

    # Load or create index
    if os.path.exists(VIDEO_INDEX_FILE):
        with open(VIDEO_INDEX_FILE, "r") as f:
            index_data = json.load(f)
    else:
        index_data = {}

    today = today_str()
    index = index_data.get(today)

    if index is None:
        index = len(index_data)
        if index >= len(video_links):
            return "🎉 सभी वीडियो पोस्ट हो चुके हैं!"
        index_data[today] = index
        with open(VIDEO_INDEX_FILE, "w") as f:
            json.dump(index_data, f)

    return video_links[index]

async def cmd_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat and is_allowed_chat(chat.id):
        link = get_today_video_link()
        await context.bot.send_message(chat_id=chat.id, text=f"📺 आज का ECCE वीडियो:\n{link}")

async def job_video_post(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data
    link = get_today_video_link()
    await context.bot.send_message(chat_id=chat_id, text=f"📺 आज का ECCE वीडियो:\n{link}")

# ---------- Existing Commands ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat and is_allowed_chat(chat.id):
        await update.message.reply_text("🙏 स्वागत है! कृपया हर दिन अपने आंगनवाड़ी की फ़ोटो इस समूह में भेजें।")

async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat:
        await update.message.reply_text(f"chat_id: {chat.id}")

async def cmd_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat and is_allowed_chat(chat.id):
        count = await context.bot.get_chat_member_count(chat_id=chat.id)
        await update.message.reply_text(f"👥 Group members right now: {count}")

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat and is_allowed_chat(chat.id):
        await post_summary_for_chat(context, chat.id)
        await post_awards_for_chat(context, chat.id)

async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat and is_allowed_chat(chat.id):
        date = today_str()
        today_ids = set(submissions[chat.id].get(date, {}).keys())
        member_ids = set(known_users[chat.id].keys())
        pending_ids = [uid for uid in member_ids if uid not in today_ids]
        names = [known_users[chat.id].get(uid, f"User {uid}") for uid in pending_ids]
        if not names:
            await update.message.reply_text("✅ आज किसी की रिपोर्ट पेंडिंग नहीं है.")
            return
        preview = ", ".join(names[:20]) + ("…" if len(names) > 20 else "")
        await update.message.reply_text(f"⏳ आज पेंडिंग: {len(names)}\n{preview}")

# ---------- Membership ----------
async def track_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m: ChatMemberUpdated = update.chat_member
    chat_id = m.chat.id
    if is_allowed_chat(chat_id):
        member = m.new_chat_member
        if member.status in {"member", "administrator"}:
            user = member.user
            known_users[chat_id][user.id] = user.first_name or "User"
            save_state()

# ---------- Photo Handler ----------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or not is_allowed_chat(chat.id):
        return
    msg = update.message
    if not msg or not msg.photo:
        return
    user = update.effective_user
    if not user:
        return
    chat_id = chat.id
    user_id = user.id
    name = user.first_name or "User"
    known_users[chat_id][user_id] = name

    mgid = msg.media_group_id
    if mgid:
        unique_key = f"{chat_id}:{user_id}:{mgid}"
        if unique_key in media_group_seen:
            return
        media_group_seen.add(unique_key)

    date = today_str()
    now = datetime.now(tz=IST).strftime("%H:%M")

    submissions[chat_id].setdefault(date, {})
    if user_id in submissions[chat_id][date]:
        return

    submissions[chat_id][date][user_id] = {"name": name, "time": now}
    prev_date = last_submission_date[chat_id].get(user_id)
    yesterday = (datetime.now(tz=IST) - timedelta(days=1)).strftime("%Y-%m-%d")
    streaks[chat_id][user_id] = streaks[chat_id].get(user_id, 0) + 1 if prev_date == yesterday else 1
    last_submission_date[chat_id][user_id] = date

    save_state()
    logging.info(f"[PHOTO] {name} submitted in chat {chat_id} at {now}")
    await context.bot.send_message(chat_id=chat_id, text=f"✅ {name}, आपकी आज की फ़ोटो दर्ज कर ली गई है। बहुत अच्छे!")

# ---------- Summary & Awards ----------
async def _build_summary_text(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> str:
    date = today_str()
    total_members = await context.bot.get_chat_member_count(chat_id=chat_id)
    today_data = submissions[chat_id].get(date, {})
    today_ids = set(today_data.keys())
    pending_count = max(0, total_members - len(today_ids))
    tracked_ids = set(known_users[chat_id].keys()) | today_ids

    top_streaks = sorted(
        [(uid, streaks[chat_id].get(uid, 0)) for uid in tracked_ids],
        key=lambda x: x[1], reverse=True
    )[:5]

    leaderboard = "\n".join(
        f"{i+1}. {known_users[chat_id].get(uid, 'User')} – {count} दिन"
        for i, (uid, count) in enumerate(top_streaks) if count > 0
    )

    return (
        f"📊 {datetime.now(tz=IST).strftime('%I:%M %p')} समूह रिपोर्ट:\n\n"
        f"👥 कुल Group सदस्य: {total_members}\n"
        f"✅ आज रिपोर्ट भेजी: {len(today_ids)}\n"
        f"⏳ रिपोर्ट नहीं भेजी: {pending_count}\n\n"
        f"🏆 लगातार रिपोर्टिंग करने वाले:\n"
        f"{leaderboard if leaderboard else 'अभी कोई डेटा उपलब्ध नहीं है।'}"
    )

async def post_summary_for_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    text = await _build_summary_text(context, chat_id)
    await context.bot.send_message(chat_id=chat_id, text=text)

async def post_awards_for_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    member_ids = set(known_users[chat_id].keys())
    top_streaks = sorted(
        [(uid, streaks[chat_id].get(uid, 0)) for uid in member_ids],
        key=lambda x: x[1],
        reverse=True
    )[:5]
    if not top_streaks or top_streaks[0][1] == 0:
        return
    medals = ["🥇", "🥈", "🥉", "🎖️", "🏅"]
    for i, (uid, count) in enumerate(top_streaks):
        name = known_users[chat_id].get(uid, f"User {uid}")
        msg = f"{medals[i]} *{name}*, आप आज #{i+1} स्थान पर हैं — {count} दिनों की शानदार रिपोर्टिंग के साथ! 🎉👏"
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

# ---------- Scheduler ----------
def schedule_reports(app):
    jq = app.job_queue
    times = [(14, 0), (18, 0)]
    for cid in ALLOWED_CHAT_IDS:
        for hh, mm in times:
            jq.run_daily(callback=job_summary, time=time(hour=hh, minute=mm, tzinfo=IST), data=cid)
            jq.run_daily(callback=job_awards, time=time(hour=hh, minute=mm+2, tzinfo=IST), data=cid)
        # ⏰ Schedule video post at 10:00 AM
        jq.run_daily(callback=job_video_post, time=time(hour=10, minute=0, tzinfo=IST), data=cid)

# ---------- Entry ----------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    load_state()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("members", cmd_members))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("video", cmd_video))  # 👈 new

    app.add_handler(MessageHandler(filters.PHOTO & (filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP), handle_photo))
    app.add_handler(ChatMemberHandler(track_new_members, ChatMemberHandler.CHAT_MEMBER))

    schedule_reports(app)

    print("Bot online. Waiting for updates...")
    app.run_polling(drop_pending_updates=True)
