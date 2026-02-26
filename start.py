#!/usr/bin/env python3
import os
import sys
import subprocess
import threading
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_bot():
    """Run the Telegram bot"""
    try:
        logger.info("🤖 Starting Telegram bot...")
        # Give the web server a moment to start
        time.sleep(3)
        subprocess.run([sys.executable, "bot.py"])
    except Exception as e:
        logger.error(f"Bot error: {e}")

def run_webapp():
    """Run the web server"""
    try:
        port = int(os.getenv('PORT', 8000))
        logger.info(f"🌐 Starting web server on port {port}...")
        
        # Import and run webapp directly
        import uvicorn
        from webapp import app
        
        uvicorn.run(app, host="0.0.0.0", port=port)
    except Exception as e:
        logger.error(f"Webapp error: {e}")
        sys.exit(1)

def create_directories():
    """Create necessary directories"""
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static", exist_ok=True)
    logger.info("✅ Directories created")

def generate_cards_if_needed():
    """Generate bingo cards if they don't exist"""
    import json
    import random
    
    cards_file = "static/bingo_cards.json"
    
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

if __name__ == "__main__":
    logger.info("🚀 Starting Bingo Game System...")
    
    # Setup
    create_directories()
    generate_cards_if_needed()
    
    # Check for required token
    if not os.getenv('BOT_TOKEN'):
        logger.error("❌ BOT_TOKEN environment variable not set!")
        sys.exit(1)
    
    logger.info(f"✅ BOT_TOKEN found: {os.getenv('BOT_TOKEN')[:10]}...")
    logger.info(f"✅ ADMIN_USER_ID: {os.getenv('ADMIN_USER_ID', 'Not set')}")
    
    # Start bot in background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Run webapp in main thread (this blocks)
    run_webapp()