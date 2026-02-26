import os
import sys
import subprocess
import threading
import logging
import json
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_cards_if_needed():
    """Generate bingo cards if they don't exist"""
    cards_file = "static/bingo_cards.json"
    
    # Create static directory
    os.makedirs("static", exist_ok=True)
    
    if os.path.exists(cards_file):
        logger.info("✅ Cards already exist")
        return
    
    logger.info("📊 Generating 1000 bingo cards...")
    
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

def run_bot():
    """Run the Telegram bot"""
    try:
        logger.info("🤖 Starting Telegram bot...")
        # Use sys.executable to ensure we use the same Python interpreter
        subprocess.run([sys.executable, "bot.py"])
    except Exception as e:
        logger.error(f"Bot error: {e}")

def run_webapp():
    """Run the web server"""
    try:
        port = int(os.getenv('PORT', 8000))
        logger.info(f"🌐 Starting web server on port {port}...")
        # Run with uvicorn
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "webapp:app",
            "--host", "0.0.0.0",
            "--port", str(port)
        ])
    except Exception as e:
        logger.error(f"Webapp error: {e}")

if __name__ == "__main__":
    logger.info("🚀 Starting Bingo Game System...")
    
    # Create necessary directories
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static", exist_ok=True)
    
    # Generate cards
    generate_cards_if_needed()
    
    # Start bot in background
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Run webapp in main thread
    run_webapp()