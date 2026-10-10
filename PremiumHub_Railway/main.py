from __future__ import annotations



import asyncio

import json

import logging

import os

import random

import re

import sqlite3

import uuid

from datetime import datetime, timedelta, timezone
from pathlib import Path



import aiohttp

from aiogram import Bot, Dispatcher, F, Router

from aiogram.client.default import DefaultBotProperties

from aiogram.enums import ChatMemberStatus, ParseMode

from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command

from aiogram.fsm.context import FSMContext

from aiogram.fsm.state import State, StatesGroup

from aiogram.fsm.storage.memory import MemoryStorage

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from aiosqlite import connect

from dotenv import load_dotenv



try:

    from telethon import TelegramClient, events
    from telethon.sessions import StringSession

except ImportError:

    TelegramClient = None
    StringSession = None

    events = None



load_dotenv()



# ========================= ASOSIY SOZLAMALAR =========================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

FRAGMENT_API_KEY = os.getenv("FRAGMENT_API_KEY", "").strip()

ADMIN_IDS = {

    int(x.strip())

    for x in os.getenv("ADMIN_IDS", "").split(",")

    if x.strip().isdigit()

}

CARD_NUMBER = os.getenv("CARD_NUMBER", "KARTA_RAQAMINI_KIRITING").strip()

SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@Starsoson_bot").strip()

REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "").strip()
FORCE_SUB_ENABLED_DEFAULT = os.getenv("FORCE_SUB_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on"
}

LOG_CHAT_ID = int(os.getenv("LOG_CHAT_ID", "0") or 0)



STAR_PRICE_UZS = int(os.getenv("STAR_PRICE_UZS", "200"))

STAR_MIN = int(os.getenv("STAR_MIN", "50"))

STAR_MAX = int(os.getenv("STAR_MAX", "100000"))

PREMIUM = {

    3: int(os.getenv("PREMIUM_3_UZS", "160000")),

    6: int(os.getenv("PREMIUM_6_UZS", "225000")),

    12: int(os.getenv("PREMIUM_12_UZS", "400000")),

}



FRAGMENT_BASE_URL = os.getenv(

    "FRAGMENT_BASE_URL", "https://fragment-api.uz/api/v1"

).rstrip("/")

# Railway'da DATA_DIR=/data qilib, /data ga Volume ulang.
# Lokal kompyuterda DATA_DIR berilmasa fayllar joriy papkada qoladi.
DATA_DIR = Path(os.getenv("DATA_DIR", ".")).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "premiumhub.db")).strip()
Path(DB_PATH).expanduser().parent.mkdir(parents=True, exist_ok=True)



# ====================== AVTOMATIK TO'LOV ======================

AUTOPAY_ENABLED = os.getenv("AUTOPAY_ENABLED", "true").strip().lower() in {

    "1", "true", "yes", "on"

}

TG_API_ID = int(os.getenv("TG_API_ID", "0") or 0)

TG_API_HASH = os.getenv("TG_API_HASH", "").strip()

TG_SESSION = os.getenv("TG_SESSION", str(DATA_DIR / "userbot_session")).strip()
TG_SESSION_STRING = os.getenv("TG_SESSION_STRING", "").strip()

CARDXABAR_USERNAME = os.getenv("CARDXABAR_USERNAME", "CardXabarBot").strip().lstrip("@")

CARD_LAST4 = os.getenv("CARD_LAST4", "").strip()

ORDER_TTL_MIN = max(5, int(os.getenv("ORDER_TTL_MIN", "30")))

GRACE_MIN = max(0, int(os.getenv("GRACE_MIN", "10")))

UNIQUE_MAX = max(50, int(os.getenv("UNIQUE_MAX", "500")))



AUTO_PAYMENT_CONFIGURED = bool(

    AUTOPAY_ENABLED

    and TG_API_ID

    and TG_API_HASH

    and CARDXABAR_USERNAME

    and re.fullmatch(r"\d{4}", CARD_LAST4 or "")

)



if not BOT_TOKEN:

    raise RuntimeError("BOT_TOKEN .env faylida yozilmagan")

if not FRAGMENT_API_KEY:

    raise RuntimeError("FRAGMENT_API_KEY .env faylida yozilmagan")

if not ADMIN_IDS:

    raise RuntimeError("ADMIN_IDS .env faylida yozilmagan")

if AUTOPAY_ENABLED and CARD_LAST4 and not re.fullmatch(r"\d{4}", CARD_LAST4):

    raise RuntimeError("CARD_LAST4 faqat 4 ta raqam bo'lishi kerak. Masalan: 0089")



logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",

)

log = logging.getLogger("premiumhub")

router = Router()





class Flow(StatesGroup):
    stars = State()
    username = State()
    broadcast = State()
    admin_price = State()
    admin_channel = State()





def money(v: int) -> str:

    return f"{v:,}".replace(",", " ")





def b(text: str, data: str, style: str = "primary") -> InlineKeyboardButton:

    # Rangli Telegram tugmalari (aiogram 3.31+)

    return InlineKeyboardButton(text=text, callback_data=data, style=style)





def back(data: str = "menu:main") -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(

        inline_keyboard=[[b("↩️ Orqaga", data, "danger")]]

    )





def main_kb(admin: bool = False) -> InlineKeyboardMarkup:

    # ESKI CHIROYLI MENYU O'ZGARTIRILMAGAN

    rows = [

        [b("⭐ Stars olish", "menu:stars", "primary")],

        [

            b("💎 Premium", "menu:premium", "primary"),

            b("📦 Buyurtmalarim", "menu:orders", "primary"),

        ],

        [

            b("👤 Profil", "menu:profile", "primary"),

            b("🆘 Yordam", "menu:support", "primary"),

        ],

    ]

    if admin:

        rows.append([b("🛡 Admin panel", "admin:panel", "success")])

    return InlineKeyboardMarkup(inline_keyboard=rows)





def recipient_kb() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(

        inline_keyboard=[

            [b("👤 O'zimga", "recipient:self", "success")],

            [b("↩️ Orqaga", "menu:main", "danger")],

        ]

    )





def premium_kb(prices: dict[int, int] | None = None) -> InlineKeyboardMarkup:
    p = prices or PREMIUM
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [b(f"💎 3 oy — {money(p[3])} so'm", "premium:3")],
            [b(f"💎 6 oy — {money(p[6])} so'm", "premium:6")],
            [b(f"👑 12 oy — {money(p[12])} so'm", "premium:12")],
            [b("↩️ Orqaga", "menu:main", "danger")],
        ]
    )








def confirm_kb() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(

        inline_keyboard=[

            [b("✅ Davom etish", "order:confirm", "success")],

            [b("✏️ O'zgartirish", "order:change", "primary")],

            [b("❌ Bekor qilish", "order:abort", "danger")],

        ]

    )





def paid_kb(ref: str) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(

        inline_keyboard=[

            [b("✅ To'lov qildim", f"paid:{ref}", "success")],

            [b("❌ Bekor qilish", f"cancel:{ref}", "danger")],

        ]

    )





def review_kb(ref: str) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(

        inline_keyboard=[

            [

                b("✅ Tasdiqlash", f"admin:approve:{ref}", "success"),

                b("❌ Rad etish", f"admin:reject:{ref}", "danger"),

            ]

        ]

    )





def admin_panel_kb(enabled: bool = True) -> InlineKeyboardMarkup:
    toggle = (
        ("⛔ Botni o‘chirish", "admin:toggle:off", "danger")
        if enabled
        else ("✅ Botni yoqish", "admin:toggle:on", "success")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [b("📊 Statistika", "admin:stats"), b("📦 Buyurtmalar", "admin:orders")],
            [b("👥 Foydalanuvchilar", "admin:users"), b("📣 Ommaviy xabar", "admin:broadcast")],
            [b("💰 Narxlarni o‘zgartirish", "admin:prices", "primary")],
            [b("📢 Kanal sozlamalari", "admin:channel", "primary"), b("👑 VIP tizimi", "admin:vip", "primary")],
            [b("💳 Avto-to'lov holati", "admin:autopay", "primary")],
            [b(*toggle)],
            [b("🏠 Bosh menyu", "menu:main", "primary")],
        ]
    )


def admin_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[b("↩️ Admin", "admin:panel", "danger")]]
    )


def broadcast_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [b("✍️ Ommaviy xabar yozish", "admin:broadcast:custom", "primary")],
            [
                b("🟢 Bot ochildi", "admin:broadcast:open", "success"),
                b("🔴 Bot yopildi", "admin:broadcast:closed", "danger"),
            ],
            [b("↩️ Admin", "admin:panel", "danger")],
        ]
    )


def subscription_kb(channel: str) -> InlineKeyboardMarkup:
    username = channel.lstrip("@")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga obuna bo‘lish", url=f"https://t.me/{username}")],
            [b("✅ Tekshirish", "sub:check", "success")],
        ]
    )








# ========================= DATABASE =========================

def db_connect():
    # timeout SQLite band bo'lib qolgan paytda yozuvni kutishga yordam beradi.
    return connect(DB_PATH, timeout=30)


async def db_init() -> None:

    async with db_connect() as db:

        # Railway + SQLite uchun xavfsizroq parallel ishlash sozlamalari.
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA busy_timeout=30000")

        await db.executescript(

            """

            CREATE TABLE IF NOT EXISTS users(

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                telegram_id INTEGER UNIQUE,

                username TEXT,

                first_name TEXT,

                created_at TEXT

            );



            CREATE TABLE IF NOT EXISTS orders(

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                order_ref TEXT UNIQUE,

                telegram_id INTEGER,

                kind TEXT,

                target_username TEXT,

                stars_amount INTEGER DEFAULT 0,

                months INTEGER DEFAULT 0,

                amount_uzs INTEGER,

                status TEXT DEFAULT 'awaiting_payment',

                fragment_response TEXT,

                error TEXT,

                created_at TEXT,

                completed_at TEXT

            );



            CREATE TABLE IF NOT EXISTS settings(

                key TEXT PRIMARY KEY,

                value TEXT NOT NULL

            );



            INSERT OR IGNORE INTO settings(key,value) VALUES('bot_enabled','1');

            """

        )



        defaults = {
            "price_stars": STAR_PRICE_UZS,
            "price_p3": PREMIUM[3],
            "price_p6": PREMIUM[6],
            "price_p12": PREMIUM[12],
            "required_channel": REQUIRED_CHANNEL,
            "force_sub_enabled": "1" if FORCE_SUB_ENABLED_DEFAULT else "0",
        }
        for key, value in defaults.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
                (key, str(value)),
            )

        # Eski bazani o'chirmasdan avto-to'lov ustunlarini qo'shamiz.

        cur = await db.execute("PRAGMA table_info(orders)")

        cols = {row[1] for row in await cur.fetchall()}

        if "pay_amount" not in cols:

            await db.execute("ALTER TABLE orders ADD COLUMN pay_amount INTEGER")

        if "expires_at" not in cols:

            await db.execute("ALTER TABLE orders ADD COLUMN expires_at TEXT")



        await db.execute(

            """

            CREATE TABLE IF NOT EXISTS seen_payments(

                msg_key TEXT PRIMARY KEY,

                amount INTEGER NOT NULL,

                created_at TEXT NOT NULL

            )

            """

        )

        await db.execute(

            "CREATE INDEX IF NOT EXISTS idx_orders_pay_amount ON orders(pay_amount)"

        )

        await db.commit()





async def setting(key: str, default: str = "") -> str:

    async with db_connect() as db:

        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))

        row = await cur.fetchone()

        return row[0] if row else default





async def set_setting(key: str, value: str) -> None:
    async with db_connect() as db:
        await db.execute(
            """INSERT INTO settings(key,value) VALUES(?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (key, str(value)),
        )
        await db.commit()


async def current_star_price() -> int:
    try:
        return max(1, int(await setting("price_stars", str(STAR_PRICE_UZS))))
    except (TypeError, ValueError):
        return STAR_PRICE_UZS


async def current_premium_prices() -> dict[int, int]:
    result: dict[int, int] = {}
    for months, key in ((3, "price_p3"), (6, "price_p6"), (12, "price_p12")):
        try:
            result[months] = max(1, int(await setting(key, str(PREMIUM[months]))))
        except (TypeError, ValueError):
            result[months] = PREMIUM[months]
    return result


def vip_info(total_spent: int) -> tuple[str, int]:
    if total_spent >= 1_000_000:
        return "👑 VIP", 3
    if total_spent >= 500_000:
        return "🥇 Gold", 2
    if total_spent >= 200_000:
        return "🥈 Silver", 1
    return "⭐ Oddiy", 0


async def required_channel_settings() -> tuple[bool, str]:
    enabled = await setting(
        "force_sub_enabled",
        "1" if FORCE_SUB_ENABLED_DEFAULT else "0",
    ) == "1"
    channel = (await setting("required_channel", REQUIRED_CHANNEL)).strip()
    return enabled, channel


async def is_channel_member(bot: Bot, user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    enabled, channel = await required_channel_settings()
    if not enabled or not channel:
        return True
    try:
        member = await bot.get_chat_member(channel, user_id)
        return member.status not in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}
    except Exception:
        log.exception("Majburiy obuna tekshiruvida xato: %s", channel)
        return True


async def require_subscription_message(m: Message, bot: Bot) -> bool:
    if await is_channel_member(bot, m.from_user.id):
        return True
    _, channel = await required_channel_settings()
    await m.answer(
        f"📢 <b>Botdan foydalanish uchun kanalga obuna bo‘ling.</b>\n\n"
        f"Kanal: <b>{channel}</b>\n"
        f"Obuna bo‘lgach <b>✅ Tekshirish</b> tugmasini bosing.",
        reply_markup=subscription_kb(channel),
    )
    return False


async def require_subscription_callback(c: CallbackQuery, bot: Bot) -> bool:
    if await is_channel_member(bot, c.from_user.id):
        return True
    _, channel = await required_channel_settings()
    await c.message.edit_text(
        f"📢 <b>Botdan foydalanish uchun kanalga obuna bo‘ling.</b>\n\n"
        f"Kanal: <b>{channel}</b>\n"
        f"Obuna bo‘lgach <b>✅ Tekshirish</b> tugmasini bosing.",
        reply_markup=subscription_kb(channel),
    )
    await c.answer("Avval kanalga obuna bo‘ling.", show_alert=True)
    return False


async def all_user_ids() -> list[int]:
    async with db_connect() as db:
        rows = await (await db.execute("SELECT telegram_id FROM users")).fetchall()
    return [int(row[0]) for row in rows if row[0]]


async def broadcast_copy(bot: Bot, from_chat_id: int, message_id: int) -> tuple[int, int]:
    ok = 0
    fail = 0
    for user_id in await all_user_ids():
        try:
            await bot.copy_message(user_id, from_chat_id, message_id)
            ok += 1
            await asyncio.sleep(0.055)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 0.5)
            try:
                await bot.copy_message(user_id, from_chat_id, message_id)
                ok += 1
            except Exception:
                fail += 1
        except Exception:
            fail += 1
    return ok, fail


async def broadcast_text(bot: Bot, text: str) -> tuple[int, int]:
    ok = 0
    fail = 0
    for user_id in await all_user_ids():
        try:
            await bot.send_message(user_id, text)
            ok += 1
            await asyncio.sleep(0.055)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 0.5)
            try:
                await bot.send_message(user_id, text)
                ok += 1
            except Exception:
                fail += 1
        except Exception:
            fail += 1
    return ok, fail








async def upsert_user(u) -> int:

    async with db_connect() as db:

        await db.execute(

            """INSERT INTO users(telegram_id,username,first_name,created_at)

               VALUES(?,?,?,?)

               ON CONFLICT(telegram_id) DO UPDATE SET

               username=excluded.username, first_name=excluded.first_name""",

            (

                u.id,

                u.username or "",

                u.first_name or "Foydalanuvchi",

                datetime.utcnow().isoformat(),

            ),

        )

        await db.commit()

        cur = await db.execute("SELECT id FROM users WHERE telegram_id=?", (u.id,))

        return (await cur.fetchone())[0]





async def user_stats(tid: int):

    async with db_connect() as db:

        cur = await db.execute(

            """SELECT COUNT(*),

               COALESCE(SUM(CASE WHEN status='completed' THEN amount_uzs ELSE 0 END),0)

               FROM orders WHERE telegram_id=?""",

            (tid,),

        )

        return await cur.fetchone()





async def create_order(

    tid: int, kind: str, user: str, value: int, amount: int

) -> tuple[str, int, datetime]:

    """Buyurtma yaratadi va avto-to'lov uchun noyob summa ajratadi."""

    ref = "PH-" + uuid.uuid4().hex[:10].upper()

    now = datetime.utcnow()

    expires = now + timedelta(minutes=ORDER_TTL_MIN)



    async with db_connect() as db:

        await db.execute("BEGIN IMMEDIATE")

        try:

            # Oxirgi 24 soat ichidagi summalarni qayta ishlatmaymiz.

            cur = await db.execute(

                """SELECT pay_amount FROM orders

                   WHERE pay_amount IS NOT NULL

                     AND created_at >= ?""",

                ((now - timedelta(hours=24)).isoformat(),),

            )

            busy = {row[0] for row in await cur.fetchall() if row[0] is not None}

            free = [

                amount + i

                for i in range(1, UNIQUE_MAX + 1)

                if amount + i not in busy

            ]

            if not free:

                raise RuntimeError("Noyob to'lov summasi qolmadi. Birozdan keyin urinib ko'ring.")



            pay_amount = random.choice(free)

            await db.execute(

                """INSERT INTO orders(

                    order_ref,telegram_id,kind,target_username,stars_amount,months,

                    amount_uzs,pay_amount,expires_at,status,created_at

                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",

                (

                    ref,

                    tid,

                    kind,

                    user,

                    value if kind == "stars" else 0,

                    value if kind == "premium" else 0,

                    amount,

                    pay_amount,

                    expires.isoformat(),

                    "awaiting_payment",

                    now.isoformat(),

                ),

            )

            await db.commit()

        except Exception:

            await db.rollback()

            raise



    return ref, pay_amount, expires





async def get_order(ref: str):

    async with db_connect() as db:

        db.row_factory = sqlite3.Row

        cur = await db.execute("SELECT * FROM orders WHERE order_ref=?", (ref,))

        return await cur.fetchone()





async def set_status(ref: str, expected: tuple[str, ...], new: str, **extra) -> bool:

    fields = ["status=?"]

    params = [new]

    for k, v in extra.items():

        if k in {"fragment_response", "error", "completed_at"}:

            fields.append(f"{k}=?")

            params.append(v)



    marks = ",".join("?" for _ in expected)

    params.extend([ref, *expected])

    async with db_connect() as db:

        cur = await db.execute(

            f"UPDATE orders SET {','.join(fields)} WHERE order_ref=? AND status IN ({marks})",

            params,

        )

        await db.commit()

        return cur.rowcount == 1





# ========================= XABAR / API =========================

async def log_event(bot: Bot, text: str) -> None:

    if LOG_CHAT_ID:

        try:

            await bot.send_message(LOG_CHAT_ID, text)

        except Exception:

            log.exception("Log chatga yuborilmadi")





async def admins(bot: Bot, text: str, markup=None) -> None:

    for admin_id in ADMIN_IDS:

        try:

            await bot.send_message(admin_id, text, reply_markup=markup)

        except Exception:

            log.exception("Admin xabari yuborilmadi: %s", admin_id)





async def fragment(kind: str, user: str, value: int) -> dict:

    endpoint = "/stars/buy" if kind == "stars" else "/premium/buy"

    payload = (

        {"username": user.lstrip("@"), "amount": value}

        if kind == "stars"

        else {"username": user.lstrip("@"), "duration": value}

    )

    try:

        async with aiohttp.ClientSession(

            timeout=aiohttp.ClientTimeout(total=120)

        ) as session:

            async with session.post(

                FRAGMENT_BASE_URL + endpoint,

                json=payload,

                headers={

                    "X-API-Key": FRAGMENT_API_KEY,

                    "Content-Type": "application/json",

                    "Accept": "application/json",

                },

            ) as response:

                text = await response.text()

                try:

                    data = json.loads(text)

                except json.JSONDecodeError:

                    return {

                        "ok": False,

                        "message": "API JSON qaytarmadi",

                        "http": response.status,

                        "raw": text[:1000],

                    }

                return {

                    "ok": 200 <= response.status < 300 and data.get("ok") is True,

                    "message": data.get("message", ""),

                    "result": data.get("result"),

                    "http": response.status,

                    "raw": data,

                }

    except Exception as exc:

        log.exception("Fragment API xatosi")

        return {"ok": False, "message": str(exc)}





async def home_text(u) -> str:
    uid = await upsert_user(u)
    cnt, total = await user_stats(u.id)
    vip_name, vip_discount = vip_info(total)
    vip_line = f"👑 Daraja: <b>{vip_name}</b>"
    if vip_discount:
        vip_line += f" — <b>{vip_discount}% chegirma</b>"

    return (
        f"👋 <b>Assalomu alaykum, {u.first_name or 'Foydalanuvchi'}!</b>\n\n"
        f"StarsOson botga xush kelibsiz!\n\n"
        f"🆔 StarsOson ID: <b>{uid}</b>\n"
        f"💰 Xaridlar: <b>{money(total)} so'm</b>\n"
        f"📦 Buyurtmalar: <b>{cnt} ta</b>\n"
        f"{vip_line}\n\n"
        f"🛡 Kerakli bo'limni tanlang:"
    )








async def ensure_enabled(c: CallbackQuery) -> bool:

    if c.from_user.id in ADMIN_IDS:

        return True



@router.callback_query(F.data == "sub:check")
async def subscription_check(c: CallbackQuery, bot: Bot):
    if await is_channel_member(bot, c.from_user.id):
        await c.message.edit_text(
            await home_text(c.from_user),
            reply_markup=main_kb(c.from_user.id in ADMIN_IDS),
        )
        return await c.answer("✅ Obuna tasdiqlandi.")
    await c.answer("❌ Hali kanalga obuna bo‘lmagansiz.", show_alert=True)
    if await setting("bot_enabled", "1") != "1":

        await c.answer("⛔ Bot vaqtincha texnik xizmatda.", show_alert=True)

        return False

    return True





# ========================= YETKAZISH =========================

async def deliver(bot: Bot, ref: str) -> None:

    # Atomic lock: ikki admin bir vaqtda bossayam faqat bir marta yuboriladi.

    if not await set_status(ref, ("payment_review",), "processing"):

        return



    o = await get_order(ref)

    if not o:

        return



    value = o["stars_amount"] if o["kind"] == "stars" else o["months"]

    product = f"{value} Stars" if o["kind"] == "stars" else f"Premium {value} oy"

    result = await fragment(o["kind"], o["target_username"], value)

    raw = json.dumps(result, ensure_ascii=False, default=str)



    if result.get("ok"):

        await set_status(

            ref,

            ("processing",),

            "completed",

            fragment_response=raw,

            completed_at=datetime.utcnow().isoformat(),

            error=None,

        )

        paid_amount = o["pay_amount"] or o["amount_uzs"]

        text = (

            f"✅ <b>Buyurtma muvaffaqiyatli bajarildi!</b>\n\n"

            f"🧾 <code>{ref}</code>\n"

            f"📦 {product}\n"

            f"🎯 @{o['target_username']}\n"

            f"💰 {money(paid_amount)} so'm"

        )

        await bot.send_message(

            o["telegram_id"],

            text,

            reply_markup=main_kb(o["telegram_id"] in ADMIN_IDS),

        )

        await admins(bot, f"✅ <b>Buyurtma bajarildi</b>\n{text}")

        await log_event(bot, text)

    else:

        err = result.get("message") or "Fragment API xatosi"

        await set_status(

            ref,

            ("processing",),

            "delivery_failed",

            fragment_response=raw,

            error=err,

        )

        await bot.send_message(

            o["telegram_id"],

            f"⚠️ To'lov tasdiqlandi, ammo yetkazishda xato.\n"

            f"🧾 <code>{ref}</code>\nAdmin tekshiradi.",

        )

        await admins(bot, f"🚨 DELIVERY FAILED <code>{ref}</code>\n{err}")

        await log_event(bot, f"🚨 Yetkazish xatosi <code>{ref}</code>\n{err}")





# ====================== CARDXABAR PARSER ======================

# Haqiqiy CardXabar formatiga mos:

# 🟢 Perevod na kartu

# ➕ 30 000.00 UZS

# 💳 ***0089

INCOME_RE = re.compile(r"➕\ufe0f?\s*([\d\s]+)[.,](\d{2})\s*UZS", re.IGNORECASE)

CARD_RE = re.compile(r"\*{3}(\d{4})")

SKIP_WORDS = ("platezh", "otmena", "vozvrat", "возврат", "отмена")





def parse_income(text: str):

    """CardXabar kirimidan (summa, karta oxirgi 4 raqami) qaytaradi."""

    if "➕" not in text:

        return None

    low = text.lower()

    if any(word in low for word in SKIP_WORDS):

        return None



    amount_match = INCOME_RE.search(text)

    card_match = CARD_RE.search(text)

    if not amount_match or not card_match:

        return None

    if amount_match.group(2) != "00":

        return None



    amount = int(re.sub(r"\D", "", amount_match.group(1)))

    return amount, card_match.group(1)





def utc_naive(dt: datetime | None) -> datetime:

    if dt is None:

        return datetime.utcnow()

    if dt.tzinfo is not None:

        return dt.astimezone(timezone.utc).replace(tzinfo=None)

    return dt





async def mark_payment_seen(msg_key: str, amount: int, payment_time: datetime) -> bool:

    async with db_connect() as db:

        cur = await db.execute(

            "INSERT OR IGNORE INTO seen_payments(msg_key,amount,created_at) VALUES(?,?,?)",

            (msg_key, amount, payment_time.isoformat()),

        )

        await db.commit()

        return cur.rowcount == 1





async def handle_incoming_payment(

    bot: Bot,

    amount: int,

    msg_key: str,

    payment_time: datetime | None = None,

) -> None:

    """CardXabar kirimini faqat vaqt + noyob summa bo'yicha bitta orderga bog'laydi."""

    payment_time = utc_naive(payment_time)



    if not await mark_payment_seen(msg_key, amount, payment_time):

        return



    # Faqat ushbu to'lov vaqtida mavjud bo'lgan va muddati tugamagan order mos keladi.

    async with db_connect() as db:

        db.row_factory = sqlite3.Row

        cur = await db.execute(

            """SELECT * FROM orders

               WHERE pay_amount=?

                 AND status IN ('awaiting_payment','payment_review')

                 AND created_at <= ?

                 AND expires_at >= ?

               ORDER BY id DESC

               LIMIT 1""",

            (

                amount,

                (payment_time + timedelta(minutes=1)).isoformat(),

                (payment_time - timedelta(minutes=GRACE_MIN)).isoformat(),

            ),

        )

        order = await cur.fetchone()



    if order:

        ref = order["order_ref"]

        if order["status"] == "awaiting_payment":

            await set_status(ref, ("awaiting_payment",), "payment_review")



        try:

            await bot.send_message(

                order["telegram_id"],

                f"💰 <b>To'lov avtomatik qabul qilindi!</b>\n\n"

                f"🧾 <code>{ref}</code>\n"

                f"💵 {money(amount)} so'm\n"

                f"⚙️ Buyurtma yuborilmoqda...",

            )

        except Exception:

            log.exception("Mijozga avto-to'lov xabari yuborilmadi")



        await admins(

            bot,

            f"💳 <b>AVTO TO'LOV QABUL QILINDI</b>\n\n"

            f"🧾 <code>{ref}</code>\n"

            f"👤 Xaridor ID: <code>{order['telegram_id']}</code>\n"

            f"💰 <b>{money(amount)} so'm</b>\n"

            f"✅ CardXabar orqali avtomatik aniqlandi.",

        )

        await log_event(bot, f"💳 Avto-to'lov: <code>{ref}</code> — {money(amount)} so'm")

        await deliver(bot, ref)

        return



    # Muddati o'tgan buyurtmaga to'lov kelgan bo'lsa avtomatik yetkazmaymiz.

    async with db_connect() as db:

        db.row_factory = sqlite3.Row

        cur = await db.execute(

            """SELECT * FROM orders

               WHERE pay_amount=?

                 AND status='expired'

                 AND created_at <= ?

                 AND created_at >= ?

               ORDER BY id DESC LIMIT 1""",

            (

                amount,

                (payment_time + timedelta(minutes=1)).isoformat(),

                (payment_time - timedelta(hours=24)).isoformat(),

            ),

        )

        late = await cur.fetchone()



    if late:

        ref = late["order_ref"]

        if await set_status(ref, ("expired",), "payment_review"):

            value = late["stars_amount"] if late["kind"] == "stars" else late["months"]

            product = f"{value} Stars" if late["kind"] == "stars" else f"Premium {value} oy"

            await admins(

                bot,

                f"⏰ <b>KECH KELGAN TO'LOV</b>\n\n"

                f"🧾 <code>{ref}</code>\n"

                f"📦 {product} → @{late['target_username']}\n"

                f"💰 {money(amount)} so'm\n\n"

                f"Buyurtma muddati tugagan. Qo'lda tasdiqlaysizmi?",

                review_kb(ref),

            )

        return



    # CardXabar'dagi boshqa kirimlar ham ko'rinadi; faqat adminlarga ma'lumot beramiz.

    await admins(

        bot,

        f"❓ Kartaga <b>{money(amount)} so'm</b> tushdi, lekin mos aktiv PremiumHub buyurtma topilmadi."

    )





async def start_userbot(bot: Bot):

    """Faqat @CardXabarBot chatini tinglaydi. Boshqa guruh/chatga umuman handler yo'q."""

    if not AUTOPAY_ENABLED:

        log.info("Avto-to'lov .env orqali o'chirilgan")

        return None

    if TelegramClient is None:

        log.warning("telethon o'rnatilmagan: avto-to'lov o'chiq")

        return None

    if not AUTO_PAYMENT_CONFIGURED:

        log.warning(

            "TG_API_ID/TG_API_HASH/CARDXABAR_USERNAME/CARD_LAST4 to'liq emas: avto-to'lov o'chiq"

        )

        return None



    # Railway uchun TG_SESSION_STRING tavsiya qilinadi.
    # Agar u bo'sh bo'lsa, eski .session fayl usuli ishlashda davom etadi.
    if TG_SESSION_STRING and StringSession is not None:
        client = TelegramClient(StringSession(TG_SESSION_STRING), TG_API_ID, TG_API_HASH)
        session_mode = "string"
    else:
        client = TelegramClient(TG_SESSION, TG_API_ID, TG_API_HASH)
        session_mode = "file"

    await client.connect()

    if not await client.is_user_authorized():

        if session_mode == "string":
            log.warning("TG_SESSION_STRING yaroqsiz yoki login bekor bo'lgan: avto-to'lov o'chiq")
        else:
            log.warning(
                "Userbot login qilinmagan. Lokal session yarating yoki Railway uchun TG_SESSION_STRING kiriting."
            )

        await client.disconnect()

        return None



    # Aynan bitta chat ID ni resolve qilib olamiz; guruhlar / boshqa botlar tinglanmaydi.

    try:

        card_entity = await client.get_entity(CARDXABAR_USERNAME)

        card_chat_id = int(card_entity.id)

    except Exception:

        log.exception("@%s chatini topib bo'lmadi", CARDXABAR_USERNAME)

        await client.disconnect()

        return None



    @client.on(events.NewMessage(chats=card_entity, incoming=True))

    async def on_cardxabar(event):

        try:

            # Qo'shimcha himoya: faqat resolve qilingan CardXabar chat ID.

            event_chat_id = int(getattr(event, "chat_id", 0) or 0)

            # Bot/private peer ID Telethon'da ba'zan signed/unsigned ko'rinishi mumkin.

            if abs(event_chat_id) != abs(card_chat_id):

                return



            parsed = parse_income(event.raw_text or "")

            if not parsed:

                return

            amount, last4 = parsed

            if last4 != CARD_LAST4:

                return



            await handle_incoming_payment(

                bot,

                amount,

                f"{event_chat_id}:{event.id}",

                getattr(event.message, "date", None),

            )

        except Exception:

            log.exception("CardXabar xabarini qayta ishlashda xato")

            await admins(

                bot,

                "🚨 CardXabar xabarini qayta ishlashda xato. Buyurtmalarni qo'lda tekshiring.",

            )



    # Bot o'chiq turgan paytda kelgan juda yangi xabarlarni xavfsiz qayta tekshiramiz.

    # Vaqt filtri sabab eski kirim yangi orderni tasdiqlay olmaydi.

    try:

        newest_allowed = datetime.utcnow() - timedelta(

            minutes=ORDER_TTL_MIN + GRACE_MIN + 10

        )

        async for msg in client.iter_messages(card_entity, limit=50):

            msg_time = utc_naive(getattr(msg, "date", None))

            if msg_time < newest_allowed:

                break

            parsed = parse_income(msg.raw_text or "")

            if not parsed:

                continue

            amount, last4 = parsed

            if last4 != CARD_LAST4:

                continue

            await handle_incoming_payment(

                bot,

                amount,

                f"{card_chat_id}:{msg.id}",

                msg_time,

            )

    except Exception:

        log.exception("CardXabar yangi xabarlarini startupda tekshirish bajarilmadi")



    log.info(

        "Userbot ishga tushdi: avto-to'lov YOQILGAN (@%s, karta ***%s). Faqat shu chat tinglanadi.",

        CARDXABAR_USERNAME,

        CARD_LAST4,

    )

    return client





async def order_sweeper(bot: Bot) -> None:

    """Muddati o'tgan to'lanmagan buyurtmalarni expired qiladi."""

    while True:

        try:

            cutoff = (datetime.utcnow() - timedelta(minutes=GRACE_MIN)).isoformat()

            async with db_connect() as db:

                db.row_factory = sqlite3.Row

                cur = await db.execute(

                    """SELECT order_ref,telegram_id FROM orders

                       WHERE status='awaiting_payment'

                         AND pay_amount IS NOT NULL

                         AND expires_at < ?""",

                    (cutoff,),

                )

                rows = await cur.fetchall()



            for row in rows:

                if await set_status(row["order_ref"], ("awaiting_payment",), "expired"):

                    try:

                        await bot.send_message(

                            row["telegram_id"],

                            f"⌛ Buyurtma muddati tugadi: <code>{row['order_ref']}</code>\n"

                            f"Agar to'lov qilgan bo'lsangiz {SUPPORT_USERNAME} bilan bog'laning, "

                            f"aks holda yangi buyurtma bering.",

                            reply_markup=main_kb(row["telegram_id"] in ADMIN_IDS),

                        )

                    except Exception:

                        pass

        except Exception:

            log.exception("Order sweeper xatosi")



        await asyncio.sleep(60)





# ========================= FOYDALANUVCHI FLOW =========================

@router.message(Command("start"))

async def start(m: Message, state: FSMContext, bot: Bot):

    await state.clear()

    await upsert_user(m.from_user)

    if await setting("bot_enabled", "1") != "1" and m.from_user.id not in ADMIN_IDS:

        return await m.answer(

            "⛔ Bot vaqtincha texnik xizmatda. Keyinroq urinib ko‘ring."

        )

    
    if not await require_subscription_message(m, bot):
        return

    await m.answer(

        await home_text(m.from_user),

        reply_markup=main_kb(m.from_user.id in ADMIN_IDS),

    )





@router.callback_query(F.data == "menu:main")

async def home(c: CallbackQuery, state: FSMContext, bot: Bot):

    await state.clear()

    if not await require_subscription_callback(c, bot):
        return

    await c.message.edit_text(

        await home_text(c.from_user),

        reply_markup=main_kb(c.from_user.id in ADMIN_IDS),

    )

    await c.answer()





@router.callback_query(F.data == "menu:stars")

async def stars(c: CallbackQuery, state: FSMContext, bot: Bot):

    if not await ensure_enabled(c):

        return

    if not await require_subscription_callback(c, bot):
        return

    star_price = await current_star_price()

    await state.set_state(Flow.stars)

    await c.message.edit_text(

        f"🔥 <b>Telegram Stars do'koni</b>\n\n"

        f"🟢 Minimal: <b>{STAR_MIN} Stars</b>\n"

        f"🟢 Maksimal: <b>{STAR_MAX} Stars</b>\n"

        f"💰 1 Stars = <b>{money(star_price)} so'm</b>\n\n"

        f"✍️ Kerakli miqdorni yuboring:",

        reply_markup=back(),

    )

    await c.answer()





@router.message(Flow.stars)

async def stars_amount(m: Message, state: FSMContext):

    try:

        value = int((m.text or "").strip())

    except ValueError:

        value = 0



    if not STAR_MIN <= value <= STAR_MAX:

        return await m.answer(

            f"❌ {STAR_MIN} dan {STAR_MAX} gacha butun son kiriting."

        )



    await state.update_data(kind="stars", value=value)

    await state.set_state(Flow.username)

    await m.answer(

        f"@ <b>Foydalanuvchi nomi</b>\n\n"

        f"⭐ {value} Stars qaysi profilga yuborilsin?\n"

        f"💡 Masalan: <code>@username</code>\n\n"

        f"✏️ Username yuboring:",

        reply_markup=recipient_kb(),

    )





@router.callback_query(F.data == "menu:premium")

async def premium_menu(c: CallbackQuery, bot: Bot):

    if not await ensure_enabled(c):

        return

    if not await require_subscription_callback(c, bot):
        return

    prices = await current_premium_prices()

    await c.message.edit_text(

        "💎 <b>Telegram Premium</b>\n\n"

        "🎁 Premium hadya sifatida yuboriladi.\n"

        "🔐 Akkauntga kirish talab qilinmaydi.\n\n"

        "Paketni tanlang:",

        reply_markup=premium_kb(prices),

    )

    await c.answer()





@router.callback_query(F.data.startswith("premium:"))

async def premium_pick(c: CallbackQuery, state: FSMContext, bot: Bot):

    if not await ensure_enabled(c):

        return

    if not await require_subscription_callback(c, bot):
        return

    value = int(c.data.split(":")[1])

    await state.update_data(kind="premium", value=value)

    await state.set_state(Flow.username)

    await c.message.edit_text(

        f"💎 <b>Premium {value} oy</b>\n\n"

        f"Kimga yuboriladi? <b>@username</b> kiriting yoki o'zingizga oling:",

        reply_markup=recipient_kb(),

    )

    await c.answer()





async def show_confirm(
    target: str,
    ui,
    state: FSMContext,
    buyer_id: int,
    edit: bool = False,
):
    data = await state.get_data()
    kind = data["kind"]
    value = int(data["value"])

    if kind == "stars":
        base_amount = value * await current_star_price()
    else:
        base_amount = (await current_premium_prices())[value]

    _, total_spent = await user_stats(buyer_id)
    vip_name, vip_discount = vip_info(total_spent)
    amount = max(1, round(base_amount * (100 - vip_discount) / 100))
    product = f"{value} Stars" if kind == "stars" else f"Premium {value} oy"

    await state.update_data(
        target=target,
        amount=amount,
        base_amount=base_amount,
        vip_discount=vip_discount,
    )

    discount_text = ""
    if vip_discount:
        discount_text = (
            f"👑 {vip_name}: <b>{vip_discount}% chegirma</b>\n"
            f"🏷 Oddiy narx: <s>{money(base_amount)} so'm</s>\n"
        )

    text = (
        f"🧾 <b>Buyurtmani tekshiring</b>\n\n"
        f"📦 {product}\n"
        f"👤 Qabul qiluvchi: <b>@{target}</b>\n"
        f"{discount_text}"
        f"💰 Narxi: <b>{money(amount)} so'm</b>\n\n"
        f"Ma'lumotlar to'g'rimi?"
    )

    if edit:
        await ui.edit_text(text, reply_markup=confirm_kb())
    else:
        await ui.answer(text, reply_markup=confirm_kb())








@router.callback_query(F.data == "recipient:self")

async def self_rec(c: CallbackQuery, state: FSMContext):

    if not c.from_user.username:

        return await c.answer(

            "Profilingizda username yo'q. Username'ni qo'lda kiriting.",

            show_alert=True,

        )

    await show_confirm(c.from_user.username, c.message, state, c.from_user.id, True)

    await c.answer()





@router.message(Flow.username)

async def username(m: Message, state: FSMContext):

    username_value = (m.text or "").strip().lstrip("@")

    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username_value):

        return await m.answer(

            "❌ Username noto'g'ri. Masalan: <code>@ibrohimjon</code>"

        )

    await show_confirm(username_value, m, state, m.from_user.id)





@router.callback_query(F.data == "order:change")

async def change(c: CallbackQuery, state: FSMContext):

    await state.set_state(Flow.username)

    await c.message.edit_text(

        "✏️ Yangi <b>@username</b> kiriting:",

        reply_markup=recipient_kb(),

    )

    await c.answer()





@router.callback_query(F.data == "order:abort")

async def abort(c: CallbackQuery, state: FSMContext):

    await state.clear()

    await c.message.edit_text(

        "❌ Buyurtma bekor qilindi.",

        reply_markup=main_kb(c.from_user.id in ADMIN_IDS),

    )

    await c.answer()





@router.callback_query(F.data == "order:confirm")

async def confirm(c: CallbackQuery, state: FSMContext, bot: Bot):

    data = await state.get_data()

    if not data.get("target"):

        return await c.answer("Ma’lumot yetarli emas.", show_alert=True)



    try:

        ref, pay_amount, expires = await create_order(

            c.from_user.id,

            data["kind"],

            data["target"],

            int(data["value"]),

            int(data["amount"]),

        )

    except Exception as exc:

        log.exception("Buyurtma yaratishda xato")

        return await c.answer(str(exc)[:180], show_alert=True)



    product = (

        f"{data['value']} Stars"

        if data["kind"] == "stars"

        else f"Premium {data['value']} oy"

    )

    await state.clear()

    until = (expires + timedelta(hours=5)).strftime("%H:%M")



    text = (

        f"💳 <b>To'lov so'rovi yaratildi!</b>\n\n"

        f"🧾 Buyurtma: <code>{ref}</code>\n"

        f"📦 {product}\n"

        f"👤 @{data['target']}\n"

        f"💰 To'lov: <code>{pay_amount}</code> so'm\n\n"

        f"💳 To'lov uchun karta:\n<code>{CARD_NUMBER}</code>\n\n"

        f"⚠️ <b>Aynan</b> <code>{pay_amount}</code> so'm yuboring.\n"

        f"1 so'm farq qilsa avto-to'lov topa olmaydi.\n\n"

        f"⏱ Muddat: <b>{ORDER_TTL_MIN} daqiqa</b> ({until} gacha)\n"

        f"🤖 Pul tushgach avtomatik tekshiriladi.\n\n"

        f"Agar avto-aniqlash ishlamasa, <b>✅ To'lov qildim</b> tugmasi zaxira sifatida qoladi."

    )

    await c.message.edit_text(text, reply_markup=paid_kb(ref))
    new_order_text = (
        f"🆕 <b>Yangi buyurtma</b>\n"
        f"🧾 <code>{ref}</code>\n"
        f"👤 {c.from_user.full_name} ({c.from_user.id})\n"
        f"📦 {product}\n"
        f"🎯 @{data['target']}\n"
        f"💰 Narx: {money(int(data['amount']))} so'm\n"
        f"💳 To'lov summasi: {money(pay_amount)} so'm"
    )
    await log_event(bot, new_order_text)
    await admins(bot, new_order_text)

    await c.answer()





@router.callback_query(F.data.startswith("paid:"))

async def paid(c: CallbackQuery, bot: Bot):

    ref = c.data.split(":", 1)[1]

    order = await get_order(ref)

    if not order or order["telegram_id"] != c.from_user.id:

        return await c.answer("Buyurtma topilmadi.", show_alert=True)



    if order["status"] == "expired":

        return await c.answer(

            f"Buyurtma muddati tugagan. To'lov qilgan bo'lsangiz {SUPPORT_USERNAME} bilan bog'laning.",

            show_alert=True,

        )



    if not await set_status(ref, ("awaiting_payment",), "payment_review"):

        return await c.answer(

            "Bu buyurtma allaqachon ko‘rib chiqilgan.", show_alert=True

        )



    value = order["stars_amount"] if order["kind"] == "stars" else order["months"]

    product = f"{value} Stars" if order["kind"] == "stars" else f"Premium {value} oy"

    pay_amount = order["pay_amount"] or order["amount_uzs"]



    await admins(

        bot,

        f"💳 <b>TO'LOVNI TEKSHIRING</b>\n\n"

        f"🧾 <code>{ref}</code>\n"

        f"👤 Xaridor ID: <code>{order['telegram_id']}</code>\n"

        f"📦 {product}\n"

        f"🎯 @{order['target_username']}\n"

        f"💰 <b>{money(pay_amount)} so'm</b>\n\n"

        f"Mijoz 'To'lov qildim' bosdi. CardXabar hali avtomatik tasdiqlamagan.",

        review_kb(ref),

    )

    await c.message.edit_text(

        f"⏳ <b>To'lov tekshirilmoqda</b>\n\n"

        f"🧾 <code>{ref}</code>\n"

        f"Avto-aniqlash yoki admin tasdiqlashi kutilmoqda."

    )

    await c.answer("Adminga yuborildi.")





@router.callback_query(F.data.startswith("cancel:"))

async def cancel(c: CallbackQuery, bot: Bot):

    ref = c.data.split(":", 1)[1]

    order = await get_order(ref)

    if not order or order["telegram_id"] != c.from_user.id:

        return await c.answer("Buyurtma topilmadi.", show_alert=True)

    if not await set_status(ref, ("awaiting_payment",), "cancelled"):

        return await c.answer("Endi bekor qilib bo‘lmaydi.", show_alert=True)



    await log_event(bot, f"❌ Bekor qilindi: <code>{ref}</code>")

    await c.message.edit_text(

        "❌ Buyurtma bekor qilindi.",

        reply_markup=main_kb(c.from_user.id in ADMIN_IDS),

    )

    await c.answer()





# ========================= ADMIN TASDIQLASH =========================

@router.callback_query(F.data.startswith("admin:approve:"))

async def approve(c: CallbackQuery, bot: Bot):

    if c.from_user.id not in ADMIN_IDS:

        return await c.answer("Ruxsat yo‘q.", show_alert=True)



    ref = c.data.split(":", 2)[2]

    order = await get_order(ref)

    if not order:

        return await c.answer("Buyurtma topilmadi.", show_alert=True)

    if order["status"] != "payment_review":

        return await c.answer(

            f"Joriy holat: {order['status']}", show_alert=True

        )



    await c.answer("Tasdiqlandi. Yetkazish boshlandi.")

    try:

        await c.message.edit_reply_markup(reply_markup=None)

    except Exception:

        pass

    await log_event(bot, f"✅ To‘lov tasdiqlandi: <code>{ref}</code>")

    await deliver(bot, ref)





@router.callback_query(F.data.startswith("admin:reject:"))

async def reject(c: CallbackQuery, bot: Bot):

    if c.from_user.id not in ADMIN_IDS:

        return await c.answer("Ruxsat yo‘q.", show_alert=True)



    ref = c.data.split(":", 2)[2]

    order = await get_order(ref)

    if not order or not await set_status(ref, ("payment_review",), "rejected"):

        return await c.answer("Holat o‘zgargan.", show_alert=True)



    try:

        await c.message.edit_reply_markup(reply_markup=None)

    except Exception:

        pass

    await bot.send_message(

        order["telegram_id"],

        f"❌ To'lov tasdiqlanmadi.\n🧾 <code>{ref}</code>\n{SUPPORT_USERNAME}",

    )

    await log_event(bot, f"❌ To‘lov rad etildi: <code>{ref}</code>")

    await c.answer("Rad etildi.")





# ========================= PROFIL / YORDAM / ORDERS =========================

@router.callback_query(F.data == "menu:profile")
async def profile(c: CallbackQuery):
    uid = await upsert_user(c.from_user)
    cnt, total = await user_stats(c.from_user.id)
    vip_name, vip_discount = vip_info(total)
    vip_text = vip_name + (f" — {vip_discount}% chegirma" if vip_discount else "")

    await c.message.edit_text(
        f"👤 <b>Profil</b>\n\n"
        f"🆔 StarsOson ID: <b>{uid}</b>\n"
        f"👤 {c.from_user.full_name}\n"
        f"🔗 @{c.from_user.username or 'username yo‘q'}\n"
        f"📦 Buyurtmalar: <b>{cnt}</b>\n"
        f"💰 Xaridlar: <b>{money(total)} so'm</b>\n"
        f"👑 Daraja: <b>{vip_text}</b>",
        reply_markup=back(),
    )
    await c.answer()








@router.callback_query(F.data == "menu:support")

async def support(c: CallbackQuery):

    await c.message.edit_text(

        f"🆘 <b>Yordam</b>\n\nMurojaat: <b>{SUPPORT_USERNAME}</b>",

        reply_markup=back(),

    )

    await c.answer()





@router.callback_query(F.data == "menu:orders")

async def orders(c: CallbackQuery):

    async with db_connect() as db:

        db.row_factory = sqlite3.Row

        cur = await db.execute(

            "SELECT * FROM orders WHERE telegram_id=? ORDER BY id DESC LIMIT 10",

            (c.from_user.id,),

        )

        rows = await cur.fetchall()



    names = {

        "awaiting_payment": "💳 To‘lov kutilmoqda",

        "payment_review": "⏳ Tekshirilmoqda",

        "processing": "⚙️ Yuborilmoqda",

        "completed": "✅ Bajarildi",

        "delivery_failed": "⚠️ Yetkazish xatosi",

        "rejected": "❌ Rad etildi",

        "cancelled": "❌ Bekor qilindi",

        "expired": "⌛ Muddati tugadi",

    }

    lines = []

    for order in rows:

        value = order["stars_amount"] if order["kind"] == "stars" else order["months"]

        product = f"{value} Stars" if order["kind"] == "stars" else f"Premium {value} oy"

        lines.append(

            f"<code>{order['order_ref']}</code>\n"

            f"{product} → @{order['target_username']}\n"

            f"{money(order['amount_uzs'])} so'm — {names.get(order['status'], order['status'])}"

        )



    await c.message.edit_text(

        "📦 <b>Oxirgi buyurtmalar</b>\n\n"

        + ("\n\n".join(lines) if lines else "Hali buyurtma yo‘q."),

        reply_markup=back(),

    )

    await c.answer()





# ========================= ADMIN PANEL =========================

async def autopay_status_text() -> str:

    telethon_ok = TelegramClient is not None

    session_file = f"{TG_SESSION}.session"
    session_string_ok = bool(TG_SESSION_STRING)
    session_exists = session_string_ok or os.path.exists(session_file)
    session_kind = "Railway secret" if session_string_ok else "session fayl"

    return (

        f"💳 <b>Avto-to'lov holati</b>\n\n"

        f"Avto-to'lov: {'✅ YOQILGAN' if AUTOPAY_ENABLED else '❌ O‘CHIRILGAN'}\n"

        f"Sozlamalar: {'✅ tayyor' if AUTO_PAYMENT_CONFIGURED else '❌ to‘liq emas'}\n"

        f"Telethon: {'✅' if telethon_ok else '❌'}\n"

        f"Userbot session: {'✅' if session_exists else '❌'} ({session_kind})\n"

        f"CardXabar: <b>@{CARDXABAR_USERNAME or '-'}</b>\n"

        f"Karta: <b>***{CARD_LAST4 or '----'}</b>\n"

        f"Buyurtma muddati: <b>{ORDER_TTL_MIN} daqiqa</b>\n"

        f"Grace: <b>{GRACE_MIN} daqiqa</b>\n"

        f"Noyob summa diapazoni: <b>+1…+{UNIQUE_MAX} so'm</b>\n\n"

        f"🔒 Userbot faqat @CardXabarBot chatini tinglaydi."

    )





@router.message(Command("admin"))

async def admin_cmd(m: Message):

    if m.from_user.id not in ADMIN_IDS:

        return

    enabled = await setting("bot_enabled", "1") == "1"

    await m.answer(

        f"🛡 <b>StarsOson Admin</b>\n\n"

        f"Bot holati: {'🟢 ISHLAYAPTI' if enabled else '🔴 O‘CHIRILGAN'}",

        reply_markup=admin_panel_kb(enabled),

    )





@router.message(Command("autopay_status"))

async def autopay_status_cmd(m: Message):

    if m.from_user.id not in ADMIN_IDS:

        return

    await m.answer(await autopay_status_text())





@router.callback_query(F.data == "admin:panel")

async def admin_panel(c: CallbackQuery):

    if c.from_user.id not in ADMIN_IDS:

        return await c.answer("Ruxsat yo‘q.", show_alert=True)

    enabled = await setting("bot_enabled", "1") == "1"

    await c.message.edit_text(

        f"🛡 <b>StarsOson Admin</b>\n\n"

        f"Bot holati: {'🟢 ISHLAYAPTI' if enabled else '🔴 O‘CHIRILGAN'}",

        reply_markup=admin_panel_kb(enabled),

    )

    await c.answer()





@router.callback_query(F.data == "admin:autopay")

async def admin_autopay(c: CallbackQuery):

    if c.from_user.id not in ADMIN_IDS:

        return await c.answer("Ruxsat yo‘q.", show_alert=True)

    await c.message.edit_text(

        await autopay_status_text(),

        reply_markup=InlineKeyboardMarkup(

            inline_keyboard=[[b("↩️ Admin", "admin:panel", "danger")]]

        ),

    )

    await c.answer()






# ====================== YANGI ADMIN FUNKSIYALAR ======================

async def price_admin_text() -> str:
    star_price = await current_star_price()
    premium_prices = await current_premium_prices()
    return (
        "💰 <b>Narxlarni boshqarish</b>\n\n"
        f"⭐ 1 Stars: <b>{money(star_price)} so'm</b>\n"
        f"💎 Premium 3 oy: <b>{money(premium_prices[3])} so'm</b>\n"
        f"💎 Premium 6 oy: <b>{money(premium_prices[6])} so'm</b>\n"
        f"👑 Premium 12 oy: <b>{money(premium_prices[12])} so'm</b>\n\n"
        "O‘zgartirmoqchi bo‘lgan narxni tanlang:"
    )


def price_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [b("⭐ 1 Stars", "admin:price:stars", "primary")],
            [b("💎 3 oy", "admin:price:p3", "primary"), b("💎 6 oy", "admin:price:p6", "primary")],
            [b("👑 12 oy", "admin:price:p12", "primary")],
            [b("↩️ Admin", "admin:panel", "danger")],
        ]
    )


@router.callback_query(F.data == "admin:prices")
async def admin_prices(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)
    await state.clear()
    await c.message.edit_text(await price_admin_text(), reply_markup=price_admin_kb())
    await c.answer()


@router.callback_query(F.data.startswith("admin:price:"))
async def admin_price_pick(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)

    code = c.data.rsplit(":", 1)[1]
    mapping = {
        "stars": ("price_stars", "⭐ 1 Stars"),
        "p3": ("price_p3", "💎 Premium 3 oy"),
        "p6": ("price_p6", "💎 Premium 6 oy"),
        "p12": ("price_p12", "👑 Premium 12 oy"),
    }
    if code not in mapping:
        return await c.answer("Noto‘g‘ri tanlov.", show_alert=True)

    key, title = mapping[code]
    await state.set_state(Flow.admin_price)
    await state.update_data(admin_price_key=key, admin_price_title=title)
    await c.message.edit_text(
        f"💰 <b>{title}</b>\n\n"
        "Yangi narxni faqat raqamda yuboring.\n"
        "Masalan: <code>210</code> yoki <code>165000</code>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[b("❌ Bekor qilish", "admin:prices", "danger")]]
        ),
    )
    await c.answer()


@router.message(Flow.admin_price)
async def admin_price_value(m: Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS:
        return
    raw = re.sub(r"\D", "", m.text or "")
    if not raw:
        return await m.answer("❌ Narxni faqat raqamda yuboring.")
    value = int(raw)
    if value <= 0:
        return await m.answer("❌ Narx 0 dan katta bo‘lishi kerak.")

    data = await state.get_data()
    key = data.get("admin_price_key")
    title = data.get("admin_price_title", "Narx")
    if key not in {"price_stars", "price_p3", "price_p6", "price_p12"}:
        await state.clear()
        return await m.answer("❌ Sozlama topilmadi. /admin ni qayta oching.")

    await set_setting(key, str(value))
    await state.clear()
    await m.answer(
        f"✅ <b>{title}</b> yangi narxi: <b>{money(value)} so'm</b>",
        reply_markup=admin_back_kb(),
    )


@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)
    await state.clear()
    await c.message.edit_text(
        "📣 <b>Ommaviy xabar</b>\n\n"
        "Matn, rasm, video yoki boshqa postni barcha foydalanuvchilarga yuborishingiz mumkin.\n"
        "Yoki bot ochildi/yopildi tezkor xabaridan foydalaning.",
        reply_markup=broadcast_menu_kb(),
    )
    await c.answer()


@router.callback_query(F.data == "admin:broadcast:custom")
async def admin_broadcast_custom(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)
    await state.set_state(Flow.broadcast)
    await c.message.edit_text(
        "✍️ <b>Ommaviy yuboriladigan xabarni yuboring.</b>\n\n"
        "Matn, rasm, video yoki post bo‘lishi mumkin.\n"
        "Avval preview ko‘rsatiladi, keyin tasdiqlaysiz.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[b("❌ Bekor qilish", "admin:broadcast:cancel", "danger")]]
        ),
    )
    await c.answer()


@router.message(Flow.broadcast)
async def admin_broadcast_receive(m: Message, state: FSMContext, bot: Bot):
    if m.from_user.id not in ADMIN_IDS:
        return
    await state.update_data(
        broadcast_chat_id=m.chat.id,
        broadcast_message_id=m.message_id,
    )
    await bot.copy_message(m.chat.id, m.chat.id, m.message_id)
    await m.answer(
        "👆 <b>Preview</b>\n\nShu xabarni barcha foydalanuvchilarga yuboraymi?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [b("✅ Hammaga yuborish", "admin:broadcast:confirm", "success")],
                [b("❌ Bekor qilish", "admin:broadcast:cancel", "danger")],
            ]
        ),
    )


@router.callback_query(F.data == "admin:broadcast:cancel")
async def admin_broadcast_cancel(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)
    await state.clear()
    await c.message.edit_text("❌ Ommaviy xabar bekor qilindi.", reply_markup=admin_back_kb())
    await c.answer()


@router.callback_query(F.data == "admin:broadcast:confirm")
async def admin_broadcast_confirm(c: CallbackQuery, state: FSMContext, bot: Bot):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)
    data = await state.get_data()
    from_chat_id = data.get("broadcast_chat_id")
    message_id = data.get("broadcast_message_id")
    if not from_chat_id or not message_id:
        await state.clear()
        return await c.answer("Xabar topilmadi. Qaytadan urinib ko‘ring.", show_alert=True)

    await c.answer("Yuborish boshlandi.")
    await c.message.edit_text("📤 <b>Ommaviy xabar yuborilmoqda...</b>")
    ok, fail = await broadcast_copy(bot, int(from_chat_id), int(message_id))
    await state.clear()
    await c.message.edit_text(
        f"✅ <b>Ommaviy xabar yakunlandi</b>\n\n"
        f"✅ Yuborildi: <b>{ok} ta</b>\n"
        f"❌ Yetmadi: <b>{fail} ta</b>",
        reply_markup=admin_back_kb(),
    )


@router.callback_query(F.data.in_({"admin:broadcast:open", "admin:broadcast:closed"}))
async def admin_broadcast_status_preview(c: CallbackQuery):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)
    is_open = c.data.endswith(":open")
    text = (
        "🟢 <b>StarsOson bot yana ishga tushdi!</b>\n\n"
        "⭐ Stars va 💎 Premium xaridlarini bot orqali 24/7 amalga oshirishingiz mumkin.\n\n"
        "👇 Xarid qilish uchun /start"
        if is_open
        else
        "🔴 <b>StarsOson bot vaqtincha yopildi.</b>\n\n"
        "🛠 Texnik ishlar olib borilmoqda. Bot qayta ishga tushganda xabar beramiz."
    )
    action = "open" if is_open else "closed"
    await c.message.edit_text(
        f"{text}\n\n<b>Bu xabar barcha foydalanuvchilarga yuboriladi.</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [b("✅ Tasdiqlash", f"admin:broadcast:status:{action}", "success")],
                [b("❌ Bekor qilish", "admin:broadcast", "danger")],
            ]
        ),
    )
    await c.answer()


@router.callback_query(F.data.startswith("admin:broadcast:status:"))
async def admin_broadcast_status_send(c: CallbackQuery, bot: Bot):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)

    action = c.data.rsplit(":", 1)[1]
    is_open = action == "open"
    text = (
        "🟢 <b>StarsOson bot yana ishga tushdi!</b>\n\n"
        "⭐ Stars va 💎 Premium xaridlarini bot orqali 24/7 amalga oshirishingiz mumkin.\n\n"
        "👇 Xarid qilish uchun /start"
        if is_open
        else
        "🔴 <b>StarsOson bot vaqtincha yopildi.</b>\n\n"
        "🛠 Texnik ishlar olib borilmoqda. Bot qayta ishga tushganda xabar beramiz."
    )

    await set_setting("bot_enabled", "1" if is_open else "0")
    await c.answer("Yuborish boshlandi.")
    await c.message.edit_text("📤 <b>Status xabari yuborilmoqda...</b>")
    ok, fail = await broadcast_text(bot, text)
    await c.message.edit_text(
        f"{'🟢 Bot yoqildi.' if is_open else '🔴 Bot o‘chirildi.'}\n\n"
        f"✅ Yuborildi: <b>{ok} ta</b>\n"
        f"❌ Yetmadi: <b>{fail} ta</b>",
        reply_markup=admin_back_kb(),
    )


@router.callback_query(F.data == "admin:channel")
async def admin_channel(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)

    await state.clear()
    enabled, channel = await required_channel_settings()
    await c.message.edit_text(
        "📢 <b>Majburiy kanal obunasi</b>\n\n"
        f"Holat: <b>{'✅ YOQILGAN' if enabled else '❌ O‘CHIRILGAN'}</b>\n"
        f"Kanal: <b>{channel or 'kiritilmagan'}</b>\n\n"
        "⚠️ Obunani aniq tekshirish uchun bot kanalda administrator bo‘lishi kerak.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [b("✏️ Kanalni o‘zgartirish", "admin:channel:set", "primary")],
                [b("✅ Yoqish", "admin:channel:on", "success"), b("⛔ O‘chirish", "admin:channel:off", "danger")],
                [b("↩️ Admin", "admin:panel", "danger")],
            ]
        ),
    )
    await c.answer()


@router.callback_query(F.data == "admin:channel:set")
async def admin_channel_set(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)
    await state.set_state(Flow.admin_channel)
    await c.message.edit_text(
        "📢 Kanal username'ini yuboring.\n\n"
        "Masalan: <code>@starsoson</code>\n"
        "Kanal public bo‘lishi kerak.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[b("❌ Bekor qilish", "admin:channel", "danger")]]
        ),
    )
    await c.answer()


@router.message(Flow.admin_channel)
async def admin_channel_value(m: Message, state: FSMContext, bot: Bot):
    if m.from_user.id not in ADMIN_IDS:
        return

    value = (m.text or "").strip()
    if value.startswith("https://t.me/"):
        value = "@" + value.rstrip("/").rsplit("/", 1)[-1]
    if not value.startswith("@"):
        value = "@" + value
    if not re.fullmatch(r"@[A-Za-z0-9_]{5,32}", value):
        return await m.answer("❌ Kanal username noto‘g‘ri. Masalan: <code>@starsoson</code>")

    try:
        await bot.get_chat(value)
    except Exception:
        return await m.answer("❌ Bot bu kanalni topolmadi. Username to‘g‘riligini tekshiring.")

    await set_setting("required_channel", value)
    await state.clear()
    await m.answer(
        f"✅ Majburiy obuna kanali saqlandi: <b>{value}</b>\n\n"
        "Endi botni shu kanalga administrator qiling, so‘ng admin paneldan obunani yoqing.",
        reply_markup=admin_back_kb(),
    )


@router.callback_query(F.data.in_({"admin:channel:on", "admin:channel:off"}))
async def admin_channel_toggle(c: CallbackQuery, bot: Bot):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)

    on = c.data.endswith(":on")
    _, channel = await required_channel_settings()
    if on and not channel:
        return await c.answer("Avval kanal username'ini kiriting.", show_alert=True)

    if on:
        try:
            me = await bot.get_me()
            member = await bot.get_chat_member(channel, me.id)
            if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
                return await c.answer("Avval botni kanalda administrator qiling.", show_alert=True)
        except Exception:
            return await c.answer(
                "Kanalni tekshirib bo‘lmadi. Botni kanalda admin qiling.",
                show_alert=True,
            )

    await set_setting("force_sub_enabled", "1" if on else "0")
    await c.answer("✅ Saqlandi.")
    enabled, channel = await required_channel_settings()
    await c.message.edit_text(
        "📢 <b>Majburiy kanal obunasi</b>\n\n"
        f"Holat: <b>{'✅ YOQILGAN' if enabled else '❌ O‘CHIRILGAN'}</b>\n"
        f"Kanal: <b>{channel or 'kiritilmagan'}</b>",
        reply_markup=admin_back_kb(),
    )


@router.callback_query(F.data == "admin:vip")
async def admin_vip(c: CallbackQuery):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Ruxsat yo‘q.", show_alert=True)

    async with db_connect() as db:
        rows = await (
            await db.execute(
                """
                SELECT u.telegram_id, u.first_name, u.username,
                       COALESCE(SUM(CASE WHEN o.status='completed' THEN o.amount_uzs ELSE 0 END),0) AS total
                FROM users u
                LEFT JOIN orders o ON o.telegram_id=u.telegram_id
                GROUP BY u.telegram_id, u.first_name, u.username
                ORDER BY total DESC
                LIMIT 10
                """
            )
        ).fetchall()

    top_lines = []
    for idx, row in enumerate(rows, 1):
        level, _ = vip_info(int(row[3] or 0))
        name = row[1] or row[2] or str(row[0])
        top_lines.append(f"{idx}. {name} — <b>{money(int(row[3] or 0))} so'm</b> — {level}")

    await c.message.edit_text(
        "👑 <b>VIP tizimi</b>\n\n"
        "⭐ Oddiy: 0 — 199 999 so‘m, 0%\n"
        "🥈 Silver: 200 000+ so‘m, 1%\n"
        "🥇 Gold: 500 000+ so‘m, 2%\n"
        "👑 VIP: 1 000 000+ so‘m, 3%\n\n"
        "<b>TOP xaridorlar:</b>\n"
        + ("\n".join(top_lines) if top_lines else "Hali xaridorlar yo‘q."),
        reply_markup=admin_back_kb(),
    )
    await c.answer()


@router.callback_query(F.data.startswith("admin:toggle:"))

async def toggle(c: CallbackQuery, bot: Bot):

    if c.from_user.id not in ADMIN_IDS:

        return await c.answer("Ruxsat yo‘q.", show_alert=True)

    on = c.data.endswith(":on")

    await set_setting("bot_enabled", "1" if on else "0")

    await log_event(

        bot,

        f"🛡 Bot {'yoqildi' if on else 'o‘chirildi'} — admin {c.from_user.id}",

    )

    await c.message.edit_text(

        f"🛡 <b>StarsOson Admin</b>\n\n"

        f"Bot holati: {'🟢 ISHLAYAPTI' if on else '🔴 O‘CHIRILGAN'}",

        reply_markup=admin_panel_kb(on),

    )

    await c.answer("Saqlandi.")





@router.callback_query(F.data == "admin:stats")

async def astats(c: CallbackQuery):

    if c.from_user.id not in ADMIN_IDS:

        return

    async with db_connect() as db:

        users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]

        total_orders = (await (await db.execute("SELECT COUNT(*) FROM orders")).fetchone())[0]

        done, total = await (

            await db.execute(

                "SELECT COUNT(*),COALESCE(SUM(amount_uzs),0) FROM orders WHERE status='completed'"

            )

        ).fetchone()

    await c.message.edit_text(

        f"📊 <b>Statistika</b>\n\n"

        f"👥 Foydalanuvchilar: {users}\n"

        f"📦 Buyurtmalar: {total_orders}\n"

        f"✅ Bajarilgan: {done}\n"

        f"💰 Savdo: {money(total)} so'm",

        reply_markup=InlineKeyboardMarkup(

            inline_keyboard=[[b("↩️ Admin", "admin:panel", "danger")]]

        ),

    )

    await c.answer()





@router.callback_query(F.data == "admin:orders")

async def aorders(c: CallbackQuery):

    if c.from_user.id not in ADMIN_IDS:

        return

    async with db_connect() as db:

        db.row_factory = sqlite3.Row

        rows = await (

            await db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 15")

        ).fetchall()

    lines = [

        f"<code>{o['order_ref']}</code> | {o['kind']} | {money(o['amount_uzs'])} | {o['status']}"

        for o in rows

    ]

    await c.message.edit_text(

        "📦 <b>So‘nggi buyurtmalar</b>\n\n"

        + ("\n".join(lines) if lines else "Yo‘q"),

        reply_markup=InlineKeyboardMarkup(

            inline_keyboard=[[b("↩️ Admin", "admin:panel", "danger")]]

        ),

    )

    await c.answer()





@router.callback_query(F.data == "admin:users")

async def ausers(c: CallbackQuery):

    if c.from_user.id not in ADMIN_IDS:

        return

    async with db_connect() as db:

        rows = await (

            await db.execute(

                "SELECT telegram_id,first_name,username FROM users ORDER BY id DESC LIMIT 15"

            )

        ).fetchall()

    lines = [f"👤 {x[1]} | <code>{x[0]}</code> | @{x[2] or '-'}" for x in rows]

    await c.message.edit_text(

        "👥 <b>Foydalanuvchilar</b>\n\n"

        + ("\n".join(lines) if lines else "Yo‘q"),

        reply_markup=InlineKeyboardMarkup(

            inline_keyboard=[[b("↩️ Admin", "admin:panel", "danger")]]

        ),

    )

    await c.answer()





@router.callback_query(F.data == "admin:logtest")

async def logtest(c: CallbackQuery, bot: Bot):

    if c.from_user.id not in ADMIN_IDS:

        return

    if not LOG_CHAT_ID:

        return await c.answer(

            "LOG_CHAT_ID .env da kiritilmagan.", show_alert=True

        )

    await log_event(bot, "✅ <b>PremiumHub log testi muvaffaqiyatli.</b>")

    await c.answer("Log kanalga test yuborildi.")





# ========================= START =========================

async def main() -> None:

    await db_init()

    bot = Bot(

        BOT_TOKEN,

        default=DefaultBotProperties(parse_mode=ParseMode.HTML),

    )

    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(router)



    me = await bot.get_me()

    log.info("Bot ishga tushdi: @%s", me.username)

    log.info("Adminlar: %s", sorted(ADMIN_IDS))

    log.info(

        "Avto-to'lov config: %s",

        "TAYYOR" if AUTO_PAYMENT_CONFIGURED else "TO'LIQ EMAS",

    )



    sweeper_task = asyncio.create_task(order_sweeper(bot))

    userbot = await start_userbot(bot)



    try:

        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    finally:

        sweeper_task.cancel()

        try:

            await sweeper_task

        except asyncio.CancelledError:

            pass

        if userbot is not None:

            await userbot.disconnect()

        await bot.session.close()





if __name__ == "__main__":

    asyncio.run(main())
