import os
import json
import asyncio
import random
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

# Load cards
try:
    with open("static/bingo_cards.json", "r") as f:
        BINGO_CARDS = json.load(f)
        CARDS_BY_ID = {c["id"]: c["card"] for c in BINGO_CARDS}
    logger.info(f"✅ Loaded {len(BINGO_CARDS)} cards")
except:
    logger.error("❌ No cards found")
    CARDS_BY_ID = {}

CARD_PRICE = 1000
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID', '')

class GameManager:
    def __init__(self):
        self.games = {}
        self.connections = {}
    
    async def connect(self, game_id: int, ws: WebSocket, user_id: int):
        await ws.accept()
        
        if game_id not in self.connections:
            self.connections[game_id] = set()
            self.games[game_id] = {
                'players': {},
                'called': [],
                'started': False,
                'winner': None
            }
        
        self.connections[game_id].add(ws)
        
        user = db.get_user(user_id) or db.get_or_create_user(user_id)
        
        await ws.send_json({
            'type': 'connected',
            'players': list(self.games[game_id]['players'].values()),
            'called': self.games[game_id]['called'],
            'started': self.games[game_id]['started'],
            'balance': user['balance'] / 100
        })
    
    def disconnect(self, game_id: int, ws: WebSocket):
        if game_id in self.connections:
            self.connections[game_id].discard(ws)
    
    async def broadcast(self, game_id: int, msg: dict):
        if game_id in self.connections:
            for conn in self.connections[game_id]:
                try:
                    await conn.send_json(msg)
                except:
                    pass

manager = GameManager()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/game", response_class=HTMLResponse)
async def game_page(request: Request, user_id: int, game_id: int = 1):
    user = db.get_user(user_id) or db.get_or_create_user(user_id)
    
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
async def websocket_endpoint(ws: WebSocket, game_id: int, user_id: int):
    await manager.connect(game_id, ws, user_id)
    
    try:
        while True:
            data = await ws.receive_json()
            
            if data['type'] == 'select_cards':
                game = manager.games[game_id]
                
                if user_id not in game['players']:
                    user = db.get_user(user_id)
                    game['players'][user_id] = {
                        'id': user_id,
                        'name': user.get('first_name', f'User{user_id}'),
                        'cards': [],
                        'ready': False
                    }
                
                player = game['players'][user_id]
                total_cost = len(data['card_ids']) * CARD_PRICE
                
                await ws.send_json({'type': 'cards_selected', 'success': True})
                
                for card_id in data['card_ids']:
                    if card_id in CARDS_BY_ID:
                        player['cards'].append({
                            'id': card_id,
                            'data': CARDS_BY_ID[card_id],
                            'marked': []
                        })
                        await ws.send_json({
                            'type': 'your_card',
                            'card_id': card_id,
                            'card': CARDS_BY_ID[card_id]
                        })
            
            elif data['type'] == 'finalize':
                game = manager.games[game_id]
                if user_id in game['players']:
                    player = game['players'][user_id]
                    card_count = len(player['cards'])
                    
                    if card_count > 0:
                        total_cost = card_count * CARD_PRICE
                        result = db.update_balance(
                            user_id, -total_cost, 'game_fee', 
                            f'Game {game_id} - {card_count} cards'
                        )
                        
                        if result:
                            player['ready'] = True
                            await manager.broadcast(game_id, {
                                'type': 'player_ready',
                                'players': list(game['players'].values())
                            })
                            await ws.send_json({'type': 'finalized', 'success': True})
                        else:
                            await ws.send_json({'type': 'finalized', 'success': False})
            
            elif data['type'] == 'start_game' and str(user_id) == ADMIN_USER_ID:
                game = manager.games[game_id]
                game['started'] = True
                game['called'] = []
                
                asyncio.create_task(run_game(game_id))
                await manager.broadcast(game_id, {'type': 'game_started'})
            
            elif data['type'] == 'ping':
                await ws.send_json({'type': 'pong'})

    except WebSocketDisconnect:
        manager.disconnect(game_id, ws)

async def run_game(game_id: int):
    game = manager.games[game_id]
    
    for _ in range(75):
        if not game['started'] or game['winner']:
            break
        
        await asyncio.sleep(2)
        
        available = [n for n in range(1, 76) if n not in game['called']]
        if available:
            number = random.choice(available)
            game['called'].append(number)
            
            await manager.broadcast(game_id, {
                'type': 'number_called',
                'number': number,
                'called': game['called']
            })
            
            # Check for winner
            for player in game['players'].values():
                if not player.get('ready'):
                    continue
                
                for card in player['cards']:
                    if check_bingo(card['data'], game['called']):
                        await declare_winner(game_id, player['id'], card['id'])
                        return

def check_bingo(card, called):
    called_set = set(called)
    
    for row in range(5):
        if all(card[col][row] == 'FREE' or card[col][row] in called_set for col in range(5)):
            return True
    
    for col in range(5):
        if all(card[col][row] == 'FREE' or card[col][row] in called_set for row in range(5)):
            return True
    
    if all(card[i][i] == 'FREE' or card[i][i] in called_set for i in range(5)):
        return True
    
    if all(card[i][4-i] == 'FREE' or card[i][4-i] in called_set for i in range(5)):
        return True
    
    return False

async def declare_winner(game_id: int, user_id: int, card_id: int):
    game = manager.games[game_id]
    game['started'] = False
    game['winner'] = {'user_id': user_id, 'card_id': card_id}
    
    # Calculate prize (total stakes * 0.9)
    total_stake = 0
    for p in game['players'].values():
        if p.get('ready'):
            total_stake += len(p['cards']) * CARD_PRICE
    
    prize = int(total_stake * 0.9)
    
    # Add to winner's balance
    db.update_balance(user_id, prize, 'game_win', f'Won game {game_id}')
    
    # Get winner name
    user = db.get_user(user_id)
    name = user.get('first_name', f'User{user_id}') if user else f'User{user_id}'
    
    await manager.broadcast(game_id, {
        'type': 'game_won',
        'winner': {'name': name, 'card_id': card_id, 'prize': prize / 100}
    })

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)