import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

from models import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = Database()

# States
PHONE, AMOUNT = range(2)

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')
BASE_URL = os.getenv('RAILWAY_PUBLIC_DOMAIN', 'https://your-app.railway.app')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    
    if not user_data.get('phone_number'):
        contact_btn = KeyboardButton("📱 Share Phone Number", request_contact=True)
        reply_markup = ReplyKeyboardMarkup([[contact_btn]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Welcome! Please share your phone number:", reply_markup=reply_markup)
        return
    
    await show_main_menu(update, context)

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user = update.effective_user
    
    db.get_or_create_user(user.id, user.username, user.first_name, user.last_name, contact.phone_number)
    
    await update.message.reply_text("✅ Phone number saved!", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id) or {'balance': 1000}
    
    keyboard = [
        [InlineKeyboardButton("🎮 Play Bingo", callback_data="play")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance"),
         InlineKeyboardButton("💳 Deposit", callback_data="deposit")],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ]
    
    if str(user.id) == ADMIN_USER_ID:
        keyboard.append([InlineKeyboardButton("👑 Admin", callback_data="admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = f"Welcome {user.first_name}!\nBalance: {user_data['balance']/100:.2f} ETB"
    
    if update.message:
        await update.message.reply_text(msg, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(msg, reply_markup=reply_markup)

async def play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    webapp_url = f"{BASE_URL}/game?user_id={user.id}&game_id=1"
    
    keyboard = [[InlineKeyboardButton("🎮 Open Bingo", web_app={'url': webapp_url})]]
    await query.edit_message_text("Click to play:", reply_markup=InlineKeyboardMarkup(keyboard))

async def balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_data = db.get_user(user.id) or {'balance': 1000}
    
    await query.edit_message_text(
        f"💰 Your Balance: {user_data['balance']/100:.2f} ETB",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="main_menu")]])
    )

async def deposit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    methods = db.get_payment_methods()
    keyboard = []
    
    for m in methods:
        emoji = "💚" if "CBE" in m['name'] else "🔵"
        keyboard.append([InlineKeyboardButton(f"{emoji} {m['name']}", callback_data=f"deposit_{m['id']}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="main_menu")])
    await query.edit_message_text("Choose payment method:", reply_markup=InlineKeyboardMarkup(keyboard))

async def deposit_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    method_id = int(query.data.split('_')[1])
    method = db.get_payment_method(method_id)
    context.user_data['method'] = method
    
    await query.edit_message_text(
        f"{method['name']}\n\nEnter amount in ETB:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancel", callback_data="deposit")]])
    )
    return AMOUNT

async def amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
        amount_cents = int(amount * 100)
        
        method = context.user_data.get('method')
        if not method:
            await update.message.reply_text("Please start over")
            return ConversationHandler.END
        
        user = update.effective_user
        request_id = db.create_payment_request(user.id, method['id'], amount_cents)
        
        msg = f"""
{method['instructions']}

💰 Amount: {amount:.2f} ETB
📱 Send to: {method['account_number']}
🆔 Request ID: `{request_id}`

After payment, send the reference number to admin.
        """
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
        # Notify admin
        if ADMIN_USER_ID:
            await context.bot.send_message(
                ADMIN_USER_ID,
                f"💰 New payment request: {amount:.2f} ETB from {user.first_name}"
            )
        
    except ValueError:
        await update.message.reply_text("Please enter a valid number")
        return AMOUNT
    
    return ConversationHandler.END

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if str(update.effective_user.id) != ADMIN_USER_ID:
        await query.edit_message_text("Unauthorized")
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Pending Payments", callback_data="admin_payments")],
        [InlineKeyboardButton("◀️ Back", callback_data="main_menu")]
    ]
    await query.edit_message_text("Admin Panel", reply_markup=InlineKeyboardMarkup(keyboard))

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    help_text = """
🎮 How to Play:
1. Click Play Bingo
2. Select your cards (10 ETB each)
3. Wait for admin to start
4. Mark numbers as called
5. Click BINGO when you win!

💰 Payments:
• Telbirr: *127#
• CBE Birr: *847#
• Send to: 0953933030
    """
    
    await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Back", callback_data="main_menu")
    ]]))

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled")
    return ConversationHandler.END

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    
    # Callbacks
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
    
    logger.info("🤖 Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()