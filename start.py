import os
import subprocess
import sys
import time
import threading
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_bot():
    """Run the Telegram bot"""
    try:
        logger.info("🤖 Starting Telegram bot...")
        subprocess.run([sys.executable, "bot.py"])
    except Exception as e:
        logger.error(f"Bot error: {e}")

def run_webapp():
    """Run the webapp server"""
    try:
        port = int(os.getenv('PORT', 8000))
        logger.info(f"🌐 Starting webapp on port {port}...")
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "webapp:app", 
            "--host", "0.0.0.0", 
            "--port", str(port)
        ])
    except Exception as e:
        logger.error(f"Webapp error: {e}")

if __name__ == "__main__":
    logger.info("🚀 Starting Bingo Game Server...")
    
    # Generate cards if they don't exist
    if not os.path.exists("static/bingo_cards.json"):
        logger.info("📊 Generating bingo cards...")
        import generate_cards
        generate_cards.generate_bingo_cards(1000)
    
    # Create static directory if it doesn't exist
    os.makedirs("static", exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    
    # Run both services
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Run webapp in main thread
    run_webapp()