#!/usr/bin/env python3
import os
import sys
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("🚀 Starting Bingo Game System...")
    
    # Print environment info
    logger.info(f"PORT: {os.getenv('PORT', '8000')}")
    logger.info(f"BOT_TOKEN exists: {'Yes' if os.getenv('BOT_TOKEN') else 'No'}")
    
    # Import here to avoid circular imports
    import uvicorn
    import webapp
    
    # Run the web server
    port = int(os.getenv('PORT', 8000))
    logger.info(f"🌐 Starting web server on port {port}")
    uvicorn.run(webapp.app, host="0.0.0.0", port=port)