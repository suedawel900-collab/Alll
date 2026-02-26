#!/usr/bin/env python3
import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Bingo Game")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Configuration
CARD_PRICE = 1000  # 10 ETB in cents
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID', '8741250511')

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "status": "online",
        "message": "Bingo Game API",
        "version": "1.0.0"
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.get("/game", response_class=HTMLResponse)
async def game_page(request: Request, user_id: int, game_id: int = 1):
    """Serve the game page"""
    logger.info(f"Serving game page for user {user_id}, game {game_id}")
    
    return templates.TemplateResponse("bingo.html", {
        "request": request,
        "user_id": user_id,
        "game_id": game_id,
        "admin_id": ADMIN_USER_ID,
        "price_per_card": CARD_PRICE / 100,
        "max_cards": 20,
        "initial_balance": 10.0,
        "initial_active_games": 0,
        "initial_stake": 0
    })