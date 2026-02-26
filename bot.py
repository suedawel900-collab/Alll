import os
import logging
import threading
import random
import time
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, render_template, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

# --- Configuration ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN environment variable set")

ADMIN_IDS = [int(id.strip()) for id in os.environ.get("ADMIN_IDS", "").split(",") if id.strip()]

PUBLIC_URL = os.environ.get("RAILWAY_STATIC_URL")
if not PUBLIC_URL:
    PUBLIC_URL = "https://your-ngrok-url.ngrok.io"  # fallback for local testing

WEBAPP_URL = f"{PUBLIC_URL}/webapp"

CARD_COST = 10
MAX_CARDS_PER_PLAYER = 20
HOUSE_COMMISSION = 0.2

TELBIRR_NUMBER = "0953933030"
CBEBIRR_NUMBER = "0953933030"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Telegram Application (polling) ---
telegram_app = Application.builder().token(BOT_TOKEN).build()

# --- Database helpers (thread‑safe, no Flask g) ---
DATABASE = 'bingo.db'

def get_db_connection():
    """Return a new SQLite connection. Caller must close it."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            balance INTEGER DEFAULT 0,
            referrer_id INTEGER,
            referral_bonus_given BOOLEAN DEFAULT 0,
            signup_bonus_given BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT DEFAULT 'waiting',
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            prize_pool INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER,
            user_id INTEGER,
            board TEXT,
            bingo_claimed BOOLEAN DEFAULT 0,
            FOREIGN KEY(round_id) REFERENCES rounds(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS called_numbers (
            round_id INTEGER,
            number INTEGER,
            called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(round_id) REFERENCES rounds(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            method TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- Bingo board generation ---
def generate_board():
    col_ranges = [(1,15), (16,30), (31,45), (46,60), (61,75)]
    cols = []
    for i, (low, high) in enumerate(col_ranges):
        if i == 2:
            nums = random.sample(range(low, high+1), 4)
            nums.insert(2, "FREE")
        else:
            nums = random.sample(range(low, high+1), 5)
        cols.append(nums)
    board = []
    for row in range(5):
        row_cells = [cols[col][row] for col in range(5)]
        board.append(row_cells)
    return board

def generate_unique_boards(count):
    unique = set()
    result = []
    while len(result) < count:
        board = generate_board()
        board_tuple = tuple(tuple(row) for row in board)
        if board_tuple not in unique:
            unique.add(board_tuple)
            result.append(board)
    return result

logger.info("Generating 1000 unique Bingo boards...")
BOARD_POOL = generate_unique_boards(1000)
BOARD_LOCK = threading.Lock()
logger.info(f"Generated {len(BOARD_POOL)} unique boards.")

# --- Round state (in-memory) ---
active_round = {
    'id': None,
    'status': 'waiting',
    'players': [],
    'player_cards': {},
    'called_numbers': set(),
    'last_call_time': 0,
    'winner_id': None
}
round_lock = threading.Lock()

def get_or_create_active_round():
    with round_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM rounds WHERE status='waiting' LIMIT 1")
        row = cursor.fetchone()
        if row:
            round_id = row['id']
        else:
            cursor.execute("INSERT INTO rounds (status) VALUES ('waiting')")
            conn.commit()
            round_id = cursor.lastrowid
        cursor.execute('''
            SELECT u.telegram_id, c.id as card_id, c.board
            FROM cards c
            JOIN users u ON c.user_id = u.id
            WHERE c.round_id = ? AND c.bingo_claimed=0
        ''', (round_id,))
        rows = cursor.fetchall()
        conn.close()
        players = {}
        for row in rows:
            tid = row['telegram_id']
            if tid not in players:
                players[tid] = []
            players[tid].append(row['card_id'])
        active_round['id'] = round_id
        active_round['status'] = 'waiting'
        active_round['players'] = list(players.keys())
        active_round['player_cards'] = players
        active_round['called_numbers'] = set()
        active_round['last_call_time'] = 0
        active_round['winner_id'] = None
        return round_id

def reset_round(keep_players=False):
    with round_lock:
        if active_round['id']:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE rounds SET status='finished', end_time=? WHERE id=?",
                           (datetime.now(), active_round['id']))
            conn.commit()
            conn.close()
        old_players = active_round['players'][:] if keep_players else []
        active_round['id'] = None
        active_round['status'] = 'waiting'
        active_round['players'] = []
        active_round['player_cards'] = {}
        active_round['called_numbers'] = set()
        active_round['last_call_time'] = 0
        active_round['winner_id'] = None
        new_round_id = get_or_create_active_round()
        if keep_players:
            for tid in old_players:
                if tid not in active_round['players']:
                    active_round['players'].append(tid)
                    active_round['player_cards'][tid] = []
        return new_round_id

def round_worker():
    while True:
        time.sleep(2)
        with round_lock:
            if active_round['status'] != 'active':
                continue
            now = time.time()
            if now - active_round['last_call_time'] >= 3.0:
                available = set(range(1, 76)) - active_round['called_numbers']
                if not available:
                    reset_round(keep_players=False)
                    continue
                number = random.choice(list(available))
                active_round['called_numbers'].add(number)
                active_round['last_call_time'] = now

                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO called_numbers (round_id, number) VALUES (?, ?)",
                               (active_round['id'], number))
                conn.commit()
                conn.close()
                logger.info(f"Round {active_round['id']} called {number}")

                for tid in active_round['players']:
                    if check_any_bingo(tid):
                        active_round['winner_id'] = tid
                        active_round['status'] = 'finished'
                        distribute_prize(tid)
                        notify_round_end(tid)
                        reset_round(keep_players=True)
                        break

def check_any_bingo(telegram_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT board FROM cards
        WHERE round_id=? AND user_id=(SELECT id FROM users WHERE telegram_id=?)
    ''', (active_round['id'], telegram_id))
    rows = cursor.fetchall()
    conn.close()
    called = active_round['called_numbers']
    for row in rows:
        board = json.loads(row['board'])
        if check_bingo_board(board, called):
            return True
    return False

def check_bingo_board(board, called_numbers):
    marked = [[False]*5 for _ in range(5)]
    for r in range(5):
        for c in range(5):
            cell = board[r][c]
            if cell == "FREE" or cell in called_numbers:
                marked[r][c] = True
    for r in range(5):
        if all(marked[r][c] for c in range(5)):
            return True
    for c in range(5):
        if all(marked[r][c] for r in range(5)):
            return True
    if all(marked[i][i] for i in range(5)):
        return True
    if all(marked[i][4-i] for i in range(5)):
        return True
    return False

def distribute_prize(winner_telegram_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT prize_pool FROM rounds WHERE id=?", (active_round['id'],))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return
    total_pool = row['prize_pool']
    winner_share = int(total_pool * (1 - HOUSE_COMMISSION))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?",
                   (winner_share, winner_telegram_id))
    conn.commit()
    conn.close()
    logger.info(f"Winner {winner_telegram_id} gets {winner_share} from {total_pool}")

def notify_round_end(winner_id):
    for pid in active_round['players']:
        try:
            telegram_app.bot.send_message(
                chat_id=pid,
                text=f"🎉 Bingo! Player {winner_id} won the round! Get ready for the next round."
            )
        except:
            pass

threading.Thread(target=round_worker, daemon=True).start()

def is_admin(user_id):
    return user_id in ADMIN_IDS

# --- Telegram command handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, balance, signup_bonus_given FROM users WHERE telegram_id=?", (user_id,))
    user = cursor.fetchone()
    
    referrer_id = None
    if context.args:
        try:
            referrer_id = int(context.args[0])
            if referrer_id == user_id:
                referrer_id = None
            else:
                cursor.execute("SELECT id FROM users WHERE telegram_id=?", (referrer_id,))
                if not cursor.fetchone():
                    referrer_id = None
        except:
            referrer_id = None
    
    if not user:
        cursor.execute('''
            INSERT INTO users (telegram_id, balance, referrer_id, signup_bonus_given)
            VALUES (?, 0, ?, 0)
        ''', (user_id, referrer_id))
        conn.commit()
        cursor.execute("UPDATE users SET balance = balance + 10, signup_bonus_given = 1 WHERE telegram_id=?", (user_id,))
        conn.commit()
        bonus_text = "You received 10 ETB sign-up bonus!"
    else:
        if not user['signup_bonus_given']:
            cursor.execute("UPDATE users SET balance = balance + 10, signup_bonus_given = 1 WHERE telegram_id=?", (user_id,))
            conn.commit()
            bonus_text = "You received 10 ETB sign-up bonus!"
        else:
            bonus_text = ""
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton(
            text="🎰 Open Bingo Game",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = (
        "Welcome to Bingo Bot!\n"
        f"• Each card costs {CARD_COST} ETB.\n"
        f"• Max {MAX_CARDS_PER_PLAYER} cards per round.\n"
        f"• Invite friends and earn 5% of their first deposit!\n"
        f"{bonus_text}\n\n"
        "Commands:\n"
        "/balance - Check your balance\n"
        "/deposit <amount> [method] - Request deposit (method: telbirr or cbebirr)\n"
        "/mydeposits - View your pending deposits\n"
        "/join - Join the current round\n"
        "/round_info - Current round status\n"
        "/referral - Get your referral link\n\n"
        "Admin commands:\n"
        "/pending_deposits - List pending deposits\n"
        "/approve <deposit_id> - Approve deposit\n"
        "/reject <deposit_id> - Reject deposit\n"
        "/start_round - Start the round (admin)\n"
        "/next_round - Reset round for next game (keeps players)"
    )
    await update.message.reply_text(msg, reply_markup=reply_markup)

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={user_id}"
    await update.message.reply_text(
        f"Your referral link:\n{link}\n\n"
        "Share it with friends. You'll get 5% of their first deposit!"
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    bal = row['balance'] if row else 0
    await update.message.reply_text(f"Your balance: {bal} ETB")

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Usage: /deposit <amount> [method] (method: telbirr or cbebirr)")
        return
    try:
        amount = int(args[0])
        if amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("Amount must be a positive integer.")
        return
    method = "telbirr"
    if len(args) >= 2:
        method = args[1].lower()
        if method not in ["telbirr", "cbebirr"]:
            await update.message.reply_text("Method must be 'telbirr' or 'cbebirr'.")
            return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (telegram_id, balance) VALUES (?, 0)", (user_id,))
    cursor.execute("SELECT id FROM users WHERE telegram_id=?", (user_id,))
    user_db_id = cursor.fetchone()['id']
    cursor.execute('''
        INSERT INTO deposits (user_id, amount, method, status)
        VALUES (?, ?, ?, 'pending')
    ''', (user_db_id, amount, method))
    conn.commit()
    deposit_id = cursor.lastrowid
    conn.close()
    number = TELBIRR_NUMBER if method == "telbirr" else CBEBIRR_NUMBER
    await update.message.reply_text(
        f"✅ Deposit request #{deposit_id} created.\n"
        f"Please send {amount} ETB to {method.upper()} number {number}.\n"
        f"Then wait for admin approval. Use /mydeposits to check status."
    )

async def my_deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT d.id, d.amount, d.method, d.status, d.created_at
        FROM deposits d
        JOIN users u ON d.user_id = u.id
        WHERE u.telegram_id = ?
        ORDER BY d.created_at DESC
        LIMIT 10
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("You have no deposit requests.")
        return
    msg = "Your recent deposits:\n"
    for r in rows:
        msg += f"#{r['id']}: {r['amount']} ETB via {r['method']} - {r['status']}\n"
    await update.message.reply_text(msg)

async def pending_deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT d.id, u.telegram_id, d.amount, d.method, d.created_at
        FROM deposits d
        JOIN users u ON d.user_id = u.id
        WHERE d.status = 'pending'
        ORDER BY d.created_at
    ''')
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("No pending deposits.")
        return
    msg = "Pending deposits:\n"
    for r in rows:
        msg += f"#{r['id']} | User {r['telegram_id']} | {r['amount']} ETB | {r['method']} | {r['created_at']}\n"
    msg += "\nUse /approve <id> or /reject <id>"
    await update.message.reply_text(msg)

async def approve_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    try:
        deposit_id = int(context.args[0])
    except:
        await update.message.reply_text("Usage: /approve <deposit_id>")
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT d.id, d.user_id, d.amount, d.status
        FROM deposits d
        WHERE d.id = ?
    ''', (deposit_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        await update.message.reply_text("Deposit not found.")
        return
    if row['status'] != 'pending':
        conn.close()
        await update.message.reply_text(f"Deposit already {row['status']}.")
        return
    
    cursor.execute("UPDATE deposits SET status='approved' WHERE id=?", (deposit_id,))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?", (row['amount'], row['user_id']))
    
    # Check if this is the user's first approved deposit
    cursor.execute('''
        SELECT COUNT(*) as cnt FROM deposits
        WHERE user_id = ? AND status='approved'
    ''', (row['user_id'],))
    count = cursor.fetchone()['cnt']
    if count == 1:
        cursor.execute('''
            SELECT u.referrer_id, u.referral_bonus_given
            FROM users u
            WHERE u.id = ?
        ''', (row['user_id'],))
        user = cursor.fetchone()
        if user and user['referrer_id'] and not user['referral_bonus_given']:
            referrer_tid = user['referrer_id']
            bonus = int(row['amount'] * 0.05)
            if bonus > 0:
                cursor.execute('''
                    UPDATE users SET balance = balance + ? WHERE telegram_id = ?
                ''', (bonus, referrer_tid))
                cursor.execute('''
                    UPDATE users SET referral_bonus_given = 1 WHERE id = ?
                ''', (row['user_id'],))
                try:
                    await telegram_app.bot.send_message(
                        chat_id=referrer_tid,
                        text=f"🎉 You earned {bonus} ETB referral bonus from a friend's first deposit!"
                    )
                except:
                    pass
    conn.commit()
    
    cursor.execute("SELECT telegram_id FROM users WHERE id=?", (row['user_id'],))
    user_tid = cursor.fetchone()['telegram_id']
    conn.close()
    try:
        await telegram_app.bot.send_message(
            chat_id=user_tid,
            text=f"✅ Your deposit of {row['amount']} ETB has been approved. Balance updated."
        )
    except:
        pass
    await update.message.reply_text(f"Deposit #{deposit_id} approved.")

async def reject_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    try:
        deposit_id = int(context.args[0])
    except:
        await update.message.reply_text("Usage: /reject <deposit_id>")
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT d.id, d.status, u.telegram_id
        FROM deposits d
        JOIN users u ON d.user_id = u.id
        WHERE d.id = ?
    ''', (deposit_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        await update.message.reply_text("Deposit not found.")
        return
    if row['status'] != 'pending':
        conn.close()
        await update.message.reply_text(f"Deposit already {row['status']}.")
        return
    cursor.execute("UPDATE deposits SET status='rejected' WHERE id=?", (deposit_id,))
    conn.commit()
    user_tid = row['telegram_id']
    conn.close()
    try:
        await telegram_app.bot.send_message(
            chat_id=user_tid,
            text=f"❌ Your deposit #{deposit_id} has been rejected. Please contact admin."
        )
    except:
        pass
    await update.message.reply_text(f"Deposit #{deposit_id} rejected.")

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (telegram_id, balance) VALUES (?, 0)", (user_id,))
    conn.commit()
    conn.close()
    get_or_create_active_round()
    with round_lock:
        if user_id not in active_round['players']:
            active_round['players'].append(user_id)
            active_round['player_cards'][user_id] = []
    await update.message.reply_text("You joined the round! Open the WebApp to select your cards.")

async def start_round(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    with round_lock:
        if active_round['status'] != 'waiting':
            await update.message.reply_text("Round already active or finished.")
            return
        if len(active_round['players']) == 0:
            await update.message.reply_text("No players in this round.")
            return
        active_round['status'] = 'active'
        active_round['last_call_time'] = time.time()
        for pid in active_round['players']:
            try:
                await telegram_app.bot.send_message(
                    chat_id=pid,
                    text="🚀 Round started! Numbers are being called. Open the WebApp to play."
                )
            except:
                pass
        await update.message.reply_text("Round started!")

async def next_round(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    with round_lock:
        reset_round(keep_players=True)
    await update.message.reply_text("Next round is ready. Players can now buy new cards.")

async def round_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with round_lock:
        await update.message.reply_text(
            f"Round {active_round['id']} status: {active_round['status']}\n"
            f"Players: {len(active_round['players'])}\n"
            f"Numbers called: {len(active_round['called_numbers'])}"
        )

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("referral", referral))
telegram_app.add_handler(CommandHandler("balance", balance))
telegram_app.add_handler(CommandHandler("deposit", deposit))
telegram_app.add_handler(CommandHandler("mydeposits", my_deposits))
telegram_app.add_handler(CommandHandler("pending_deposits", pending_deposits))
telegram_app.add_handler(CommandHandler("approve", approve_deposit))
telegram_app.add_handler(CommandHandler("reject", reject_deposit))
telegram_app.add_handler(CommandHandler("join", join))
telegram_app.add_handler(CommandHandler("start_round", start_round))
telegram_app.add_handler(CommandHandler("next_round", next_round))
telegram_app.add_handler(CommandHandler("round_info", round_info))

# --- Flask endpoints for WebApp ---
@app.route("/webapp")
def webapp():
    return render_template("index.html")

@app.route("/get_user_data")
def get_user_data():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify(error="No user id"), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    balance = row['balance'] if row else 0
    with round_lock:
        active_games = len(active_round['player_cards'].get(int(user_id), [])) if active_round['status'] == 'active' else 0
        round_status = active_round['status']
    return jsonify({
        'balance': balance,
        'active_games': active_games,
        'round_prize': get_round_prize(),
        'round_number': active_round['id'] if active_round['id'] else 0,
        'stake': 0,
        'round_status': round_status
    })

def get_round_prize():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT prize_pool FROM rounds WHERE id=?", (active_round['id'],))
    row = cursor.fetchone()
    conn.close()
    return row['prize_pool'] if row else 0

@app.route("/get_called_numbers")
def get_called_numbers():
    with round_lock:
        return jsonify({
            'called': list(active_round['called_numbers']),
            'status': active_round['status']
        })

@app.route("/get_my_cards")
def get_my_cards():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify(error="No user id"), 400
    with round_lock:
        round_id = active_round['id']
        if not round_id:
            return jsonify(cards=[])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.board, c.id
            FROM cards c
            JOIN users u ON c.user_id = u.id
            WHERE c.round_id = ? AND u.telegram_id = ?
        ''', (round_id, user_id))
        rows = cursor.fetchall()
        conn.close()
        cards = [{'id': row['id'], 'board': json.loads(row['board'])} for row in rows]
        return jsonify(cards=cards)

@app.route("/buy_cards", methods=["POST"])
def buy_cards():
    data = request.get_json()
    user_id = data.get('user_id')
    card_ids = data.get('card_ids', [])
    if not user_id or not card_ids:
        return jsonify(success=False, message="Missing data")
    if len(card_ids) > MAX_CARDS_PER_PLAYER:
        return jsonify(success=False, message=f"Max {MAX_CARDS_PER_PLAYER} cards")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance, id FROM users WHERE telegram_id=?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return jsonify(success=False, message="User not found")
    balance = user['balance']
    user_db_id = user['id']
    total_cost = len(card_ids) * CARD_COST
    if balance < total_cost:
        conn.close()
        return jsonify(success=False, message="Insufficient balance")
    with round_lock:
        if active_round['status'] != 'waiting':
            conn.close()
            return jsonify(success=False, message="Round already started")
        round_id = active_round['id']
        new_card_ids = []
        for _ in card_ids:
            with BOARD_LOCK:
                if BOARD_POOL:
                    board = BOARD_POOL.pop()
                else:
                    board = generate_board()
            cursor.execute('''
                INSERT INTO cards (round_id, user_id, board)
                VALUES (?, ?, ?)
            ''', (round_id, user_db_id, json.dumps(board)))
            card_id = cursor.lastrowid
            new_card_ids.append(card_id)
        cursor.execute("UPDATE users SET balance = balance - ? WHERE id=?", (total_cost, user_db_id))
        cursor.execute("UPDATE rounds SET prize_pool = prize_pool + ? WHERE id=?", (total_cost, round_id))
        conn.commit()
        conn.close()
        if user_id not in active_round['player_cards']:
            active_round['player_cards'][user_id] = []
        active_round['player_cards'][user_id].extend(new_card_ids)
        if user_id not in active_round['players']:
            active_round['players'].append(user_id)
    return jsonify(success=True, card_ids=new_card_ids, new_balance=balance - total_cost)

@app.route("/claim_bingo", methods=["POST"])
def claim_bingo():
    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id:
        return jsonify(success=False, message="No user")
    with round_lock:
        if active_round['status'] != 'active':
            return jsonify(success=False, message="Round not active")
        if user_id not in active_round['players']:
            return jsonify(success=False, message="You are not in this round")
        if check_any_bingo(user_id):
            active_round['winner_id'] = user_id
            active_round['status'] = 'finished'
            distribute_prize(user_id)
            notify_round_end(user_id)
            reset_round(keep_players=True)
            return jsonify(success=True, message="Bingo! You win!")
        else:
            return jsonify(success=False, message="No Bingo on your cards")

# --- Start bot polling in background ---
def start_bot():
    logger.info("Starting Telegram bot polling...")
    telegram_app.run_polling()

bot_thread = threading.Thread(target=start_bot, daemon=True)
bot_thread.start()

# --- Run Flask ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)