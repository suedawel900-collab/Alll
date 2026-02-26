#!/usr/bin/env python3
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID', '8741250511')
BASE_URL = os.getenv('RAILWAY_PUBLIC_DOMAIN', 'https://your-app.railway.app')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) started the bot")
    
    # Create web app button
    web_app_url = f"{BASE_URL}/game?user_id={user.id}&game_id=1"
    
    keyboard = [[
        InlineKeyboardButton(
            "🎮 Open Bingo Game",
            web_app={'url': web_app_url}
        )
    ]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 Welcome {user.first_name} to Bingo Bot!\n\n"
        f"Click the button below to start playing:",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    await update.message.reply_text(
        "🎮 **How to Play Bingo:**\n\n"
        "1. Click 'Open Bingo Game'\n"
        "2. Select your cards (10 ETB each)\n"
        "3. Wait for admin to start the game\n"
        "4. Numbers are called every 2 seconds\n"
        "5. Mark numbers on your card\n"
        "6. Click BINGO when you have 5 in a row!\n\n"
        "💰 **Payment Methods:**\n"
        "• Telbirr: Send to 0953933030 via *127#\n"
        "• CBE Birr: Send to 0953933030 via *847#",
        parse_mode='Markdown'
    )

def main():
    """Main function to run the bot"""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set!")
        return
    
    logger.info("🤖 Initializing bot...")
    
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    
    logger.info("✅ Bot initialized, starting polling...")
    
    # Start polling
    app.run_polling(allowed_updates=['message'])

if __name__ == "__main__":
    main()