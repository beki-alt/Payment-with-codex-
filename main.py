from __future__ import annotations

import asyncio
import os
from datetime import datetime, time

import pytz
from ethiopian_date import EthiopianDateConverter
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from admin_handlers import (
    add_admin,
    admin_home,
    broadcast,
    debtors,
    export_report,
    list_admins,
    override_paid,
    process_receipt_callback,
    remove_admin,
    set_bank,
    set_cycle,
)
from database import Database, cycle_key_ethiopian, keep_alive
from user_handlers import edit_name, history, pay, profile, receipt_photo, schedule, start, support

TZ = pytz.timezone("Africa/Addis_Ababa")


async def admin_guard(update, context, fn):
    db: Database = context.application.bot_data["db"]
    if not await db.is_admin(update.effective_user.id):
        return await update.effective_message.reply_text("Admin only.")
    await fn(update, context)


async def reminders(context):
    db: Database = context.application.bot_data["db"]
    now_dt = datetime.now(TZ)
    e = EthiopianDateConverter.to_ethiopian(now_dt.year, now_dt.month, now_dt.day)
    settings = await db.get_settings()

    mapping = {
        settings["billing_start_day"]: ("notify_25", settings["msg_start"]),
        4: ("notify_4", settings["msg_before_last"]),
        settings["billing_end_day"]: ("notify_5", settings["msg_last"]),
    }
    if e.day not in mapping:
        return
    toggle_key, msg = mapping[e.day]
    if not settings.get(toggle_key, True):
        return

    cycle_key = cycle_key_ethiopian(now_dt, settings["billing_start_day"])
    for u in await db.debtors(cycle_key):
        try:
            await context.bot.send_message(u["telegram_id"], msg)
        except Exception:
            pass


async def on_start(app: Application):
    db: Database = app.bot_data["db"]
    await db.connect()
    asyncio.create_task(keep_alive(db, 48))


def main():
    token = os.getenv("TELEGRAM_TOKEN")
    db = Database(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    super_admin = int(os.getenv("ADMIN_ID", "0"))
    channel_id = int(os.getenv("CHANNEL_ID", "-1000000000000"))

    app = Application.builder().token(token).post_init(on_start).timezone(TZ).build()
    app.bot_data["db"] = db

    app.add_handler(CommandHandler("start", lambda u, c: start(u, c, db)))
    app.add_handler(CommandHandler("profile", lambda u, c: profile(u, c, db)))
    app.add_handler(CommandHandler("pay", lambda u, c: pay(u, c, db)))
    app.add_handler(CommandHandler("schedule", lambda u, c: schedule(u, c, db)))
    app.add_handler(CommandHandler("history", lambda u, c: history(u, c, db)))
    app.add_handler(CommandHandler("edit_name", lambda u, c: edit_name(u, c, db)))
    app.add_handler(CommandHandler("support", lambda u, c: support(u, c, db)))
    app.add_handler(MessageHandler(filters.PHOTO, lambda u, c: receipt_photo(u, c, db, channel_id)))

    app.add_handler(CommandHandler("admin", lambda u, c: admin_guard(u, c, admin_home)))
    app.add_handler(CommandHandler("add_admin", lambda u, c: admin_guard(u, c, lambda uu, cc: add_admin(uu, cc, db, super_admin))))
    app.add_handler(CommandHandler("remove_admin", lambda u, c: admin_guard(u, c, lambda uu, cc: remove_admin(uu, cc, db, super_admin))))
    app.add_handler(CommandHandler("admins", lambda u, c: admin_guard(u, c, lambda uu, cc: list_admins(uu, cc, db))))
    app.add_handler(CommandHandler("debtors", lambda u, c: admin_guard(u, c, lambda uu, cc: debtors(uu, cc, db, datetime.now(TZ)))))
    app.add_handler(CommandHandler("override_paid", lambda u, c: admin_guard(u, c, lambda uu, cc: override_paid(uu, cc, db, datetime.now(TZ)))))
    app.add_handler(CommandHandler("set_bank", lambda u, c: admin_guard(u, c, lambda uu, cc: set_bank(uu, cc, db))))
    app.add_handler(CommandHandler("set_cycle", lambda u, c: admin_guard(u, c, lambda uu, cc: set_cycle(uu, cc, db))))
    app.add_handler(CommandHandler("broadcast", lambda u, c: admin_guard(u, c, lambda uu, cc: broadcast(uu, cc, db))))
    app.add_handler(CommandHandler("report", lambda u, c: admin_guard(u, c, lambda uu, cc: export_report(uu, cc, db))))
    app.add_handler(CallbackQueryHandler(lambda u, c: process_receipt_callback(u, c, db, datetime.now(TZ))))

    app.job_queue.run_daily(reminders, time=time(9, 0, tzinfo=TZ), name="eth_reminders")
    app.run_polling()


if __name__ == "__main__":
    main()
