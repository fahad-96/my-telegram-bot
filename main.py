# main.py

import os
import io
import base64
import asyncio
import logging
import sqlite3
from dotenv import load_dotenv
from PIL import Image
import google.generativeai as genai
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("MultiBot")

# --- Load Environment Variables ---
load_dotenv()
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Account Settings (MANDATORY from .env) ---
TELETHON_SESSION_1 = os.getenv("TELETHON_SESSION_1")
SYSTEM_PROMPT_1 = os.getenv("SYSTEM_PROMPT_1")
TELETHON_SESSION_2 = os.getenv("TELETHON_SESSION_2")
SYSTEM_PROMPT_2 = os.getenv("SYSTEM_PROMPT_2")

# Validate required env vars
required_vars = {
    "TELEGRAM_API_ID": TELEGRAM_API_ID,
    "TELEGRAM_API_HASH": TELEGRAM_API_HASH,
    "GEMINI_API_KEY": GEMINI_API_KEY,
    "TELETHON_SESSION_1": TELETHON_SESSION_1,
    "SYSTEM_PROMPT_1": SYSTEM_PROMPT_1,
    "TELETHON_SESSION_2": TELETHON_SESSION_2,
    "SYSTEM_PROMPT_2": SYSTEM_PROMPT_2,
}
missing = [k for k, v in required_vars.items() if not v]
if missing:
    raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

# --- Gemini AI Configuration ---
genai.configure(api_key=GEMINI_API_KEY)

# --- SQLite Setup (Persistent History) ---
DB_PATH = "chat_history.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    role TEXT,
    content TEXT
)
""")
conn.commit()

def save_message(user_id, role, content):
    cur.execute("INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, role, content))
    conn.commit()

def load_history(user_id, limit=10):
    cur.execute("SELECT role, content FROM conversations WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit))
    rows = cur.fetchall()
    return [{"role": r, "parts": [c]} for r, c in reversed(rows)]


# --- Utility: Encode PIL image for Gemini ---
def encode_image(pil_image):
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    img_bytes = buf.getvalue()
    return {
        "mime_type": "image/png",
        "data": base64.b64encode(img_bytes).decode("utf-8")
    }


# --- Main Bot Logic ---
async def run_bot(account_name, session_string, system_prompt):
    logger.info(f"🤖 Starting bot for {account_name}")

    client = TelegramClient(StringSession(session_string), TELEGRAM_API_ID, TELEGRAM_API_HASH)
    model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system_prompt)

    BOT_IS_ACTIVE = True
    greeted_users = set()

    # --- Self commands (/bot_sleep & /bot_wakeup) ---
    @client.on(events.NewMessage(outgoing=True, chats="me"))
    async def handle_commands(event):
        nonlocal BOT_IS_ACTIVE
        cmd = event.message.text.lower()
        if cmd == "/bot_sleep":
            BOT_IS_ACTIVE = False
            await event.edit(f"Bot for {account_name} is now asleep. 😴")
        elif cmd == "/bot_wakeup":
            BOT_IS_ACTIVE = True
            await event.edit(f"Bot for {account_name} is now awake. 😎")

    # --- Incoming Messages ---
    @client.on(events.NewMessage(incoming=True))
    async def handle_messages(event):
        nonlocal BOT_IS_ACTIVE
        sender = await event.get_sender()

        if not BOT_IS_ACTIVE or not event.is_private or sender.bot:
            return

        me = await client.get_me()
        if sender.id == me.id:
            return

        user_id = sender.id

        # --- First-time greeting ---
        if user_id not in greeted_users:
            intro = (
                f"Hey, this is {me.first_name}'s Super Power Bot. "
                "He's not here at the moment, but I can help you with any topic or pass a message along."
            )
            await event.reply(intro)
            greeted_users.add(user_id)
            return

        # --- THIS ENTIRE 'TRY' BLOCK IS CORRECTED ---
        try:
            # --- Collect user message ---
            parts = []
            user_text_message = None
            if event.message.text:
                user_text_message = event.message.text
                parts.append(user_text_message)
            if event.photo:
                photo_bytes = await event.download_media(file=bytes)
                pil_img = Image.open(io.BytesIO(photo_bytes))
                parts.append(encode_image(pil_img))

            if not parts:
                return

            # --- MOVED: Load PAST history first ---
            history = load_history(user_id, limit=10)

            # --- Ask Gemini ---
            conversation = model.start_chat(history=history)
            response = await conversation.send_message_async(parts)

            # --- MOVED: Save the conversation turn AFTER getting a successful response ---
            # Save the user's message
            if user_text_message:
                save_message(user_id, "user", user_text_message)
            else: # If it was just an image
                save_message(user_id, "user", "[Image]")
            
            # Save the model's reply
            reply_text = response.text or "Sorry, I couldn't generate a reply."
            save_message(user_id, "model", reply_text)

            await event.reply(reply_text)

        except Exception as e:
            logger.exception(f"Error in {account_name}: {e}")
            await event.reply("⚠️ Oops, something went wrong. Let's continue fresh.")

    try:
        await client.start()
        logger.info(f"✅ Client for {account_name} connected and listening.")
        await client.run_until_disconnected()
    except Exception as e:
        logger.critical(f"CRITICAL ERROR for {account_name}: {e}")
        if "database is locked" in str(e) or "AuthKeyUnregisteredError" in str(e):
            logger.error(f"SESSION ERROR for {account_name}: Invalid/expired session. Regenerate it.")


# --- Entry Point ---
async def main():
    tasks = [
        run_bot("Account 1", TELETHON_SESSION_1, SYSTEM_PROMPT_1),
        run_bot("Account 2", TELETHON_SESSION_2, SYSTEM_PROMPT_2),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error(f"Bot {i+1} crashed with error: {r}")


if __name__ == "__main__":
    logger.info("🚀 Starting multi-account bot manager...")
    asyncio.run(main())
