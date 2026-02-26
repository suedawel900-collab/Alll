import os
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

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
AMOUNT = 1
PHONE = 2
REFERENCE = 3
WITHDRAW_AMOUNT = 4
WITHDRAW_PHONE = 5
WITHDRAW_NAME = 6

# Environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID', '8741250511')
BASE_URL = os.getenv('RAILWAY_PUBLIC_DOMAIN', 'https://bingo-production.up.railway.app')
WEBAPP_URL = f"{BASE_URL}/game"

# Game settings
CARD_PRICE = 1000  # 10 ETB in cents
WELCOME_BONUS = 1000  # 10 ETB

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
        contact_button = KeyboardButton("📱 ስልክ ቁጥር ያጋሩ / Share Phone Number", request_contact=True)
        reply_markup = ReplyKeyboardMarkup(
            [[contact_button]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        
        await update.message.reply_text(
            "👋 እንኳን ወደ ቢንጎ ቦት በደህና መጡ!\n\n"
            "Welcome to Bingo Bot!\n\n"
            "እባክዎ ስልክ ቁጥርዎን ያጋሩ:\n"
            "Please share your phone number:",
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
        "✅ ስልክ ቁጥር ተቀምጧል!\nPhone number saved!",
        reply_markup=ReplyKeyboardRemove()
    )
    
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu"""
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if not user_data:
        user_data = {'balance': 1000, 'games_played': 0, 'games_won': 0}
    
    balance = user_data['balance'] / 100
    
    keyboard = [
        [InlineKeyboardButton("🎮 ተጫወት / Play", callback_data="play")],
        [InlineKeyboardButton("💰 ሂሳብ / Balance", callback_data="balance"),
         InlineKeyboardButton("💳 ገንዘብ ጨምር / Deposit", callback_data="deposit")],
        [InlineKeyboardButton("💸 ገንዘብ አውጣ / Withdraw", callback_data="withdraw"),
         InlineKeyboardButton("📊 ታሪክ / History", callback_data="history")],
        [InlineKeyboardButton("❓ እገዛ / Help", callback_data="help")]
    ]
    
    # Add admin button if admin
    if str(user.id) == ADMIN_USER_ID:
        keyboard.append([InlineKeyboardButton("👑 አስተዳዳሪ / Admin", callback_data="admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = (
        f"🎯 እንኳን ደህና መጡ {user.first_name}!\n"
        f"Welcome {user.first_name}!\n\n"
        f"💰 ሂሳብ / Balance: **{balance:.2f} ETB**\n"
        f"🎮 የተጫወቱት / Games: {user_data['games_played']} | "
        f"🏆 ያሸነፉት / Wins: {user_data['games_won']}\n\n"
        f"ምርጫዎን ያድርጉ:\n"
        f"Choose an option:"
    )
    
    if update.message:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Launch game"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if user_data['balance'] < CARD_PRICE:
        await query.edit_message_text(
            f"❌ በቂ ገንዘብ የለዎትም!\n"
            f"Insufficient balance!\n\n"
            f"ያለዎት: {user_data['balance']/100:.2f} ETB\n"
            fያስፈልጋል: {CARD_PRICE/100:.2f} ETB",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💳 ገንዘብ ጨምር / Deposit", callback_data="deposit")
            ]])
        )
        return
    
    # Get or create active game
    game = db.get_active_game()
    if not game:
        game_id = db.create_game()
    else:
        game_id = game['id']
    
    webapp_url = f"{WEBAPP_URL}?user_id={user.id}&game_id={game_id}"
    
    keyboard = [[
        InlineKeyboardButton(
            "🎮 ቢንጎ ክፈት / Open Bingo", 
            web_app={'url': webapp_url}
        )
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🎮 **ቢንጎ ተጫወት / Play Bingo**\n\n"
        f"ዋጋ / Price: {CARD_PRICE/100:.2f} ETB በካርድ / per card\n"
        f"ሂሳብ / Balance: {user_data['balance']/100:.2f} ETB\n\n"
        f"ከ1000 ካርዶች ይምረጡ!\n"
        f"Choose from 1000 unique cards!",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show balance"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    balance = user_data['balance'] / 100
    total_deposits = user_data['total_deposits'] / 100
    total_withdrawals = user_data['total_withdrawals'] / 100
    
    await query.edit_message_text(
        f"💰 **ሂሳብዎ / Your Balance**\n\n"
        f"ያለዎት / Current: **{balance:.2f} ETB**\n"
        f"ያስገቡት / Deposits: {total_deposits:.2f} ETB\n"
        f"ያወጡት / Withdrawals: {total_withdrawals:.2f} ETB",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ ተመለስ / Back", callback_data="main_menu")
        ]])
    )

async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show deposit options"""
    query = update.callback_query
    await query.answer()
    
    methods = db.get_payment_methods()
    
    keyboard = []
    for method in methods:
        emoji = "💚" if "CBE" in method['name'] else "🔵"
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {method['name']}", 
            callback_data=f"deposit_method_{method['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("◀️ ተመለስ / Back", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "💳 **የክፍያ ዘዴ ይምረጡ**\n"
        "**Choose Payment Method**\n\n"
        "ቴሌቢር ወይም ሲቢኢ ቢር ይምረጡ:\n"
        "Choose Telbirr or CBE Birr:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def deposit_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment method selection"""
    query = update.callback_query
    await query.answer()
    
    method_id = int(query.data.split('_')[2])
    method = db.get_payment_method(method_id)
    
    context.user_data['payment_method'] = method
    
    await query.edit_message_text(
        f"{method['name']}\n\n"
        f"መጠኑን ያስገቡ (ETB):\n"
        f"Enter amount in ETB:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ ተመለስ / Back", callback_data="deposit")
        ]])
    )
    return AMOUNT

async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit amount"""
    try:
        amount = float(update.message.text.strip())
        amount_cents = int(amount * 100)
        
        method = context.user_data.get('payment_method')
        if not method:
            await update.message.reply_text("❌ እባክዎ እንደገና ይጀምሩ / Please start over")
            return ConversationHandler.END
        
        if amount_cents < method['min_amount']:
            await update.message.reply_text(f"❌ ዝቅተኛው {method['min_amount']/100:.0f} ETB ነው")
            return AMOUNT
        if amount_cents > method['max_amount']:
            await update.message.reply_text(f"❌ ከፍተኛው {method['max_amount']/100:.0f} ETB ነው")
            return AMOUNT
        
        context.user_data['deposit_amount'] = amount_cents
        
        await update.message.reply_text(
            "📱 **ስልክ ቁጥርዎን ያስገቡ**\n"
            "**Enter your phone number**\n\n"
            "ለምሳሌ / Example: 0912345678",
            parse_mode='Markdown'
        )
        return PHONE
        
    except ValueError:
        await update.message.reply_text("❌ ትክክለኛ ቁጥር ያስገቡ / Enter a valid number")
        return AMOUNT

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phone number"""
    phone = update.message.text.strip()
    
    if not phone.startswith('09') or len(phone) != 10:
        await update.message.reply_text(
            "❌ ትክክለኛ ስልክ ቁጥር ያስገቡ (09xxxxxxxx)\n"
            "Enter a valid phone number"
        )
        return PHONE
    
    user = update.effective_user
    method = context.user_data['payment_method']
    amount = context.user_data['deposit_amount']
    
    # Create payment request
    request_id = db.create_payment_request(
        user_id=user.id,
        method_id=method['id'],
        amount=amount,
        sender_phone=phone
    )
    
    # Show payment instructions
    instructions = f"""
{method['instructions']}

**የክፍያ መረጃ / Payment Details:**
💰 መጠን / Amount: {amount/100:.0f} ETB
📱 ስልክ / Phone: {phone}
🆔 መለያ / Request ID: `{request_id}`

**ከተከፈለ በኋላ የደረሰኝ ቁጥር ይላኩ**
**After payment, send the reference number:**
    """
    
    keyboard = [
        [InlineKeyboardButton("✅ ከፍያዬን አረጋገጥኩ / I've Paid", callback_data=f"paid_{request_id}")],
        [InlineKeyboardButton("◀️ ሰርዝ / Cancel", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        instructions,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    
    # Notify admin
    await notify_admin(
        context,
        f"💰 **አዲስ የክፍያ ጥያቄ / New Payment Request**\n\n"
        f"መለያ / ID: `{request_id}`\n"
        fተጠቃሚ / User: {user.first_name} (ID: {user.id})\n"
        f"መጠን / Amount: {amount/100:.0f} ETB\n"
        f"ዘዴ / Method: {method['name']}\n"
        f"ስልክ / Phone: {phone}"
    )
    
    return ConversationHandler.END

async def paid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment confirmation"""
    query = update.callback_query
    await query.answer()
    
    request_id = query.data.split('_')[1]
    
    context.user_data['pending_request'] = request_id
    
    await query.edit_message_text(
        "✅ **እሺ / OK**\n\n"
        "እባክዎ የክፍያ ማረጋገጫ ቁጥርዎን ያስገቡ:\n"
        "Please enter your transaction reference number:",
        parse_mode='Markdown'
    )
    return REFERENCE

async def handle_reference(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment reference"""
    reference = update.message.text.strip()
    request_id = context.user_data.get('pending_request')
    
    if not request_id:
        await update.message.reply_text("❌ እባክዎ እንደገና ይጀምሩ / Please start over")
        return ConversationHandler.END
    
    # Store reference (in real system, you'd save this)
    await update.message.reply_text(
        f"✅ **ክፍያ ሪፖርት ተደርጓል!**\n"
        f"**Payment Reported!**\n\n"
        f"የክፍያ መለያ / Request ID: `{request_id}`\n"
        f"ማረጋገጫ / Reference: `{reference}`\n\n"
        f"አስተዳዳሪ ክፍያዎን በቅርቡ ያረጋግጣል።\n"
        f"Admin will verify your payment shortly.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ ዋና መደብ / Main Menu", callback_data="main_menu")
        ]])
    )
    
    # Notify admin
    await notify_admin(
        context,
        f"📝 **ክፍያ ሪፖርት ተደርጓል / Payment Reported**\n\n"
        f"መለያ / ID: `{request_id}`\n"
        f"ማረጋገጫ / Reference: `{reference}`"
    )
    
    return ConversationHandler.END

async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start withdrawal"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if user_data['balance'] < 500:  # Minimum 5 ETB
        await query.edit_message_text(
            f"❌ በቂ ገንዘብ የለዎትም!\n"
            f"Insufficient balance!\n\n"
            f"ዝቅተኛው {5} ETB ነው።\n"
            f"Minimum withdrawal is 5 ETB",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ ተመለስ / Back", callback_data="main_menu")
            ]])
        )
        return ConversationHandler.END
    
    methods = db.get_payment_methods()
    keyboard = []
    for method in methods:
        emoji = "💚" if "CBE" in method['name'] else "🔵"
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {method['name']}", 
            callback_data=f"withdraw_method_{method['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("◀️ ሰርዝ / Cancel", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💸 **ገንዘብ አውጣ / Withdraw**\n\n"
        f"ያለዎት / Balance: {user_data['balance']/100:.2f} ETB\n\n"
        f"ዘዴ ይምረጡ:\n"
        f"Select method:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    return WITHDRAW_AMOUNT

async def withdraw_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal method selection"""
    query = update.callback_query
    await query.answer()
    
    method_id = int(query.data.split('_')[2])
    method = db.get_payment_method(method_id)
    context.user_data['withdraw_method'] = method
    
    await query.edit_message_text(
        f"{method['name']}\n\n"
        f"መጠኑን ያስገቡ (ETB):\n"
        f"Enter amount in ETB:",
        parse_mode='Markdown'
    )
    return WITHDRAW_AMOUNT

async def withdraw_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal amount"""
    try:
        amount = float(update.message.text.strip())
        amount_cents = int(amount * 100)
        
        user = update.effective_user
        user_data = db.get_user(user.id)
        method = context.user_data.get('withdraw_method')
        
        if not method:
            await update.message.reply_text("❌ እባክዎ እንደገና ይጀምሩ / Please start over")
            return ConversationHandler.END
        
        if amount_cents > user_data['balance']:
            await update.message.reply_text(f"❌ በቂ ገንዘብ የለዎትም!")
            return WITHDRAW_AMOUNT
        
        if amount_cents < method['min_amount']:
            await update.message.reply_text(f"❌ ዝቅተኛው {method['min_amount']/100:.0f} ETB ነው")
            return WITHDRAW_AMOUNT
        
        context.user_data['withdraw_amount'] = amount_cents
        
        await update.message.reply_text(
            "📱 **ስልክ ቁጥር ያስገቡ**\n"
            "**Enter phone number**\n\n"
            "ለምሳሌ / Example: 0912345678"
        )
        return WITHDRAW_PHONE
        
    except ValueError:
        await update.message.reply_text("❌ ትክክለኛ ቁጥር ያስገቡ")
        return WITHDRAW_AMOUNT

async def withdraw_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal phone"""
    phone = update.message.text.strip()
    
    if not phone.startswith('09') or len(phone) != 10:
        await update.message.reply_text(
            "❌ ትክክለኛ ስልክ ቁጥር ያስገቡ (09xxxxxxxx)"
        )
        return WITHDRAW_PHONE
    
    context.user_data['withdraw_phone'] = phone
    
    await update.message.reply_text(
        "📝 **ሙሉ ስም ያስገቡ**\n"
        "**Enter full name**"
    )
    return WITHDRAW_NAME

async def withdraw_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal name"""
    name = update.message.text.strip()
    user = update.effective_user
    method = context.user_data['withdraw_method']
    amount = context.user_data['withdraw_amount']
    phone = context.user_data['withdraw_phone']
    
    # Create withdrawal request
    request_id = db.create_withdrawal_request(
        user_id=user.id,
        method_id=method['id'],
        amount=amount,
        account_number=phone,
        account_name=name
    )
    
    if request_id:
        await update.message.reply_text(
            f"✅ **የገንዘብ ማውጫ ጥያቄ ተልኳል!**\n"
            f"**Withdrawal Request Sent!**\n\n"
            f"መለያ / ID: `{request_id}`\n"
            f"መጠን / Amount: {amount/100:.2f} ETB\n"
            f"ስልክ / Phone: {phone}\n"
            f"ስም / Name: {name}\n\n"
            f"አስተዳዳሪ በቅርቡ ያረጋግጣል።\n"
            f"Admin will process shortly.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ ዋና መደብ / Main Menu", callback_data="main_menu")
            ]])
        )
        
        # Notify admin
        await notify_admin(
            context,
            f"💸 **አዲስ የማውጫ ጥያቄ / New Withdrawal Request**\n\n"
            f"መለያ / ID: `{request_id}`\n"
            fተጠቃሚ / User: {user.first_name} (ID: {user.id})\n"
            f"መጠን / Amount: {amount/100:.2f} ETB\n"
            f"ስልክ / Phone: {phone}\n"
            f"ስም / Name: {name}"
        )
    else:
        await update.message.reply_text("❌ ጥያቄ መፍጠር አልተቻለም")
    
    return ConversationHandler.END

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show transaction history"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    
    # This would fetch from database
    await query.edit_message_text(
        "📊 **ታሪክ / History**\n\n"
        "በቅርቡ ይጨመራል / Coming soon...",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ ተመለስ / Back", callback_data="main_menu")
        ]])
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help"""
    query = update.callback_query
    await query.answer()
    
    help_text = """
❓ **እገዛ / Help**

**እንዴት እንደሚጫወት / How to Play:**
1. ተጫወት ይምረጡ / Click Play
2. ካርድ ይምረጡ / Choose your card
3. አስተዳዳሪ ሲጀምር ይጠብቁ / Wait for admin to start
4. ቁጥሮች ሲወጡ ይምልክቱ / Mark numbers as called
5. ቢንጎ ሲኖርዎት ይጫኑ / Click BINGO when you win

**💰 ክፍያ / Payment:**
• ቴሌቢር - *127#
• ሲቢኢ ቢር - *847#
• ደቂቃዎች / Minutes: 2-5

**📞 ድጋፍ / Support:**
@Treeeeestbot
    """
    
    await query.edit_message_text(
        help_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ ተመለስ / Back", callback_data="main_menu")
        ]])
    )

# Admin functions
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel"""
    query = update.callback_query
    await query.answer()
    
    if str(update.effective_user.id) != ADMIN_USER_ID:
        await query.edit_message_text("❌ ያልተፈቀደ / Unauthorized")
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 ያልተረጋገጡ ክፍያዎች / Pending Payments", callback_data="admin_payments")],
        [InlineKeyboardButton("💸 ያልተረጋገጡ ማውጫዎች / Pending Withdrawals", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("📊 ስታቲስቲክስ / Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("◀️ ተመለስ / Back", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "👑 **አስተዳዳሪ ፓነል / Admin Panel**",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def admin_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pending payments"""
    query = update.callback_query
    await query.answer()
    
    if str(update.effective_user.id) != ADMIN_USER_ID:
        return
    
    pending = db.get_pending_payment_requests()
    
    if not pending:
        await query.edit_message_text(
            "📊 ምንም ያልተረጋገጠ ክፍያ የለም\nNo pending payments",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ ተመለስ / Back", callback_data="admin")
            ]])
        )
        return
    
    for p in pending:
        emoji = "💚" if "CBE" in p['method_name'] else "🔵"
        keyboard = [
            [
                InlineKeyboardButton("✅ አረጋግጥ / Approve", callback_data=f"approve_payment_{p['request_id']}"),
                InlineKeyboardButton("❌ አትቀበል / Reject", callback_data=f"reject_payment_{p['request_id']}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = (
            f"{emoji} **ያልተረጋገጠ ክፍያ / Pending Payment**\n\n"
            f"መለያ / ID: `{p['request_id']}`\n"
            fተጠቃሚ / User: {p['first_name']} (ID: {p['user_id']})\n"
            f"ስልክ / Phone: {p['phone_number']}\n"
            f"መጠን / Amount: {p['amount']/100:.0f} ETB\n"
            f"ዘዴ / Method: {p['method_name']}\n"
            f"ጊዜ / Time: {p['created_at']}"
        )
        
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve payment"""
    query = update.callback_query
    await query.answer()
    
    if str(update.effective_user.id) != ADMIN_USER_ID:
        return
    
    request_id = query.data.split('_')[2]
    
    if db.approve_payment(request_id):
        await query.edit_message_text(
            f"✅ **ክፍያ ተረጋግጧል!**\n"
            f"**Payment Approved!**\n\n"
            f"መለያ / ID: `{request_id}`"
        )
        
        # Notify user (you'd need to get user_id from the request)
        # await context.bot.send_message(chat_id=user_id, text="✅ ክፍያዎ ተረጋግጧል!")
    else:
        await query.edit_message_text("❌ ክፍያ ማረጋገጥ አልተቻለም")

async def notify_admin(context, message):
    """Send notification to admin"""
    try:
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=message,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    await update.message.reply_text(
        "ተሰርዟል / Cancelled",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

def main():
    """Start bot"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation handlers
    deposit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_method_selected, pattern='^deposit_method_')],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone)],
            REFERENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reference)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(withdraw_command, pattern='^withdraw$'),
                     CallbackQueryHandler(withdraw_method_selected, pattern='^withdraw_method_')],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_handler)],
            WITHDRAW_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_phone_handler)],
            WITHDRAW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_name_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Add handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern='^main_menu$'))
    application.add_handler(CallbackQueryHandler(play_command, pattern='^play$'))
    application.add_handler(CallbackQueryHandler(balance_command, pattern='^balance$'))
    application.add_handler(CallbackQueryHandler(deposit_command, pattern='^deposit$'))
    application.add_handler(CallbackQueryHandler(withdraw_command, pattern='^withdraw$'))
    application.add_handler(CallbackQueryHandler(history_command, pattern='^history$'))
    application.add_handler(CallbackQueryHandler(help_command, pattern='^help$'))
    application.add_handler(CallbackQueryHandler(paid_callback, pattern='^paid_'))
    
    # Admin handlers
    application.add_handler(CallbackQueryHandler(admin_panel, pattern='^admin$'))
    application.add_handler(CallbackQueryHandler(admin_payments, pattern='^admin_payments$'))
    application.add_handler(CallbackQueryHandler(approve_payment, pattern='^approve_payment_'))
    
    # Add conversation handlers
    application.add_handler(deposit_conv)
    application.add_handler(withdraw_conv)
    
    # Start bot
    application.run_polling(allowed_updates=['message', 'callback_query'])

if __name__ == '__main__':
    main()