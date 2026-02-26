import os
import sqlite3
import json
import threading
import uuid
from datetime import datetime
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

class Database:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        self.db_path = 'bingo.db'
        self._create_tables()
        self._insert_payment_methods()
        logger.info("✅ Database initialized")
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _create_tables(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    phone_number TEXT,
                    balance INTEGER DEFAULT 1000,
                    total_deposits INTEGER DEFAULT 0,
                    total_withdrawals INTEGER DEFAULT 0,
                    games_played INTEGER DEFAULT 0,
                    games_won INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Games table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    status TEXT DEFAULT 'waiting',
                    started_at TIMESTAMP,
                    ended_at TIMESTAMP,
                    winner_id INTEGER,
                    winner_card_id INTEGER,
                    winning_amount INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Player cards table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS player_cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    card_id INTEGER NOT NULL,
                    card_data TEXT NOT NULL,
                    stake INTEGER NOT NULL,
                    is_winner BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (game_id) REFERENCES games(id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Called numbers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS called_numbers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    number INTEGER NOT NULL,
                    called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (game_id) REFERENCES games(id)
                )
            ''')
            
            # Transactions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Payment methods table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payment_methods (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    code TEXT UNIQUE NOT NULL,
                    account_number TEXT NOT NULL,
                    instructions TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Payment requests table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payment_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    method_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    sender_phone TEXT,
                    transaction_reference TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (method_id) REFERENCES payment_methods(id)
                )
            ''')
            
            conn.commit()
    
    def _insert_payment_methods(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) as count FROM payment_methods')
            if cursor.fetchone()['count'] > 0:
                return
            
            # Telbirr
            cursor.execute('''
                INSERT INTO payment_methods (name, code, account_number, instructions)
                VALUES (?, ?, ?, ?)
            ''', (
                'ቴሌቢር (Telbirr)',
                'TELBIRR',
                '0953933030',
                '🔵 ቴሌቢር ክፍያ:\n1. ወደ *127# ይደውሉ\n2. ገንዘብ ላክ ይምረጡ\n3. ቁጥር 0953933030 ያስገቡ\n4. መጠኑን ያስገቡ\n5. ፒንዎን ያስገቡ'
            ))
            
            # CBE Birr
            cursor.execute('''
                INSERT INTO payment_methods (name, code, account_number, instructions)
                VALUES (?, ?, ?, ?)
            ''', (
                'ሲቢኢ ቢር (CBE Birr)',
                'CBEBIRR',
                '0953933030',
                '💚 ሲቢኢ ቢር ክፍያ:\n1. ወደ *847# ይደውሉ\n2. ገንዘብ ላክ ይምረጡ\n3. ቁጥር 0953933030 ያስገቡ\n4. መጠኑን ያስገቡ\n5. ፒንዎን ያስገቡ'
            ))
            
            conn.commit()
    
    def get_or_create_user(self, user_id, username=None, first_name=None, last_name=None, phone_number=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            user = cursor.fetchone()
            
            if user:
                return dict(user)
            
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, last_name, phone_number, balance)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, phone_number, 1000))
            conn.commit()
            
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            return dict(cursor.fetchone())
    
    def get_user(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            user = cursor.fetchone()
            return dict(user) if user else None
    
    def update_balance(self, user_id, amount, transaction_type, description=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            user = cursor.fetchone()
            if not user:
                return None
            
            new_balance = user['balance'] + amount
            
            cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?', (new_balance, user_id))
            cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (?, ?, ?, ?)
            ''', (user_id, amount, transaction_type, description))
            
            if transaction_type == 'game_win':
                cursor.execute('UPDATE users SET games_won = games_won + 1 WHERE user_id = ?', (user_id,))
            
            conn.commit()
            return {'new_balance': new_balance}
    
    def create_game(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO games (status) VALUES (?)', ('waiting',))
            conn.commit()
            return cursor.lastrowid
    
    def get_active_game(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM games WHERE status = "waiting" ORDER BY created_at DESC LIMIT 1')
            game = cursor.fetchone()
            return dict(game) if game else None
    
    def add_player_card(self, game_id, user_id, card_id, card_data, stake):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO player_cards (game_id, user_id, card_id, card_data, stake)
                VALUES (?, ?, ?, ?, ?)
            ''', (game_id, user_id, card_id, json.dumps(card_data), stake))
            conn.commit()
            return cursor.lastrowid
    
    def start_game(self, game_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE games SET status = "active", started_at = CURRENT_TIMESTAMP WHERE id = ?', (game_id,))
            conn.commit()
    
    def end_game(self, game_id, winner_id, winner_card_id, amount):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE games 
                SET status = "ended", 
                    ended_at = CURRENT_TIMESTAMP,
                    winner_id = ?,
                    winner_card_id = ?,
                    winning_amount = ?
                WHERE id = ?
            ''', (winner_id, winner_card_id, amount, game_id))
            conn.commit()
    
    def add_called_number(self, game_id, number):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO called_numbers (game_id, number) VALUES (?, ?)', (game_id, number))
            conn.commit()
    
    def get_called_numbers(self, game_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT number FROM called_numbers WHERE game_id = ? ORDER BY called_at', (game_id,))
            return [row['number'] for row in cursor.fetchall()]
    
    def get_payment_methods(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM payment_methods')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_payment_method(self, method_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM payment_methods WHERE id = ?', (method_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def create_payment_request(self, user_id, method_id, amount, sender_phone=None):
        request_id = f"PAY-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO payment_requests (request_id, user_id, method_id, amount, sender_phone)
                VALUES (?, ?, ?, ?, ?)
            ''', (request_id, user_id, method_id, amount, sender_phone))
            conn.commit()
            return request_id