"""
═══════════════════════════════════════════════════════════════════════
🤖 ربات پیام ناشناس — Anonymous Messenger Bot (v4.0)
═══════════════════════════════════════════════════════════════════════
✨ تغییرات این نسخه:
   ✅ حذف کامل ثبت‌نام با شماره (ثبت‌نام خودکار)
   ✅ حذف لینک زمان‌دار
   ✅ افزودن لینک دائمی (چندبارمصرف) + لینک یکبار مصرف
   ✅ افزودن قفل کانال اجباری (Admin-Managed Force Join)
   ✅ بازنویسی کامل بخش Config
   ✅ افزودن SettingsRepo برای ذخیره تنظیمات سراسری
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Optional

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

try:
    from aiogram.enums import ButtonStyle
    STYLE_SUPPORTED = True
except ImportError:
    ButtonStyle = None  # type: ignore
    STYLE_SUPPORTED = False


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۱ — تنظیمات (Config) — بازنویسی‌شده
# ═══════════════════════════════════════════════════════════════════════
#
# 🔴 راهنمای پیکربندی:
#
# 1) BOT_TOKEN : توکن ربات را از @BotFather دریافت کرده و اینجا قرار دهید.
# 2) ADMIN_ID  : آیدی عددی شما (از @userinfobot قابل دریافت است).
# 3) BOT_USERNAME : یوزرنیم ربات بدون @ (برای ساخت لینک استفاده می‌شود).
#    اگر خالی بگذارید، هنگام راه‌اندازی خودکار از تلگرام خوانده می‌شود.
#
# بقیه مقادیر پیش‌فرض مناسب هستند و در صورت نیاز قابل تغییرند.
# ═══════════════════════════════════════════════════════════════════════

class Config:
    """تمام متغیرهای پیکربندی ربات در یک جا."""

    # ─────────── 🔴 این دو مقدار اجباری را پر کنید ───────────
    BOT_TOKEN: str = "8654406992:AAECfMfmYjc9_W8sFG-yNR78kASBh7CRMTs"
    ADMIN_ID: int = 8094551428
    # ─────────────────────────────────────────────────────────

    # ─── اطلاعات ربات ───
    BOT_USERNAME: str = "YourBot"                # بدون @ — اگر خالی بماند خودکار خوانده می‌شود

    # ─── دیتابیس ───
    DB_PATH: str = "anonymous_bot_v4.db"         # نام فایل دیتابیس

    # ─── محدودیت نرخ (Rate Limit) ───
    RATE_LIMIT_MESSAGES: int = 10                # حداکثر پیام در بازه
    RATE_LIMIT_WINDOW: int = 60                  # بازه زمانی (ثانیه)

    # ─── لاگ ───
    LOG_LEVEL: str = "INFO"                      # DEBUG | INFO | WARNING | ERROR | CRITICAL
    LOG_FILE: str = "logs/bot.log"

    # ─── ظرفیت‌ها ───
    MAX_MESSAGE_LENGTH: int = 4096               # حداکثر طول پیام تلگرام

    @classmethod
    def validate(cls) -> None:
        """اعتبارسنجی مقادیر حیاتی قبل از راه‌اندازی."""
        errors: list[str] = []

        # 1) BOT_TOKEN
        if not cls.BOT_TOKEN or cls.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            errors.append("❌ BOT_TOKEN تنظیم نشده است. از @BotFather توکن بگیرید.")
        elif not re.match(r"^\d+:[A-Za-z0-9_-]+$", cls.BOT_TOKEN):
            errors.append("❌ فرمت BOT_TOKEN نامعتبر است. مثال: 123456:ABC-DEF...")

        # 2) ADMIN_ID
        if not isinstance(cls.ADMIN_ID, int) or cls.ADMIN_ID <= 0:
            errors.append("❌ ADMIN_ID باید یک عدد مثبت باشد (مثال: 123456789).")

        # 3) Rate Limit
        if cls.RATE_LIMIT_MESSAGES <= 0:
            errors.append("❌ RATE_LIMIT_MESSAGES باید مثبت باشد.")
        if cls.RATE_LIMIT_WINDOW <= 0:
            errors.append("❌ RATE_LIMIT_WINDOW باید مثبت باشد.")

        # 4) Log Level
        if cls.LOG_LEVEL.upper() not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            errors.append(f"❌ LOG_LEVEL نامعتبر: {cls.LOG_LEVEL}")

        if errors:
            raise RuntimeError("\n".join(errors))


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۲ — لاگ‌گیری
# ═══════════════════════════════════════════════════════════════════════

def setup_logger() -> logging.Logger:
    os.makedirs(os.path.dirname(Config.LOG_FILE) or ".", exist_ok=True)
    logger = logging.getLogger("anonymous_bot")
    logger.setLevel(getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))
    logger.propagate = False

    fmt = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if not logger.handlers:
        fh = RotatingFileHandler(
            Config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger


log = setup_logger()
if not STYLE_SUPPORTED:
    log.warning("⚠️ ButtonStyle یافت نشد. دکمه‌ها بدون رنگ ساخته می‌شوند.")
    log.warning("   برای فعال‌سازی رنگ‌ها: pip install -U 'aiogram>=3.31.0'")


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۳ — دیتابیس
# ═══════════════════════════════════════════════════════════════════════

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    full_name TEXT,
    username TEXT,
    is_banned INTEGER DEFAULT 0,
    ban_reason TEXT,
    message_count INTEGER DEFAULT 0,
    link_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned);

CREATE TABLE IF NOT EXISTS anonymous_links (
    token TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL,
    link_type TEXT NOT NULL DEFAULT 'onetime',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_used INTEGER DEFAULT 0,
    used_at TIMESTAMP,
    used_by INTEGER,
    FOREIGN KEY(owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_links_owner ON anonymous_links(owner_id);
CREATE INDEX IF NOT EXISTS idx_links_type ON anonymous_links(link_type);
CREATE INDEX IF NOT EXISTS idx_links_used ON anonymous_links(is_used);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    sender_token TEXT,
    content TEXT,
    content_type TEXT DEFAULT 'text',
    file_id TEXT,
    is_read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_owner ON messages(owner_id);
CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(created_at);

CREATE TABLE IF NOT EXISTS admin_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    target_id INTEGER,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    """مدیریت اتصال SQLite (Singleton + Async)."""

    _instance: Optional["Database"] = None
    _conn: Optional[aiosqlite.Connection] = None
    _lock: Optional[asyncio.Lock] = None

    def __new__(cls) -> "Database":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def connect(self) -> None:
        async with self._get_lock():
            if self._conn is not None:
                return
            self._conn = await aiosqlite.connect(Config.DB_PATH)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.executescript(SCHEMA_SQL)
            await self._conn.commit()
            log.info("✅ دیتابیس متصل شد: %s", Config.DB_PATH)

    async def close(self) -> None:
        async with self._get_lock():
            if self._conn is not None:
                try:
                    await self._conn.close()
                except Exception as e:
                    log.warning("خطا در بستن دیتابیس: %s", e)
                self._conn = None
                log.info("🔌 دیتابیس بسته شد.")

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("دیتابیس متصل نیست.")
        return self._conn

    async def execute(self, query: str, params: tuple = ()) -> aiosqlite.Cursor:
        cur = await self.conn.execute(query, params)
        await self.conn.commit()
        return cur

    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute(query, params)
        row = await cur.fetchone()
        await cur.close()
        return row

    async def fetch_all(self, query: str, params: tuple = ()) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(query, params)
        rows = await cur.fetchall()
        await cur.close()
        return list(rows)


db = Database()


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۴ — مدل‌ها
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class User:
    user_id: int
    full_name: Optional[str]
    username: Optional[str]
    is_banned: int
    ban_reason: Optional[str]
    message_count: int
    link_count: int
    created_at: str
    last_seen: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "User":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class AnonymousLink:
    token: str
    owner_id: int
    link_type: str
    created_at: str
    is_used: int
    used_at: Optional[str]
    used_by: Optional[int]

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "AnonymousLink":
        return cls(**{k: row[k] for k in row.keys()})


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۵ — ریپازیتوری‌ها
# ═══════════════════════════════════════════════════════════════════════

class UserRepo:
    async def create(self, user_id: int, full_name: Optional[str], username: Optional[str]) -> None:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, full_name, username) VALUES (?,?,?)",
            (user_id, full_name, username),
        )

    async def get_by_id(self, user_id: int) -> Optional[User]:
        row = await db.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return User.from_row(row) if row else None

    async def exists(self, user_id: int) -> bool:
        row = await db.fetch_one("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        return row is not None

    async def update_last_seen(self, user_id: int) -> None:
        await db.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))

    async def update_profile(self, user_id: int, full_name: Optional[str], username: Optional[str]) -> None:
        await db.execute(
            "UPDATE users SET full_name = ?, username = ?, last_seen = CURRENT_TIMESTAMP WHERE user_id = ?",
            (full_name, username, user_id),
        )

    async def ban(self, user_id: int, reason: str) -> None:
        await db.execute("UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?", (reason, user_id))

    async def unban(self, user_id: int) -> None:
        await db.execute("UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?", (user_id,))

    async def increment_message_count(self, user_id: int) -> None:
        await db.execute("UPDATE users SET message_count = message_count + 1 WHERE user_id = ?", (user_id,))

    async def increment_link_count(self, user_id: int) -> None:
        await db.execute("UPDATE users SET link_count = link_count + 1 WHERE user_id = ?", (user_id,))

    async def get_all(self, limit: int = 10, offset: int = 0) -> list[User]:
        rows = await db.fetch_all(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return [User.from_row(r) for r in rows]

    async def count_total(self) -> int:
        row = await db.fetch_one("SELECT COUNT(*) AS c FROM users")
        return int(row["c"]) if row else 0

    async def count_banned(self) -> int:
        row = await db.fetch_one("SELECT COUNT(*) AS c FROM users WHERE is_banned = 1")
        return int(row["c"]) if row else 0

    async def all_ids(self) -> list[int]:
        rows = await db.fetch_all("SELECT user_id FROM users WHERE is_banned = 0")
        return [int(r["user_id"]) for r in rows]


class LinkRepo:
    async def create(self, token: str, owner_id: int, link_type: str) -> None:
        await db.execute(
            "INSERT INTO anonymous_links (token, owner_id, link_type) VALUES (?,?,?)",
            (token, owner_id, link_type),
        )

    async def get_by_token(self, token: str) -> Optional[AnonymousLink]:
        row = await db.fetch_one("SELECT * FROM anonymous_links WHERE token = ?", (token,))
        return AnonymousLink.from_row(row) if row else None

    async def mark_used(self, token: str, used_by: int) -> None:
        await db.execute(
            "UPDATE anonymous_links SET is_used = 1, used_at = CURRENT_TIMESTAMP, used_by = ? WHERE token = ?",
            (used_by, token),
        )

    async def delete(self, token: str) -> None:
        await db.execute("DELETE FROM anonymous_links WHERE token = ?", (token,))

    async def delete_all_for_owner(self, owner_id: int) -> int:
        cur = await db.execute("DELETE FROM anonymous_links WHERE owner_id = ?", (owner_id,))
        return cur.rowcount or 0

    async def get_active_by_owner(self, owner_id: int) -> list[AnonymousLink]:
        rows = await db.fetch_all(
            "SELECT * FROM anonymous_links WHERE owner_id = ? ORDER BY created_at DESC",
            (owner_id,),
        )
        return [AnonymousLink.from_row(r) for r in rows]

    async def count_active(self) -> int:
        row = await db.fetch_one(
            "SELECT COUNT(*) AS c FROM anonymous_links WHERE link_type = 'permanent' OR is_used = 0"
        )
        return int(row["c"]) if row else 0

    async def count_total(self) -> int:
        row = await db.fetch_one("SELECT COUNT(*) AS c FROM anonymous_links")
        return int(row["c"]) if row else 0

    async def cleanup_used_onetime(self) -> int:
        """پاکسازی لینک‌های یکبارمصرف استفاده‌شده."""
        cur = await db.execute(
            "DELETE FROM anonymous_links WHERE link_type = 'onetime' AND is_used = 1"
        )
        return cur.rowcount or 0


class MessageRepo:
    async def create(
        self,
        owner_id: int,
        sender_id: int,
        sender_token: Optional[str],
        content: Optional[str],
        content_type: str,
        file_id: Optional[str],
    ) -> int:
        cur = await db.execute(
            """INSERT INTO messages (owner_id, sender_id, sender_token, content, content_type, file_id)
               VALUES (?,?,?,?,?,?)""",
            (owner_id, sender_id, sender_token, content, content_type, file_id),
        )
        return cur.lastrowid or 0

    async def count_total(self) -> int:
        row = await db.fetch_one("SELECT COUNT(*) AS c FROM messages")
        return int(row["c"]) if row else 0

    async def count_for_owner(self, owner_id: int) -> int:
        row = await db.fetch_one("SELECT COUNT(*) AS c FROM messages WHERE owner_id = ?", (owner_id,))
        return int(row["c"]) if row else 0


class AdminLogRepo:
    async def log(self, admin_id: int, action: str, target_id: Optional[int] = None, details: str = "") -> None:
        await db.execute(
            "INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?,?,?,?)",
            (admin_id, action, target_id, details),
        )

    async def recent(self, limit: int = 20) -> list[aiosqlite.Row]:
        return await db.fetch_all("SELECT * FROM admin_logs ORDER BY id DESC LIMIT ?", (limit,))


class SettingsRepo:
    """مدیریت تنظیمات سراسری (key-value)."""

    KEY_REQUIRED_CHANNEL = "required_channel"

    async def get(self, key: str) -> Optional[str]:
        row = await db.fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else None

    async def set(self, key: str, value: str) -> None:
        await db.execute(
            """INSERT INTO settings (key, value, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP""",
            (key, value),
        )

    async def delete(self, key: str) -> None:
        await db.execute("DELETE FROM settings WHERE key = ?", (key,))

    async def get_required_channel(self) -> Optional[str]:
        val = await self.get(self.KEY_REQUIRED_CHANNEL)
        return val if val else None

    async def set_required_channel(self, channel: str) -> None:
        await self.set(self.KEY_REQUIRED_CHANNEL, channel)

    async def clear_required_channel(self) -> None:
        await self.delete(self.KEY_REQUIRED_CHANNEL)


user_repo = UserRepo()
link_repo = LinkRepo()
message_repo = MessageRepo()
admin_log_repo = AdminLogRepo()
settings_repo = SettingsRepo()


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۶ — ابزارها
# ═══════════════════════════════════════════════════════════════════════

def generate_secure_token(length: int = 16) -> str:
    return secrets.token_urlsafe(length)


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:8]


def sanitize_text(text: str) -> str:
    return re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", text).strip()


def parse_channel_input(raw: str) -> Optional[str]:
    """
    ورودی ادمین را به فرمت قابل استفاده برای get_chat_member تبدیل می‌کند.
    پشتیبانی از:
      • @channel_username
      • https://t.me/channel_username
      • -1001234567890  (آیدی عددی)
    """
    raw = raw.strip()
    if not raw:
        return None
    # آیدی عددی
    if re.match(r"^-?\d+$", raw):
        return raw
    # لینک
    m = re.match(r"^https?://t\.me/([A-Za-z0-9_]+)/?$", raw)
    if m:
        return f"@{m.group(1)}"
    # یوزرنیم بدون @
    if raw.startswith("@"):
        return raw
    if re.match(r"^[A-Za-z0-9_]{4,}$", raw):
        return f"@{raw}"
    return None


async def get_channel_invite_url(bot: Bot, channel: str) -> str:
    """ساخت لینک دعوت کانال (برای نمایش در دکمه)."""
    if channel.startswith("@"):
        return f"https://t.me/{channel.lstrip('@')}"
    try:
        link = await bot.export_chat_invite_link(channel)
        return link
    except Exception:
        return "https://t.me/"


async def check_membership(bot: Bot, channel: str, user_id: int) -> bool:
    """بررسی عضویت کاربر در کانال. اگر خطا رخ دهد، True برمی‌گرداند تا کاربر بلاک نشود."""
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status not in ("left", "kicked")
    except TelegramBadRequest as e:
        log.warning("خطا در بررسی عضویت کانال %s: %s", channel, e)
        # اگر کانال پیدا نشد یا ربات ادمین نبود → کاربر را بلاک نکن
        return True
    except Exception as e:
        log.warning("خطای غیرمنتظره در check_membership: %s", e)
        return True


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۷ — کیبوردها
# ═══════════════════════════════════════════════════════════════════════

def _btn(text: str, style: Optional[str] = None, **kwargs) -> KeyboardButton:
    if STYLE_SUPPORTED and style is not None:
        return KeyboardButton(text=text, style=style, **kwargs)
    return KeyboardButton(text=text, **kwargs)


def _ibtn(text: str, style: Optional[str] = None, **kwargs) -> InlineKeyboardButton:
    if STYLE_SUPPORTED and style is not None:
        return InlineKeyboardButton(text=text, style=style, **kwargs)
    return InlineKeyboardButton(text=text, **kwargs)


if STYLE_SUPPORTED:
    S_PRIMARY = ButtonStyle.PRIMARY
    S_SUCCESS = ButtonStyle.SUCCESS
    S_DANGER = ButtonStyle.DANGER
else:
    S_PRIMARY = S_SUCCESS = S_DANGER = None


def main_menu_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """منوی اصلی کاربر."""
    keyboard = [
        [_btn("🔗 دریافت لینک ناشناس", S_PRIMARY)],
        [_btn("📊 آمار من", S_PRIMARY), _btn("⚙️ تنظیمات", S_PRIMARY)],
        [_btn("🗑 حذف همه لینک‌ها", S_DANGER)],
    ]
    if is_admin:
        keyboard.append([_btn("👑 پنل ادمین", S_PRIMARY)])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="یک گزینه انتخاب کنید...",
    )


def admin_menu_kb() -> ReplyKeyboardMarkup:
    """منوی ادمین."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [_btn("📊 آمار کلی", S_PRIMARY), _btn("👥 کاربران", S_PRIMARY)],
            [_btn("📢 پیام همگانی", S_PRIMARY), _btn("📝 لاگ‌ها", S_PRIMARY)],
            [_btn("🔒 کانال اجباری", S_PRIMARY)],
            [_btn("🚫 مدیریت بن‌ها", S_DANGER)],
            [_btn("🗑 پاکسازی لینک‌های یکبارمصرف", S_DANGER)],
            [_btn("◀️ بازگشت به منوی کاربر", S_PRIMARY)],
        ],
        resize_keyboard=True,
    )


def link_type_kb() -> InlineKeyboardMarkup:
    """انتخاب نوع لینک."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_ibtn("♾ لینک دائمی (چندبارمصرف)", S_PRIMARY, callback_data="linktype:permanent")],
            [_ibtn("1️⃣ لینک یکبارمصرف", S_SUCCESS, callback_data="linktype:onetime")],
            [_ibtn("❌ لغو", S_DANGER, callback_data="linktype:cancel")],
        ]
    )


def link_actions_kb(token: str, link_type: str) -> InlineKeyboardMarkup:
    """عملیات روی لینک ساخته‌شده."""
    share_url = f"https://t.me/share/url?url=https://t.me/{Config.BOT_USERNAME}?start={token}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_ibtn("📤 اشتراک‌گذاری لینک", S_SUCCESS, url=share_url)],
            [_ibtn("🗑 حذف این لینک", S_DANGER, callback_data=f"link:del:{token}")],
            [_ibtn("📊 آمار این لینک", S_PRIMARY, callback_data=f"link:stats:{token}")],
        ]
    )


def confirm_kb(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _ibtn("✅ بله، انجام بده", S_SUCCESS, callback_data=f"confirm:{action}"),
                _ibtn("❌ انصراف", S_DANGER, callback_data=f"cancel:{action}"),
            ]
        ]
    )


def cancel_kb(callback: str = "global:cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_ibtn("❌ لغو عملیات", S_DANGER, callback_data=callback)]]
    )


def join_channel_kb(invite_url: str) -> InlineKeyboardMarkup:
    """کیبورد عضویت اجباری."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_ibtn("📢 عضویت در کانال", S_PRIMARY, url=invite_url)],
            [_ibtn("✅ بررسی عضویت", S_SUCCESS, callback_data="check_join")],
        ]
    )


def admin_channel_manage_kb(has_channel: bool) -> InlineKeyboardMarkup:
    """مدیریت کانال اجباری."""
    rows = [
        [_ibtn("🔧 تغییر / تنظیم کانال", S_PRIMARY, callback_data="admin_ch:set")],
    ]
    if has_channel:
        rows.append([_ibtn("🗑 حذف کانال اجباری", S_DANGER, callback_data="admin_ch:remove")])
    rows.append([_ibtn("◀️ بازگشت", S_PRIMARY, callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۸ — FSM States
# ═══════════════════════════════════════════════════════════════════════

class LinkCreationStates(StatesGroup):
    choosing_type = State()


class AnonymousSendStates(StatesGroup):
    waiting_message = State()
    confirm_send = State()


class AdminStates(StatesGroup):
    broadcasting = State()
    broadcasting_confirm = State()
    setting_channel = State()


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۹ — Middlewares
# ═══════════════════════════════════════════════════════════════════════

class BanCheckMiddleware(BaseMiddleware):
    """بررسی بن بودن کاربر."""

    async def __call__(self, handler, event, data):
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id and user_id != Config.ADMIN_ID:
            user = await user_repo.get_by_id(user_id)
            if user and user.is_banned:
                reason = user.ban_reason or "بدون دلیل"
                if isinstance(event, Message):
                    await event.answer(f"🚫 شما بن شده‌اید.\nدلیل: {reason}")
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚫 شما بن شده‌اید.", show_alert=True)
                return None

        if user_id:
            data["user_id"] = user_id
        return await handler(event, data)


class JoinCheckMiddleware(BaseMiddleware):
    """
    بررسی عضویت اجباری در کانال.
    اگر ادمین کانالی تنظیم کرده باشد، کاربران غیرعضو بلاک می‌شوند.
    """

    async def __call__(self, handler, event, data):
        bot: Bot = data.get("bot")
        user_id: Optional[int] = None

        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        # ادمین و ربات معاف
        if not user_id or user_id == Config.ADMIN_ID:
            return await handler(event, data)

        # کانال تنظیم نشده؟ عبور
        required = await settings_repo.get_required_channel()
        if not required:
            return await handler(event, data)

        # هندل دکمه بررسی عضویت
        if isinstance(event, CallbackQuery) and event.data == "check_join":
            ok = await check_membership(bot, required, user_id)
            if ok:
                await event.answer("✅ عضویت تایید شد! حالا /start بزنید.", show_alert=True)
            else:
                await event.answer("❌ هنوز عضو نشده‌اید!", show_alert=True)
            return None

        # بررسی عضویت
        is_member = await check_membership(bot, required, user_id)
        if is_member:
            return await handler(event, data)

        # کاربر عضو نیست → نمایش پیام
        invite_url = await get_channel_invite_url(bot, required)
        text = (
            "🔒 <b>ورود محدود به ربات!</b>\n\n"
            "برای استفاده از ربات، ابتدا باید در کانال زیر عضو شوید:\n\n"
            f"📢 <b>{required}</b>\n\n"
            "پس از عضویت، روی دکمه «✅ بررسی عضویت» بزنید."
        )
        kb = join_channel_kb(invite_url)

        try:
            if isinstance(event, Message):
                await event.answer(text, reply_markup=kb)
            else:
                await event.message.answer(text, reply_markup=kb)
                await event.answer()
        except Exception as e:
            log.debug("خطا در نمایش پیام عضویت: %s", e)
        return None


class RateLimitMiddleware(BaseMiddleware):
    """محدودیت نرخ — فقط برای فلوی پیام ناشناس."""

    def __init__(self, max_messages: int = 10, window_seconds: int = 60):
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        self._buckets: dict[int, list[datetime]] = {}

    async def __call__(self, handler, event, data):
        state: Optional[FSMContext] = data.get("state")
        if state is not None:
            try:
                current = await state.get_state()
                if current != AnonymousSendStates.waiting_message.state:
                    return await handler(event, data)
            except Exception:
                return await handler(event, data)

        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id

        if user_id and user_id != Config.ADMIN_ID:
            now = datetime.now()
            bucket = self._buckets.setdefault(user_id, [])
            bucket[:] = [t for t in bucket if (now - t).total_seconds() < self.window_seconds]
            if len(bucket) >= self.max_messages:
                if isinstance(event, Message):
                    await event.answer("⏳ خیلی سریع! لطفاً چند لحظه صبر کنید.")
                return None
            bucket.append(now)

        return await handler(event, data)


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۱۰ — سرویس‌ها
# ═══════════════════════════════════════════════════════════════════════

class AuthService:
    """ثبت‌نام خودکار بدون شماره تلفن."""

    async def ensure_registered(
        self, user_id: int, full_name: Optional[str], username: Optional[str]
    ) -> bool:
        """اگر کاربر جدید است، ثبت‌نام خودکار انجام بده."""
        exists = await user_repo.exists(user_id)
        if not exists:
            await user_repo.create(user_id, full_name, username)
            log.info("🆕 کاربر جدید (خودکار): %s", user_id)
            return True
        # به‌روزرسانی پروفایل
        await user_repo.update_profile(user_id, full_name, username)
        return False


class LinkService:
    async def create_link(self, owner_id: int, link_type: str = "onetime") -> dict:
        """ساخت لینک دائمی یا یکبارمصرف."""
        if link_type not in ("permanent", "onetime"):
            return {"ok": False, "error": "نوع لینک نامعتبر است."}

        user = await user_repo.get_by_id(owner_id)
        if not user:
            return {"ok": False, "error": "ابتدا ثبت‌نام کنید."}
        if user.is_banned:
            return {"ok": False, "error": "شما بن هستید."}

        token = generate_secure_token()
        while await link_repo.get_by_token(token):
            token = generate_secure_token()

        await link_repo.create(token, owner_id, link_type)
        await user_repo.increment_link_count(owner_id)

        link = f"https://t.me/{Config.BOT_USERNAME}?start={token}"
        log.info(
            "🔗 لینک جدید (%s): %s (مالک: %s)",
            link_type, token_fingerprint(token), owner_id,
        )
        return {"ok": True, "token": token, "link": link, "link_type": link_type}

    async def validate_link(self, token: str) -> tuple[bool, Optional[AnonymousLink], str]:
        if not token or len(token) < 10:
            return False, None, "توکن نامعتبر است."
        link = await link_repo.get_by_token(token)
        if not link:
            return False, None, "این لینک وجود ندارد."
        # فقط برای لینک‌های یکبارمصرف بررسی می‌شود
        if link.link_type == "onetime" and link.is_used:
            return False, None, "این لینک قبلاً استفاده شده است."
        return True, link, ""

    async def consume_link(self, token: str, used_by: int, link_type: str) -> None:
        """فقط لینک یکبارمصرف را مصرف می‌کند."""
        if link_type == "onetime":
            await link_repo.mark_used(token, used_by)


class MessageService:
    async def send_anonymous(
        self,
        bot: Bot,
        owner_id: int,
        sender_id: int,
        token: str,
        content_type: str,
        content: Optional[str],
        file_id: Optional[str],
    ) -> dict:
        await message_repo.create(owner_id, sender_id, token, content, content_type, file_id)
        await user_repo.increment_message_count(owner_id)

        header = (
            "📩 <b>پیام ناشناس جدید</b>\n"
            f"🕐 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            "─────────────────\n"
        )
        try:
            if content_type == "text":
                await bot.send_message(owner_id, header + (content or ""))
            elif content_type == "photo":
                await bot.send_photo(owner_id, file_id, caption=header + (content or ""))
            elif content_type == "voice":
                await bot.send_voice(owner_id, file_id, caption=header + (content or ""))
            elif content_type == "video":
                await bot.send_video(owner_id, file_id, caption=header + (content or ""))
            elif content_type == "document":
                await bot.send_document(owner_id, file_id, caption=header + (content or ""))
            elif content_type == "sticker":
                await bot.send_message(owner_id, header)
                await bot.send_sticker(owner_id, file_id)
            else:
                return {"ok": False, "error": "نوع پیام پشتیبانی نمی‌شود."}
        except TelegramForbiddenError:
            log.warning("مالک %s ربات را بلاک کرده.", owner_id)
            return {"ok": False, "error": "مالک لینک ربات را بلاک کرده است."}
        except Exception as e:
            log.exception("خطا در ارسال: %s", e)
            return {"ok": False, "error": "خطا در ارسال پیام."}

        log.info("📨 پیام ناشناس: از %s به %s", sender_id, owner_id)
        return {"ok": True}


class AdminService:
    async def get_stats(self) -> dict:
        required = await settings_repo.get_required_channel()
        return {
            "users": await user_repo.count_total(),
            "banned": await user_repo.count_banned(),
            "links": await link_repo.count_total(),
            "active_links": await link_repo.count_active(),
            "messages": await message_repo.count_total(),
            "required_channel": required or "—",
        }

    async def broadcast(self, bot: Bot, from_chat_id: int, message_id: int, user_ids: list[int]) -> dict:
        success, failed = 0, 0
        for uid in user_ids:
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=from_chat_id, message_id=message_id)
                success += 1
            except (TelegramForbiddenError, TelegramBadRequest):
                failed += 1
            except Exception as e:
                log.debug("broadcast fail %s: %s", uid, e)
                failed += 1
            await asyncio.sleep(0.05)
        return {"success": success, "failed": failed}


auth_service = AuthService()
link_service = LinkService()
message_service = MessageService()
admin_service = AdminService()


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۱۱ — هندلرها
# ═══════════════════════════════════════════════════════════════════════

common_router = Router(name="common")
user_router = Router(name="user_panel")
anon_router = Router(name="anonymous")
admin_router = Router(name="admin_panel")


# ─── /start ───
@common_router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    # ثبت‌نام خودکار
    await auth_service.ensure_registered(
        user_id=user_id,
        full_name=message.from_user.full_name,
        username=message.from_user.username,
    )

    payload = (command.args or "").strip()

    # ─── فلوی پیام ناشناس ───
    if payload:
        ok, link, error = await link_service.validate_link(payload)
        if not ok:
            await message.answer(f"❌ {error}", reply_markup=ReplyKeyboardRemove())
            return
        if link.owner_id == user_id:
            await message.answer("🙂 نمی‌توانید به خودتان پیام ناشناس بفرستید.")
            return
        await state.update_data(token=payload, owner_id=link.owner_id, link_type=link.link_type)
        await state.set_state(AnonymousSendStates.waiting_message)
        await message.answer(
            "📩 <b>ارسال پیام ناشناس</b>\n\n"
            "پیام خود را بنویسید یا عکس/ویس/ویدیو/فایل بفرستید.\n"
            "برای لغو: /cancel",
            reply_markup=cancel_kb("anon:cancel"),
        )
        return

    # ─── منوی اصلی ───
    is_admin = user_id == Config.ADMIN_ID
    await message.answer(
        "🏠 <b>منوی اصلی</b>\n\nیک گزینه انتخاب کنید:",
        reply_markup=main_menu_kb(is_admin),
    )


@common_router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "❓ <b>راهنما</b>\n\n"
        "🔗 <b>دریافت لینک ناشناس:</b> می‌توانید لینک دائمی یا یکبارمصرف بسازید.\n"
        "♾ <b>لینک دائمی:</b> چند نفر می‌توانند پیام بفرستند.\n"
        "1️⃣ <b>لینک یکبارمصرف:</b> فقط یک نفر می‌تواند پیام بفرستد.\n"
        "📊 <b>آمار من:</b> تعداد پیام‌ها و لینک‌ها.\n"
        "🗑 <b>حذف لینک‌ها:</b> همه لینک‌های شما پاک می‌شود.\n\n"
        "دستورات: /start | /help | /cancel",
    )


@common_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer(
            "چیزی برای لغو وجود ندارد.",
            reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID),
        )
        return
    await state.clear()
    await message.answer(
        "❌ عملیات لغو شد.",
        reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID),
    )


@common_router.callback_query(F.data == "anon:cancel")
async def cb_anon_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.edit_text("❌ ارسال پیام لغو شد.")
    except TelegramBadRequest:
        await cb.message.answer("❌ ارسال پیام لغو شد.")
    await cb.answer()


@common_router.callback_query(F.data == "global:cancel")
async def cb_global_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.edit_text("❌ لغو شد.")
    except TelegramBadRequest:
        await cb.message.answer("❌ لغو شد.")
    await cb.answer()


# ─── پنل کاربر ───
@user_router.message(F.text == "🔗 دریافت لینک ناشناس")
async def user_get_link(message: Message, state: FSMContext):
    await state.set_state(LinkCreationStates.choosing_type)
    await message.answer(
        "🔗 <b>نوع لینک را انتخاب کنید:</b>\n\n"
        "♾ <b>دائمی:</b> هر تعداد نفر می‌تواند پیام بفرستد.\n"
        "1️⃣ <b>یکبارمصرف:</b> فقط یک نفر می‌تواند پیام بفرستد و بعد باطل می‌شود.",
        reply_markup=link_type_kb(),
    )


@user_router.callback_query(F.data.startswith("linktype:"))
async def cb_link_type(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    value = cb.data.split(":", 1)[1]

    if value == "cancel":
        try:
            await cb.message.edit_text("❌ لغو شد.")
        except TelegramBadRequest:
            pass
        await cb.answer()
        return

    link_type = "permanent" if value == "permanent" else "onetime"
    result = await link_service.create_link(cb.from_user.id, link_type)
    if not result["ok"]:
        try:
            await cb.message.edit_text(f"❌ {result['error']}")
        except TelegramBadRequest:
            pass
        await cb.answer()
        return

    type_label = "♾ دائمی" if link_type == "permanent" else "1️⃣ یکبارمصرف"
    warning = (
        "🔓 این لینک <b>چندبارمصرف</b> است و تا حذف دستی معتبر می‌ماند."
        if link_type == "permanent"
        else "⚠️ این لینک فقط <b>یکبار</b> قابل استفاده است."
    )
    text = (
        f"✅ <b>لینک شما آماده است! ({type_label})</b>\n\n"
        f"🔗 <code>{result['link']}</code>\n\n"
        f"{warning}"
    )
    try:
        await cb.message.edit_text(text, reply_markup=link_actions_kb(result["token"], link_type))
    except TelegramBadRequest:
        await cb.message.answer(text, reply_markup=link_actions_kb(result["token"], link_type))
    await cb.answer("✅ لینک ساخته شد.")


@user_router.callback_query(F.data.startswith("link:del:"))
async def cb_link_delete(cb: CallbackQuery):
    token = cb.data.split(":", 2)[2]
    link = await link_repo.get_by_token(token)
    if not link or link.owner_id != cb.from_user.id:
        await cb.answer("❌ این لینک متعلق به شما نیست.", show_alert=True)
        return
    await link_repo.delete(token)
    try:
        await cb.message.edit_text("🗑 لینک حذف شد.", reply_markup=None)
    except TelegramBadRequest:
        pass
    await cb.answer("✅ حذف شد.")


@user_router.callback_query(F.data.startswith("link:stats:"))
async def cb_link_stats(cb: CallbackQuery):
    token = cb.data.split(":", 2)[2]
    link = await link_repo.get_by_token(token)
    if not link or link.owner_id != cb.from_user.id:
        await cb.answer("❌ دسترسی ندارید.", show_alert=True)
        return
    type_label = "♾ دائمی" if link.link_type == "permanent" else "1️⃣ یکبارمصرف"
    status = "✅ سالم" if not link.is_used else "🔴 استفاده‌شده"
    await cb.answer(
        f"نوع: {type_label}\nوضعیت: {status}\nساخته شده: {link.created_at}",
        show_alert=True,
    )


@user_router.message(F.text == "📊 آمار من")
async def user_stats(message: Message):
    user = await user_repo.get_by_id(message.from_user.id)
    if not user:
        await message.answer("ابتدا /start بزنید.")
        return
    msg_count = await message_repo.count_for_owner(message.from_user.id)
    active = await link_repo.get_active_by_owner(message.from_user.id)
    perm = sum(1 for l in active if l.link_type == "permanent")
    once = sum(1 for l in active if l.link_type == "onetime")
    await message.answer(
        "📊 <b>آمار شما</b>\n\n"
        f"📨 پیام‌های دریافتی: <b>{msg_count}</b>\n"
        f"♾ لینک‌های دائمی: <b>{perm}</b>\n"
        f"1️⃣ لینک‌های یکبارمصرف: <b>{once}</b>\n"
        f"📅 عضویت از: <b>{user.created_at[:10]}</b>",
        reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID),
    )


@user_router.message(F.text == "⚙️ تنظیمات")
async def user_settings(message: Message):
    await message.answer(
        "⚙️ <b>تنظیمات</b>\n\nبه‌زودی امکانات بیشتری اضافه می‌شود.",
        reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID),
    )


@user_router.message(F.text == "🗑 حذف همه لینک‌ها")
async def user_delete_links(message: Message):
    count = await link_repo.delete_all_for_owner(message.from_user.id)
    await message.answer(
        f"🗑 <b>{count}</b> لینک حذف شد.",
        reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID),
    )


# ─── دریافت پیام ناشناس ───
@anon_router.message(AnonymousSendStates.waiting_message)
async def anon_receive(message: Message, state: FSMContext):
    content_type = "text"
    file_id = None
    content = None

    if message.text:
        content = sanitize_text(message.text)
    elif message.photo:
        content_type, file_id, content = "photo", message.photo[-1].file_id, message.caption
    elif message.voice:
        content_type, file_id, content = "voice", message.voice.file_id, message.caption
    elif message.video:
        content_type, file_id, content = "video", message.video.file_id, message.caption
    elif message.document:
        content_type, file_id, content = "document", message.document.file_id, message.caption
    else:
        await message.answer("⚠️ این نوع پیام پشتیبانی نمی‌شود. متن/عکس/ویس/ویدیو/فایل بفرست.")
        return

    await state.update_data(
        preview_type=content_type,
        preview_file_id=file_id,
        preview_content=content,
    )
    await state.set_state(AnonymousSendStates.confirm_send)
    await message.answer(
        "📝 <b>پیش‌نمایش پیام شما</b>\n\n"
        "آیا از ارسال مطمئن هستید؟",
        reply_markup=confirm_kb("anon_send"),
    )


@anon_router.callback_query(F.data == "cancel:anon_send")
async def anon_cancel_send(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.edit_text("❌ ارسال لغو شد.")
    except TelegramBadRequest:
        pass
    await cb.answer()


@anon_router.callback_query(F.data == "confirm:anon_send")
async def anon_confirm_send(cb: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    token = data.get("token")
    owner_id = data.get("owner_id")
    link_type = data.get("link_type", "onetime")
    content_type = data.get("preview_type", "text")
    content = data.get("preview_content")
    file_id = data.get("preview_file_id")

    if not token or not owner_id:
        await state.clear()
        await cb.answer("❌ اطلاعات ناقص است.", show_alert=True)
        return

    ok, link, error = await link_service.validate_link(token)
    if not ok:
        await state.clear()
        try:
            await cb.message.edit_text(f"❌ {error}")
        except TelegramBadRequest:
            pass
        await cb.answer()
        return

    result = await message_service.send_anonymous(
        bot=bot,
        owner_id=owner_id,
        sender_id=cb.from_user.id,
        token=token,
        content_type=content_type,
        content=content,
        file_id=file_id,
    )
    if not result["ok"]:
        await cb.answer(f"❌ {result['error']}", show_alert=True)
        return

    await link_service.consume_link(token, cb.from_user.id, link_type)
    await state.clear()

    thank = "✅ <b>پیام شما با موفقیت ارسال شد!</b>\n\n🙏 ممنون از استفاده شما."
    if link_type == "permanent":
        thank += "\n\n♾ این لینک همچنان فعال است."

    try:
        await cb.message.edit_text(thank)
    except TelegramBadRequest:
        await cb.message.answer(thank)
    await cb.answer("✅ ارسال شد.")


# ─── پنل ادمین ───
@admin_router.message(F.text == "👑 پنل ادمین")
async def admin_panel(message: Message):
    if message.from_user.id != Config.ADMIN_ID:
        await message.answer("⛔ دسترسی ندارید.")
        return
    await message.answer("👑 <b>پنل مدیریت</b>\n\nیک گزینه انتخاب کنید:", reply_markup=admin_menu_kb())


@admin_router.message(F.text == "◀️ بازگشت به منوی کاربر")
async def admin_back_to_user(message: Message):
    await message.answer("🏠 <b>منوی اصلی</b>", reply_markup=main_menu_kb(True))


@admin_router.message(F.text == "📊 آمار کلی")
async def admin_stats(message: Message):
    if message.from_user.id != Config.ADMIN_ID:
        return
    stats = await admin_service.get_stats()
    await message.answer(
        "📊 <b>آمار کلی ربات</b>\n\n"
        f"👥 کل کاربران: <b>{stats['users']}</b>\n"
        f"🚫 بن‌شده‌ها: <b>{stats['banned']}</b>\n"
        f"🔗 کل لینک‌ها: <b>{stats['links']}</b>\n"
        f"🟢 لینک‌های فعال: <b>{stats['active_links']}</b>\n"
        f"📨 کل پیام‌ها: <b>{stats['messages']}</b>\n"
        f"🔒 کانال اجباری: <b>{stats['required_channel']}</b>",
        reply_markup=admin_menu_kb(),
    )


@admin_router.message(F.text == "👥 کاربران")
async def admin_users(message: Message):
    if message.from_user.id != Config.ADMIN_ID:
        return
    users = await user_repo.get_all(limit=10)
    if not users:
        await message.answer("هیچ کاربری یافت نشد.", reply_markup=admin_menu_kb())
        return
    lines = ["👥 <b>آخرین ۱۰ کاربر</b>\n"]
    for u in users:
        status = "🚫" if u.is_banned else "✅"
        lines.append(f"{status} <code>{u.user_id}</code> — {u.full_name or '—'}")
    await message.answer("\n".join(lines), reply_markup=admin_menu_kb())


@admin_router.message(F.text == "📝 لاگ‌ها")
async def admin_logs(message: Message):
    if message.from_user.id != Config.ADMIN_ID:
        return
    logs = await admin_log_repo.recent(10)
    if not logs:
        await message.answer("لاگی موجود نیست.", reply_markup=admin_menu_kb())
        return
    lines = ["📝 <b>۱۰ لاگ آخر</b>\n"]
    for row in logs:
        lines.append(f"• [{row['created_at'][11:16]}] {row['action']} → {row['target_id'] or '-'}")
    await message.answer("\n".join(lines), reply_markup=admin_menu_kb())


@admin_router.message(F.text == "🗑 پاکسازی لینک‌های یکبارمصرف")
async def admin_cleanup(message: Message):
    if message.from_user.id != Config.ADMIN_ID:
        return
    count = await link_repo.cleanup_used_onetime()
    await admin_log_repo.log(Config.ADMIN_ID, "cleanup_links", None, f"حذف {count} لینک")
    await message.answer(
        f"🗑 <b>{count}</b> لینک یکبارمصرفِ استفاده‌شده حذف شد.",
        reply_markup=admin_menu_kb(),
    )


# ─── کانال اجباری ───
@admin_router.message(F.text == "🔒 کانال اجباری")
async def admin_channel_panel(message: Message):
    if message.from_user.id != Config.ADMIN_ID:
        return
    required = await settings_repo.get_required_channel()
    if required:
        text = (
            "🔒 <b>مدیریت کانال اجباری</b>\n\n"
            f"کانال فعلی: <code>{required}</code>\n\n"
            "کاربران برای استفاده از ربات باید در این کانال عضو باشند.\n"
            "برای تغییر یا حذف، از دکمه‌های زیر استفاده کنید."
        )
    else:
        text = (
            "🔒 <b>مدیریت کانال اجباری</b>\n\n"
            "❗ هیچ کانال اجباری تنظیم نشده است.\n"
            "با دکمه «🔧 تنظیم کانال» یک کانال تعیین کنید."
        )
    await message.answer(text, reply_markup=admin_channel_manage_kb(bool(required)))


@admin_router.callback_query(F.data == "admin_ch:set")
async def admin_ch_set(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("⛔", show_alert=True)
        return
    await state.set_state(AdminStates.setting_channel)
    text = (
        "🔧 <b>تنظیم کانال اجباری</b>\n\n"
        "یکی از این فرمت‌ها را ارسال کنید:\n"
        "• <code>@channel_username</code>\n"
        "• <code>https://t.me/channel_username</code>\n"
        "• <code>-1001234567890</code> (آیدی عددی)\n\n"
        "⚠️ <b>مهم:</b> ربات باید در آن کانال ادمین باشد.\n"
        "برای لغو: /cancel"
    )
    try:
        await cb.message.edit_text(text, reply_markup=cancel_kb("global:cancel"))
    except TelegramBadRequest:
        await cb.message.answer(text, reply_markup=cancel_kb("global:cancel"))
    await cb.answer()


@admin_router.callback_query(F.data == "admin_ch:remove")
async def admin_ch_remove(cb: CallbackQuery):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("⛔", show_alert=True)
        return
    await settings_repo.clear_required_channel()
    await admin_log_repo.log(Config.ADMIN_ID, "remove_required_channel", None, "")
    try:
        await cb.message.edit_text("🗑 کانال اجباری حذف شد.")
    except TelegramBadRequest:
        pass
    await cb.answer("✅ حذف شد.")


@admin_router.message(AdminStates.setting_channel)
async def admin_ch_receive(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id != Config.ADMIN_ID:
        return
    raw = (message.text or "").strip()
    parsed = parse_channel_input(raw)
    if not parsed:
        await message.answer(
            "❌ فرمت نامعتبر. مثال: <code>@mychannel</code> یا <code>https://t.me/mychannel</code>"
        )
        return

    # تست دسترسی ربات به کانال
    try:
        chat = await bot.get_chat(parsed)
        await bot.get_chat_member(chat_id=parsed, user_id=bot.id)
    except TelegramBadRequest as e:
        await message.answer(
            f"❌ خطا در دسترسی به کانال:\n<code>{e}</code>\n\n"
            "مطمئن شوید ربات در کانال ادمین است."
        )
        return

    await settings_repo.set_required_channel(parsed)
    await admin_log_repo.log(Config.ADMIN_ID, "set_required_channel", None, parsed)
    await state.clear()
    await message.answer(
        f"✅ کانال اجباری تنظیم شد:\n<b>{parsed}</b>\n\n"
        "از این به بعد کاربران باید ابتدا عضو این کانال شوند.",
        reply_markup=admin_menu_kb(),
    )


# ─── پیام همگانی ───
@admin_router.message(F.text == "📢 پیام همگانی")
async def admin_broadcast_start(message: Message, state: FSMContext):
    if message.from_user.id != Config.ADMIN_ID:
        return
    await state.set_state(AdminStates.broadcasting)
    await message.answer(
        "📢 <b>پیام همگانی</b>\n\nپیام خود را ارسال کنید.\nبرای لغو: /cancel",
        reply_markup=cancel_kb("global:cancel"),
    )


@admin_router.message(AdminStates.broadcasting)
async def admin_broadcast_receive(message: Message, state: FSMContext):
    await state.update_data(
        broadcast_chat_id=message.chat.id,
        broadcast_message_id=message.message_id,
    )
    await state.set_state(AdminStates.broadcasting_confirm)
    total = await user_repo.count_total()
    await message.answer(
        f"⚠️ آیا از ارسال به <b>{total}</b> کاربر مطمئن هستید؟",
        reply_markup=confirm_kb("broadcast"),
    )


@admin_router.callback_query(F.data == "cancel:broadcast")
async def admin_broadcast_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.edit_text("❌ ارسال همگانی لغو شد.")
    except TelegramBadRequest:
        pass
    await cb.answer()


@admin_router.callback_query(F.data == "confirm:broadcast")
async def admin_broadcast_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    chat_id = data.get("broadcast_chat_id")
    msg_id = data.get("broadcast_message_id")
    await state.clear()

    if not chat_id or not msg_id:
        await cb.answer("❌ اطلاعات پیام یافت نشد.", show_alert=True)
        return

    user_ids = await user_repo.all_ids()
    try:
        await cb.message.edit_text(f"⏳ در حال ارسال به {len(user_ids)} کاربر...")
    except TelegramBadRequest:
        pass

    result = await admin_service.broadcast(bot, chat_id, msg_id, user_ids)
    await admin_log_repo.log(
        Config.ADMIN_ID, "broadcast", None,
        f"موفق: {result['success']} ناموفق: {result['failed']}",
    )
    try:
        await cb.message.edit_text(
            "✅ <b>ارسال همگانی تمام شد</b>\n\n"
            f"✅ موفق: <b>{result['success']}</b>\n"
            f"❌ ناموفق: <b>{result['failed']}</b>"
        )
    except TelegramBadRequest:
        pass
    await cb.answer()


# ─── بن / آنبن ───
@admin_router.message(F.text == "🚫 مدیریت بن‌ها")
async def admin_ban_management(message: Message):
    if message.from_user.id != Config.ADMIN_ID:
        return
    await message.answer(
        "🚫 <b>مدیریت بن‌ها</b>\n\n"
        "برای بن کردن:\n<code>/ban USER_ID دلیل</code>\n\n"
        "برای آنبن:\n<code>/unban USER_ID</code>",
        reply_markup=admin_menu_kb(),
    )


@admin_router.message(Command("ban"))
async def admin_ban(message: Message, command: CommandObject):
    if message.from_user.id != Config.ADMIN_ID:
        return
    args = (command.args or "").split(maxsplit=1)
    if not args or not args[0].isdigit():
        await message.answer("⚠️ فرمت: <code>/ban USER_ID دلیل</code>")
        return
    target = int(args[0])
    reason = args[1] if len(args) > 1 else "بدون دلیل"
    await user_repo.ban(target, reason)
    await admin_log_repo.log(Config.ADMIN_ID, "ban", target, reason)
    await message.answer(f"🚫 کاربر <code>{target}</code> بن شد.\nدلیل: {reason}")


@admin_router.message(Command("unban"))
async def admin_unban(message: Message, command: CommandObject):
    if message.from_user.id != Config.ADMIN_ID:
        return
    args = (command.args or "").strip()
    if not args.isdigit():
        await message.answer("⚠️ فرمت: <code>/unban USER_ID</code>")
        return
    target = int(args)
    await user_repo.unban(target)
    await admin_log_repo.log(Config.ADMIN_ID, "unban", target, "")
    await message.answer(f"✅ کاربر <code>{target}</code> آنبن شد.")


@admin_router.callback_query(F.data == "admin:back")
async def admin_cb_back(cb: CallbackQuery):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("⛔", show_alert=True)
        return
    await cb.answer("بازگشت از طریق منوی پایین صفحه.")


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۱۲ — Scheduler
# ═══════════════════════════════════════════════════════════════════════

scheduler = AsyncIOScheduler()


async def job_cleanup_links():
    try:
        count = await link_repo.cleanup_used_onetime()
        if count:
            log.info("🧹 پاکسازی خودکار: %s لینک یکبارمصرف حذف شد.", count)
    except Exception as e:
        log.exception("خطا در پاکسازی: %s", e)


async def job_update_last_seen():
    try:
        await db.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP")
    except Exception as e:
        log.exception("خطا در last_seen: %s", e)


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۱۳ — Main
# ═══════════════════════════════════════════════════════════════════════

bot: Optional[Bot] = None
dp: Optional[Dispatcher] = None


async def on_startup(bot: Bot, **kwargs) -> None:
    """هوک استارت."""
    log.info("🚀 ربات در حال اجراست...")
    me = await bot.get_me()
    Config.BOT_USERNAME = me.username or Config.BOT_USERNAME
    log.info("🤖 Bot: @%s (id=%s)", me.username, me.id)
    log.info("👑 Admin ID: %s", Config.ADMIN_ID)

    required = await settings_repo.get_required_channel()
    log.info("🔒 کانال اجباری: %s", required or "تنظیم نشده")

    try:
        await bot.send_message(
            Config.ADMIN_ID,
            f"✅ ربات با موفقیت راه‌اندازی شد.\n@{me.username}"
        )
    except Exception as e:
        log.warning("ارسال پیام به ادمین ناموفق: %s", e)


async def on_shutdown(bot: Bot = None, **kwargs) -> None:
    """هوک خاموش شدن."""
    log.info("🛑 در حال خاموش کردن ربات...")
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception as e:
        log.warning("خطا در بستن scheduler: %s", e)
    await db.close()
    if bot is not None:
        try:
            await bot.session.close()
        except Exception as e:
            log.warning("خطا در بستن session: %s", e)
    log.info("✅ خاموش شد.")


async def main() -> None:
    global bot, dp

    # اعتبارسنجی تنظیمات
    Config.validate()
    await db.connect()

    bot = Bot(
        token=Config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # ── Middlewares (ترتیب مهم: JoinCheck قبل از BanCheck نباید باشد چون
    #    اول باید کاربر عضو باشد، ولی BanCheck اول اجرا می‌شود تا کاربر بن‌شده
    #    حتی اگر عضو کانال نبود، پیام بن ببیند) ──
    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())
    dp.message.middleware(JoinCheckMiddleware())
    dp.callback_query.middleware(JoinCheckMiddleware())
    dp.message.middleware(
        RateLimitMiddleware(Config.RATE_LIMIT_MESSAGES, Config.RATE_LIMIT_WINDOW)
    )

    # ── Routers ──
    dp.include_router(admin_router)
    dp.include_router(anon_router)
    dp.include_router(user_router)
    dp.include_router(common_router)

    # ── Scheduler ──
    scheduler.add_job(job_cleanup_links, "interval", hours=1, id="cleanup_links")
    scheduler.add_job(job_update_last_seen, "interval", minutes=5, id="update_last_seen")
    scheduler.start()
    log.info("⏰ زمان‌بند فعال شد.")

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        try:
            await on_shutdown(bot=bot)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("👋 برنامه متوقف شد.")
