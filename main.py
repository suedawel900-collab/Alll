import os
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)

from database import (
    init_db,
    SessionLocal,
    User,
    Round,
    Card,
    CardPurchase,
    HouseCommission
)

# =========================
# INIT
# =========================

init_db()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set!")

logging.basicConfig(level=logging.INFO)

# =========================
# DATABASE HELPERS
# =========================

def get_active_round(db):
    return db.query(Round).filter_by(is_active=True).first()


def create_new_round():
    db = SessionLocal()

    last_round = db.query(Round).order_by(Round.id.desc()).first()
    next_number = 1 if not last_round else last_round.round_number + 1

    new_round = Round(round_number=next_number)
    db.add(new_round)
    db.commit()

    # Create 1000 cards
    for i in range(1, 1001):
        card = Card(card_number=i, round_id=new_round.id)
        db.add(card)

    db.commit()
    db.close()


# =========================
# COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()

    telegram_id = str(update.effective_user.id)
    username = update.effective_user.username

    user = db.query(User).filter_by(telegram_id=telegram_id).first()

    if not user:
        user = User(
            telegram_id=telegram_id,
            username=username,
            balance=100  # starter bonus
        )
        db.add(user)
        db.commit()

    if not get_active_round(db):
        create_new_round()

    await update.message.reply_text(
        f"🎉 Welcome to Bingo!\n\n"
        f"💰 Balance: {user.balance}\n"
        f"🎟 Card price: 10\n\n"
        f"Use /buy <card_number>\nExample: /buy 25"
    )

    db.close()


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()

    telegram_id = str(update.effective_user.id)
    user = db.query(User).filter_by(telegram_id=telegram_id).first()

    await update.message.reply_text(f"💰 Your Balance: {user.balance}")

    db.close()


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()

    telegram_id = str(update.effective_user.id)
    user = db.query(User).filter_by(telegram_id=telegram_id).first()

    if len(context.args) == 0:
        await update.message.reply_text("❌ Use /buy <card_number>")
        db.close()
        return

    card_number = int(context.args[0])

    if user.balance < 10:
        await update.message.reply_text("❌ Not enough balance.")
        db.close()
        return

    current_round = get_active_round(db)

    card = db.query(Card).filter_by(
        round_id=current_round.id,
        card_number=card_number,
        is_taken=False
    ).first()

    if not card:
        await update.message.reply_text("❌ Card already taken.")
        db.close()
        return

    card.is_taken = True
    user.balance -= 10
    current_round.total_pool += 10

    purchase = CardPurchase(
        user_id=user.id,
        card_id=card.id,
        round_id=current_round.id
    )

    db.add(purchase)
    db.commit()

    await update.message.reply_text(f"✅ Card {card_number} purchased!")

    db.close()


async def win(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin command: /win <telegram_id>
    """
    db = SessionLocal()

    if len(context.args) == 0:
        await update.message.reply_text("❌ Use /win <telegram_id>")
        db.close()
        return

    winner_telegram_id = context.args[0]

    winner = db.query(User).filter_by(
        telegram_id=winner_telegram_id
    ).first()

    current_round = get_active_round(db)

    if not winner or not current_round:
        await update.message.reply_text("❌ Error.")
        db.close()
        return

    total_pool = float(current_round.total_pool)
    house_cut = total_pool * 0.20
    winner_amount = total_pool - house_cut

    winner.balance += winner_amount
    winner.total_wins += 1

    current_round.winner_id = winner.id
    current_round.is_active = False
    current_round.ended_at = datetime.utcnow()

    commission = HouseCommission(
        round_id=current_round.id,
        amount=house_cut
    )

    db.add(commission)
    db.commit()

    await update.message.reply_text(
        f"🏆 Winner Paid!\n"
        f"💰 Prize: {winner_amount}\n"
        f"🏦 House: {house_cut}"
    )

    db.close()

    # Auto start new round
    create_new_round()


# =========================
# MAIN
# =========================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("win", win))

    app.run_polling()


if __name__ == "__main__":
    main()