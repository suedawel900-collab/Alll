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
except Exception as e:
    logger.error(f"❌ Failed to load cards: {e}")
    CARDS_BY_ID = {}

CARD_PRICE = 1000  # 10 ETB in cents
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID', '')

# Add health check endpoint
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "cards": len(CARDS_BY_ID),
        "timestamp": asyncio.get_event_loop().time()
    }

@app.get("/")
async def root():
    return {
        "message": "Bingo Game API",
        "cards": len(CARDS_BY_ID),
        "price_per_card": CARD_PRICE / 100
    }

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

# ... rest of your WebSocket code remains the same ...