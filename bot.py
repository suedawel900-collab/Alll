import os
import logging
import threading
import random
import time
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, render_template, jsonify, g
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

# --- Configuration ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN environment variable set")

PUBLIC_URL = os.environ.get("RAILWAY_STATIC_URL")
if not PUBLIC_URL:
    PUBLIC_URL = "https://your-ngrok-url.ngrok.io"  # for local testing

WEBAPP_URL = f"{PUBLIC_URL}/webapp"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{PUBLIC_URL}{WEBHOOK_PATH"

CARD_COST = 10          # ETB per card
MAX_CARDS_PER_PLAYER = 20
HOUSE_COMMISSION = 0.2  # 20%

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Flask app ---
app = Flask(__name__)

# --- Telegram application ---
telegram_app = Application.builder().token(BOT_TOKEN).updater(None).build()

# --- Database helpers ---
DATABASE = 'bingo.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        # Users
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                balance INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Rounds
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT DEFAULT 'waiting',  -- waiting, active, finished
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                prize_pool INTEGER DEFAULT 0
            )
        ''')
        # Cards – each card is a separate Bingo board owned by a player in a round
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER,
                user_id INTEGER,
                board TEXT,  -- JSON array
                bingo_claimed BOOLEAN DEFAULT 0,
                FOREIGN KEY(round_id) REFERENCES rounds(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        # Called numbers
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS called_numbers (
                round_id INTEGER,
                number INTEGER,
                called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(round_id) REFERENCES rounds(id)
            )
        ''')
        db.commit()

init_db()

# --- Bingo board generation (5x5 with FREE center) ---
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

# Pre-generate 1000 unique boards
logger.info("Generating 1000 unique Bingo boards...")
BOARD_POOL = generate_unique_boards(1000)
BOARD_LOCK = threading.Lock()
logger.info(f"Generated {len(BOARD_POOL)} unique boards.")

# --- Round state (in-memory for speed) ---
active_round = {
    'id': None,
    'status': 'waiting',      # waiting, active, finished
    'players': [],            # list of telegram_ids (unique players)
    'player_cards': {},       # telegram_id -> list of card_ids
    'called_numbers': set(),
    'last_call_time': 0,
    'winner_id': None
}
round_lock = threading.Lock()

def get_or_create_active_round():
    """Ensure a waiting round exists in DB and memory."""
    with round_lock:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id FROM rounds WHERE status='waiting' LIMIT 1")
        row = cursor.fetchone()
        if row:
            round_id = row['id']
        else:
            cursor.execute("INSERT INTO rounds (status) VALUES ('waiting')")
            db.commit()
            round_id = cursor.lastrowid
        # Load existing data into memory
        active_round['id'] = round_id
        active_round['status'] = 'waiting'
        # Get players and their cards
        cursor.execute('''
            SELECT u.telegram_id, c.id as card_id, c.board
            FROM cards c
            JOIN users u ON c.user_id = u.id
            WHERE c.round_id = ? AND c.bingo_claimed=0
        ''', (round_id,))
        rows = cursor.fetchall()
        players = {}
        for row in rows:
            tid = row['telegram_id']
            if tid not in players:
                players[tid] = []
            players[tid].append(row['card_id'])
        active_round['players'] = list(players.keys())
        active_round['player_cards'] = players
        active_round['called_numbers'] = set()
        active_round['last_call_time'] = 0
        active_round['winner_id'] = None
        return round_id

def reset_round():
    """Mark current round as finished and create a new waiting round."""
    with round_lock:
        if active_round['id']:
            db = get_db()
            cursor = db.cursor()
            cursor.execute("UPDATE rounds SET status='finished', end_time=? WHERE id=?",
                           (datetime.now(), active_round['id']))
            db.commit()
        # Clear memory
        active_round['id'] = None
        active_round['status'] = 'waiting'
        active_round['players'] = []
        active_round['player_cards'] = {}
        active_round['called_numbers'] = set()
        active_round['last_call_time'] = 0
        active_round['winner_id'] = None
        # Create new round
        get_or_create_active_round()

# --- Background round worker (calls numbers every 3 seconds) ---
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
                    # No numbers left – rare, but reset
                    reset_round()
                    continue
                number = random.choice(list(available))
                active_round['called_numbers'].add(number)
                active_round['last_call_time'] = now

                db = get_db()
                cursor = db.cursor()
                cursor.execute("INSERT INTO called_numbers (round_id, number) VALUES (?, ?)",
                               (active_round['id'], number))
                db.commit()
                logger.info(f"Round {active_round['id']} called {number}")

                # Check for winners among all cards
                for tid in active_round['players']:
                    if check_any_bingo(tid):
                        # Player wins
                        active_round['winner_id'] = tid
                        active_round['status'] = 'finished'
                        distribute_prize(tid)
                        notify_round_end(tid)
                        reset_round()
                        break

def check_any_bingo(telegram_id):
    """Return True if any card of this player has a Bingo."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT board FROM cards
        WHERE round_id=? AND user_id=(SELECT id FROM users WHERE telegram_id=?)
    ''', (active_round['id'], telegram_id))
    rows = cursor.fetchall()
    called = active_round['called_numbers']
    for row in rows:
        board = json.loads(row['board'])
        if check_bingo_board(board, called):
            return True
    return False

def check_bingo_board(board, called_numbers):
    """Check if a single board has Bingo."""
    marked = [[False]*5 for _ in range(5)]
    for r in range(5):
        for c in range(5):
            cell = board[r][c]
            if cell == "FREE" or cell in called_numbers:
                marked[r][c] = True
    # Rows
    for r in range(5):
        if all(marked[r][c] for c in range(5)):
            return True
    # Columns
    for c in range(5):
        if all(marked[r][c] for r in range(5)):
            return True
    # Diagonals
    if all(marked[i][i] for i in range(5)):
        return True
    if all(marked[i][4-i] for i in range(5)):
        return True
    return False

def distribute_prize(winner_telegram_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT prize_pool FROM rounds WHERE id=?", (active_round['id'],))
    row = cursor.fetchone()
    if not row:
        return
    total_pool = row['prize_pool']
    winner_share = int(total_pool * (1 - HOUSE_COMMISSION))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?",
                   (winner_share, winner_telegram_id))
    db.commit()
    logger.info(f"Winner {winner_telegram_id} gets {winner_share} from {total_pool}")

def notify_round_end(winner_id):
    for pid in active_round['players']:
        try:
            telegram_app.bot.send_message(
                chat_id=pid,
                text=f"🎉 Bingo! Player {winner_id} won the round! Prize distributed."
            )
        except:
            pass

# Start worker thread
threading.Thread(target=round_worker, daemon=True).start()

# --- Telegram command handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(
            text="🎰 Open Bingo Game",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome to Bingo Bot!\n"
        f"• Each card costs {CARD_COST} ETB.\n"
        f"• Max {MAX_CARDS_PER_PLAYER} cards per round.\n"
        "Use /balance, /deposit <amount>, /join to enter a round.",
        reply_markup=reply_markup
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (user_id,))
    row = cursor.fetchone()
    bal = row['balance'] if row else 0
    await update.message.reply_text(f"Your balance: {bal} ETB")

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(context.args[0])
    except:
        await update.message.reply_text("Usage: /deposit <amount>")
        return
    user_id = update.effective_user.id
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (telegram_id, balance) VALUES (?, 0)", (user_id,))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (amount, user_id))
    db.commit()
    new_bal = get_balance(user_id)
    await update.message.reply_text(f"Added {amount} ETB. New balance: {new_bal} ETB")

def get_balance(user_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (user_id,))
    row = cursor.fetchone()
    return row['balance'] if row else 0

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows user to join the current round (just registers them, cards selected in WebApp)."""
    user_id = update.effective_user.id
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (telegram_id, balance) VALUES (?, 0)", (user_id,))
    db.commit()
    # Ensure round exists
    get_or_create_active_round()
    await update.message.reply_text("You can now open the WebApp and select your cards.")

async def start_round(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to start the round."""
    with round_lock:
        if active_round['status'] != 'waiting':
            await update.message.reply_text("Round already active or finished.")
            return
        if len(active_round['players']) == 0:
            await update.message.reply_text("No players in this round.")
            return
        active_round['status'] = 'active'
        active_round['last_call_time'] = time.time()
        # Notify players
        for pid in active_round['players']:
            try:
                await telegram_app.bot.send_message(
                    chat_id=pid,
                    text="🚀 Round started! Numbers are being called. Open the WebApp to play."
                )
            except:
                pass
        await update.message.reply_text("Round started!")

async def round_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with round_lock:
        await update.message.reply_text(
            f"Round {active_round['id']} status: {active_round['status']}\n"
            f"Players: {len(active_round['players'])}\n"
            f"Numbers called: {len(active_round['called_numbers'])}"
        )

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("balance", balance))
telegram_app.add_handler(CommandHandler("deposit", deposit))
telegram_app.add_handler(CommandHandler("join", join))
telegram_app.add_handler(CommandHandler("start_round", start_round))
telegram_app.add_handler(CommandHandler("round_info", round_info))

# --- Flask endpoints for WebApp ---
@app.route("/webapp")
def webapp():
    return render_template("index.html")

@app.route("/get_user_data")
def get_user_data():
    """Return user info: balance, active games, etc. Expects tgWebAppData with user id."""
    # In production, parse Telegram.WebApp.initData to get user id.
    # For simplicity, we'll use a query parameter for testing.
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify(error="No user id"), 400
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT balance FROM users WHERE telegram_id=?", (user_id,))
    row = cursor.fetchone()
    balance = row['balance'] if row else 0
    # Count active games (cards in current round)
    with round_lock:
        active_games = len(active_round['player_cards'].get(int(user_id), [])) if active_round['status'] == 'active' else 0
    return jsonify({
        'balance': balance,
        'active_games': active_games,
        'round_prize': get_round_prize(),
        'round_number': active_round['id'] if active_round['id'] else 0,
        'stake': 0  # will be updated as cards are selected
    })

def get_round_prize():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT prize_pool FROM rounds WHERE id=?", (active_round['id'],))
    row = cursor.fetchone()
    return row['prize_pool'] if row else 0

@app.route("/get_called_numbers")
def get_called_numbers():
    with round_lock:
        return jsonify({
            'called': list(active_round['called_numbers']),
            'status': active_round['status']
        })

@app.route("/buy_cards", methods=["POST"])
def buy_cards():
    """User confirms purchase of selected card IDs."""
    data = request.get_json()
    user_id = data.get('user_id')
    card_ids = data.get('card_ids', [])  # list of card IDs they want to buy
    if not user_id or not card_ids:
        return jsonify(success=False, message="Missing data")
    if len(card_ids) > MAX_CARDS_PER_PLAYER:
        return jsonify(success=False, message=f"Max {MAX_CARDS_PER_PLAYER} cards")
    db = get_db()
    cursor = db.cursor()
    # Check balance
    cursor.execute("SELECT balance, id FROM users WHERE telegram_id=?", (user_id,))
    user = cursor.fetchone()
    if not user:
        return jsonify(success=False, message="User not found")
    balance = user['balance']
    user_db_id = user['id']
    total_cost = len(card_ids) * CARD_COST
    if balance < total_cost:
        return jsonify(success=False, message="Insufficient balance")
    # Ensure round is waiting
    with round_lock:
        if active_round['status'] != 'waiting':
            return jsonify(success=False, message="Round already started")
        round_id = active_round['id']
        # Check that card_ids are available (not already bought in this round)
        # For simplicity, we'll generate new cards on the fly.
        # In a real system, you'd have a pool of pre-generated card IDs.
        # Here we'll create new cards and return their IDs.
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
        # Deduct balance
        cursor.execute("UPDATE users SET balance = balance - ? WHERE id=?", (total_cost, user_db_id))
        # Update round prize pool
        cursor.execute("UPDATE rounds SET prize_pool = prize_pool + ? WHERE id=?", (total_cost, round_id))
        db.commit()
        # Update in-memory state
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
            # Winner!
            active_round['winner_id'] = user_id
            active_round['status'] = 'finished'
            distribute_prize(user_id)
            notify_round_end(user_id)
            reset_round()
            return jsonify(success=True, message="Bingo! You win!")
        else:
            return jsonify(success=False, message="No Bingo on your cards")

@app.route(WEBHOOK_PATH, methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    await telegram_app.process_update(update)
    return "OK", 200

@app.before_first_request
async def set_webhook():
    webhook_info = await telegram_app.bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        logger.info(f"Setting webhook to {WEBHOOK_URL}")
        await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
    else:
        logger.info("Webhook already set correctly")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
