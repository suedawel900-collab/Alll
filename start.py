#!/usr/bin/env python3
import os
import sys
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_webapp():
    """Run the web server"""
    try:
        port = int(os.getenv('PORT', 8000))
        logger.info(f"🌐 Starting web server on port {port}...")
        
        # Import and run uvicorn
        import uvicorn
        import webapp
        
        uvicorn.run(
            "webapp:app",
            host="0.0.0.0",
            port=port,
            log_level="info"
        )
    except Exception as e:
        logger.error(f"Webapp error: {e}")
        sys.exit(1)

def run_bot():
    """Run the Telegram bot"""
    try:
        logger.info("🤖 Starting Telegram bot...")
        # Give web server time to start
        time.sleep(2)
        
        # Import and run bot
        import bot
        bot.main()
    except Exception as e:
        logger.error(f"Bot error: {e}")

if __name__ == "__main__":
    logger.info("🚀 Starting Bingo Game System...")
    
    # Check for required environment variables
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        logger.error("❌ BOT_TOKEN environment variable not set!")
        logger.info("Please add BOT_TOKEN to Railway environment variables")
        sys.exit(1)
    
    logger.info(f"✅ BOT_TOKEN found: {bot_token[:10]}...")
    logger.info(f"✅ ADMIN_USER_ID: {os.getenv('ADMIN_USER_ID', 'Not set')}")
    
    # Create necessary directories
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static", exist_ok=True)
    logger.info("✅ Directories created")
    
    # Start bot in a separate thread
    import threading
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Run webapp in main thread
    run_webapp()