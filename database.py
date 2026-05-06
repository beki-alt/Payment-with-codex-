from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from ethiopian_date import EthiopianDateConverter
from supabase import AsyncClient, acreate_client


@dataclass
class BillingCycle:
    start_day: int = 25
    end_day: int = 5


class Database:
    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key
        self.client: Optional[AsyncClient] = None

    async def connect(self):
        self.client = await acreate_client(self.url, self.key)

    def c(self) -> AsyncClient:
        if not self.client:
            raise RuntimeError("Supabase not connected")
        return self.client

    async def ensure_user(self, telegram_id: int, full_name: str, username: str | None) -> None:
        await self.c().table("users").upsert({
            "telegram_id": telegram_id,
            "full_name": full_name,
            "username": username,
            "updated_at": datetime.utcnow().isoformat(),
        }, on_conflict="telegram_id").execute()

    async def update_user_name(self, telegram_id: int, full_name: str) -> None:
        await self.c().table("users").update({"full_name": full_name}).eq("telegram_id", telegram_id).execute()

    async def get_user(self, telegram_id: int) -> Optional[dict[str, Any]]:
        r = await self.c().table("users").select("*").eq("telegram_id", telegram_id).limit(1).execute()
        return r.data[0] if r.data else None

    async def list_users(self) -> list[dict[str, Any]]:
        r = await self.c().table("users").select("*").execute()
        return r.data or []

    async def create_receipt(self, telegram_id: int, channel_message_id: int, file_id: str) -> dict[str, Any]:
        r = await self.c().table("receipts").insert({
            "telegram_id": telegram_id,
            "channel_message_id": channel_message_id,
            "file_id": file_id,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
        return r.data[0]

    async def set_receipt_review(self, receipt_id: int, status: str, reviewed_by: int, reason: str | None = None):
        await self.c().table("receipts").update({
            "status": status,
            "reviewed_by": reviewed_by,
            "reason": reason,
            "reviewed_at": datetime.utcnow().isoformat(),
        }).eq("id", receipt_id).execute()

    async def mark_paid(self, telegram_id: int, cycle_key: str, eth_payment_date: str):
        await self.c().table("payments").upsert({
            "telegram_id": telegram_id,
            "cycle_key": cycle_key,
            "status": "paid",
            "ethiopian_payment_date": eth_payment_date,
            "paid_at": datetime.utcnow().isoformat(),
        }, on_conflict="telegram_id,cycle_key").execute()

    async def payment_status(self, telegram_id: int, cycle_key: str) -> str:
        r = await self.c().table("payments").select("status").eq("telegram_id", telegram_id).eq("cycle_key", cycle_key).limit(1).execute()
        return r.data[0]["status"] if r.data else "unpaid"

    async def payment_history(self, telegram_id: int) -> list[dict[str, Any]]:
        r = await self.c().table("payments").select("*").eq("telegram_id", telegram_id).order("paid_at", desc=True).execute()
        return r.data or []

    async def debtors(self, cycle_key: str) -> list[dict[str, Any]]:
        users = await self.list_users()
        output = []
        for u in users:
            if await self.payment_status(u["telegram_id"], cycle_key) != "paid":
                output.append(u)
        return output

    async def get_settings(self) -> dict[str, Any]:
        r = await self.c().table("settings").select("*").limit(1).execute()
        if r.data:
            return r.data[0]
        default = {
            "billing_start_day": 25,
            "billing_end_day": 5,
            "bank_name": "",
            "bank_account": "",
            "msg_approval": "Payment approved.",
            "msg_rejection": "Payment rejected.",
            "msg_start": "Payment window started.",
            "msg_before_last": "One day left before deadline.",
            "msg_last": "Final day to pay.",
            "notify_25": True,
            "notify_4": True,
            "notify_5": True,
        }
        await self.c().table("settings").insert(default).execute()
        return (await self.get_settings())

    async def update_settings(self, values: dict[str, Any]):
        s = await self.get_settings()
        await self.c().table("settings").update(values).eq("id", s["id"]).execute()

    async def is_admin(self, telegram_id: int) -> bool:
        r = await self.c().table("admins").select("role").eq("telegram_id", telegram_id).limit(1).execute()
        return bool(r.data)

    async def role(self, telegram_id: int) -> Optional[str]:
        r = await self.c().table("admins").select("role").eq("telegram_id", telegram_id).limit(1).execute()
        return r.data[0]["role"] if r.data else None

    async def add_admin(self, telegram_id: int, role: str = "admin"):
        await self.c().table("admins").upsert({"telegram_id": telegram_id, "role": role}, on_conflict="telegram_id").execute()

    async def remove_admin(self, telegram_id: int):
        await self.c().table("admins").delete().eq("telegram_id", telegram_id).execute()



def ethiopian_today(now_dt) -> tuple[int, int, int]:
    e = EthiopianDateConverter.to_ethiopian(now_dt.year, now_dt.month, now_dt.day)
    return e.year, e.month, e.day


def cycle_key_ethiopian(now_dt, start_day: int = 25) -> str:
    y, m, d = ethiopian_today(now_dt)
    if d >= start_day:
        return f"{y}-{m:02d}"
    pm = 13 if m == 1 else m - 1
    py = y - 1 if m == 1 else y
    return f"{py}-{pm:02d}"


def days_until_end_ethiopian(now_dt, end_day: int = 5) -> int:
    y, m, d = ethiopian_today(now_dt)
    if d <= end_day:
        return end_day - d
    return (30 - d) + end_day


async def keep_alive(db: Database, hours: int = 48):
    while True:
        await db.c().table("settings").select("id").limit(1).execute()
        await asyncio.sleep(hours * 3600)
