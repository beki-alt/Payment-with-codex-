from __future__ import annotations

import io

import pandas as pd
from ethiopian_date import EthiopianDateConverter
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Database, cycle_key_ethiopian


async def admin_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Admin menu: /add_admin /remove_admin /admins /debtors /override_paid /set_bank /set_cycle /broadcast /report")


async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database, super_admin: int):
    if update.effective_user.id != super_admin:
        return await update.message.reply_text("Only super admin can add admins.")
    if not context.args:
        return await update.message.reply_text("Use: /add_admin user_id")
    uid = int(context.args[0])
    await db.add_admin(uid)
    await update.message.reply_text("Admin added.")


async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database, super_admin: int):
    if update.effective_user.id != super_admin:
        return await update.message.reply_text("Only super admin can remove admins.")
    uid = int(context.args[0])
    await db.remove_admin(uid)
    await update.message.reply_text("Admin removed.")


async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    r = await db.c().table("admins").select("telegram_id,role").execute()
    text = "Admins:\n" + "\n".join([f"- {a['telegram_id']} ({a['role']})" for a in (r.data or [])])
    await update.message.reply_text(text)


async def debtors(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database, now_dt):
    settings = await db.get_settings()
    key = cycle_key_ethiopian(now_dt, settings["billing_start_day"])
    d = await db.debtors(key)
    if not d:
        return await update.message.reply_text("No debtors for this cycle.")
    await update.message.reply_text("Debtors:\n" + "\n".join([f"- {x['full_name']} ({x['telegram_id']})" for x in d[:200]]))


async def override_paid(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database, now_dt):
    uid = int(context.args[0])
    settings = await db.get_settings()
    key = cycle_key_ethiopian(now_dt, settings["billing_start_day"])
    e = EthiopianDateConverter.to_ethiopian(now_dt.year, now_dt.month, now_dt.day)
    await db.mark_paid(uid, key, f"{e.year}-{e.month:02d}-{e.day:02d}")
    await update.message.reply_text("User marked as paid.")


async def set_bank(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    payload = " ".join(context.args)
    if "|" not in payload:
        return await update.message.reply_text("Use: /set_bank BankName|AccountNumber")
    name, acc = payload.split("|", 1)
    await db.update_settings({"bank_name": name.strip(), "bank_account": acc.strip()})
    await update.message.reply_text("Bank info updated.")


async def set_cycle(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    start, end = int(context.args[0]), int(context.args[1])
    await db.update_settings({"billing_start_day": start, "billing_end_day": end})
    await update.message.reply_text("Cycle updated.")


async def process_receipt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database, now_dt):
    q = update.callback_query
    await q.answer()
    action, receipt_id, user_id = q.data.split(":")
    receipt_id, user_id = int(receipt_id), int(user_id)
    reviewer = q.from_user.id
    settings = await db.get_settings()

    if action == "approve":
        key = cycle_key_ethiopian(now_dt, settings["billing_start_day"])
        e = EthiopianDateConverter.to_ethiopian(now_dt.year, now_dt.month, now_dt.day)
        await db.set_receipt_review(receipt_id, "approved", reviewer)
        await db.mark_paid(user_id, key, f"{e.year}-{e.month:02d}-{e.day:02d}")
        await context.bot.send_message(user_id, settings["msg_approval"])
        await q.edit_message_caption("Approved ✅")
    else:
        reason = "Rejected by admin"
        await db.set_receipt_review(receipt_id, "rejected", reviewer, reason)
        await context.bot.send_message(user_id, f"{settings['msg_rejection']}\nReason: {reason}")
        await q.edit_message_caption("Rejected ❌")


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    text = " ".join(context.args)
    users = await db.list_users()
    for u in users:
        try:
            await context.bot.send_message(u["telegram_id"], text)
        except Exception:
            pass
    await update.message.reply_text("Broadcast sent.")


async def export_report(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    p = (await db.c().table("payments").select("*").execute()).data or []
    df = pd.DataFrame(p)
    file = io.BytesIO()
    df.to_excel(file, index=False)
    file.seek(0)
    file.name = "report.xlsx"
    await update.message.reply_document(file, caption="Report")


def approval_keyboard(receipt_id: int, user_id: int):
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve", callback_data=f"approve:{receipt_id}:{user_id}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject:{receipt_id}:{user_id}")]])
