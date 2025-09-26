# main.py

import os
import asyncio
import io
from dotenv import load_dotenv
from PIL import Image
import google.generativeai as genai
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# --- Load Environment Variables ---
load_dotenv()
TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
TELETHON_SESSION = os.getenv('TELETHON_SESSION')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# --- Bot State ---
BOT_IS_ACTIVE = True
greeted_users = set()
chat_histories = {}

# --- Gemini AI Configuration ---
genai.configure(api_key=GEMINI_API_KEY)
SYSTEM_PROMPT = """
You are Fady, an AI assistant representing Fahad. Professional, polite, approachable, and responding in concise Hinglish. 
Use English if user uses English. Describe images neutrally, keep answers 2–3 lines unless necessary.
Do not drag answers into follow-up questions. If unsure, ask for clarification.
If the user wants to chat about some development topic, get nessarry details and then say i have stored your info about your project and i will inform fahad about it when he is back.
Always try to answer in the language the user used to ask the question.
"""
model = genai.GenerativeModel('gemini-2.5-flash', system_instruction=SYSTEM_PROMPT)

# --- Telegram Client ---
client = TelegramClient(StringSession(TELETHON_SESSION), TELEGRAM_API_ID, TELEGRAM_API_HASH)

print("🤖 User bot started...")

# --- Bot Commands (from self-chat) ---
@client.on(events.NewMessage(outgoing=True, chats='me'))
async def handle_commands(event):
    global BOT_IS_ACTIVE
    cmd = event.message.text.lower()
    if cmd == '/bot_sleep':
        BOT_IS_ACTIVE = False
        await event.edit("Bot is now asleep. 😴")
    elif cmd == '/bot_wakeup':
        BOT_IS_ACTIVE = True
        await event.edit("Bot is now awake. 😎")

# --- Incoming Messages Handler ---
@client.on(events.NewMessage(incoming=True))
async def handle_messages(event):
    if not BOT_IS_ACTIVE or not event.is_private:
        return

    sender = await event.get_sender()
    me = await client.get_me()
    if sender.id == me.id:
        return

    user_id = sender.id

    # --- Initial Greeting ---
    if user_id not in greeted_users:
        intro = (
            "Hey, this is Fahad's AI assistant. "
            "He's not here at the moment, but I can help you with any topic or pass a message along."
        )
        await event.reply(intro)
        greeted_users.add(user_id)
        return

    # --- Process Conversation ---
    try:
        if user_id not in chat_histories:
            chat_histories[user_id] = []

        user_message_parts = []

        # Text message
        if event.message.text:
            user_message_parts.append(event.message.text)

        # Photo message
        if event.photo:
            photo_bytes = await event.download_media(file=bytes)
            pil_image = Image.open(io.BytesIO(photo_bytes))
            user_message_parts.append(pil_image)

        chat_histories[user_id].append({'role': 'user', 'parts': user_message_parts})

        # Send to Gemini AI
        conversation = model.start_chat(history=chat_histories[user_id])
        response = conversation.send_message(user_message_parts)

        # Save AI response
        chat_histories[user_id].append(response.candidates[0].content)

        # Trim chat history to last 10 messages
        if len(chat_histories[user_id]) > 10:
            chat_histories[user_id] = chat_histories[user_id][-10:]

        await event.reply(response.text)

    except Exception as e:
        await event.reply("Sorry, something went wrong. Let's start over.")
        chat_histories.pop(user_id, None)

# --- Main ---
async def main():
    try:
        await client.start()
        print("✅ Client connected and listening for messages.")
        await client.run_until_disconnected()
    except Exception as e:
        msg = str(e)
        if "database is locked" in msg or "AuthKeyUnregisteredError" in msg:
            print("SESSION ERROR: Your session is invalid or expired. Generate a new session string.")
        else:
            print(f"Unexpected startup error: {e}")

if __name__ == '__main__':
    client.loop.run_until_complete(main())
