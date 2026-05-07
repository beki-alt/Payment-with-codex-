from __future__ import annotations

from datetime import datetime

import pytz
from ethiopian_date import EthiopianDateConverter
from telegram import Update
from telegram.ext import ContextTypes

from admin_handlers import approval_keyboard
from database import Database, cycle_key_ethiopian, days_until_end_ethiopian
from image_gen import generate_membership_card

TZ = pytz.timezone("Africa/Addis_Ababa")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    u = update.effective_user
    await db.ensure_user(u.id, u.full_name, u.username)
    await update.message.reply_text("Welcome. Use menu: Profile | Pay | Schedule | Support | Edit Name | History")


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    now_dt = datetime.now(TZ)
    settings = await db.get_settings()
    key = cycle_key_ethiopian(now_dt, settings["billing_start_day"])
    status = await db.payment_status(update.effective_user.id, key)
    user = await db.get_user(update.effective_user.id)
    e = EthiopianDateConverter.to_ethiopian(now_dt.year, now_dt.month, now_dt.day)
    expire = f"{e.year}-{e.month:02d}-{settings['billing_end_day']:02d}"
    await update.message.reply_text(f"Name: {user.get('full_name')}\nID: {update.effective_user.id}\nStatus: {status}\nExpire(ETH): {expire}")
    card = generate_membership_card(user.get("full_name", "-"), update.effective_user.id, status, expire)
    await update.message.reply_photo(photo=card)


async def edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    if not context.args:
        return await update.message.reply_text("Use: /edit_name New Name")
    await db.update_user_name(update.effective_user.id, " ".join(context.args))
    await update.message.reply_text("Name updated.")


async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    s = await db.get_settings()
    await update.message.reply_text(f"Bank: {s.get('bank_name')}\nAccount: {s.get('bank_account')}\nSend receipt photo here.")


async def receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database, channel_id: int):
    photo = update.message.photo[-1]
    posted = await context.bot.send_photo(channel_id, photo.file_id, caption=f"Receipt user={update.effective_user.id}")
    receipt = await db.create_receipt(update.effective_user.id, posted.message_id, photo.file_id)
    admins = (await db.c().table("admins").select("telegram_id").execute()).data or []
    for a in admins:
        await context.bot.send_photo(a["telegram_id"], photo.file_id, caption=f"Pending receipt #{receipt['id']}", reply_markup=approval_keyboard(receipt["id"], update.effective_user.id))
    await update.message.reply_text("Receipt sent to admin.")


async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    now_dt = datetime.now(TZ)
    e = EthiopianDateConverter.to_ethiopian(now_dt.year, now_dt.month, now_dt.day)
    s = await db.get_settings()
    left = days_until_end_ethiopian(now_dt, s["billing_end_day"])
    await update.message.reply_text(f"Today(ETH): {e.year}-{e.month:02d}-{e.day:02d}\nCycle: {s['billing_start_day']} to {s['billing_end_day']}\nDays left to deadline: {left}")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    rows = await db.payment_history(update.effective_user.id)
    if not rows:
        return await update.message.reply_text("No payment history.")
    lines = [f"- {r['cycle_key']} | {r.get('ethiopian_payment_date')}" for r in rows[:20]]
    await update.message.reply_text("Payment History:\n" + "\n".join(lines))


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    text = update.message.text.replace("Support", "").strip()
    admins = (await db.c().table("admins").select("telegram_id").execute()).data or []
    for a in admins:
        await context.bot.send_message(a["telegram_id"], f"Support from {update.effective_user.id}: {text}")
    await update.message.reply_text("Support message sent.")
