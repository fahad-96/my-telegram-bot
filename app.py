from flask import Flask
import threading
import asyncio
from main import main as run_bot

app = Flask(__name__)

def run_async_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_bot())
    loop.close()

@app.route('/')
def hello_world():
    return 'Bot is running in the background!'

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_async_bot)
    bot_thread.start()
    app.run(host='0.0.0.0', port=10000)