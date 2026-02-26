import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def root():
    return {"status": "online", "message": "Bingo Game API"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/game", response_class=HTMLResponse)
async def game(request: Request, user_id: int, game_id: int = 1):
    return templates.TemplateResponse("bingo.html", {
        "request": request,
        "user_id": user_id,
        "game_id": game_id,
        "admin_id": os.getenv('ADMIN_USER_ID', '8741250511'),
        "price_per_card": 10,
        "max_cards": 20,
        "initial_balance": 10,
        "initial_active_games": 0,
        "initial_stake": 0
    })