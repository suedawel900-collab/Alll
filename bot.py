import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

from models import Database

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize database
db = Database()

# Conversation states
PHONE, AMOUNT = range(2)

# Environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID', '8741250511')
BASE_URL = os.getenv('RAILWAY_PUBLIC_DOMAIN', 'https://your-app.railway.app')

# Game settings
CARD_PRICE = 1000  # 10 ETB in cents

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    
    # Get or create user
    user_data = db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Check if phone number exists
    if not user_data.get('phone_number'):
        contact_button = KeyboardButton("📱 Share Phone Number", request_contact=True)
        reply_markup = ReplyKeyboardMarkup(
            [[contact_button]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        
        await update.message.reply_text(
            "👋 Welcome to Bingo Bot!\n\nPlease share your phone number to continue:",
            reply_markup=reply_markup
        )
        return
    
    await show_main_menu(update, context)

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle shared contact"""
    contact = update.message.contact
    user = update.effective_user
    
    # Update user with phone number
    db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        phone_number=contact.phone_number
    )
    
    await update.message.reply_text(
        "✅ Phone number saved!",
        reply_markup=ReplyKeyboardRemove()
    )
    
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu"""
    user = update.effective_user
    user_data = db.get_user(user.id) or {'balance': 1000}
    
    balance = user_data['balance'] / 100
    
    keyboard = [
        [InlineKeyboardButton("🎮 Play Bingo", callback_data="play")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance"),
         InlineKeyboardButton("💳 Deposit", callback_data="deposit")],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ]
    
    # Add admin button if user is admin
    if str(user.id) == ADMIN_USER_ID:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = f"👋 Welcome {user.first_name}!\n💰 Balance: {balance:.2f} ETB"
    
    if update.message:
        await update.message.reply_text(message, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)

async def play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Launch game"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_data = db.get_user(user.id) or {'balance': 1000}
    
    if user_data['balance'] < CARD_PRICE:
        await query.edit_message_text(
            f"❌ Insufficient balance!\nYou need {CARD_PRICE/100:.2f} ETB to play.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💳 Deposit", callback_data="deposit")
            ]])
        )
        return
    
    # Get or create active game
    game = db.get_active_game()
    if not game:
        game_id = db.create_game()
    else:
        game_id = game['id']
    
    webapp_url = f"{BASE_URL}/game?user_id={user.id}&game_id={game_id}"
    
    keyboard = [[InlineKeyboardButton("🎮 Open Bingo Game", web_app={'url': webapp_url})]]
    await query.edit_message_text(
        "Click below to open the game:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show balance"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_data = db.get_user(user.id) or {'balance': 1000, 'games_played': 0, 'games_won': 0}
    
    balance = user_data['balance'] / 100
    games_played = user_data['games_played']
    games_won = user_data['games_won']
    
    await query.edit_message_text(
        f"💰 **Your Balance**\n\n"
        f"Current: **{balance:.2f} ETB**\n"
        f"Games Played: {games_played}\n"
        f"Games Won: {games_won}",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Back", callback_data="main_menu")
        ]])
    )

async def deposit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show deposit options"""
    query = update.callback_query
    await query.answer()
    
    methods = db.get_payment_methods()
    keyboard = []
    
    for method in methods:
        emoji = "💚" if "CBE" in method['name'] else "🔵"
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {method['name']}", 
            callback_data=f"deposit_{method['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="main_menu")])
    
    await query.edit_message_text(
        "Choose payment method:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def deposit_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment method selection"""
    query = update.callback_query
    await query.answer()
    
    method_id = int(query.data.split('_')[1])
    method = db.get_payment_method(method_id)
    context.user_data['method'] = method
    
    await query.edit_message_text(
        f"{method['name']}\n\nEnter amount in ETB:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Cancel", callback_data="deposit")
        ]])
    )
    return AMOUNT

async def amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit amount"""
    try:
        amount = float(update.message.text.strip())
        amount_cents = int(amount * 100)
        
        method = context.user_data.get('method')
        if not method:
            await update.message.reply_text("Please start over")
            return ConversationHandler.END
        
        user = update.effective_user
        user_data = db.get_user(user.id)
        phone = user_data.get('phone_number') if user_data else None
        
        request_id = db.create_payment_request(
            user.id, 
            method['id'], 
            amount_cents, 
            phone
        )
        
        message = f"""
{method['instructions']}

💰 Amount: {amount:.2f} ETB
📱 Send to: {method['account_number']}
🆔 Request ID: `{request_id}`

After payment, send the reference number to admin.
        """
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
        # Notify admin
        if ADMIN_USER_ID:
            await context.bot.send_message(
                ADMIN_USER_ID,
                f"💰 New payment request:\n"
                f"User: {user.first_name} (ID: {user.id})\n"
                f"Amount: {amount:.2f} ETB\n"
                f"Method: {method['name']}\n"
                f"Request ID: {request_id}"
            )
        
    except ValueError:
        await update.message.reply_text("Please enter a valid number")
        return AMOUNT
    
    return ConversationHandler.END

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel"""
    query = update.callback_query
    await query.answer()
    
    if str(update.effective_user.id) != ADMIN_USER_ID:
        await query.edit_message_text("❌ Unauthorized")
        return
    
    await query.edit_message_text(
        "👑 Admin Panel\n\nUse the bot to manage payments.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Back", callback_data="main_menu")
        ]])
    )

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help"""
    query = update.callback_query
    await query.answer()
    
    help_text = """
🎮 **How to Play Bingo:**
1. Click "Play Bingo" and open the game
2. Select your cards (10 ETB each)
3. Wait for admin to start the game
4. Numbers are called every 2 seconds
5. Mark numbers on your card
6. Click BINGO when you have 5 in a row!

💰 **Payment Methods:**
• Telbirr: Send to 0953933030 via *127#
• CBE Birr: Send to 0953933030 via *847#

📞 **Support:** @Treeeeestbot
    """
    
    await query.edit_message_text(
        help_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Back", callback_data="main_menu")
        ]])
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    await update.message.reply_text("Cancelled")
    return ConversationHandler.END

def main():
    """Main function to run the bot"""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set!")
        return
    
    try:
        # Create application
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Command handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.CONTACT, contact_handler))
        
        # Callback handlers
        app.add_handler(CallbackQueryHandler(show_main_menu, pattern="^main_menu$"))
        app.add_handler(CallbackQueryHandler(play_callback, pattern="^play$"))
        app.add_handler(CallbackQueryHandler(balance_callback, pattern="^balance$"))
        app.add_handler(CallbackQueryHandler(deposit_callback, pattern="^deposit$"))
        app.add_handler(CallbackQueryHandler(help_callback, pattern="^help$"))
        app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin$"))
        
        # Deposit conversation
        deposit_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(deposit_method_callback, pattern="^deposit_\\d+$")],
            states={AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_handler)]},
            fallbacks=[CommandHandler("cancel", cancel)]
        )
        app.add_handler(deposit_conv)
        
        logger.info("🤖 Bot started successfully")
        
        # Start the bot
        app.run_polling(allowed_updates=['message', 'callback_query'])
        
    except Exception as e:
        logger.error(f"Bot error: {e}")

if __name__ == "__main__":
    main()