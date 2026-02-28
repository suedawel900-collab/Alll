import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from database import Base, engine
from game_engine import auto_draw, create_new_game
import bot

Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def startup():
    create_new_game()
    asyncio.create_task(auto_draw())

@app.get("/", response_class=HTMLResponse)
def webapp(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
def admin_panel(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

if __name__ == "__main__":
    import threading
    threading.Thread(target=bot.run_bot).start()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)