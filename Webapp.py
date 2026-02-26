import os
import json
import asyncio
import random
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging

from models import Database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Bingo Game WebApp")

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize database
db = Database()

# Load bingo cards
try:
    with open("static/bingo_cards.json", "r") as f:
        BINGO_CARDS = json.load(f)
        CARDS_BY_ID = {card["id"]: card["card"] for card in BINGO_CARDS}
    logger.info(f"✅ Loaded {len(BINGO_CARDS)} bingo cards")
except FileNotFoundError:
    logger.warning("⚠️ bingo_cards.json not found, generating sample cards")
    # Generate sample cards if file doesn't exist
    BINGO_CARDS = []
    for i in range(1, 101):  # Generate 100 sample cards
        card = []
        ranges = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75)]
        for col in range(5):
            min_num, max_num = ranges[col]
            numbers = random.sample(range(min_num, max_num + 1), 5)
            card.append(numbers)
        card[2][2] = "FREE"
        BINGO_CARDS.append({"id": i, "card": card})
    CARDS_BY_ID = {card["id"]: card["card"] for card in BINGO_CARDS}
    logger.info(f"✅ Generated {len(BINGO_CARDS)} sample cards")
except Exception as e:
    logger.error(f"❌ Error loading cards: {e}")
    BINGO_CARDS = []
    CARDS_BY_ID = {}

# Game settings
CARD_PRICE = 1000  # 10 ETB in cents
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID', '8741250511')

# Health check and root endpoints
@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Bingo Game API",
        "cards": len(CARDS_BY_ID),
        "price_per_card": CARD_PRICE / 100,
        "admin_id": ADMIN_USER_ID
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy", 
        "timestamp": time.time(),
        "cards_loaded": len(CARDS_BY_ID) > 0
    }

# API endpoint to get card data
@app.get("/api/cards")
async def get_cards():
    return {
        "total": len(BINGO_CARDS),
        "cards": [{"id": c["id"]} for c in BINGO_CARDS[:100]]  # Return first 100 card IDs
    }

@app.get("/api/card/{card_id}")
async def get_card(card_id: int):
    card = CARDS_BY_ID.get(card_id)
    if card:
        return {"id": card_id, "card": card}
    return JSONResponse({"error": "Card not found"}, status_code=404)

# Game Manager Class
class GameManager:
    def __init__(self):
        self.games = {}  # game_id -> game state
        self.connections = {}  # game_id -> set of websockets
    
    async def connect(self, game_id: int, websocket: WebSocket, user_id: int):
        await websocket.accept()
        
        # Initialize game if not exists
        if game_id not in self.connections:
            self.connections[game_id] = set()
            self.games[game_id] = {
                'players': {},
                'called_numbers': [],
                'started': False,
                'winner': None,
                'prize_pool': 0
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
            'called_numbers': self.games[game_id]['called_numbers'],
            'started': self.games[game_id]['started'],
            'balance': user['balance'] / 100,
            'prize_pool': self.games[game_id]['prize_pool'] / 100
        })
        
        logger.info(f"User {user_id} connected to game {game_id}")
    
    def disconnect(self, game_id: int, websocket: WebSocket):
        if game_id in self.connections:
            self.connections[game_id].discard(websocket)
            logger.info(f"User disconnected from game {game_id}")
    
    async def broadcast(self, game_id: int, message: dict):
        if game_id in self.connections:
            for conn in list(self.connections[game_id]):
                try:
                    await conn.send_json(message)
                except:
                    pass
    
    def get_players(self, game_id: int):
        if game_id not in self.games:
            return []
        
        players = []
        for uid, data in self.games[game_id]['players'].items():
            players.append({
                'id': uid,
                'name': data.get('name', f'Player{uid}'),
                'cards': len(data.get('cards', [])),
                'ready': data.get('ready', False)
            })
        return players
    
    async def select_cards(self, game_id: int, user_id: int, card_ids: list):
        if game_id not in self.games:
            return False, "Game not found"
        
        if self.games[game_id]['started']:
            return False, "Game already started"
        
        if self.games[game_id]['winner']:
            return False, "Game has ended"
        
        user = db.get_user(user_id)
        if not user:
            return False, "User not found"
        
        # Initialize player if not exists
        if user_id not in self.games[game_id]['players']:
            self.games[game_id]['players'][user_id] = {
                'name': user.get('first_name', f'Player{user_id}'),
                'cards': [],
                'card_ids': [],
                'ready': False
            }
        
        player = self.games[game_id]['players'][user_id]
        
        # Check if cards are available
        for card_id in card_ids:
            if card_id not in CARDS_BY_ID:
                return False, f"Card {card_id} not found"
            
            # Check if card is already taken by another player
            for p in self.games[game_id]['players'].values():
                if card_id in p.get('card_ids', []):
                    return False, f"Card {card_id} is already taken"
        
        # Add cards to player
        for card_id in card_ids:
            player['cards'].append({
                'id': card_id,
                'data': CARDS_BY_ID[card_id],
                'marked': []
            })
            player['card_ids'].append(card_id)
        
        return True, f"Selected {len(card_ids)} cards"
    
    async def finalize_selection(self, game_id: int, user_id: int):
        if game_id not in self.games:
            return False, "Game not found"
        
        if user_id not in self.games[game_id]['players']:
            return False, "Player not found"
        
        player = self.games[game_id]['players'][user_id]
        card_count = len(player['cards'])
        
        if card_count == 0:
            return False, "No cards selected"
        
        if player.get('ready'):
            return False, "Already ready"
        
        # Calculate total cost
        total_cost = card_count * CARD_PRICE
        
        # Check balance and deduct
        user = db.get_user(user_id)
        if not user or user['balance'] < total_cost:
            return False, "Insufficient balance"
        
        # Deduct from database
        result = db.update_balance(
            user_id=user_id,
            amount=-total_cost,
            transaction_type='game_fee',
            description=f'Joined game #{game_id} with {card_count} cards'
        )
        
        if not result:
            return False, "Failed to deduct balance"
        
        # Save cards to database
        for card in player['cards']:
            db.add_player_card(
                game_id=game_id,
                user_id=user_id,
                card_id=card['id'],
                card_data=card['data'],
                stake=CARD_PRICE
            )
        
        # Update prize pool
        self.games[game_id]['prize_pool'] += total_cost
        
        # Mark player as ready
        player['ready'] = True
        
        # Broadcast update
        await self.broadcast(game_id, {
            'type': 'player_ready',
            'players': self.get_players(game_id),
            'prize_pool': self.games[game_id]['prize_pool'] / 100
        })
        
        return True, "Ready to play"
    
    async def start_game(self, game_id: int, user_id: int):
        if str(user_id) != ADMIN_USER_ID:
            return False, "Not authorized"
        
        if game_id not in self.games:
            return False, "Game not found"
        
        if self.games[game_id]['started']:
            return False, "Game already started"
        
        # Check if any players are ready
        ready_count = sum(1 for p in self.games[game_id]['players'].values() if p.get('ready'))
        if ready_count == 0:
            return False, "No players ready"
        
        # Start the game
        self.games[game_id]['started'] = True
        self.games[game_id]['called_numbers'] = []
        self.games[game_id]['winner'] = None
        
        # Update database
        db.start_game(game_id)
        
        # Start number generation task
        asyncio.create_task(self.run_game(game_id))
        
        await self.broadcast(game_id, {'type': 'game_started'})
        
        return True, "Game started"
    
    async def run_game(self, game_id: int):
        """Run the game - generate numbers every 2 seconds"""
        game = self.games[game_id]
        
        for _ in range(75):  # Max 75 numbers
            if not game['started'] or game['winner']:
                break
            
            await asyncio.sleep(2)
            
            # Get available numbers
            available = [n for n in range(1, 76) 
                        if n not in game['called_numbers']]
            
            if available:
                number = random.choice(available)
                game['called_numbers'].append(number)
                
                # Save to database
                db.add_called_number(game_id, number)
                
                # Broadcast number
                await self.broadcast(game_id, {
                    'type': 'number_called',
                    'number': number,
                    'called': game['called_numbers'],
                    'left': len(available) - 1
                })
                
                # Check for winners
                await self.check_winners(game_id, number)
            else:
                # No numbers left
                await self.broadcast(game_id, {'type': 'game_over'})
                break
    
    async def check_winners(self, game_id: int, last_number: int):
        """Check if anyone won after a number is called"""
        game = self.games[game_id]
        
        if game['winner']:
            return
        
        called_set = set(game['called_numbers'])
        
        for user_id, player in game['players'].items():
            if not player.get('ready') or not player.get('cards'):
                continue
            
            for card in player['cards']:
                if self.check_bingo(card['data'], called_set):
                    await self.declare_winner(game_id, user_id, card['id'])
                    return
    
    def check_bingo(self, card, called_set):
        """Check if a card has bingo"""
        # Check rows
        for row in range(5):
            if all(card[col][row] == 'FREE' or card[col][row] in called_set for col in range(5)):
                return True
        
        # Check columns
        for col in range(5):
            if all(card[col][row] == 'FREE' or card[col][row] in called_set for row in range(5)):
                return True
        
        # Check diagonals
        if all(card[i][i] == 'FREE' or card[i][i] in called_set for i in range(5)):
            return True
        if all(card[i][4-i] == 'FREE' or card[i][4-i] in called_set for i in range(5)):
            return True
        
        return False
    
    async def declare_winner(self, game_id: int, user_id: int, card_id: int):
        """Declare a winner and award prize"""
        game = self.games[game_id]
        
        # Stop the game
        game['started'] = False
        game['winner'] = {
            'user_id': user_id,
            'card_id': card_id
        }
        
        # Calculate prize (90% of prize pool)
        prize_pool = game['prize_pool']
        winner_prize = int(prize_pool * 0.9)
        
        # Award prize to winner
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
        winner_name = user.get('first_name', f'Player{user_id}') if user else f'Player{user_id}'
        
        # Broadcast win
        await self.broadcast(game_id, {
            'type': 'game_won',
            'winner': {
                'name': winner_name,
                'card_id': card_id,
                'prize': winner_prize / 100
            }
        })
        
        logger.info(f"Game {game_id} winner: {winner_name} with card #{card_id}, prize: {winner_prize/100} ETB")

# Initialize game manager
game_manager = GameManager()

# Game page endpoint
@app.get("/game", response_class=HTMLResponse)
async def game_page(request: Request, user_id: int, game_id: int = 1):
    """Serve the bingo game HTML page"""
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

# WebSocket endpoint for real-time game communication
@app.websocket("/ws/{game_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: int, user_id: int):
    await game_manager.connect(game_id, websocket, user_id)
    
    try:
        while True:
            # Receive message from client
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
                
                # Send each selected card to the client
                if success:
                    for card_id in data['card_ids']:
                        if card_id in CARDS_BY_ID:
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
            
            elif data['type'] == 'ping':
                await websocket.send_json({'type': 'pong'})
            
    except WebSocketDisconnect:
        game_manager.disconnect(game_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")

# Run with uvicorn if executed directly
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)