import os
import sys
import subprocess
import threading
import time
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
    """Run the web server"""
    try:
        port = int(os.getenv('PORT', 8000))
        logger.info(f"🌐 Starting web server on port {port}...")
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "webapp:app",
            "--host", "0.0.0.0",
            "--port", str(port)
        ])
    except Exception as e:
        logger.error(f"Webapp error: {e}")

def generate_cards_if_needed():
    """Generate bingo cards if they don't exist"""
    import json
    import random
    import os
    
    cards_file = "static/bingo_cards.json"
    if os.path.exists(cards_file):
        logger.info("✅ Cards already exist")
        return
    
    logger.info("📊 Generating 1000 bingo cards...")
    os.makedirs("static", exist_ok=True)
    
    cards = []
    for card_id in range(1, 1001):
        card = []
        ranges = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75)]
        
        for col in range(5):
            min_num, max_num = ranges[col]
            numbers = random.sample(range(min_num, max_num + 1), 5)
            card.append(numbers)
        
        card[2][2] = "FREE"
        cards.append({"id": card_id, "card": card})
    
    with open(cards_file, "w") as f:
        json.dump(cards, f)
    
    logger.info(f"✅ Generated {len(cards)} cards")

if __name__ == "__main__":
    logger.info("🚀 Starting Bingo Game System...")
    
    # Create necessary directories
    os.makedirs("static", exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    
    # Generate cards
    generate_cards_if_needed()
    
    # Start bot in background
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Run webapp in main thread
    run_webapp()