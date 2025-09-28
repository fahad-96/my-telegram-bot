from flask import Flask
import threading
import asyncio
from main import main as run_bot

app = Flask(__name__)

def run_async_bot():
    """Sets up and runs the bot in a new asyncio event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_bot())
    loop.close()

@app.route('/')
def hello_world():
    """Endpoint for uptime monitor to hit."""
    return 'Bot is running in the background!'

bot_thread = threading.Thread(target=run_async_bot)
bot_thread.daemon = True  # Allows the main app to exit even if the thread is running
bot_thread.start()

# This block is now only used for running the app locally for testing.
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
