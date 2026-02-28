import random
from database import SessionLocal
from models import Game, Draw, Card, User, Transaction
import os
from telegram import Bot
import asyncio

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

bot = Bot(BOT_TOKEN)

def generate_card():
    columns = [
        range(1,16),
        range(16,31),
        range(31,46),
        range(46,61),
        range(61,76)
    ]
    card = []
    for col in columns:
        card.append(random.sample(list(col),5))
    return card

def create_new_game():
    db = SessionLocal()
    game = Game(game_code=random.randint(10000,99999), status="running")
    db.add(game)
    db.commit()

    for _ in range(1000):
        card = Card(game_id=game.id, numbers=generate_card())
        db.add(card)

    db.commit()
    db.close()

def get_running_game():
    db = SessionLocal()
    game = db.query(Game).filter(Game.status=="running").first()
    db.close()
    return game

def draw_number():
    db = SessionLocal()
    game = db.query(Game).filter(Game.status=="running").first()
    if not game:
        db.close()
        return

    drawn = [d.number_drawn for d in db.query(Draw).filter(Draw.game_id==game.id).all()]
    available = list(set(range(1,76)) - set(drawn))

    if not available:
        end_game(game.id)
        db.close()
        return

    number = random.choice(available)
    db.add(Draw(game_id=game.id, number_drawn=number))
    db.commit()
    db.close()

def check_winner(game_id):
    db = SessionLocal()
    drawn = [d.number_drawn for d in db.query(Draw).filter(Draw.game_id==game_id).all()]
    cards = db.query(Card).filter(Card.game_id==game_id).all()

    for card in cards:
        flat = [num for col in card.numbers for num in col]
        if all(n in drawn for n in flat[:5]):  # simple row check
            reward_winner(card.user_id, game_id)
            break

    db.close()

def reward_winner(user_id, game_id):
    db = SessionLocal()
    game = db.query(Game).get(game_id)
    user = db.query(User).get(user_id)

    total = game.prize_pool
    commission = total * 0.20
    winner_amount = total - commission

    user.balance += winner_amount
    db.add(Transaction(user_id=user.id, amount=winner_amount, type="win"))
    db.add(Transaction(user_id=0, amount=commission, type="commission"))

    game.status = "ended"
    db.commit()

    asyncio.create_task(
        bot.send_message(CHANNEL_ID,
        f"🏆 Winner: {user.username}\n💰 Prize: {winner_amount}")
    )

    db.close()
    asyncio.create_task(start_new_round())

async def auto_draw():
    while True:
        await asyncio.sleep(5)
        draw_number()

async def start_new_round():
    await asyncio.sleep(10)
    create_new_game()