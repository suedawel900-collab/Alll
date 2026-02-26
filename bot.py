import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')
BASE_URL = os.getenv('RAILWAY_PUBLIC_DOMAIN', 'https://your-app.railway.app')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Welcome {user.first_name} to Bingo Bot!\n\n"
        f"Use the button below to play:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🎮 Play Bingo", web_app={'url': f"{BASE_URL}/game?user_id={user.id}&game_id=1"})
        ]])
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 How to Play:\n"
        "1. Click Play Bingo\n"
        "2. Select your cards\n"
        "3. Wait for admin to start\n"
        "4. Mark numbers as called\n"
        "5. Click BINGO when you win!"
    )

def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    
    logger.info("🤖 Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()