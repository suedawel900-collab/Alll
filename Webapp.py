import os
import json
import asyncio
import random
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging

from models import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

db = Database()

# Load bingo cards
with open("static/bingo_cards.json", "r") as f:
    BINGO_CARDS = json.load(f)
    CARDS_BY_ID = {card["id"]: card["card"] for card in BINGO_CARDS}

# Game settings
CARD_PRICE = 1000  # 10 ETB in cents
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID', '8741250511')

# Game manager
class GameManager:
    def __init__(self):
        self.active_games = {}
        self.connections = {}
        self.number_tasks = {}
    
    async def connect(self, game_id: int, websocket: WebSocket, user_id: int):
        await websocket.accept()
        
        if game_id not in self.connections:
            self.connections[game_id] = set()
            self.active_games[game_id] = {
                'players': {},
                'called_numbers': [],
                'started': False,
                'winner': None
            }
        
        self.connections[game_id].add(websocket)
        
        # Get user data
        user = db.get_user(user_id)
        if not user:
            user = db.get_or_create_user(user_id)
        
        # Send initial state
        await websocket.send_json({
            'type': 'connected',
            'players': self.get_players(game_id),
            'called_numbers': self.active_games[game_id]['called_numbers'],
            'started': self.active_games[game_id]['started'],
            'balance': user['balance'] / 100
        })
    
    def disconnect(self, game_id: int, websocket: WebSocket):
        if game_id in self.connections:
            self.connections[game_id].discard(websocket)
    
    async def broadcast(self, game_id: int, message: dict):
        if game_id in self.connections:
            for conn in self.connections[game_id]:
                try:
                    await conn.send_json(message)
                except:
                    pass
    
    def get_players(self, game_id: int):
        players = []
        for uid, data in self.active_games[game_id]['players'].items():
            players.append({
                'id': uid,
                'name': data.get('name', f'Player{uid}'),
                'cards': data.get('cards', []),
                'ready': data.get('ready', False)
            })
        return players
    
    async def select_cards(self, game_id: int, user_id: int, card_ids: list):
        if game_id not in self.active_games:
            return False, "Game not found"
        
        if self.active_games[game_id]['started']:
            return False, "Game already started"
        
        user = db.get_user(user_id)
        total_cost = len(card_ids) * CARD_PRICE
        
        if user['balance'] < total_cost:
            return False, "Insufficient balance"
        
        # Store player cards
        if user_id not in self.active_games[game_id]['players']:
            user_data = db.get_user(user_id)
            self.active_games[game_id]['players'][user_id] = {
                'name': user_data.get('first_name', f'Player{user_id}'),
                'cards': [],
                'marked': {},
                'ready': False
            }
        
        player = self.active_games[game_id]['players'][user_id]
        
        for card_id in card_ids:
            if card_id in CARDS_BY_ID:
                player['cards'].append({
                    'id': card_id,
                    'data': CARDS_BY_ID[card_id],
                    'marked': []
                })
                player['marked'][card_id] = []
        
        return True, "Cards selected"
    
    async def finalize_selection(self, game_id: int, user_id: int):
        if game_id not in self.active_games:
            return False, "Game not found"
        
        if user_id not in self.active_games[game_id]['players']:
            return False, "Player not found"
        
        player = self.active_games[game_id]['players'][user_id]
        card_count = len(player['cards'])
        
        if card_count == 0:
            return False, "No cards selected"
        
        total_cost = card_count * CARD_PRICE
        
        # Deduct balance
        result = db.update_balance(
            user_id=user_id,
            amount=-total_cost,
            transaction_type='game_fee',
            description=f'Joined game #{game_id} with {card_count} cards'
        )
        
        if not result:
            return False, "Failed to deduct balance"
        
        # Store cards in database
        for card in player['cards']:
            db.add_player_card(
                game_id=game_id,
                user_id=user_id,
                card_id=card['id'],
                card_data=card['data'],
                stake=CARD_PRICE
            )
        
        player['ready'] = True
        
        await self.broadcast(game_id, {
            'type': 'player_ready',
            'players': self.get_players(game_id)
        })
        
        return True, "Ready to play"
    
    async def start_game(self, game_id: int, user_id: int):
        if str(user_id) != ADMIN_USER_ID:
            return False, "Not authorized"
        
        if game_id not in self.active_games:
            return False, "Game not found"
        
        if self.active_games[game_id]['started']:
            return False, "Game already started"
        
        # Check if any players are ready
        ready_count = sum(1 for p in self.active_games[game_id]['players'].values() if p.get('ready', False))
        if ready_count == 0:
            return False, "No players ready"
        
        self.active_games[game_id]['started'] = True
        self.active_games[game_id]['called_numbers'] = []
        
        # Update game in database
        db.start_game(game_id)
        
        # Start number generation
        self.number_tasks[game_id] = asyncio.create_task(
            self.generate_numbers(game_id)
        )
        
        await self.broadcast(game_id, {'type': 'game_started'})
        
        return True, "Game started"
    
    async def generate_numbers(self, game_id: int):
        try:
            while game_id in self.active_games and self.active_games[game_id]['started']:
                await asyncio.sleep(2)
                
                available = [n for n in range(1, 76) 
                           if n not in self.active_games[game_id]['called_numbers']]
                
                if available:
                    number = random.choice(available)
                    self.active_games[game_id]['called_numbers'].append(number)
                    
                    # Save to database
                    db.add_called_number(game_id, number)
                    
                    await self.broadcast(game_id, {
                        'type': 'number_called',
                        'number': number,
                        'called': self.active_games[game_id]['called_numbers']
                    })
                    
                    # Check for winners
                    await self.check_winners(game_id, number)
                else:
                    # No numbers left
                    await self.broadcast(game_id, {'type': 'game_over'})
                    break
                    
        except asyncio.CancelledError:
            pass
    
    async def check_winners(self, game_id: int, last_number: int):
        if self.active_games[game_id]['winner']:
            return
        
        called = set(self.active_games[game_id]['called_numbers'])
        
        for user_id, player in self.active_games[game_id]['players'].items():
            if not player.get('ready', False):
                continue
            
            for card in player['cards']:
                if self.check_bingo(card['data'], card['marked'], called):
                    await self.declare_winner(game_id, user_id, card['id'])
                    return
    
    def check_bingo(self, card, marked, called):
        marked_set = set(marked)
        
        # Check rows
        for row in range(5):
            bingo = True
            for col in range(5):
                val = card[col][row]
                if val != 'FREE' and val not in called:
                    bingo = False
                    break
            if bingo:
                return True
        
        # Check columns
        for col in range(5):
            bingo = True
            for row in range(5):
                val = card[col][row]
                if val != 'FREE' and val not in called:
                    bingo = False
                    break
            if bingo:
                return True
        
        # Check diagonals
        diag1 = True
        diag2 = True
        for i in range(5):
            val1 = card[i][i]
            val2 = card[4-i][i]
            
            if val1 != 'FREE' and val1 not in called:
                diag1 = False
            if val2 != 'FREE' and val2 not in called:
                diag2 = False
        
        return diag1 or diag2
    
    async def declare_winner(self, game_id: int, user_id: int, card_id: int):
        self.active_games[game_id]['started'] = False
        self.active_games[game_id]['winner'] = {
            'user_id': user_id,
            'card_id': card_id
        }
        
        # Calculate prize pool (90% of total stakes)
        prize_pool = db.get_game_prize_pool(game_id)
        winner_prize = int(prize_pool * 0.9)
        
        # Add to winner's balance - IMMEDIATELY!
        db.update_balance(
            user_id=user_id,
            amount=winner_prize,
            transaction_type='game_win',
            description=f'Won game #{game_id} with card #{card_id}'
        )
        
        # End game in database
        db.end_game(game_id, user_id, card_id, winner_prize)
        
        # Get winner info
        user = db.get_user(user_id)
        winner_name = user.get('first_name', f'Player{user_id}')
        
        await self.broadcast(game_id, {
            'type': 'game_won',
            'winner': {
                'name': winner_name,
                'card_id': card_id,
                'prize': winner_prize / 100
            }
        })
        
        # Cancel number generation
        if game_id in self.number_tasks:
            self.number_tasks[game_id].cancel()
    
    def mark_number(self, game_id: int, user_id: int, card_id: int, number: int):
        if game_id not in self.active_games:
            return False
        
        if not self.active_games[game_id]['started']:
            return False
        
        if user_id not in self.active_games[game_id]['players']:
            return False
        
        player = self.active_games[game_id]['players'][user_id]
        
        for card in player['cards']:
            if card['id'] == card_id:
                if number not in card['marked']:
                    card['marked'].append(number)
                return True
        
        return False

game_manager = GameManager()

# API endpoints
@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/game", response_class=HTMLResponse)
async def game_page(request: Request, user_id: int, game_id: int = 1):
    user = db.get_user(user_id)
    if not user:
        user = db.get_or_create_user(user_id)
    
    return templates.TemplateResponse("bingo.html", {
        "request": request,
        "user_id": user_id,
        "game_id": game_id,
        "admin_id": ADMIN_USER_ID,
        "price_per_card": CARD_PRICE / 100,
        "max_cards": 20,
        "initial_balance": user['balance'] / 100,
        "initial_active_games": 0,
        "initial_stake": 0
    })

@app.websocket("/ws/{game_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: int, user_id: int):
    await game_manager.connect(game_id, websocket, user_id)
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data['type'] == 'select_cards':
                success, message = await game_manager.select_cards(
                    game_id, user_id, data['card_ids']
                )
                await websocket.send_json({
                    'type': 'cards_selected',
                    'success': success,
                    'message': message
                })
                
                if success:
                    for card_id in data['card_ids']:
                        await websocket.send_json({
                            'type': 'your_card',
                            'card_id': card_id,
                            'card': CARDS_BY_ID[card_id]
                        })
            
            elif data['type'] == 'finalize':
                success, message = await game_manager.finalize_selection(game_id, user_id)
                await websocket.send_json({
                    'type': 'finalized',
                    'success': success,
                    'message': message
                })
            
            elif data['type'] == 'start_game':
                success, message = await game_manager.start_game(game_id, user_id)
                await websocket.send_json({
                    'type': 'start_result',
                    'success': success,
                    'message': message
                })
            
            elif data['type'] == 'mark_number':
                success = game_manager.mark_number(
                    game_id, user_id, data['card_id'], data['number']
                )
                if success:
                    await websocket.send_json({
                        'type': 'number_marked',
                        'card_id': data['card_id'],
                        'number': data['number']
                    })
            
            elif data['type'] == 'ping':
                await websocket.send_json({'type': 'pong'})
                
    except WebSocketDisconnect:
        game_manager.disconnect(game_id, websocket)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)