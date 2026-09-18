"""
═══════════════════════════════════════════════════════════════════════
🧠 Anonymous AI Bot — v9.0 ULTRA
═══════════════════════════════════════════════════════════════════════
Architecture:
  • Layered: Config / Infra / Domain / Services / Handlers
  • Local AI moderation (Persian + English)
  • Gamification, Analytics, Smart-Match, Referral
  • Enterprise admin panel + health check + metrics
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import math
import os
import random
import re
import secrets
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from logging.handlers import RotatingFileHandler
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove,
)

try:
    from aiogram.enums import ButtonStyle
    STYLE_SUPPORTED = True
except ImportError:
    ButtonStyle = None  # type: ignore
    STYLE_SUPPORTED = False


# ═══════════════════════════════════════════════════════════════════════
# ۱ ── CONFIG
# ═══════════════════════════════════════════════════════════════════════

class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "8654406992:AAECfMfmYjc9_W8sFG-yNR78kASBh7CRMTs")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "8094551428"))
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "YourBot")
    DB_PATH: str = os.getenv("DB_PATH", "anon_v9.db")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production-please")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = "logs/bot_v9.log"
    HEALTH_PORT: int = int(os.getenv("HEALTH_PORT", "8080"))

    # Rate limiting (token bucket)
    RATE_CAPACITY: int = 30
    RATE_REFILL_PER_SEC: float = 0.5  # 30 per minute

    # Cache
    CACHE_SIZE: int = 10_000
    CACHE_TTL: int = 300

    # Moderation
    TOXICITY_THRESHOLD: float = 0.6
    SPAM_THRESHOLD: float = 0.7

    # XP
    XP_PER_MESSAGE_RECEIVED: int = 2
    XP_PER_MESSAGE_SENT: int = 1
    XP_PER_NEW_REFERRAL: int = 25
    XP_PER_DAY_ACTIVE: int = 5

    @classmethod
    def validate(cls):
        errs = []
        if not re.match(r"^\d+:[A-Za-z0-9_-]+$", cls.BOT_TOKEN):
            errs.append("BOT_TOKEN invalid")
        if cls.ADMIN_ID <= 0:
            errs.append("ADMIN_ID invalid")
        if len(cls.SECRET_KEY) < 16:
            errs.append("SECRET_KEY must be ≥16 chars")
        if errs:
            raise RuntimeError("\n".join(errs))


# ═══════════════════════════════════════════════════════════════════════
# ۲ ── LOGGING
# ═══════════════════════════════════════════════════════════════════════

def setup_logger() -> logging.Logger:
    os.makedirs(os.path.dirname(Config.LOG_FILE) or ".", exist_ok=True)
    logger = logging.getLogger("anon_v9")
    logger.setLevel(getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))
    logger.propagate = False
    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
                            "%Y-%m-%d %H:%M:%S")
    if not logger.handlers:
        fh = RotatingFileHandler(Config.LOG_FILE, maxBytes=10 * 1024 * 1024,
                                 backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger

log = setup_logger()


# ═══════════════════════════════════════════════════════════════════════
# ۳ ── TIME (Iran TZ)
# ═══════════════════════════════════════════════════════════════════════

IRAN_TZ = ZoneInfo("Asia/Tehran")
WEEKDAYS_FA = ["شنبه", "یک‌شنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"]
MONTHS_FA = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
             "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]


def now_iran() -> datetime:
    return datetime.now(IRAN_TZ)


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100
            + (gy2 + 399) // 400 + gd + g_d_m[gm - 1])
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def now_shamsi():
    n = now_iran()
    jy, jm, jd = gregorian_to_jalali(n.year, n.month, n.day)
    fa_wd = (n.weekday() + 2) % 7
    return jy, jm, jd, n.hour, n.minute, n.second, fa_wd


def fa_now_str() -> str:
    jy, jm, jd, hh, mm, ss, wd = now_shamsi()
    return f"🕐 {hh:02d}:{mm:02d}  |  📅 {WEEKDAYS_FA[wd]} {jd} {MONTHS_FA[jm-1]} {jy}"


def fa_now_str_full() -> str:
    jy, jm, jd, hh, mm, ss, wd = now_shamsi()
    return (f"🇮🇷 <b>ساعت ایران</b>\n"
            f"🕐 <code>{hh:02d}:{mm:02d}:{ss:02d}</code>\n"
            f"📅 {WEEKDAYS_FA[wd]} {jd} {MONTHS_FA[jm-1]} {jy}")


def with_footer(text: str) -> str:
    return f"{text}\n\n━━━━━━━━━━━━━━━━━━\n{fa_now_str()}"


# ═══════════════════════════════════════════════════════════════════════
# ۴ ── CACHE LAYER (TTL + LRU)
# ═══════════════════════════════════════════════════════════════════════

class TTLCache:
    def __init__(self, max_size: int = 10_000, default_ttl: int = 300):
        self._data: dict[str, tuple[Any, float]] = {}
        self._max = max_size
        self._ttl = default_ttl
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            item = self._data.get(key)
            if item is None:
                self._misses += 1
                return None
            value, exp = item
            if exp < time.monotonic():
                self._data.pop(key, None)
                self._misses += 1
                return None
            self._hits += 1
            return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        async with self._lock:
            if len(self._data) >= self._max:
                # evict oldest
                oldest = min(self._data.items(), key=lambda x: x[1][1])
                self._data.pop(oldest[0], None)
                self._evictions += 1
            self._data[key] = (value, time.monotonic() + (ttl or self._ttl))

    async def delete(self, key: str):
        async with self._lock:
            self._data.pop(key, None)

    async def flush(self):
        async with self._lock:
            self._data.clear()

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._data),
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate": round(self._hits / total, 3) if total else 0.0,
        }


cache = TTLCache(Config.CACHE_SIZE, Config.CACHE_TTL)


# ═══════════════════════════════════════════════════════════════════════
# ۵ ── SECURITY & CRYPTO
# ═══════════════════════════════════════════════════════════════════════

def generate_secure_token(length: int = 16) -> str:
    return secrets.token_urlsafe(length)


def sign_payload(data: str) -> str:
    sig = hmac.new(Config.SECRET_KEY.encode(), data.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{data}.{sig}"


def verify_payload(signed: str) -> Optional[str]:
    if "." not in signed:
        return None
    data, sig = signed.rsplit(".", 1)
    expected = hmac.new(Config.SECRET_KEY.encode(), data.encode(), hashlib.sha256).hexdigest()[:16]
    return data if hmac.compare_digest(sig, expected) else None


def hash_user_id(uid: int) -> str:
    return hashlib.sha256(f"{Config.SECRET_KEY}:{uid}".encode()).hexdigest()[:12]


# ═══════════════════════════════════════════════════════════════════════
# ۶ ── AI MODERATION ENGINE (Local)
# ═══════════════════════════════════════════════════════════════════════

class ModerationEngine:
    """
    موتور تحلیل محتوای محلی — کاملاً آفلاین.
    • Profanity detection (FA + EN)
    • Spam / URL flood detection
    • Sentiment analysis
    • Toxicity score (0..1)
    """

    # الفاظ رکیک انگلیسی (حداقلی — قابل توسعه)
    PROFANITY_EN = {
        "fuck", "fucking", "shit", "bitch", "asshole", "bastard",
        "cunt", "dick", "pussy", "whore", "slut", "nigger", "faggot",
    }

    # الگوهای فحش فارسی (regex)
    PROFANITY_FA_PATTERNS = [
        re.compile(r"ک[\u200c]?ی[\u200c]?ر", re.IGNORECASE),
        re.compile(r"ج[\u200c]?ا[\u200c]?ق", re.IGNORECASE),
        re.compile(r"خ[\u200c]?ر", re.IGNORECASE),
        re.compile(r"ع[\u200c]?و[\u200c]?ض", re.IGNORECASE),
        re.compile(r"م[\u200c]?ا[\u200c]?د[\u200c]?ر", re.IGNORECASE),
        re.compile(r"ل[\u200c]?ا[\u200c]?ط", re.IGNORECASE),
        re.compile(r"پ[\u200c]?ف[\u200c]?ت", re.IGNORECASE),
    ]

    URL_RE = re.compile(r"(https?://\S+|t\.me/\S+|@\w{4,})")
    REPEAT_RE = re.compile(r"(.)\1{7,}")
    PHONE_RE = re.compile(r"\b09\d{9}\b|\b\+98\d{10}\b")

    POSITIVE_WORDS = {
        "ممنون", "مرسی", "سپاس", "عالی", "خوب", "دوست", "دوستت", "عاشق",
        "thanks", "thank", "great", "love", "nice", "good", "awesome",
    }
    NEGATIVE_WORDS = {
        "بد", "زشت", "نفرت", "متنفر", "کثیف", "خسته", "ناراحت",
        "hate", "bad", "awful", "terrible", "suck", "ugly",
    }

    def analyze(self, text: str) -> dict:
        if not text:
            return self._empty()
        low = text.lower()
        flags: list[str] = []

        # Profanity
        prof_en = sum(1 for w in self.PROFANITY_EN if w in low)
        prof_fa = sum(1 for p in self.PROFANITY_FA_PATTERNS if p.search(text))
        prof_total = prof_en + prof_fa
        if prof_total:
            flags.append("profanity")

        # URLs / mentions
        urls = self.URL_RE.findall(text)
        if len(urls) >= 5:
            flags.append("url_flood")
        elif len(urls) >= 3:
            flags.append("url_many")

        # Phone numbers
        if self.PHONE_RE.search(text):
            flags.append("phone")

        # Repetition
        if self.REPEAT_RE.search(text):
            flags.append("repetition")

        # All caps (only for Latin)
        if len(text) > 15 and text.isascii() and text.isupper():
            flags.append("caps")

        # Sentiment
        pos = sum(1 for w in self.POSITIVE_WORDS if w in low)
        neg = sum(1 for w in self.NEGATIVE_WORDS if w in low)
        sentiment = 0.0
        if pos + neg > 0:
            sentiment = round((pos - neg) / (pos + neg), 3)

        # Toxicity
        toxicity = min(1.0, prof_total * 0.35 + (0.2 if "phone" in flags else 0))

        # Spam score
        spam = 0.0
        if "url_flood" in flags:
            spam += 0.6
        elif "url_many" in flags:
            spam += 0.3
        if "repetition" in flags:
            spam += 0.3
        if "caps" in flags:
            spam += 0.15
        spam = min(1.0, spam)

        return {
            "toxicity": round(toxicity, 3),
            "spam": round(spam, 3),
            "sentiment": sentiment,
            "flags": flags,
            "word_count": len(text.split()),
        }

    def _empty(self) -> dict:
        return {"toxicity": 0.0, "spam": 0.0, "sentiment": 0.0, "flags": [], "word_count": 0}

    def is_flagged(self, analysis: dict) -> bool:
        return (analysis["toxicity"] >= Config.TOXICITY_THRESHOLD or
                analysis["spam"] >= Config.SPAM_THRESHOLD)


moderation = ModerationEngine()


# ═══════════════════════════════════════════════════════════════════════
# ۷ ── GAMIFICATION
# ═══════════════════════════════════════════════════════════════════════

class Badges:
    EARLY_ADOPTER = ("🌱", "Early Adopter", "از اولین کاربران")
    CHATTER = ("💬", "Chatter", "بیش از 100 پیام")
    POPULAR = ("⭐", "Popular", "بیش از 50 پیام دریافتی")
    MATCHMAKER = ("🎯", "Matchmaker", "بیش از 20 مچ")
    SOCIAL = ("🤝", "Social", "بیش از 10 دعوت موفق")
    VERIFIED = ("✅", "Verified", "پروفایل کامل با آواتار سفارشی")

    ALL = [EARLY_ADOPTER, CHATTER, POPULAR, MATCHMAKER, SOCIAL, VERIFIED]


def level_from_xp(xp: int) -> int:
    """سطح = floor(sqrt(xp/100)) + 1"""
    return int(math.sqrt(max(0, xp) / 100)) + 1


def xp_for_level(lvl: int) -> int:
    return max(0, (lvl - 1) ** 2 * 100)


def progress_bar(current: int, total: int, width: int = 12) -> str:
    if total <= 0:
        return "▱" * width
    filled = min(width, int(width * current / total))
    return "▰" * filled + "▱" * (width - filled)


# ═══════════════════════════════════════════════════════════════════════
# ۸ ── DATABASE + MIGRATIONS
# ═══════════════════════════════════════════════════════════════════════

SCHEMA_VERSION = 3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    full_name TEXT,
    username TEXT,
    language TEXT DEFAULT 'fa',
    rules_accepted INTEGER DEFAULT 0,
    is_banned INTEGER DEFAULT 0,
    ban_reason TEXT,
    warn_count INTEGER DEFAULT 0,
    mute_until TIMESTAMP,
    message_count INTEGER DEFAULT 0,
    link_count INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    karma INTEGER DEFAULT 0,
    referrer_id INTEGER,
    referral_code TEXT UNIQUE,
    badges TEXT DEFAULT '[]',
    last_daily_bonus DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_referrer ON users(referrer_id);

CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER PRIMARY KEY,
    gender TEXT NOT NULL,
    age INTEGER NOT NULL,
    province TEXT NOT NULL,
    city TEXT NOT NULL,
    avatar_url TEXT,
    bio TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    web_mode INTEGER DEFAULT 0,
    silent_mode INTEGER DEFAULT 0,
    copyright_mode INTEGER DEFAULT 0,
    read_receipt INTEGER DEFAULT 1,
    auto_translate INTEGER DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS anonymous_links (
    token TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL,
    link_type TEXT NOT NULL DEFAULT 'onetime',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_used INTEGER DEFAULT 0,
    used_at TIMESTAMP,
    used_by INTEGER,
    use_count INTEGER DEFAULT 0,
    FOREIGN KEY(owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_links_owner ON anonymous_links(owner_id);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    sender_token TEXT,
    content TEXT,
    content_type TEXT DEFAULT 'text',
    file_id TEXT,
    toxicity REAL DEFAULT 0,
    sentiment REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_owner ON messages(owner_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);

CREATE TABLE IF NOT EXISTS target_chats (
    token TEXT PRIMARY KEY,
    creator_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pairings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user1_id INTEGER NOT NULL,
    user2_id INTEGER NOT NULL,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    target_id INTEGER,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_logs_action ON admin_logs(action);

CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    admin_id INTEGER NOT NULL,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id INTEGER NOT NULL,
    reported_id INTEGER,
    message_id INTEGER,
    reason TEXT,
    status TEXT DEFAULT 'pending',
    reviewed_by INTEGER,
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);

CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    badge TEXT NOT NULL,
    earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, badge)
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date DATE PRIMARY KEY,
    new_users INTEGER DEFAULT 0,
    messages_sent INTEGER DEFAULT 0,
    matches INTEGER DEFAULT 0,
    active_users INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rooms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    max_members INTEGER DEFAULT 10,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS room_members (
    room_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(room_id, user_id)
);

CREATE TABLE IF NOT EXISTS scheduled_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    content TEXT,
    content_type TEXT DEFAULT 'text',
    file_id TEXT,
    send_at TIMESTAMP NOT NULL,
    sent INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    _instance: Optional["Database"] = None
    _conn: Optional[aiosqlite.Connection] = None
    _lock: Optional[asyncio.Lock] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _lock_obj(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def connect(self):
        async with self._lock_obj():
            if self._conn is not None:
                return
            self._conn = await aiosqlite.connect(Config.DB_PATH)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.executescript(SCHEMA_SQL)
            await self._conn.commit()
            await self._run_migrations()
            log.info("✅ DB ready at %s (schema v%d)", Config.DB_PATH, SCHEMA_VERSION)

    async def _run_migrations(self):
        cur = await self._conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = await cur.fetchone()
        current = row["version"] if row else 0
        if current == 0:
            await self._conn.execute("INSERT INTO schema_version (version) VALUES (?)",
                                     (SCHEMA_VERSION,))
        elif current < SCHEMA_VERSION:
            log.info("🔧 Migrating DB from v%d → v%d", current, SCHEMA_VERSION)
            # future migration steps here
            await self._conn.execute("UPDATE schema_version SET version=?", (SCHEMA_VERSION,))
        await self._conn.commit()

    async def close(self):
        async with self._lock_obj():
            if self._conn is not None:
                try:
                    await self._conn.close()
                except Exception:
                    pass
                self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("DB not connected")
        return self._conn

    async def execute(self, q, p=()):
        cur = await self.conn.execute(q, p)
        await self.conn.commit()
        return cur

    async def fetch_one(self, q, p=()):
        cur = await self.conn.execute(q, p)
        row = await cur.fetchone()
        await cur.close()
        return row

    async def fetch_all(self, q, p=()):
        cur = await self.conn.execute(q, p)
        rows = await cur.fetchall()
        await cur.close()
        return list(rows)

    async def fetch_val(self, q, p=(), default=None):
        r = await self.fetch_one(q, p)
        if not r:
            return default
        return list(r)[0]


db = Database()


# ═══════════════════════════════════════════════════════════════════════
# ۹ ── REPOSITORIES
# ═══════════════════════════════════════════════════════════════════════

class UserRepo:
    async def create(self, uid, fn, un, referrer_id=None):
        code = secrets.token_urlsafe(8)
        await db.execute(
            """INSERT OR IGNORE INTO users (user_id, full_name, username, referral_code, referrer_id)
               VALUES (?,?,?,?,?)""",
            (uid, fn, un, code, referrer_id))

    async def get(self, uid):
        # cache hot user data
        cached = await cache.get(f"u:{uid}")
        if cached is not None:
            return cached
        r = await db.fetch_one("SELECT * FROM users WHERE user_id=?", (uid,))
        if r:
            await cache.set(f"u:{uid}", r, ttl=60)
        return r

    async def invalidate(self, uid):
        await cache.delete(f"u:{uid}")

    async def exists(self, uid) -> bool:
        return bool(await db.fetch_one("SELECT 1 FROM users WHERE user_id=?", (uid,)))

    async def update_profile(self, uid, fn, un):
        await db.execute(
            "UPDATE users SET full_name=?, username=?, last_seen=CURRENT_TIMESTAMP WHERE user_id=?",
            (fn, un, uid))
        await self.invalidate(uid)

    async def set_language(self, uid, lang):
        await db.execute("UPDATE users SET language=? WHERE user_id=?", (lang, uid))
        await self.invalidate(uid)

    async def set_rules_accepted(self, uid):
        await db.execute("UPDATE users SET rules_accepted=1 WHERE user_id=?", (uid,))
        await self.invalidate(uid)

    async def ban(self, uid, reason):
        await db.execute("UPDATE users SET is_banned=1, ban_reason=? WHERE user_id=?", (reason, uid))
        await self.invalidate(uid)

    async def unban(self, uid):
        await db.execute("UPDATE users SET is_banned=0, ban_reason=NULL WHERE user_id=?", (uid,))
        await self.invalidate(uid)

    async def add_warn(self, uid) -> int:
        await db.execute("UPDATE users SET warn_count=warn_count+1 WHERE user_id=?", (uid,))
        await self.invalidate(uid)
        return int(await db.fetch_val("SELECT warn_count FROM users WHERE user_id=?", (uid,), 0))

    async def clear_warns(self, uid):
        await db.execute("UPDATE users SET warn_count=0 WHERE user_id=?", (uid,))
        await self.invalidate(uid)

    async def mute(self, uid, minutes):
        until = (now_iran() + timedelta(minutes=minutes)).isoformat()
        await db.execute("UPDATE users SET mute_until=? WHERE user_id=?", (until, uid))
        await self.invalidate(uid)

    async def unmute(self, uid):
        await db.execute("UPDATE users SET mute_until=NULL WHERE user_id=?", (uid,))
        await self.invalidate(uid)

    async def is_muted(self, uid) -> tuple[bool, Optional[str]]:
        r = await db.fetch_one("SELECT mute_until FROM users WHERE user_id=?", (uid,))
        if not r or not r["mute_until"]:
            return False, None
        try:
            until = datetime.fromisoformat(r["mute_until"])
            if until.tzinfo is None:
                until = until.replace(tzinfo=IRAN_TZ)
            if now_iran() < until:
                return True, r["mute_until"]
        except Exception:
            pass
        return False, None

    async def add_xp(self, uid, amount: int) -> tuple[int, int, bool]:
        """returns (new_xp, new_level, leveled_up)"""
        cur = await db.fetch_one("SELECT xp, level FROM users WHERE user_id=?", (uid,))
        if not cur:
            return 0, 1, False
        new_xp = cur["xp"] + amount
        new_level = level_from_xp(new_xp)
        leveled = new_level > cur["level"]
        await db.execute("UPDATE users SET xp=?, level=? WHERE user_id=?",
                         (new_xp, new_level, uid))
        await self.invalidate(uid)
        return new_xp, new_level, leveled

    async def inc_msg(self, uid):
        await db.execute("UPDATE users SET message_count=message_count+1 WHERE user_id=?", (uid,))
        await self.invalidate(uid)

    async def inc_link(self, uid):
        await db.execute("UPDATE users SET link_count=link_count+1 WHERE user_id=?", (uid,))
        await self.invalidate(uid)

    async def all_ids(self):
        rows = await db.fetch_all("SELECT user_id FROM users WHERE is_banned=0")
        return [int(r["user_id"]) for r in rows]

    async def count(self) -> int:
        return int(await db.fetch_val("SELECT COUNT(*) FROM users", (), 0))

    async def count_banned(self) -> int:
        return int(await db.fetch_val("SELECT COUNT(*) FROM users WHERE is_banned=1", (), 0))

    async def count_today(self) -> int:
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM users WHERE date(created_at)=date('now')", (), 0))

    async def count_active_24h(self) -> int:
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM users WHERE datetime(last_seen) > datetime('now','-1 day')", (), 0))

    async def get_all(self, limit=10, offset=0):
        return await db.fetch_all(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))

    async def search(self, query: str, limit=10):
        q = f"%{query}%"
        return await db.fetch_all(
            """SELECT * FROM users WHERE CAST(user_id AS TEXT) LIKE ?
               OR full_name LIKE ? OR username LIKE ?
               ORDER BY last_seen DESC LIMIT ?""",
            (q, q, q, limit))

    async def set_referrer(self, uid, referrer_id):
        await db.execute("UPDATE users SET referrer_id=? WHERE user_id=?", (referrer_id, uid))
        await self.invalidate(uid)

    async def top_by_xp(self, limit=10):
        return await db.fetch_all(
            "SELECT user_id, full_name, xp, level FROM users WHERE is_banned=0 ORDER BY xp DESC LIMIT ?",
            (limit,))


class ProfileRepo:
    async def create(self, uid, gender, age, province, city, avatar):
        await db.execute(
            """INSERT INTO profiles (user_id, gender, age, province, city, avatar_url)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 gender=excluded.gender, age=excluded.age,
                 province=excluded.province, city=excluded.city,
                 avatar_url=excluded.avatar_url, updated_at=CURRENT_TIMESTAMP""",
            (uid, gender, age, province, city, avatar))

    async def get(self, uid):
        return await db.fetch_one("SELECT * FROM profiles WHERE user_id=?", (uid,))

    async def set_avatar(self, uid, avatar):
        await db.execute(
            "UPDATE profiles SET avatar_url=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
            (avatar, uid))


class UserSettingsRepo:
    async def ensure(self, uid):
        await db.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (uid,))

    async def get(self, uid):
        await self.ensure(uid)
        return await db.fetch_one("SELECT * FROM user_settings WHERE user_id=?", (uid,))

    async def toggle(self, uid, field_name):
        await self.ensure(uid)
        if field_name not in ("web_mode", "silent_mode", "copyright_mode",
                              "read_receipt", "auto_translate"):
            raise ValueError("invalid")
        await db.execute(
            f"UPDATE user_settings SET {field_name} = 1 - {field_name} WHERE user_id=?", (uid,))
        return int(await db.fetch_val(
            f"SELECT {field_name} FROM user_settings WHERE user_id=?", (uid,), 0))


class LinkRepo:
    async def create(self, token, owner, ltype):
        await db.execute(
            "INSERT INTO anonymous_links (token, owner_id, link_type) VALUES (?,?,?)",
            (token, owner, ltype))

    async def get(self, token):
        return await db.fetch_one("SELECT * FROM anonymous_links WHERE token=?", (token,))

    async def mark_used(self, token, user):
        await db.execute(
            """UPDATE anonymous_links
               SET is_used=1, used_at=CURRENT_TIMESTAMP, used_by=?,
                   use_count=use_count+1
               WHERE token=?""",
            (user, token))

    async def delete(self, token):
        await db.execute("DELETE FROM anonymous_links WHERE token=?", (token,))

    async def delete_all_owner(self, uid) -> int:
        c = await db.execute("DELETE FROM anonymous_links WHERE owner_id=?", (uid,))
        return c.rowcount or 0

    async def active_of_owner(self, uid):
        return await db.fetch_all(
            "SELECT * FROM anonymous_links WHERE owner_id=? ORDER BY created_at DESC", (uid,))

    async def count_active(self) -> int:
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM anonymous_links WHERE link_type='permanent' OR is_used=0",
            (), 0))

    async def count_total(self) -> int:
        return int(await db.fetch_val("SELECT COUNT(*) FROM anonymous_links", (), 0))

    async def cleanup_onetime(self) -> int:
        c = await db.execute(
            "DELETE FROM anonymous_links WHERE link_type='onetime' AND is_used=1")
        return c.rowcount or 0


class MessageRepo:
    async def create(self, owner, sender, token, content, ctype, fid, tox=0.0, sent=0.0):
        c = await db.execute(
            """INSERT INTO messages
               (owner_id, sender_id, sender_token, content, content_type, file_id, toxicity, sentiment)
               VALUES (?,?,?,?,?,?,?,?)""",
            (owner, sender, token, content, ctype, fid, tox, sent))
        return c.lastrowid or 0

    async def count_total(self) -> int:
        return int(await db.fetch_val("SELECT COUNT(*) FROM messages", (), 0))

    async def count_for(self, owner) -> int:
        return int(await db.fetch_val("SELECT COUNT(*) FROM messages WHERE owner_id=?", (owner,), 0))

    async def count_today(self) -> int:
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM messages WHERE date(created_at)=date('now')", (), 0))

    async def count_flagged_today(self) -> int:
        return int(await db.fetch_val(
            """SELECT COUNT(*) FROM messages
               WHERE date(created_at)=date('now') AND toxicity >= ?""",
            (Config.TOXICITY_THRESHOLD,), 0))


class TargetChatRepo:
    async def create(self, token, creator, target):
        await db.execute(
            "INSERT INTO target_chats (token, creator_id, target_id) VALUES (?,?,?)",
            (token, creator, target))

    async def get(self, token):
        return await db.fetch_one(
            "SELECT * FROM target_chats WHERE token=? AND active=1", (token,))

    async def deactivate(self, token):
        await db.execute("UPDATE target_chats SET active=0 WHERE token=?", (token,))


class PairingRepo:
    async def create(self, u1, u2) -> int:
        c = await db.execute("INSERT INTO pairings (user1_id, user2_id) VALUES (?,?)", (u1, u2))
        return c.lastrowid or 0

    async def active_for(self, uid):
        return await db.fetch_one(
            """SELECT * FROM pairings WHERE active=1 AND (user1_id=? OR user2_id=?)
               ORDER BY id DESC LIMIT 1""", (uid, uid))

    async def end(self, pid):
        await db.execute(
            "UPDATE pairings SET active=0, ended_at=CURRENT_TIMESTAMP WHERE id=?", (pid,))

    async def count_total(self) -> int:
        return int(await db.fetch_val("SELECT COUNT(*) FROM pairings", (), 0))

    async def count_active(self) -> int:
        return int(await db.fetch_val("SELECT COUNT(*) FROM pairings WHERE active=1", (), 0))


class AdminLogRepo:
    async def log(self, admin, action, target=None, details=""):
        await db.execute(
            "INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?,?,?,?)",
            (admin, action, target, details))

    async def recent(self, limit=15):
        return await db.fetch_all("SELECT * FROM admin_logs ORDER BY id DESC LIMIT ?", (limit,))

    async def search(self, query: str, limit=20):
        q = f"%{query}%"
        return await db.fetch_all(
            """SELECT * FROM admin_logs
               WHERE action LIKE ? OR details LIKE ? OR CAST(target_id AS TEXT) LIKE ?
               ORDER BY id DESC LIMIT ?""", (q, q, q, limit))


class WarningRepo:
    async def add(self, uid, admin_id, reason):
        await db.execute(
            "INSERT INTO warnings (user_id, admin_id, reason) VALUES (?,?,?)",
            (uid, admin_id, reason))

    async def list_for(self, uid, limit=10):
        return await db.fetch_all(
            "SELECT * FROM warnings WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit))

    async def clear(self, uid):
        await db.execute("DELETE FROM warnings WHERE user_id=?", (uid,))


class ReportRepo:
    async def create(self, reporter, reported, message_id, reason):
        c = await db.execute(
            """INSERT INTO reports (reporter_id, reported_id, message_id, reason)
               VALUES (?,?,?,?)""", (reporter, reported, message_id, reason))
        return c.lastrowid or 0

    async def pending(self, limit=20):
        return await db.fetch_all(
            "SELECT * FROM reports WHERE status='pending' ORDER BY id DESC LIMIT ?", (limit,))

    async def count_pending(self) -> int:
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM reports WHERE status='pending'", (), 0))

    async def mark(self, rid, status, admin):
        await db.execute(
            """UPDATE reports SET status=?, reviewed_by=?, reviewed_at=CURRENT_TIMESTAMP
               WHERE id=?""", (status, admin, rid))


class AchievementRepo:
    async def grant(self, uid, badge: str) -> bool:
        try:
            await db.execute(
                "INSERT INTO achievements (user_id, badge) VALUES (?,?)", (uid, badge))
            return True
        except aiosqlite.IntegrityError:
            return False

    async def list_for(self, uid):
        return await db.fetch_all(
            "SELECT badge, earned_at FROM achievements WHERE user_id=? ORDER BY earned_at DESC",
            (uid,))

    async def has(self, uid, badge) -> bool:
        return bool(await db.fetch_one(
            "SELECT 1 FROM achievements WHERE user_id=? AND badge=?", (uid, badge)))


class DailyStatsRepo:
    async def bump(self, field_name: str, amount: int = 1):
        if field_name not in ("new_users", "messages_sent", "matches", "active_users"):
            return
        today = now_iran().date().isoformat()
        await db.execute(
            f"""INSERT INTO daily_stats (date, {field_name}) VALUES (?, ?)
                ON CONFLICT(date) DO UPDATE SET {field_name} = {field_name} + ?""",
            (today, amount, amount))

    async def last_days(self, days=7):
        return await db.fetch_all(
            "SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?", (days,))


class RoomRepo:
    async def create(self, name, owner_id, max_members=10) -> str:
        rid = secrets.token_urlsafe(8)
        await db.execute(
            "INSERT INTO rooms (id, name, owner_id, max_members) VALUES (?,?,?,?)",
            (rid, name, owner_id, max_members))
        await db.execute(
            "INSERT OR IGNORE INTO room_members (room_id, user_id) VALUES (?,?)",
            (rid, owner_id))
        return rid

    async def get(self, rid):
        return await db.fetch_one("SELECT * FROM rooms WHERE id=? AND active=1", (rid,))

    async def members(self, rid):
        return await db.fetch_all(
            "SELECT user_id FROM room_members WHERE room_id=?", (rid,))

    async def join(self, rid, uid) -> bool:
        try:
            await db.execute(
                "INSERT OR IGNORE INTO room_members (room_id, user_id) VALUES (?,?)", (rid, uid))
            return True
        except Exception:
            return False

    async def leave(self, rid, uid):
        await db.execute(
            "DELETE FROM room_members WHERE room_id=? AND user_id=?", (rid, uid))

    async def count(self) -> int:
        return int(await db.fetch_val("SELECT COUNT(*) FROM rooms WHERE active=1", (), 0))


class ScheduledRepo:
    async def create(self, owner, sender, content, ctype, fid, send_at: datetime) -> int:
        c = await db.execute(
            """INSERT INTO scheduled_messages
               (owner_id, sender_id, content, content_type, file_id, send_at)
               VALUES (?,?,?,?,?,?)""",
            (owner, sender, content, ctype, fid, send_at.isoformat()))
        return c.lastrowid or 0

    async def due(self):
        return await db.fetch_all(
            """SELECT * FROM scheduled_messages
               WHERE sent=0 AND datetime(send_at) <= datetime('now') LIMIT 50""")

    async def mark_sent(self, sid):
        await db.execute("UPDATE scheduled_messages SET sent=1 WHERE id=?", (sid,))


class SettingsRepo:
    KEY_CH = "required_channel"
    KEY_MAINT = "maintenance"

    async def get(self, key):
        return await db.fetch_val("SELECT value FROM settings WHERE key=?", (key,))

    async def set(self, key, value):
        await db.execute(
            """INSERT INTO settings (key, value) VALUES (?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP""",
            (key, value))

    async def delete(self, key):
        await db.execute("DELETE FROM settings WHERE key=?", (key,))

    async def get_required_channel(self): return await self.get(self.KEY_CH)
    async def set_required_channel(self, ch): await self.set(self.KEY_CH, ch)
    async def clear_required_channel(self): await self.delete(self.KEY_CH)

    async def is_maintenance(self) -> bool:
        return (await self.get(self.KEY_MAINT)) == "1"

    async def set_maintenance(self, on: bool):
        await self.set(self.KEY_MAINT, "1" if on else "0")


user_repo = UserRepo()
profile_repo = ProfileRepo()
usettings_repo = UserSettingsRepo()
link_repo = LinkRepo()
message_repo = MessageRepo()
target_repo = TargetChatRepo()
pairing_repo = PairingRepo()
admin_log_repo = AdminLogRepo()
warning_repo = WarningRepo()
report_repo = ReportRepo()
achievement_repo = AchievementRepo()
stats_repo = DailyStatsRepo()
room_repo = RoomRepo()
scheduled_repo = ScheduledRepo()
settings_repo = SettingsRepo()


# ═══════════════════════════════════════════════════════════════════════
# ۱۰ ── STATIC DATA
# ═══════════════════════════════════════════════════════════════════════

IRAN_DATA: dict[str, list[str]] = {
    "آذربایجان شرقی": ["تبریز","مراغه","مرند","اهر","میانه","بناب","سراب","جلفا","آذرشهر","اسکو","شبستر","هریس","بستان‌آباد","هشترود","ملکان","عجب‌شیر","خداآفرین","ورزقان","کلیبر","هوراند"],
    "آذربایجان غربی": ["ارومیه","خوی","میاندوآب","مهاباد","بوکان","سلماس","پیرانشهر","نقده","اشنویه","شاهین‌دژ","ماکو","چالدران","پلدشت","شوط","تکاب","سردشت","کشاورز","مرگنلر","محمودآباد","نازک‌علیا"],
    "اردبیل": ["اردبیل","پارس‌آباد","مشگین‌شهر","خلخال","گرمی","بیله‌سوار","نمین","نیر","سرعین","کوثر","هیر","لاهرود","قصابه","رضی","فخرآباد","جعفرآباد","کیوی","عنبران","ابی‌بیگلو","اصلاندوز"],
    "اصفهان": ["اصفهان","کاشان","خمینی‌شهر","نجف‌آباد","شهرضا","شاهین‌شهر","فولادشهر","زرین‌شهر","آران و بیدگل","اردستان","نائین","سمیرم","فریدن","فریدون‌شهر","چادگان","خوانسار","گلپایگان","دهاقان","مبارکه","نطنز","نوش‌آباد","کوهپایه","هرند","ورزنه"],
    "البرز": ["کرج","فردیس","هشتگرد","نظرآباد","محمدشهر","ماهدشت","مشکین‌دشت","اشتهارد","گرمدره","کوهسار","طالقان","آسارا","کمال‌شهر"],
    "ایلام": ["ایلام","دهلران","آبدانان","مهران","دره‌شهر","ایوان","چرداول","ملکشاهی","بدره","سیروان","هلیلان","ارکواز","موسیان","دلگشا","ماژین","پهله","زرین‌آباد","لومار"],
    "بوشهر": ["بوشهر","برازجان","گناوه","دیر","کنگان","جم","عسلویه","خورموج","اهرم","دیلم","بندر ریگ","شنبه","کاکی","بردخون","دلوار","آبدان","ریز","سعدآباد","چغادک"],
    "تهران": ["تهران","شهریار","اسلامشهر","قدس","ملارد","پاکدشت","ورامین","پردیس","رباط‌کریم","فیروزکوه","دماوند","شمشک","لواسان","بومهن","رودهن","آبعلی","چهاردانگه","نسیم‌شهر","صباشهر","وحیدیه","باقرشهر","کهریزک","حسن‌آباد","جوادآباد","قرچک","پیشوا","شریف‌آباد","جاجرود","فشم","میگون"],
    "چهارمحال و بختیاری": ["شهرکرد","بروجن","فارسان","لردگان","سامان","بن","سفیددشت","هفشجان","کیار","اردل","دزپارت","فلارد","خانمیرزا","گندمان","بلداجی","نقنه","دستنا","وردنجان"],
    "خراسان جنوبی": ["بیرجند","قائن","فردوس","نهبندان","سربیشه","طبس","بشرویه","خوسف","درمیان","زیرکوه","سرایان","آیسک","اسدیه","حاجی‌آباد","مود","سده","خضری","نیمبلوک"],
    "خراسان رضوی": ["مشهد","نیشابور","سبزوار","تربت حیدریه","قوچان","کاشمر","گناباد","تربت جام","چناران","خواف","تایباد","بردسکن","درگز","سرخس","فریمان","جغتای","جوین","خلیل‌آباد","رشتخوار","زاوه","باخرز","بجستان","فیروزه","مه‌ولات","کوهسرخ","داورزن","صالح‌آباد","طرقبه","شاندیز","گلمکان"],
    "خراسان شمالی": ["بجنورد","شیروان","اسفراین","آشخانه","گرمه","جاجرم","فاروج","راز","صفی‌آباد","سنخواست","قاضی","لوجلی","حصارگرمخان","تیتکانلو","درق","زیارت"],
    "خوزستان": ["اهواز","آبادان","خرمشهر","دزفول","اندیمشک","بهبهان","ماهشهر","شوشتر","ایذه","شوش","مسجد سلیمان","رامهرمز","باغ‌ملک","امیدیه","هندیجان","لالی","هفتکل","آغاجاری","رامشیر","حمیدیه","دشت آزادگان","کارون","باوی","گتوند","کرخه","شادگان","هویزه","بستان","سوسنگرد","رفیع"],
    "زنجان": ["زنجان","ابهر","خرمدره","قیدار","صائین‌قلعه","ماه‌نشان","هیدج","صومعه","سجاس","چورزق","گرماب","ارمغانخانه","زری‌آباد","نوربهار","خدابنده"],
    "سمنان": ["سمنان","شاهرود","دامغان","گرمسار","مهدی‌شهر","میامی","بسطام","مجن","بیارجمند","رودیان","امیریه","ایوانکی","آرادان","کهن‌آباد","شهمیرزاد","درجزین"],
    "سیستان و بلوچستان": ["زاهدان","زابل","چابهار","ایرانشهر","سراوان","خاش","میرجاوه","نیک‌شهر","کنارک","زهک","هیرمند","قصرقند","سرباز","راسک","مهرستان","سیب و سوران","فنوج","بمپور","جالق","پیشین","بن‌جار","نصرت‌آباد","بزمان","محمدآباد"],
    "فارس": ["شیراز","مرودشت","کازرون","جهرم","فسا","داراب","لار","آباده","نی‌ریز","اقلید","سپیدان","استهبان","زرین‌دشت","خرامه","سروستان","کوار","فیروزآباد","قیر و کارزین","مهر","لامرد","خنج","گراش","اوز","جویم","بنارویه","بیرم","بالاده","کامفیروز","رونیز","ایج"],
    "قزوین": ["قزوین","الوند","تاکستان","آبیک","بوئین‌زهرا","محمدیه","آوج","شال","اسفرورین","ضیاءآباد","خرمدشت","نرجه","معلم‌کلایه","رازمیان","کوهین","بیدستان","شریفیه"],
    "قم": ["قم","قنوات","جعفریه","دستجرد","سلفچگان","کهک","خلجستان","راهجرد","ورجان","قاهان","فردو"],
    "کردستان": ["سنندج","سقز","مریوان","بانه","قروه","بیجار","کامیاران","دیواندره","دهگلان","سروآباد","چناره","شویشه","مالوجه","زرینه","دلبران","بابارشانی"],
    "کرمان": ["کرمان","رفسنجان","سیرجان","جیرفت","بم","زرند","کهنوج","بردسیر","شهربابک","انار","ریگان","فهرج","منوجان","رودبار جنوب","قلعه‌گنج","عنبرآباد","فاریاب","ارزوئیه","راور","کوهبنان","رابر","بافت","نرماشیر","گلباف","شهداد","ماهان","چترود","نجف‌شهر","خواجو"],
    "کرمانشاه": ["کرمانشاه","اسلام‌آباد غرب","هرسین","کنگاور","سنقر","پاوه","جوانرود","صحنه","قصر شیرین","گیلانغرب","سرپل ذهاب","روانسر","دالاهو","ثلاث باباجانی","باینگان","نوسود","ازگله","کرند غرب","رباط","بیستون","ماهیدشت"],
    "کهگیلویه و بویراحمد": ["یاسوج","دوگنبدان","دهدشت","سی‌سخت","لیکک","چرام","باشت","مارگون","دنا","لنده","سوق","قلعه رئیسی","پاتاوه","سرفاریاب"],
    "گلستان": ["گرگان","گنبد کاووس","علی‌آباد کتول","بندر ترکمن","آق‌قلا","کردکوی","مینودشت","آزادشهر","رامیان","مراوه‌تپه","گمیشان","بندر گز","نوکنده","خالدنبی","اینچه‌برون","دلند","فاضل‌آباد","سیمین‌شهر","نگین‌شهر"],
    "گیلان": ["رشت","انزلی","لاهیجان","لنگرود","آستارا","تالش","رودسر","فومن","صومعه‌سرا","رودبار","آستانه اشرفیه","املش","رضوانشهر","ماسال","شفت","سیاهکل","خمام","منجیل","لوشان","بره‌سر","کومله","چابکسر","واجارگاه"],
    "لرستان": ["خرم‌آباد","بروجرد","دورود","الیگودرز","کوهدشت","نورآباد","ازنا","پل‌دختر","چگنی","رومشکان","سلسله","دلفان","معمولان","بی‌بی‌سید","اشترینان"],
    "مازندران": ["ساری","بابل","آمل","قائم‌شهر","بهشهر","چالوس","نوشهر","تنکابن","رامسر","نکا","جویبار","فریدونکنار","محمودآباد","نور","عباس‌آباد","گلوگاه","کلاردشت","پل سفید","سوادکوه","زیراب","شیرگاه","بلده","کجور"],
    "مرکزی": ["اراک","ساوه","خمین","محلات","دلیجان","تفرش","شازند","زرندیه","کمیجان","آشتیان","فرمهین","خنداب","مأمونیه","غرق‌آباد","پرندک","نراق","جاسب"],
    "هرمزگان": ["بندرعباس","میناب","بندر لنگه","قشم","کیش","بندر خمیر","حاجی‌آباد","رودان","بستک","پارسیان","جاسک","سیریک","ابوموسی","بندر جاسک","گاوبندی","کوهستک","هشتبندی"],
    "همدان": ["همدان","ملایر","نهاوند","تویسرکان","اسدآباد","بهار","کبودراهنگ","رزن","فامنین","لالجین","مریانج","جورقان","قهاوند","دمق","سامن","برزول","فیروزان","گل‌تپه"],
    "یزد": ["یزد","میبد","اردکان","بافق","مهریز","ابرکوه","تفت","اشکذر","خاتم","بهاباد","مروست","هرات","زارچ","شاهدیه","حمیدیا","ندوشن","نیر","عقدا"],
}
PROVINCES = list(IRAN_DATA.keys())
ALL_AGES = list(range(9, 100))


# ═══════════════════════════════════════════════════════════════════════
# ۱۱ ── AVATAR
# ═══════════════════════════════════════════════════════════════════════

def avatar_url(gender: str, seed: int | str, size: int = 512) -> str:
    base = f"https://api.dicebear.com/9.x/avataaars/png?seed={seed}"
    common = ("&mouth=smile,twinkle&eyes=happy,default,squint"
              "&eyebrow=default,defaultNatural,raisedExcited,raisedExcitedNatural,upDown"
              "&nose=default&facialHairProbability=0"
              "&skinColor=edb98a,d08b5b,ae5d29,614335,ffdbb4"
              f"&style=circle&size={size}")
    if gender == "male":
        return (f"{base}{common}"
                "&top=shortFlat,shortRound,shortWaved,shortCurly,shortDreads,theCaesar,shortShaggy,sides"
                "&hairColor=2c1b18,4a312c,724133,a55728,b58143,d6b370"
                "&clothing=blazerAndShirt,blazerAndSweater,graphicShirt,hoodie,shirtCrewNeck,shirtVNeck"
                "&clothingColor=262e33,3c4f5c,65c9ff,5199e4,25557c,929598"
                "&accessories=prescription01,prescription02,round,wayfarers"
                "&accessoriesColor=262e33,3c4f5c,25557c&accessoriesProbability=18"
                "&backgroundColor=b6e3f4,c0aede,d1d4f9,ffd5dc,ffdfbf")
    elif gender == "female":
        return (f"{base}{common}"
                "&top=bigHair,bob,bun,curly,curvy,frida,fro,froBand,longButNotTooLong,miaWallace,straight01,straight02"
                "&hairColor=2c1b18,4a312c,724133,a55728,b58143,d6b370,ff5c5c,ff9c9c,ffd5dc"
                "&clothing=blazerAndShirt,collarAndSweater,graphicShirt,hoodie,shirtCrewNeck,shirtScoopNeck,shirtVNeck"
                "&clothingColor=ff5c5c,ff9c9c,ffb0b0,ffd5dc,c0aede,d1d4f9,b6e3f4"
                "&accessories=prescription01,prescription02,round"
                "&accessoriesColor=262e33,3c4f5c,25557c,ff5c5c&accessoriesProbability=22"
                "&backgroundColor=ffd5dc,ffdfbf,c0aede,d1d4f9,b6e3f4")
    return (f"{base}{common}&top=shortFlat,shortRound,bob,curly,fro"
            "&clothing=graphicShirt,hoodie,shirtCrewNeck"
            "&clothingColor=d1d4f9,b6e3f4,c0aede&accessoriesProbability=10"
            "&backgroundColor=d1d4f9,b6e3f4,c0aede")


def is_custom_avatar(a: str) -> bool:
    return bool(a) and a.startswith("file:")


def extract_file_id(a: str) -> str:
    return a[5:] if is_custom_avatar(a) else a


# ═══════════════════════════════════════════════════════════════════════
# ۱۲ ── RULES
# ═══════════════════════════════════════════════════════════════════════

RULES_FA = """📜 <b>قوانین و شرایط استفاده</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>1️⃣ رفتار محترمانه</b>
• هرگونه توهین، فحاشی، تهمت ممنوع است.

<b>2️⃣ محتوای مجاز</b>
• محتوای مستهجن، خشونت‌آمیز، غیرقانونی ممنوع است.
• تبلیغات و اسپم بدون اجازه ممنوع است.

<b>3️⃣ حریم خصوصی</b>
• هویت فرستنده محفوظ است.
• انتشار اطلاعات شخصی دیگران ممنوع است.

<b>4️⃣ آزار و اذیت</b>
• آزار، تهدید، باج‌گیری = <b>بن دائمی</b>.

<b>5️⃣ سن</b>
• زیر ۱۳ سال ممنوع.

<b>6️⃣ مسئولیت</b>
• مسئولیت محتوا بر عهده کاربر است.

━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ با زدن دکمه «✅ قوانین را می‌پذیرم»، تأیید می‌کنید تمام قوانین را خوانده و پذیرفته‌اید.
"""


# ═══════════════════════════════════════════════════════════════════════
# ۱۳ ── KEYBOARDS
# ═══════════════════════════════════════════════════════════════════════

def _ibtn(t, style=None, **kw):
    if STYLE_SUPPORTED and style is not None:
        return InlineKeyboardButton(text=t, style=style, **kw)
    return InlineKeyboardButton(text=t, **kw)


def _btn(t, style=None, **kw):
    if STYLE_SUPPORTED and style is not None:
        return KeyboardButton(text=t, style=style, **kw)
    return KeyboardButton(text=t, **kw)


S_PRIMARY = ButtonStyle.PRIMARY if STYLE_SUPPORTED else None
S_SUCCESS = ButtonStyle.SUCCESS if STYLE_SUPPORTED else None
S_DANGER = ButtonStyle.DANGER if STYLE_SUPPORTED else None


def language_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("🇮🇷 فارسی", S_PRIMARY, callback_data="lang:fa")],
        [_ibtn("🇬🇧 English", S_PRIMARY, callback_data="lang:en")],
        [_ibtn("🇸🇦 العربية", S_PRIMARY, callback_data="lang:ar")],
    ])


def rules_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("✅ قوانین را می‌پذیرم", S_SUCCESS, callback_data="rules:accept")],
        [_ibtn("❌ انصراف", S_DANGER, callback_data="rules:decline")],
    ])


def main_menu_kb(is_admin=False):
    kb = [
        [_btn("🔗 دریافت لینک ناشناس", S_PRIMARY), _btn("🎭 اتصال به ناشناس", S_PRIMARY)],
        [_btn("👤 اتصال به مخاطب خاص", S_PRIMARY), _btn("👥 اتاق گروهی", S_PRIMARY)],
        [_btn("🎖 سطح من", S_SUCCESS), _btn("🏆 لیدربورد", S_SUCCESS)],
        [_btn("📊 آمار من", S_PRIMARY), _btn("⚙️ تنظیمات", S_PRIMARY)],
        [_btn("👤 پروفایل من", S_PRIMARY), _btn("🕐 ساعت", S_PRIMARY)],
        [_btn("🎁 دعوت دوستان", S_SUCCESS), _btn("📜 قوانین", S_PRIMARY)],
    ]
    if is_admin:
        kb.append([_btn("👑 پنل ادمین", S_SUCCESS)])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def admin_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [_btn("📊 داشبورد", S_PRIMARY), _btn("📈 آنالیتیکس", S_PRIMARY)],
        [_btn("👥 کاربران", S_PRIMARY), _btn("🔍 جستجو", S_PRIMARY)],
        [_btn("🚨 گزارش‌ها", S_DANGER), _btn("⚠️ اخطارها", S_DANGER)],
        [_btn("🚫 بن‌ها", S_DANGER), _btn("🔇 سکوت‌ها", S_DANGER)],
        [_btn("📢 پیام همگانی", S_PRIMARY), _btn("📨 پیام به کاربر", S_PRIMARY)],
        [_btn("🔒 کانال", S_PRIMARY), _btn("🔧 تعمیر", S_PRIMARY)],
        [_btn("💾 بکاپ", S_SUCCESS), _btn("🧹 پاکسازی", S_DANGER)],
        [_btn("📝 لاگ‌ها", S_PRIMARY), _btn("◀️ بازگشت", S_PRIMARY)],
    ], resize_keyboard=True)


def cancel_kb(cb="global:cancel"):
    return InlineKeyboardMarkup(inline_keyboard=[[_ibtn("❌ لغو", S_DANGER, callback_data=cb)]])


def confirm_kb(action):
    return InlineKeyboardMarkup(inline_keyboard=[[
        _ibtn("✅ بله", S_SUCCESS, callback_data=f"confirm:{action}"),
        _ibtn("❌ انصراف", S_DANGER, callback_data=f"cancel:{action}")]])


def gender_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("👨 پسر", S_PRIMARY, callback_data="pf:gender:male")],
        [_ibtn("👩 دختر", S_PRIMARY, callback_data="pf:gender:female")],
        [_ibtn("❌ لغو", S_DANGER, callback_data="global:cancel")]])


AGES_PER_PAGE = 25
AGES_COLS = 5


def age_grid_kb(page: int = 0) -> InlineKeyboardMarkup:
    start = page * AGES_PER_PAGE
    end = min(start + AGES_PER_PAGE, len(ALL_AGES))
    chunk = ALL_AGES[start:end]
    rows = []
    for i in range(0, len(chunk), AGES_COLS):
        rows.append([_ibtn(str(a), S_PRIMARY, callback_data=f"pf:age:{a}")
                     for a in chunk[i:i + AGES_COLS]])
    nav = []
    if page > 0:
        nav.append(_ibtn("◀️", S_PRIMARY, callback_data=f"pf:age_page:{page-1}"))
    if end < len(ALL_AGES):
        nav.append(_ibtn("▶️", S_PRIMARY, callback_data=f"pf:age_page:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([_ibtn("❌ لغو", S_DANGER, callback_data="global:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def provinces_kb(page: int = 0):
    per_page = 8
    total = len(PROVINCES)
    start = page * per_page
    end = min(start + per_page, total)
    rows = [[_ibtn(p, S_PRIMARY, callback_data=f"pf:prov:{p}")] for p in PROVINCES[start:end]]
    nav = []
    if page > 0:
        nav.append(_ibtn("◀️", S_PRIMARY, callback_data=f"pf:prov_page:{page-1}"))
    if end < total:
        nav.append(_ibtn("▶️", S_PRIMARY, callback_data=f"pf:prov_page:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([_ibtn("❌ لغو", S_DANGER, callback_data="global:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cities_kb(province: str, page: int = 0):
    cities = IRAN_DATA.get(province, [])
    per_page = 8
    total = len(cities)
    start = page * per_page
    end = min(start + per_page, total)
    rows = [[_ibtn(c, S_PRIMARY, callback_data=f"pf:city:{c}")] for c in cities[start:end]]
    nav = []
    if page > 0:
        nav.append(_ibtn("◀️", S_PRIMARY, callback_data=f"pf:city_page:{page-1}"))
    if end < total:
        nav.append(_ibtn("▶️", S_PRIMARY, callback_data=f"pf:city_page:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([_ibtn("◀️ استان‌ها", S_PRIMARY, callback_data="pf:back_prov")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def avatar_edit_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📸 آپلود عکس", S_SUCCESS, callback_data="av:upload")],
        [_ibtn("🎲 تصادفی جدید", S_PRIMARY, callback_data="av:random")],
        [_ibtn("◀️ بازگشت", S_PRIMARY, callback_data="av:back")]])


def link_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("♾ دائمی", S_PRIMARY, callback_data="linktype:permanent")],
        [_ibtn("1️⃣ یکبارمصرف", S_SUCCESS, callback_data="linktype:onetime")],
        [_ibtn("❌ لغو", S_DANGER, callback_data="global:cancel")]])


def link_actions_kb(token):
    share = f"https://t.me/share/url?url=https://t.me/{Config.BOT_USERNAME}?start={token}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📤 اشتراک‌گذاری", S_SUCCESS, url=share)],
        [_ibtn("🗑 حذف", S_DANGER, callback_data=f"link:del:{token}")]])


def settings_kb(s):
    def m(v): return "🟢" if v else "⚪"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn(f"{m(s['web_mode'])} حالت وب", S_PRIMARY, callback_data="uset:toggle:web_mode")],
        [_ibtn(f"{m(s['silent_mode'])} سایلنت", S_PRIMARY, callback_data="uset:toggle:silent_mode")],
        [_ibtn(f"{m(s['copyright_mode'])} کپی‌رایت", S_PRIMARY, callback_data="uset:toggle:copyright_mode")],
        [_ibtn(f"{m(s['read_receipt'])} اعلان مشاهده", S_PRIMARY, callback_data="uset:toggle:read_receipt")],
        [_ibtn(f"{m(s['auto_translate'])} ترجمه خودکار", S_PRIMARY, callback_data="uset:toggle:auto_translate")],
    ])


def match_menu_kb(filters):
    g = {"male": "👨", "female": "👩", "any": "🤷"}[filters["gender"]]
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("🔍 شروع جستجو", S_SUCCESS, callback_data="match:start")],
        [_ibtn(f"🎂 سن: {filters['min_age']}-{filters['max_age']}", S_PRIMARY, callback_data="filter:age")],
        [_ibtn(f"🎭 جنسیت: {g}", S_PRIMARY, callback_data="filter:gender")],
        [_ibtn(f"🏙 همشهری: {'🟢' if filters['same_city'] else '⚪'}", S_PRIMARY, callback_data="filter:city")],
        [_ibtn("❌ لغو", S_DANGER, callback_data="global:cancel")]])


def filter_gender_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("👨 پسر", S_PRIMARY, callback_data="filter:gender:male")],
        [_ibtn("👩 دختر", S_PRIMARY, callback_data="filter:gender:female")],
        [_ibtn("🤷 فرقی ندارد", S_PRIMARY, callback_data="filter:gender:any")],
        [_ibtn("◀️ بازگشت", S_PRIMARY, callback_data="filter:menu")]])


def target_chat_kb(token):
    share = (f"https://t.me/share/url?url=https://t.me/{Config.BOT_USERNAME}?start=tc_{token}"
             f"&text=یک پیام ناشناس برایت دارم")
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📤 اشتراک‌گذاری", S_SUCCESS, url=share)],
        [_ibtn("🗑 لغو", S_DANGER, callback_data=f"tc:cancel:{token}")]])


def join_channel_kb(url):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📢 عضویت", S_PRIMARY, url=url)],
        [_ibtn("✅ بررسی", S_SUCCESS, callback_data="check_join")]])


def admin_channel_manage_kb(has):
    rows = [[_ibtn("🔧 تنظیم کانال", S_PRIMARY, callback_data="admin_ch:set")]]
    if has:
        rows.append([_ibtn("🗑 حذف کانال", S_DANGER, callback_data="admin_ch:remove")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_actions_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("🚫 بن", S_DANGER, callback_data=f"adm:ban:{uid}"),
         _ibtn("✅ آنبن", S_SUCCESS, callback_data=f"adm:unban:{uid}")],
        [_ibtn("⚠️ اخطار", S_DANGER, callback_data=f"adm:warn:{uid}"),
         _ibtn("🔇 سکوت ۱س", S_DANGER, callback_data=f"adm:mute:{uid}")],
        [_ibtn("🔊 رفع سکوت", S_SUCCESS, callback_data=f"adm:unmute:{uid}")],
        [_ibtn("📨 پیام", S_PRIMARY, callback_data=f"adm:msg:{uid}")],
        [_ibtn("🗑 پاک اخطار", S_DANGER, callback_data=f"adm:clearwarn:{uid}")]]) 


def report_review_kb(rid, uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("✅ تأیید تخلف", S_SUCCESS, callback_data=f"rep:ok:{rid}:{uid}"),
         _ibtn("❌ رد", S_DANGER, callback_data=f"rep:no:{rid}:{uid}")]])


def room_kb(rid):
    share = f"https://t.me/{Config.BOT_USERNAME}?start=room_{rid}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📤 دعوت به اتاق", S_SUCCESS, url=f"https://t.me/share/url?url={share}")],
        [_ibtn("🚪 خروج از اتاق", S_DANGER, callback_data=f"room:leave:{rid}")]])


# ═══════════════════════════════════════════════════════════════════════
# ۱۴ ── STATES
# ═══════════════════════════════════════════════════════════════════════

class LangStates(StatesGroup):
    choosing = State()


class RulesStates(StatesGroup):
    showing = State()


class ProfileStates(StatesGroup):
    gender = State()
    age = State()
    province = State()
    city = State()


class AvatarStates(StatesGroup):
    uploading = State()


class LinkStates(StatesGroup):
    choosing_type = State()


class AnonymousStates(StatesGroup):
    waiting_message = State()
    confirm_send = State()
    schedule_time = State()


class TargetChatStates(StatesGroup):
    waiting_target = State()
    chat_active = State()


class TargetCreatorStates(StatesGroup):
    chatting = State()


class MatchStates(StatesGroup):
    configuring = State()
    searching = State()
    chatting = State()


class RoomStates(StatesGroup):
    creating = State()
    joining = State()
    chatting = State()


class AdminStates(StatesGroup):
    broadcasting = State()
    broadcasting_confirm = State()
    setting_channel = State()
    searching_user = State()
    sending_to_user = State()


# ═══════════════════════════════════════════════════════════════════════
# ۱۵ ── MIDDLEWARES
# ═══════════════════════════════════════════════════════════════════════

class TokenBucket:
    """Per-user token bucket rate limiter."""
    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.refill = refill_per_sec
        self._buckets: dict[int, tuple[float, float]] = {}
        self._lock = asyncio.Lock()

    async def consume(self, uid: int, cost: float = 1.0) -> tuple[bool, float]:
        async with self._lock:
            now = time.monotonic()
            tokens, last = self._buckets.get(uid, (float(self.capacity), now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill)
            if tokens >= cost:
                self._buckets[uid] = (tokens - cost, now)
                return True, tokens - cost
            self._buckets[uid] = (tokens, now)
            return False, tokens


rate_limiter = TokenBucket(Config.RATE_CAPACITY, Config.RATE_REFILL_PER_SEC)


class BanCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        uid = None
        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            uid = event.from_user.id
        if uid and uid != Config.ADMIN_ID:
            u = await user_repo.get(uid)
            if u and u["is_banned"]:
                reason = u["ban_reason"] or "بدون دلیل"
                if isinstance(event, Message):
                    await event.answer(f"🚫 شما بن شده‌اید.\nدلیل: {reason}")
                else:
                    await event.answer("🚫 بن هستید.", show_alert=True)
                return None
            muted, until = await user_repo.is_muted(uid)
            if muted:
                if isinstance(event, Message):
                    await event.answer(f"🔇 تا {until[:16]} سکوت هستید.")
                else:
                    await event.answer("🔇 سکوت.", show_alert=True)
                return None
        if uid:
            data["user_id"] = uid
        return await handler(event, data)


async def check_membership(bot, channel, uid):
    try:
        m = await bot.get_chat_member(chat_id=channel, user_id=uid)
        return m.status not in ("left", "kicked")
    except Exception:
        return True


class JoinCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        bot: Bot = data.get("bot")
        uid = None
        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            uid = event.from_user.id
        if not uid or uid == Config.ADMIN_ID:
            return await handler(event, data)

        if await settings_repo.is_maintenance():
            if isinstance(event, Message):
                await event.answer("🔧 ربات در حال تعمیر است.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🔧 در تعمیر.", show_alert=True)
            return None

        required = await settings_repo.get_required_channel()
        if not required:
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data == "check_join":
            ok = await check_membership(bot, required, uid)
            await event.answer("✅ تأیید شد!" if ok else "❌ هنوز عضو نیستید!", show_alert=True)
            return None

        if await check_membership(bot, required, uid):
            return await handler(event, data)

        if required.startswith("@"):
            url = f"https://t.me/{required.lstrip('@')}"
        else:
            try:
                url = await bot.export_chat_invite_link(required)
            except Exception:
                url = "https://t.me/"
        text = f"🔒 <b>ورود محدود!</b>\n\nبرای استفاده ابتدا عضو کانال زیر شوید:\n\n📢 <b>{required}</b>"
        try:
            if isinstance(event, Message):
                await event.answer(text, reply_markup=join_channel_kb(url))
            else:
                await event.message.answer(text, reply_markup=join_channel_kb(url))
                await event.answer()
        except Exception:
            pass
        return None


class RateLimitMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
            if uid != Config.ADMIN_ID:
                state = data.get("state")
                skip_states = {
                    AnonymousStates.waiting_message.state,
                    MatchStates.chatting.state,
                    TargetChatStates.chat_active.state,
                    TargetCreatorStates.chatting.state,
                    RoomStates.chatting.state,
                }
                cur_state = None
                if state is not None:
                    try:
                        cur_state = await state.get_state()
                    except Exception:
                        pass
                if cur_state not in skip_states:
                    ok, _ = await rate_limiter.consume(uid, 1.0)
                    if not ok:
                        await event.answer("⏳ خیلی سریع! کمی صبر کن.")
                        return None
        return await handler(event, data)


# ═══════════════════════════════════════════════════════════════════════
# ۱۶ ── SERVICES
# ═══════════════════════════════════════════════════════════════════════

class LinkService:
    async def create(self, owner, ltype="onetime"):
        if ltype not in ("permanent", "onetime"):
            return {"ok": False, "error": "نوع نامعتبر"}
        token = generate_secure_token()
        while await link_repo.get(token):
            token = generate_secure_token()
        await link_repo.create(token, owner, ltype)
        await user_repo.inc_link(owner)
        return {"ok": True, "token": token, "type": ltype,
                "link": f"https://t.me/{Config.BOT_USERNAME}?start={token}"}

    async def validate(self, token):
        if not token or len(token) < 10:
            return False, None, "توکن نامعتبر"
        link = await link_repo.get(token)
        if not link:
            return False, None, "لینک وجود ندارد"
        if link["link_type"] == "onetime" and link["is_used"]:
            return False, None, "استفاده شده"
        return True, link, ""

    async def consume(self, token, uid, ltype):
        if ltype == "onetime":
            await link_repo.mark_used(token, uid)


class MessageService:
    async def send(self, bot, owner, sender, token, ctype, content, fid, analysis=None):
        tox = analysis["toxicity"] if analysis else 0.0
        sent = analysis["sentiment"] if analysis else 0.0
        await message_repo.create(owner, sender, token, content, ctype, fid, tox, sent)
        await user_repo.inc_msg(owner)
        header = f"📩 <b>پیام ناشناس جدید</b>\n{fa_now_str()}\n────────────\n"
        try:
            if ctype == "text":
                await bot.send_message(owner, header + (content or ""))
            elif ctype == "photo":
                await bot.send_photo(owner, fid, caption=header + (content or ""))
            elif ctype == "voice":
                await bot.send_voice(owner, fid, caption=header + (content or ""))
            elif ctype == "video":
                await bot.send_video(owner, fid, caption=header + (content or ""))
            elif ctype == "document":
                await bot.send_document(owner, fid, caption=header + (content or ""))
            else:
                return {"ok": False, "error": "نوع پشتیبانی نمی‌شود"}
        except TelegramForbiddenError:
            return {"ok": False, "error": "مالک بلاک کرده"}
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            return await self.send(bot, owner, sender, token, ctype, content, fid, analysis)
        except Exception as e:
            log.exception("send_anon: %s", e)
            return {"ok": False, "error": "خطا در ارسال"}
        return {"ok": True}


class SmartMatcher:
    """
    Weighted-score matcher.
    Score = Σ wᵢ · similarityᵢ
      • age proximity
      • city/province match
      • level similarity
      • activity recency
    """
    WEIGHTS = {"age": 0.35, "city": 0.25, "level": 0.20, "activity": 0.20}

    def __init__(self):
        self.queue: list[dict] = []

    async def find_best(self, uid, filters, profile, meta):
        self.queue = [q for q in self.queue if q["user_id"] != uid]
        best = None
        best_score = -1.0
        best_idx = -1
        for i, q in enumerate(self.queue):
            if not self._passes_hard(filters, profile, q["filters"], q["profile"]):
                continue
            score = self._score(profile, meta, q["profile"], q["meta"])
            if score > best_score:
                best_score = score
                best = q
                best_idx = i
        if best is not None:
            self.queue.pop(best_idx)
            return best["user_id"], best_score
        self.queue.append({"user_id": uid, "filters": filters,
                           "profile": profile, "meta": meta})
        return None, 0.0

    @staticmethod
    def _passes_hard(f1, p1, f2, p2) -> bool:
        if not (f1["min_age"] <= p2["age"] <= f1["max_age"]): return False
        if not (f2["min_age"] <= p1["age"] <= f2["max_age"]): return False
        if f1["gender"] != "any" and f1["gender"] != p2["gender"]: return False
        if f2["gender"] != "any" and f2["gender"] != p1["gender"]: return False
        if f1["same_city"] and p1["city"] != p2["city"]: return False
        if f2["same_city"] and p1["city"] != p2["city"]: return False
        return True

    def _score(self, p1, m1, p2, m2) -> float:
        # age proximity (normalized)
        age_diff = abs(p1["age"] - p2["age"])
        age_sim = max(0.0, 1.0 - age_diff / 20.0)

        # city/province
        if p1["city"] == p2["city"]:
            city_sim = 1.0
        elif p1["province"] == p2["province"]:
            city_sim = 0.5
        else:
            city_sim = 0.0

        # level similarity
        lvl_diff = abs(m1.get("level", 1) - m2.get("level", 1))
        level_sim = max(0.0, 1.0 - lvl_diff / 10.0)

        # activity recency
        def recency_bonus(last_seen: str) -> float:
            try:
                dt = datetime.fromisoformat(last_seen)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=IRAN_TZ)
                hours = (now_iran() - dt).total_seconds() / 3600
                return max(0.0, 1.0 - hours / 72.0)
            except Exception:
                return 0.5

        act_sim = (recency_bonus(m1.get("last_seen", "")) +
                   recency_bonus(m2.get("last_seen", ""))) / 2.0

        return (self.WEIGHTS["age"] * age_sim +
                self.WEIGHTS["city"] * city_sim +
                self.WEIGHTS["level"] * level_sim +
                self.WEIGHTS["activity"] * act_sim)

    def cancel(self, uid):
        self.queue = [q for q in self.queue if q["user_id"] != uid]

    def size(self) -> int:
        return len(self.queue)


class AdminService:
    async def dashboard(self) -> dict:
        return {
            "users": await user_repo.count(),
            "users_today": await user_repo.count_today(),
            "active_24h": await user_repo.count_active_24h(),
            "banned": await user_repo.count_banned(),
            "links_total": await link_repo.count_total(),
            "links_active": await link_repo.count_active(),
            "messages_total": await message_repo.count_total(),
            "messages_today": await message_repo.count_today(),
            "flagged_today": await message_repo.count_flagged_today(),
            "pairings_total": await pairing_repo.count_total(),
            "pairings_active": await pairing_repo.count_active(),
            "reports_pending": await report_repo.count_pending(),
            "rooms": await room_repo.count(),
            "queue": match_svc.size(),
            "channel": (await settings_repo.get_required_channel()) or "—",
            "maintenance": await settings_repo.is_maintenance(),
            "cache": cache.stats(),
        }

    async def broadcast(self, bot, chat_id, msg_id, users) -> dict:
        s, f = 0, 0
        for uid in users:
            try:
                await bot.copy_message(uid, chat_id, msg_id)
                s += 1
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                try:
                    await bot.copy_message(uid, chat_id, msg_id)
                    s += 1
                except Exception:
                    f += 1
            except Exception:
                f += 1
            await asyncio.sleep(0.05)
        return {"success": s, "failed": f}

    async def backup(self) -> bytes:
        try:
            with open(Config.DB_PATH, "rb") as f:
                return f.read()
        except Exception:
            return b""


class GamificationService:
    """XP, levels, badges."""
    async def award_xp(self, bot, uid, amount: int, reason: str = "") -> Optional[dict]:
        if amount <= 0:
            return None
        xp, lvl, leveled = await user_repo.add_xp(uid, amount)
        if leveled:
            try:
                await bot.send_message(uid, with_footer(
                    f"🎉 <b>سطح جدید!</b>\n\n"
                    f"🎖 سطح: <b>{lvl}</b>\n"
                    f"✨ XP: <b>{xp}</b>"))
            except Exception:
                pass
            return {"leveled": True, "new_level": lvl}
        return None

    async def check_badges(self, bot, uid) -> list[str]:
        """Evaluate badge conditions."""
        granted = []
        u = await user_repo.get(uid)
        if not u:
            return granted
        p = await profile_repo.get(uid)

        # EARLY_ADOPTER
        if await user_repo.count() <= 100:
            if await achievement_repo.grant(uid, Badges.EARLY_ADOPTER[1]):
                granted.append(Badges.EARLY_ADOPTER[1])

        # CHATTER
        if u["message_count"] >= 100:
            if await achievement_repo.grant(uid, Badges.CHATTER[1]):
                granted.append(Badges.CHATTER[1])

        # POPULAR
        if (await message_repo.count_for(uid)) >= 50:
            if await achievement_repo.grant(uid, Badges.POPULAR[1]):
                granted.append(Badges.POPULAR[1])

        # VERIFIED
        if p and p["avatar_url"] and is_custom_avatar(p["avatar_url"]):
            if await achievement_repo.grant(uid, Badges.VERIFIED[1]):
                granted.append(Badges.VERIFIED[1])

        for b in granted:
            try:
                await bot.send_message(uid, with_footer(f"🏅 بج جدید: <b>{b}</b>"))
            except Exception:
                pass
        return granted


class AnalyticsService:
    async def funnel(self) -> dict:
        total = await user_repo.count()
        with_rules = int(await db.fetch_val(
            "SELECT COUNT(*) FROM users WHERE rules_accepted=1", (), 0))
        with_profile = int(await db.fetch_val(
            "SELECT COUNT(*) FROM profiles", (), 0))
        with_link = int(await db.fetch_val(
            "SELECT COUNT(DISTINCT owner_id) FROM anonymous_links", (), 0))
        with_msg = int(await db.fetch_val(
            "SELECT COUNT(DISTINCT owner_id) FROM messages", (), 0))
        return {
            "total": total,
            "rules": with_rules,
            "profile": with_profile,
            "link": with_link,
            "msg": with_msg,
        }

    async def dau_wau_mau(self) -> dict:
        dau = int(await db.fetch_val(
            "SELECT COUNT(DISTINCT user_id) FROM users WHERE date(last_seen)=date('now')", (), 0))
        wau = int(await db.fetch_val(
            "SELECT COUNT(DISTINCT user_id) FROM users WHERE datetime(last_seen) > datetime('now','-7 day')", (), 0))
        mau = int(await db.fetch_val(
            "SELECT COUNT(DISTINCT user_id) FROM users WHERE datetime(last_seen) > datetime('now','-30 day')", (), 0))
        return {"dau": dau, "wau": wau, "mau": mau}

    async def top_provinces(self, limit=5):
        return await db.fetch_all(
            """SELECT province, COUNT(*) AS c FROM profiles
               GROUP BY province ORDER BY c DESC LIMIT ?""", (limit,))

    async def last_7_days(self):
        return await stats_repo.last_days(7)


def render_bar(value: int, max_value: int, width: int = 20) -> str:
    if max_value <= 0:
        return ""
    filled = min(width, int(width * value / max_value))
    return "█" * filled + "░" * (width - filled)


link_svc = LinkService()
message_svc = MessageService()
match_svc = SmartMatcher()
admin_svc = AdminService()
gamification_svc = GamificationService()
analytics_svc = AnalyticsService()


# ═══════════════════════════════════════════════════════════════════════
# ۱۷ ── ROUTERS
# ═══════════════════════════════════════════════════════════════════════

lang_router = Router()
rules_router = Router()
profile_router = Router()
avatar_router = Router()
settings_router = Router()
link_router = Router()
anon_router = Router()
target_router = Router()
match_router = Router()
room_router = Router()
gamif_router = Router()
admin_router = Router()
common_router = Router()


# ─── Lang / Rules ───

@lang_router.callback_query(F.data.startswith("lang:"))
async def cb_lang(cb: CallbackQuery, state: FSMContext):
    lang = cb.data.split(":")[1]
    await user_repo.set_language(cb.from_user.id, lang)
    await state.update_data(lang=lang)
    await cb.answer("✅")
    text = with_footer(f"🌍 <b>خوش آمدی!</b>\n\n{RULES_FA}")
    try:
        await cb.message.edit_text(text, reply_markup=rules_kb())
    except TelegramBadRequest:
        pass
    await state.set_state(RulesStates.showing)


@rules_router.callback_query(F.data == "rules:accept", RulesStates.showing)
async def cb_rules_accept(cb: CallbackQuery, state: FSMContext):
    await user_repo.set_rules_accepted(cb.from_user.id)
    await state.clear()
    profile = await profile_repo.get(cb.from_user.id)
    if not profile:
        await state.set_state(ProfileStates.gender)
        try:
            await cb.message.edit_text(
                with_footer("👋 <b>خوش آمدی!</b>\n\n1️⃣ <b>جنسیتت را انتخاب کن:</b>"),
                reply_markup=gender_kb())
        except TelegramBadRequest:
            pass
    else:
        try:
            await cb.message.edit_text(
                with_footer("🏠 <b>منوی اصلی</b>"),
                reply_markup=main_menu_kb(cb.from_user.id == Config.ADMIN_ID))
        except TelegramBadRequest:
            pass
    await cb.answer("✅")


@rules_router.callback_query(F.data == "rules:decline", RulesStates.showing)
async def cb_rules_decline(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.edit_text(with_footer("😔 برای استفاده باید بپذیری. /start"))
    except TelegramBadRequest:
        pass
    await cb.answer("😔")


# ─── /start ───

@common_router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext, bot: Bot):
    await state.clear()
    uid = message.from_user.id
    payload = (command.args or "").strip()

    # First-time referral tracking
    if payload.startswith("ref_"):
        ref_code = payload[4:]
        existing = await user_repo.get(uid)
        if not existing:
            ref_user = await db.fetch_one(
                "SELECT user_id FROM users WHERE referral_code=?", (ref_code,))
            if ref_user and ref_user["user_id"] != uid:
                await user_repo.create(uid, message.from_user.full_name,
                                       message.from_user.username,
                                       referrer_id=ref_user["user_id"])
                # award referrer
                await user_repo.add_xp(ref_user["user_id"], Config.XP_PER_NEW_REFERRAL)
                try:
                    await bot.send_message(ref_user["user_id"], with_footer(
                        f"🎁 <b>یک نفر با لینک تو عضو شد!</b>\n"
                        f"✨ +{Config.XP_PER_NEW_REFERRAL} XP"))
                except Exception:
                    pass
        payload = ""

    if not await user_repo.exists(uid):
        await user_repo.create(uid, message.from_user.full_name, message.from_user.username)
    else:
        await user_repo.update_profile(uid, message.from_user.full_name, message.from_user.username)

    user = await user_repo.get(uid)
    if not user or not user["rules_accepted"]:
        await state.set_state(LangStates.choosing)
        await message.answer(
            with_footer("🌍 <b>زبان خود را انتخاب کنید:</b>"),
            reply_markup=language_kb())
        return

    # Handle special payloads
    if payload.startswith("tc_"):
        token = payload[3:]
        tc = await target_repo.get(token)
        if not tc:
            await message.answer(with_footer("❌ لینک نامعتبر."))
            return
        if tc["target_id"] != uid:
            await message.answer("❌ این لینک برای شما نیست.")
            return
        if not await profile_repo.get(uid):
            await message.answer("⚠️ ابتدا پروفایل بساز. /start")
            return
        await state.update_data(tc_creator=tc["creator_id"], tc_token=token)
        await state.set_state(TargetChatStates.chat_active)
        await message.answer(
            with_footer("🔒 <b>چت با مخاطب خاص</b>\n\n/endchat برای پایان"),
            reply_markup=ReplyKeyboardRemove())
        try:
            await bot.send_message(tc["creator_id"], with_footer("🔔 مخاطب وارد چت شد!"))
        except Exception:
            pass
        return

    if payload.startswith("room_"):
        rid = payload[5:]
        room = await room_repo.get(rid)
        if not room:
            await message.answer("❌ اتاق نامعتبر.")
            return
        await room_repo.join(rid, uid)
        await state.set_state(RoomStates.chatting)
        await state.update_data(room_id=rid)
        await message.answer(
            with_footer(f"🏠 به اتاق «<b>{room['name']}</b>» خوش آمدی!\n\n/endchat برای خروج"),
            reply_markup=ReplyKeyboardRemove())
        # Notify others
        for m in await room_repo.members(rid):
            if m["user_id"] != uid:
                try:
                    await bot.send_message(m["user_id"], with_footer(
                        f"👤 یک نفر جدید به اتاق پیوست!"))
                except Exception:
                    pass
        return

    if payload:
        ok, link, err = await link_svc.validate(payload)
        if not ok:
            await message.answer(with_footer(f"❌ {err}"))
            return
        if link["owner_id"] == uid:
            await message.answer("🙂 نمی‌توانی به خودت پیام بفرستی.")
            return
        if not await profile_repo.get(uid):
            await message.answer("⚠️ ابتدا پروفایل بساز. /start")
            return
        await state.update_data(token=payload, owner_id=link["owner_id"],
                                link_type=link["link_type"])
        await state.set_state(AnonymousStates.waiting_message)
        await message.answer(
            with_footer("📩 <b>ارسال پیام ناشناس</b>\n\nپیام خود را بفرست:"),
            reply_markup=cancel_kb("anon:cancel"))
        return

    if not await profile_repo.get(uid):
        await state.set_state(ProfileStates.gender)
        await message.answer(
            with_footer("👋 <b>خوش آمدی!</b>\n\n1️⃣ <b>جنسیت:</b>"),
            reply_markup=gender_kb())
        return

    await message.answer(
        with_footer("🏠 <b>منوی اصلی</b>"),
        reply_markup=main_menu_kb(uid == Config.ADMIN_ID))


# ─── Commands ───

@common_router.message(Command("help"))
async def cmd_help(message: Message):
    uid = message.from_user.id
    is_admin = uid == Config.ADMIN_ID
    base = (
        "❓ <b>راهنما</b>\n\n"
        "<b>📌 عمومی:</b>\n"
        "/start — شروع\n/help — راهنما\n/profile — پروفایل\n"
        "/myid — آیدی من\n/time — ساعت ایران\n/rules — قوانین\n"
        "/stats — آمار ربات\n/me — سطح و XP من\n/top — لیدربورد\n"
        "/invite — لینک دعوت\n/report — گزارش تخلف\n"
        "/cancel — لغو\n/endchat — پایان چت\n"
    )
    if is_admin:
        base += (
            "\n<b>👑 ادمین:</b>\n"
            "/admin — پنل\n/ban /unban /warn /unwarn\n/mute /unmute\n"
            "/userinfo /search /broadcast\n/maintenance on|off\n/backup /ping\n"
        )
    await message.answer(with_footer(base))


@common_router.message(Command("myid"))
async def cmd_myid(message: Message):
    uid = message.from_user.id
    u = await user_repo.get(uid)
    ref_code = u["referral_code"] if u else "—"
    await message.answer(with_footer(
        f"🆔 <b>آیدی:</b> <code>{uid}</code>\n"
        f"🔗 <b>کد دعوت:</b> <code>{ref_code}</code>"))


@common_router.message(Command("time"))
async def cmd_time(message: Message):
    await message.answer(fa_now_str_full())


@common_router.message(Command("rules"))
async def cmd_rules(message: Message):
    await message.answer(with_footer(RULES_FA))


@common_router.message(Command("me"))
async def cmd_me(message: Message):
    uid = message.from_user.id
    u = await user_repo.get(uid)
    if not u:
        await message.answer("❌")
        return
    xp = u["xp"]
    lvl = u["level"]
    next_xp = xp_for_level(lvl + 1)
    prev_xp = xp_for_level(lvl)
    progress = xp - prev_xp
    total = next_xp - prev_xp
    bar = progress_bar(progress, total)
    badges = await achievement_repo.list_for(uid)
    badge_str = " ".join(b[0] for b in [b for b in Badges.ALL if b[1] in [x["badge"] for x in badges]]) or "—"
    await message.answer(with_footer(
        f"🎖 <b>سطح من</b>\n\n"
        f"🏅 سطح: <b>{lvl}</b>\n"
        f"✨ XP: <b>{xp}</b> / {next_xp}\n"
        f"{bar} {progress}/{total}\n"
        f"🏆 بج‌ها: {badge_str}\n"
        f"💬 پیام: <b>{u['message_count']}</b>"))


@common_router.message(Command("top"))
async def cmd_top(message: Message):
    top = await user_repo.top_by_xp(10)
    lines = ["🏆 <b>لیدربورد</b>\n"]
    medals = ["🥇", "🥈", "🥉"] + ["🎖"] * 7
    for i, r in enumerate(top):
        name = r["full_name"] or "—"
        name = name[:20]
        lines.append(f"{medals[i]} {name} — <b>{r['xp']}</b> XP (L{r['level']})")
    await message.answer(with_footer("\n".join(lines)))


@common_router.message(Command("invite"))
async def cmd_invite(message: Message, bot: Bot):
    uid = message.from_user.id
    u = await user_repo.get(uid)
    if not u:
        return
    code = u["referral_code"]
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{code}"
    share = f"https://t.me/share/url?url={link}&text=بیا با هم چت ناشناس کنیم!"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📤 اشتراک‌گذاری", S_SUCCESS, url=share)]])
    count = int(await db.fetch_val(
        "SELECT COUNT(*) FROM users WHERE referrer_id=?", (uid,), 0))
    await message.answer(
        with_footer(f"🎁 <b>دعوت دوستان</b>\n\n"
                    f"🔗 لینک:\n<code>{link}</code>\n\n"
                    f"👥 دعوت موفق: <b>{count}</b>\n"
                    f"✨ پاداش: <b>{Config.XP_PER_NEW_REFERRAL} XP</b> برای هر دعوت"),
        reply_markup=kb)


@common_router.message(Command("stats"))
async def cmd_stats(message: Message):
    s = await admin_svc.dashboard()
    if message.from_user.id == Config.ADMIN_ID:
        text = (
            "📊 <b>داشبورد</b>\n\n"
            f"👥 کاربران: <b>{s['users']}</b> (+{s['users_today']} امروز)\n"
            f"🟢 فعال ۲۴س: <b>{s['active_24h']}</b>\n"
            f"🚫 بن: <b>{s['banned']}</b>\n"
            f"🔗 لینک: <b>{s['links_total']}</b> (فعال: {s['links_active']})\n"
            f"📨 پیام: <b>{s['messages_total']}</b> (امروز: {s['messages_today']})\n"
            f"⚠️ مشکوک امروز: <b>{s['flagged_today']}</b>\n"
            f"🤝 مچ: <b>{s['pairings_total']}</b> (فعال: {s['pairings_active']})\n"
            f"🚨 گزارش: <b>{s['reports_pending']}</b>\n"
            f"🏠 اتاق: <b>{s['rooms']}</b>\n"
            f"⏳ صف مچ: <b>{s['queue']}</b>\n"
            f"🔒 کانال: <b>{s['channel']}</b>\n"
            f"🔧 تعمیر: <b>{'✅' if s['maintenance'] else '❌'}</b>\n"
            f"💾 کش: <b>{s['cache']['size']}</b> (hit-rate: {s['cache']['hit_rate']})")
    else:
        text = (
            "📊 <b>آمار ربات</b>\n\n"
            f"👥 کاربران: <b>{s['users']}</b>\n"
            f"📨 پیام‌ها: <b>{s['messages_total']}</b>\n"
            f"🤝 مچ‌ها: <b>{s['pairings_total']}</b>")
    await message.answer(with_footer(text))


@common_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    match_svc.cancel(message.from_user.id)
    await state.clear()
    await message.answer(with_footer("❌ لغو شد."),
                         reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID))


@common_router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext):
    await state.clear()
    await _show_profile(message)


@common_router.message(Command("endchat"))
async def cmd_endchat(message: Message, state: FSMContext, bot: Bot):
    uid = message.from_user.id
    cur = await state.get_state()
    data = await state.get_data()

    if cur == MatchStates.chatting.state:
        p = await pairing_repo.active_for(uid)
        if p:
            await pairing_repo.end(p["id"])
            partner = p["user2_id"] if p["user1_id"] == uid else p["user1_id"]
            try:
                await bot.send_message(partner, with_footer("🚪 مخاطب چت را پایان داد."))
            except Exception:
                pass
        await state.clear()
        await message.answer(with_footer("🚪 پایان."),
                             reply_markup=main_menu_kb(uid == Config.ADMIN_ID))
        return

    if cur == TargetChatStates.chat_active.state:
        token = data.get("tc_token")
        creator = data.get("tc_creator")
        if token:
            await target_repo.deactivate(token)
        if creator:
            try:
                await bot.send_message(creator, with_footer("🚪 پایان."))
            except Exception:
                pass
        await state.clear()
        await message.answer(with_footer("🚪 پایان."),
                             reply_markup=main_menu_kb(uid == Config.ADMIN_ID))
        return

    if cur == TargetCreatorStates.chatting.state:
        token = data.get("tc_token_creator")
        target = data.get("tc_target")
        if token:
            await target_repo.deactivate(token)
        if target:
            try:
                await bot.send_message(target, with_footer("🚪 پایان."))
            except Exception:
                pass
        await state.clear()
        await message.answer(with_footer("🚪 پایان."),
                             reply_markup=main_menu_kb(uid == Config.ADMIN_ID))
        return

    if cur == RoomStates.chatting.state:
        rid = data.get("room_id")
        if rid:
            await room_repo.leave(rid, uid)
            for m in await room_repo.members(rid):
                if m["user_id"] != uid:
                    try:
                        await bot.send_message(m["user_id"], with_footer("👋 یک نفر اتاق را ترک کرد."))
                    except Exception:
                        pass
        await state.clear()
        await message.answer(with_footer("🚪 از اتاق خارج شدی."),
                             reply_markup=main_menu_kb(uid == Config.ADMIN_ID))
        return

    await message.answer("چت فعالی نداری.")


@common_router.callback_query(F.data == "global:cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    match_svc.cancel(cb.from_user.id)
    await state.clear()
    try:
        await cb.message.edit_text(with_footer("❌ لغو شد."))
    except TelegramBadRequest:
        pass
    await cb.answer()


@common_router.message(F.text == "🕐 ساعت")
async def btn_time(message: Message):
    await message.answer(fa_now_str_full())


@common_router.message(F.text == "📜 قوانین")
async def btn_rules(message: Message):
    await message.answer(with_footer(RULES_FA))


# ─── Profile ───

@profile_router.callback_query(F.data.startswith("pf:gender:"), ProfileStates.gender)
async def pf_gender(cb: CallbackQuery, state: FSMContext):
    g = cb.data.split(":")[2]
    await state.update_data(gender=g)
    await state.set_state(ProfileStates.age)
    try:
        await cb.message.edit_text(
            with_footer("2️⃣ <b>سن دقیق (۹-۹۹):</b>"),
            reply_markup=age_grid_kb(0))
    except TelegramBadRequest:
        pass
    await cb.answer()


@profile_router.callback_query(F.data.startswith("pf:age_page:"), ProfileStates.age)
async def pf_age_page(cb: CallbackQuery):
    p = int(cb.data.split(":")[2])
    try:
        await cb.message.edit_reply_markup(reply_markup=age_grid_kb(p))
    except TelegramBadRequest:
        pass
    await cb.answer()


@profile_router.callback_query(F.data.startswith("pf:age:"), ProfileStates.age)
async def pf_age(cb: CallbackQuery, state: FSMContext):
    age = int(cb.data.split(":")[2])
    await state.update_data(age=age)
    await state.set_state(ProfileStates.province)
    try:
        await cb.message.edit_text(
            with_footer(f"✅ سن: <b>{age}</b>\n\n3️⃣ <b>استان:</b>"),
            reply_markup=provinces_kb(0))
    except TelegramBadRequest:
        pass
    await cb.answer()


@profile_router.callback_query(F.data.startswith("pf:prov_page:"), ProfileStates.province)
async def pf_prov_page(cb: CallbackQuery):
    p = int(cb.data.split(":")[2])
    try:
        await cb.message.edit_reply_markup(reply_markup=provinces_kb(p))
    except TelegramBadRequest:
        pass
    await cb.answer()


@profile_router.callback_query(F.data == "pf:back_prov", ProfileStates.city)
async def pf_back_prov(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileStates.province)
    try:
        await cb.message.edit_text(with_footer("3️⃣ <b>استان:</b>"),
                                   reply_markup=provinces_kb(0))
    except TelegramBadRequest:
        pass
    await cb.answer()


@profile_router.callback_query(F.data.startswith("pf:prov:"), ProfileStates.province)
async def pf_prov(cb: CallbackQuery, state: FSMContext):
    province = cb.data.split(":", 2)[2]
    await state.update_data(province=province)
    await state.set_state(ProfileStates.city)
    try:
        await cb.message.edit_text(
            with_footer(f"4️⃣ <b>شهر ({province}):</b>"),
            reply_markup=cities_kb(province, 0))
    except TelegramBadRequest:
        pass
    await cb.answer()


@profile_router.callback_query(F.data.startswith("pf:city_page:"), ProfileStates.city)
async def pf_city_page(cb: CallbackQuery, state: FSMContext):
    p = int(cb.data.split(":")[2])
    data = await state.get_data()
    try:
        await cb.message.edit_reply_markup(reply_markup=cities_kb(data["province"], p))
    except TelegramBadRequest:
        pass
    await cb.answer()


@profile_router.callback_query(F.data.startswith("pf:city:"), ProfileStates.city)
async def pf_city(cb: CallbackQuery, state: FSMContext, bot: Bot):
    city = cb.data.split(":", 2)[2]
    data = await state.get_data()
    gender = data["gender"]
    age = data["age"]
    province = data["province"]
    seed = f"{cb.from_user.id}-{random.randint(1, 999999)}"
    avatar = avatar_url(gender, seed)
    await profile_repo.create(cb.from_user.id, gender, age, province, city, avatar)
    await state.clear()

    gender_fa = "پسر 👨" if gender == "male" else "دختر 👩"
    caption = with_footer(
        f"🎉 <b>پروفایل ساخته شد!</b>\n\n"
        f"👤 {gender_fa}\n🎂 {age} سال\n"
        f"🗺 {province}\n🏙 {city}")
    try:
        await bot.send_photo(cb.from_user.id, avatar, caption=caption)
    except Exception:
        await cb.message.answer(caption)
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer(with_footer("🏠 <b>منوی اصلی</b>"),
                            reply_markup=main_menu_kb(cb.from_user.id == Config.ADMIN_ID))
    await cb.answer("✅")


async def _show_profile(message: Message):
    uid = message.from_user.id
    p = await profile_repo.get(uid)
    if not p:
        await message.answer(with_footer("❌ پروفایل نداری. /start"))
        return
    gender_fa = "پسر 👨" if p["gender"] == "male" else "دختر 👩"
    text = with_footer(
        "👤 <b>پروفایل</b>\n\n"
        f"🎭 {gender_fa}\n🎂 {p['age']} سال\n"
        f"🗺 {p['province']}\n🏙 {p['city']}\n"
        f"📅 {p['created_at'][:10]}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("✏️ ویرایش", S_PRIMARY, callback_data="pf:edit")],
        [_ibtn("🎨 عکس", S_SUCCESS, callback_data="av:edit")]])
    if p["avatar_url"]:
        try:
            fid = extract_file_id(p["avatar_url"])
            await message.answer_photo(fid, caption=text, reply_markup=kb)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb)


@common_router.message(F.text == "👤 پروفایل من")
async def show_profile_btn(message: Message):
    await _show_profile(message)


@common_router.callback_query(F.data == "pf:edit")
async def cb_pf_edit(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileStates.gender)
    await cb.message.answer(with_footer("1️⃣ جنسیت:"), reply_markup=gender_kb())
    await cb.answer()


# ─── Avatar ───

@avatar_router.callback_query(F.data == "av:edit")
async def cb_av_edit(cb: CallbackQuery):
    await cb.message.answer(with_footer("🎨 <b>عکس پروفایل</b>"),
                            reply_markup=avatar_edit_kb())
    await cb.answer()


@avatar_router.callback_query(F.data == "av:back")
async def cb_av_back(cb: CallbackQuery):
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.answer("بازگشت")


@avatar_router.callback_query(F.data == "av:random")
async def cb_av_random(cb: CallbackQuery, bot: Bot):
    p = await profile_repo.get(cb.from_user.id)
    if not p:
        await cb.answer("❌ پروفایل نداری.", show_alert=True)
        return
    seed = f"{cb.from_user.id}-{random.randint(1, 999999999)}"
    new_avatar = avatar_url(p["gender"], seed)
    await profile_repo.set_avatar(cb.from_user.id, new_avatar)
    try:
        await cb.message.delete()
    except Exception:
        pass
    try:
        await bot.send_photo(cb.from_user.id, new_avatar,
                             caption=with_footer("🎲 عکس جدید!"))
    except Exception:
        pass
    await cb.answer("✅")


@avatar_router.callback_query(F.data == "av:upload")
async def cb_av_upload(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarStates.uploading)
    try:
        await cb.message.edit_text(with_footer("📸 <b>عکس را بفرست:</b>"),
                                   reply_markup=cancel_kb("global:cancel"))
    except TelegramBadRequest:
        pass
    await cb.answer()


@avatar_router.message(AvatarStates.uploading, F.photo)
async def av_upload_photo(message: Message, state: FSMContext, bot: Bot):
    fid = message.photo[-1].file_id
    await profile_repo.set_avatar(message.from_user.id, f"file:{fid}")
    await state.clear()
    # Verify badge
    await gamification_svc.check_badges(bot, message.from_user.id)
    try:
        await message.answer_photo(fid, caption=with_footer("✅ عکس تغییر کرد!"))
    except Exception:
        await message.answer(with_footer("✅"))


@avatar_router.message(AvatarStates.uploading)
async def av_upload_invalid(message: Message):
    await message.answer("⚠️ فقط عکس.")


# ─── Settings ───

@settings_router.message(F.text == "⚙️ تنظیمات")
async def user_settings_menu(message: Message):
    s = await usettings_repo.get(message.from_user.id)
    await message.answer(with_footer("⚙️ <b>تنظیمات</b>"),
                         reply_markup=settings_kb(s))


@settings_router.callback_query(F.data.startswith("uset:toggle:"))
async def cb_uset_toggle(cb: CallbackQuery):
    field = cb.data.split(":")[2]
    await usettings_repo.toggle(cb.from_user.id, field)
    s = await usettings_repo.get(cb.from_user.id)
    try:
        await cb.message.edit_reply_markup(reply_markup=settings_kb(s))
    except TelegramBadRequest:
        pass
    labels = {"web_mode": "وب", "silent_mode": "سایلنت",
              "copyright_mode": "کپی‌رایت", "read_receipt": "اعلان",
              "auto_translate": "ترجمه"}
    await cb.answer(f"{labels[field]}: {'✅' if s[field] else '❌'}")


# ─── Links ───

@link_router.message(F.text == "🔗 دریافت لینک ناشناس")
async def link_menu(message: Message, state: FSMContext):
    await state.set_state(LinkStates.choosing_type)
    await message.answer(with_footer("🔗 <b>نوع لینک:</b>"),
                         reply_markup=link_type_kb())


@link_router.callback_query(F.data.startswith("linktype:"), LinkStates.choosing_type)
async def cb_linktype(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    ltype = cb.data.split(":")[1]
    ltype = "permanent" if ltype == "permanent" else "onetime"
    r = await link_svc.create(cb.from_user.id, ltype)
    if not r["ok"]:
        await cb.answer(r["error"], show_alert=True)
        return
    label = "♾ دائمی" if ltype == "permanent" else "1️⃣ یکبار"
    text = with_footer(f"✅ <b>لینک ({label})</b>\n\n🔗 <code>{r['link']}</code>")
    try:
        await cb.message.edit_text(text, reply_markup=link_actions_kb(r["token"]))
    except TelegramBadRequest:
        await cb.message.answer(text, reply_markup=link_actions_kb(r["token"]))
    await cb.answer("✅")


@link_router.callback_query(F.data.startswith("link:del:"))
async def cb_link_del(cb: CallbackQuery):
    token = cb.data.split(":", 2)[2]
    l = await link_repo.get(token)
    if not l or l["owner_id"] != cb.from_user.id:
        await cb.answer("❌", show_alert=True)
        return
    await link_repo.delete(token)
    try:
        await cb.message.edit_text(with_footer("🗑 حذف شد."), reply_markup=None)
    except TelegramBadRequest:
        pass
    await cb.answer("✅")


@common_router.message(F.text == "📊 آمار من")
async def my_stats(message: Message):
    uid = message.from_user.id
    p = await profile_repo.get(uid)
    msgs = await message_repo.count_for(uid)
    links = await link_repo.active_of_owner(uid)
    perm = sum(1 for l in links if l["link_type"] == "permanent")
    once = sum(1 for l in links if l["link_type"] == "onetime")
    u = await user_repo.get(uid)
    await message.answer(with_footer(
        "📊 <b>آمار من</b>\n\n"
        f"📨 پیام: <b>{msgs}</b>\n"
        f"♾ دائمی: <b>{perm}</b>\n"
        f"1️⃣ یکبار: <b>{once}</b>\n"
        f"⚠️ اخطار: <b>{u['warn_count'] if u else 0}</b>\n"
        f"✨ XP: <b>{u['xp'] if u else 0}</b> (L{u['level'] if u else 1})\n"
        + (f"\n🎂 {p['age']} | 🏙 {p['city']}" if p else "")),
        reply_markup=main_menu_kb(uid == Config.ADMIN_ID))


# ─── Gamification buttons ───

@gamif_router.message(F.text == "🎖 سطح من")
async def btn_me(message: Message):
    await cmd_me(message)


@gamif_router.message(F.text == "🏆 لیدربورد")
async def btn_top(message: Message):
    await cmd_top(message)


@gamif_router.message(F.text == "🎁 دعوت دوستان")
async def btn_invite(message: Message, bot: Bot):
    await cmd_invite(message, bot)


# ─── Anonymous messages ───

@anon_router.message(AnonymousStates.waiting_message)
async def anon_recv(message: Message, state: FSMContext):
    ctype, fid, content = "text", None, None
    if message.text:
        content = message.text.strip()
    elif message.photo:
        ctype, fid, content = "photo", message.photo[-1].file_id, message.caption
    elif message.voice:
        ctype, fid, content = "voice", message.voice.file_id, message.caption
    elif message.video:
        ctype, fid, content = "video", message.video.file_id, message.caption
    elif message.document:
        ctype, fid, content = "document", message.document.file_id, message.caption
    else:
        await message.answer("⚠️ نوع پشتیبانی نمی‌شود.")
        return

    # AI moderation
    analysis = moderation.analyze(content or "") if content else None
    if analysis and moderation.is_flagged(analysis):
        owner_id = (await state.get_data()).get("owner_id")
        # Log report for admin
        rid = await report_repo.create(message.from_user.id, owner_id, None,
                                       f"auto:{','.join(analysis['flags'])}")
        # Notify admins
        try:
            await message.bot.send_message(Config.ADMIN_ID, with_footer(
                f"🚨 <b>محتوای مشکوک</b>\n\n"
                f"👤 فرستنده: <code>{message.from_user.id}</code>\n"
                f"⚠️ flags: {', '.join(analysis['flags'])}\n"
                f"📊 toxicity: {analysis['toxicity']}\n"
                f"📊 spam: {analysis['spam']}"),
                reply_markup=report_review_kb(rid, message.from_user.id))
        except Exception:
            pass

    await state.update_data(prev_t=ctype, prev_f=fid, prev_c=content,
                            analysis=analysis)
    await state.set_state(AnonymousStates.confirm_send)
    warning = ""
    if analysis and analysis["flags"]:
        warning = f"\n\n⚠️ <i>هشدار: {', '.join(analysis['flags'])}</i>"
    await message.answer(
        with_footer(f"📝 پیش‌نمایش. ارسال شود؟{warning}"),
        reply_markup=confirm_kb("anon"))


@anon_router.callback_query(F.data == "cancel:anon")
async def cb_anon_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.edit_text(with_footer("❌ لغو شد."))
    except TelegramBadRequest:
        pass
    await cb.answer()


@anon_router.callback_query(F.data == "confirm:anon")
async def cb_anon_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    token = data.get("token")
    owner = data.get("owner_id")
    ltype = data.get("link_type", "onetime")
    if not token or not owner:
        await state.clear()
        await cb.answer("❌", show_alert=True)
        return
    ok, _, err = await link_svc.validate(token)
    if not ok:
        await state.clear()
        await cb.answer(f"❌ {err}", show_alert=True)
        return
    r = await message_svc.send(bot, owner, cb.from_user.id, token,
                               data["prev_t"], data["prev_c"], data["prev_f"],
                               data.get("analysis"))
    if not r["ok"]:
        await cb.answer(f"❌ {r['error']}", show_alert=True)
        return
    await link_svc.consume(token, cb.from_user.id, ltype)
    # Award XP
    await gamification_svc.award_xp(bot, cb.from_user.id, Config.XP_PER_MESSAGE_SENT)
    await gamification_svc.award_xp(bot, owner, Config.XP_PER_MESSAGE_RECEIVED)
    # Bump daily stats
    await stats_repo.bump("messages_sent")
    await state.clear()
    txt = "✅ ارسال شد."
    if ltype == "permanent":
        txt += "\n♾ لینک فعال است."
    try:
        await cb.message.edit_text(with_footer(txt))
    except TelegramBadRequest:
        await cb.message.answer(with_footer(txt))
    await cb.answer("✅")


# ─── Target chat ───

@target_router.message(F.text == "👤 اتصال به مخاطب خاص")
async def target_start(message: Message, state: FSMContext):
    await state.set_state(TargetChatStates.waiting_target)
    await message.answer(
        with_footer("👤 <b>مخاطب خاص</b>\n\nآیدی عددی یا فوروارد:"),
        reply_markup=cancel_kb("global:cancel"))


@target_router.message(TargetChatStates.waiting_target)
async def target_receive(message: Message, state: FSMContext):
    target_id = None
    if message.forward_from:
        target_id = message.forward_from.id
    elif message.text and re.match(r"^\d{5,15}$", message.text.strip()):
        target_id = int(message.text.strip())
    else:
        await message.answer("⚠️ نامعتبر.")
        return
    if target_id == message.from_user.id:
        await message.answer("🙂 به خودت؟")
        return
    token = generate_secure_token()
    await target_repo.create(token, message.from_user.id, target_id)
    await state.update_data(tc_token_creator=token, tc_target=target_id)
    await state.set_state(TargetCreatorStates.chatting)
    await message.answer(
        with_footer(f"✅ لینک:\n\n<code>https://t.me/{Config.BOT_USERNAME}?start=tc_{token}</code>"),
        reply_markup=target_chat_kb(token))


@target_router.callback_query(F.data.startswith("tc:cancel:"))
async def cb_tc_cancel(cb: CallbackQuery, state: FSMContext):
    token = cb.data.split(":", 2)[2]
    await target_repo.deactivate(token)
    await state.clear()
    try:
        await cb.message.edit_text(with_footer("🗑 لغو شد."), reply_markup=None)
    except TelegramBadRequest:
        pass
    await cb.answer("✅")


@target_router.message(TargetChatStates.chat_active,
                       F.text | F.photo | F.voice | F.video | F.document | F.sticker)
async def target_chat_msg(message: Message, state: FSMContext):
    data = await state.get_data()
    creator = data.get("tc_creator")
    if not creator:
        await state.clear()
        return
    try:
        await message.copy_to(creator)
    except Exception as e:
        log.exception("target_chat: %s", e)


@target_router.message(TargetCreatorStates.chatting,
                       F.text | F.photo | F.voice | F.video | F.document | F.sticker)
async def target_creator_msg(message: Message, state: FSMContext):
    data = await state.get_data()
    target = data.get("tc_target")
    token = data.get("tc_token_creator")
    if not target or not token:
        await state.clear()
        return
    tc = await target_repo.get(token)
    if not tc:
        await message.answer("⚠️ منقضی.")
        await state.clear()
        return
    try:
        await message.copy_to(target)
    except Exception as e:
        log.exception("target_creator: %s", e)


# ─── Match (Smart) ───

async def _ensure_filters(state: FSMContext, uid: int):
    data = await state.get_data()
    if "filters" not in data:
        p = await profile_repo.get(uid)
        age = p["age"] if p else 25
        data["filters"] = {
            "min_age": max(9, age - 10),
            "max_age": min(99, age + 10),
            "gender": "any",
            "same_city": False,
        }
        await state.update_data(filters=data["filters"])
    return data["filters"]


@match_router.message(F.text == "🎭 اتصال به ناشناس")
async def match_menu(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not await profile_repo.get(uid):
        await message.answer("⚠️ پروفایل بساز.")
        return
    filters = await _ensure_filters(state, uid)
    await state.set_state(MatchStates.configuring)
    await message.answer(with_footer("🎭 <b>فیلترها:</b>"),
                         reply_markup=match_menu_kb(filters))


@match_router.callback_query(F.data == "filter:age")
async def cb_filter_age(cb: CallbackQuery, state: FSMContext):
    await state.update_data(awaiting_age=True)
    await cb.message.edit_text(with_footer("🎂 <code>20-30</code>"),
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                   [_ibtn("◀️", S_PRIMARY, callback_data="filter:menu")]]))
    await cb.answer()


@match_router.message(MatchStates.configuring, F.text.regexp(r"^\d{1,2}\s*-\s*\d{1,2}$"))
async def match_age_input(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("awaiting_age"):
        return
    lo_s, hi_s = re.split(r"\s*-\s*", message.text.strip())
    lo, hi = int(lo_s), int(hi_s)
    if not (9 <= lo <= 99 and 9 <= hi <= 99 and lo <= hi):
        await message.answer("⚠️ نامعتبر.")
        return
    f = data.get("filters") or {}
    f["min_age"] = lo
    f["max_age"] = hi
    await state.update_data(filters=f, awaiting_age=False)
    await message.answer(with_footer(f"✅ {lo}-{hi}"), reply_markup=match_menu_kb(f))


@match_router.callback_query(F.data == "filter:gender")
async def cb_filter_gender(cb: CallbackQuery):
    await cb.message.edit_text(with_footer("🎭 جنسیت:"), reply_markup=filter_gender_kb())
    await cb.answer()


@match_router.callback_query(F.data.startswith("filter:gender:"))
async def cb_filter_gender_set(cb: CallbackQuery, state: FSMContext):
    g = cb.data.split(":")[2]
    f = await _ensure_filters(state, cb.from_user.id)
    f["gender"] = g
    await state.update_data(filters=f)
    await cb.message.edit_text(with_footer("🎭"), reply_markup=match_menu_kb(f))
    await cb.answer()


@match_router.callback_query(F.data == "filter:city")
async def cb_filter_city(cb: CallbackQuery, state: FSMContext):
    f = await _ensure_filters(state, cb.from_user.id)
    f["same_city"] = not f["same_city"]
    await state.update_data(filters=f)
    await cb.message.edit_text(with_footer("🎭"), reply_markup=match_menu_kb(f))
    await cb.answer(f"همشهری: {'✅' if f['same_city'] else '❌'}")


@match_router.callback_query(F.data == "filter:menu")
async def cb_filter_menu(cb: CallbackQuery, state: FSMContext):
    f = await _ensure_filters(state, cb.from_user.id)
    await state.update_data(awaiting_age=False)
    await cb.message.edit_text(with_footer("🎭"), reply_markup=match_menu_kb(f))
    await cb.answer()


@match_router.callback_query(F.data == "match:start")
async def cb_match_start(cb: CallbackQuery, state: FSMContext, bot: Bot):
    uid = cb.from_user.id
    p = await profile_repo.get(uid)
    if not p:
        await cb.answer("❌ پروفایل بساز.", show_alert=True)
        return
    u = await user_repo.get(uid)
    filters = await _ensure_filters(state, uid)
    profile_dict = {"gender": p["gender"], "age": p["age"],
                    "city": p["city"], "province": p["province"]}
    meta_dict = {"level": u["level"] if u else 1, "last_seen": u["last_seen"] if u else ""}
    partner_id, score = await match_svc.find_best(uid, filters, profile_dict, meta_dict)
    if partner_id is None:
        await state.set_state(MatchStates.searching)
        try:
            await cb.message.edit_text(
                with_footer("🔍 <b>در جستجو...</b>"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [_ibtn("❌ لغو", S_DANGER, callback_data="match:cancel_search")]]))
        except TelegramBadRequest:
            pass
        await cb.answer("🔍")
        return
    pid = await pairing_repo.create(uid, partner_id)
    await state.set_state(MatchStates.chatting)
    await state.update_data(pairing_id=pid, partner_id=partner_id)
    await stats_repo.bump("matches")
    for target_uid in (uid, partner_id):
        try:
            await bot.send_message(target_uid, with_footer(
                f"🎉 <b>مچ پیدا شد!</b>\nامتیاز تطابق: <b>{int(score*100)}%</b>\n\n/endchat برای پایان"),
                reply_markup=ReplyKeyboardRemove())
        except Exception:
            pass
    try:
        await cb.message.edit_text(with_footer(f"✅ مچ شد! ({int(score*100)}%)"))
    except TelegramBadRequest:
        pass
    await cb.answer("🎉")


@match_router.callback_query(F.data == "match:cancel_search")
async def cb_match_cancel(cb: CallbackQuery, state: FSMContext):
    match_svc.cancel(cb.from_user.id)
    f = await _ensure_filters(state, cb.from_user.id)
    await state.set_state(MatchStates.configuring)
    try:
        await cb.message.edit_text(with_footer("❌ لغو."), reply_markup=match_menu_kb(f))
    except TelegramBadRequest:
        pass
    await cb.answer()


@match_router.message(MatchStates.chatting,
                      F.text | F.photo | F.voice | F.video | F.document | F.sticker)
async def match_chat_relay(message: Message, state: FSMContext):
    data = await state.get_data()
    partner = data.get("partner_id")
    if not partner:
        p = await pairing_repo.active_for(message.from_user.id)
        if not p:
            await state.clear()
            return
        partner = p["user2_id"] if p["user1_id"] == message.from_user.id else p["user1_id"]
        await state.update_data(partner_id=partner, pairing_id=p["id"])
    try:
        await message.copy_to(partner)
    except Exception as e:
        log.exception("match_relay: %s", e)


# ─── Rooms ───

@room_router.message(F.text == "👥 اتاق گروهی")
async def room_menu(message: Message, state: FSMContext):
    await state.set_state(RoomStates.creating)
    await message.answer(
        with_footer("👥 <b>اتاق گروهی ناشناس</b>\n\nنام اتاق را بفرست (یا /cancel):"),
        reply_markup=cancel_kb("global:cancel"))


@room_router.message(RoomStates.creating)
async def room_create(message: Message, state: FSMContext):
    name = (message.text or "").strip()[:40]
    if not name:
        await message.answer("⚠️ نامعتبر.")
        return
    rid = await room_repo.create(name, message.from_user.id)
    await state.set_state(RoomStates.chatting)
    await state.update_data(room_id=rid)
    await message.answer(
        with_footer(f"🏠 اتاق «<b>{name}</b>» ساخته شد!\n\nلینک دعوت:\n"
                    f"<code>https://t.me/{Config.BOT_USERNAME}?start=room_{rid}</code>\n\n"
                    f"/endchat برای خروج"),
        reply_markup=room_kb(rid))


@room_router.callback_query(F.data.startswith("room:leave:"))
async def cb_room_leave(cb: CallbackQuery, state: FSMContext):
    rid = cb.data.split(":")[2]
    await room_repo.leave(rid, cb.from_user.id)
    await state.clear()
    try:
        await cb.message.edit_text(with_footer("🚪 خارج شدی."), reply_markup=None)
    except TelegramBadRequest:
        pass
    await cb.answer("✅")


@room_router.message(RoomStates.chatting,
                     F.text | F.photo | F.voice | F.video | F.document | F.sticker)
async def room_chat_relay(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    rid = data.get("room_id")
    if not rid:
        return
    members = await room_repo.members(rid)
    for m in members:
        if m["user_id"] == message.from_user.id:
            continue
        try:
            await message.copy_to(m["user_id"])
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════
# ۱۸ ── ADMIN PANEL
# ═══════════════════════════════════════════════════════════════════════

def _is_admin(uid: int) -> bool:
    return uid == Config.ADMIN_ID


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer(with_footer("👑 <b>پنل مدیریت</b>"), reply_markup=admin_menu_kb())


@admin_router.message(F.text == "👑 پنل ادمین")
async def admin_panel(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer(with_footer("👑 <b>پنل مدیریت</b>"), reply_markup=admin_menu_kb())


@admin_router.message(F.text == "◀️ بازگشت")
async def admin_back(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer(with_footer("🏠 منوی اصلی"), reply_markup=main_menu_kb(True))


@admin_router.message(Command("ping"))
async def cmd_ping(message: Message):
    if not _is_admin(message.from_user.id):
        return
    t0 = time.monotonic()
    m = await message.answer("🏓")
    dt = (time.monotonic() - t0) * 1000
    await m.edit_text(with_footer(f"🏓 <b>Pong!</b>\n⚡ {dt:.1f} ms"))


@admin_router.message(F.text == "📊 داشبورد")
async def admin_dashboard(message: Message):
    if not _is_admin(message.from_user.id):
        return
    s = await admin_svc.dashboard()
    c = s["cache"]
    text = (
        "📊 <b>داشبورد</b>\n\n"
        f"👥 کاربران: <b>{s['users']}</b> (+{s['users_today']} امروز)\n"
        f"🟢 فعال ۲۴س: <b>{s['active_24h']}</b>\n"
        f"🚫 بن: <b>{s['banned']}</b>\n"
        f"🔗 لینک کل: <b>{s['links_total']}</b>\n"
        f"📨 پیام کل: <b>{s['messages_total']}</b>\n"
        f"⚠️ مشکوک امروز: <b>{s['flagged_today']}</b>\n"
        f"🤝 مچ کل: <b>{s['pairings_total']}</b> (فعال: {s['pairings_active']})\n"
        f"🚨 گزارش: <b>{s['reports_pending']}</b>\n"
        f"🏠 اتاق: <b>{s['rooms']}</b>\n"
        f"⏳ صف: <b>{s['queue']}</b>\n"
        f"🔒 کانال: <b>{s['channel']}</b>\n"
        f"🔧 تعمیر: <b>{'✅' if s['maintenance'] else '❌'}</b>\n"
        f"💾 کش: <b>{c['size']}</b> (hit: {c['hit_rate']})")
    await message.answer(with_footer(text), reply_markup=admin_menu_kb())


@admin_router.message(F.text == "📈 آنالیتیکس")
async def admin_analytics(message: Message):
    if not _is_admin(message.from_user.id):
        return
    funnel = await analytics_svc.funnel()
    dwm = await analytics_svc.dau_wau_mau()
    days = await analytics_svc.last_7_days()
    top_prov = await analytics_svc.top_provinces(5)

    lines = ["📈 <b>آنالیتیکس</b>\n"]
    lines.append("<b>🔻 قیف کاربری:</b>")
    max_v = max(funnel.values()) if funnel.values() else 1
    labels = {"total": "عضو شده", "rules": "پذیرش قوانین",
              "profile": "پروفایل", "link": "لینک", "msg": "پیام"}
    for k, v in funnel.items():
        bar = render_bar(v, max_v, 15)
        lines.append(f"  {labels[k]}: <b>{v}</b> {bar}")

    lines.append(f"\n<b>📊 کاربران فعال:</b>")
    lines.append(f"  DAU: <b>{dwm['dau']}</b> | WAU: <b>{dwm['wau']}</b> | MAU: <b>{dwm['mau']}</b>")

    if days:
        lines.append(f"\n<b>📅 ۷ روز اخیر:</b>")
        for d in days[:7]:
            lines.append(f"  {d['date']}: 👥{d['new_users']} 📨{d['messages_sent']} 🤝{d['matches']}")

    if top_prov:
        lines.append(f"\n<b>🏙 استان‌های برتر:</b>")
        for p in top_prov:
            lines.append(f"  {p['province']}: <b>{p['c']}</b>")

    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_router.message(F.text == "🚨 گزارش‌ها")
async def admin_reports(message: Message):
    if not _is_admin(message.from_user.id):
        return
    reports = await report_repo.pending(20)
    if not reports:
        await message.answer(with_footer("🚨 گزارشی نیست."), reply_markup=admin_menu_kb())
        return
    for r in reports[:10]:
        text = (
            f"🚨 <b>گزارش #{r['id']}</b>\n"
            f"👤 فرستنده: <code>{r['reporter_id']}</code>\n"
            f"🎯 هدف: <code>{r['reported_id'] or '—'}</code>\n"
            f"📝 دلیل: {r['reason']}\n"
            f"🕐 {r['created_at'][:16]}")
        await message.answer(with_footer(text),
                             reply_markup=report_review_kb(r["id"], r["reporter_id"]))


@admin_router.callback_query(F.data.startswith("rep:"))
async def admin_report_action(cb: CallbackQuery, bot: Bot):
    if not _is_admin(cb.from_user.id):
        return
    parts = cb.data.split(":")
    action, rid_s, uid_s = parts[1], parts[2], parts[3]
    rid = int(rid_s)
    uid = int(uid_s)
    if action == "ok":
        await report_repo.mark(rid, "confirmed", cb.from_user.id)
        n = await user_repo.add_warn(uid)
        await warning_repo.add(uid, cb.from_user.id, f"report#{rid}")
        try:
            await bot.send_message(uid, with_footer(f"⚠️ اخطار! تعداد: {n}"))
        except Exception:
            pass
        await cb.answer("✅ تأیید و اخطار داده شد.", show_alert=True)
    else:
        await report_repo.mark(rid, "rejected", cb.from_user.id)
        await cb.answer("❌ رد شد.", show_alert=True)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@admin_router.message(F.text == "👥 کاربران")
async def admin_users(message: Message):
    if not _is_admin(message.from_user.id):
        return
    users = await user_repo.get_all(15)
    if not users:
        await message.answer("کاربری نیست.")
        return
    lines = ["👥 <b>آخرین ۱۵</b>\n"]
    for u in users:
        st = "🚫" if u["is_banned"] else "✅"
        wn = f"⚠️{u['warn_count']}" if u["warn_count"] else ""
        lines.append(f"{st} <code>{u['user_id']}</code> — {u['full_name'] or '—'} {wn}")
    lines.append("\n💡 /userinfo ID")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_router.message(F.text == "🔍 جستجو")
async def admin_search_prompt(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.searching_user)
    await message.answer(with_footer("🔍 <b>جستجو:</b>"),
                         reply_markup=cancel_kb("global:cancel"))


@admin_router.message(AdminStates.searching_user)
async def admin_search_run(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    q = (message.text or "").strip().lstrip("@")
    await state.clear()
    if not q:
        return
    rows = await user_repo.search(q, limit=15)
    if not rows:
        await message.answer(with_footer("یافت نشد."), reply_markup=admin_menu_kb())
        return
    lines = [f"🔍 <b>نتایج ({len(rows)}):</b>\n"]
    for u in rows:
        st = "🚫" if u["is_banned"] else "✅"
        lines.append(f"{st} <code>{u['user_id']}</code> — {u['full_name'] or '—'}")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_router.message(Command("userinfo"))
async def cmd_userinfo(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return
    a = (command.args or "").strip()
    if not a.isdigit():
        await message.answer("فرمت: <code>/userinfo ID</code>")
        return
    uid = int(a)
    u = await user_repo.get(uid)
    if not u:
        await message.answer("یافت نشد.")
        return
    p = await profile_repo.get(uid)
    warns = await warning_repo.list_for(uid, 5)
    msgs = await message_repo.count_for(uid)
    text = (
        f"👤 <b>کاربر</b>\n\n"
        f"🆔 <code>{u['user_id']}</code>\n"
        f"👤 {u['full_name'] or '—'}\n"
        f"🔗 @{u['username'] or '—'}\n"
        f"🌍 {u['language']}\n"
        f"📜 قوانین: {'✅' if u['rules_accepted'] else '❌'}\n"
        f"🚫 بن: {'✅ ' + (u['ban_reason'] or '') if u['is_banned'] else '❌'}\n"
        f"⚠️ اخطار: <b>{u['warn_count']}</b>\n"
        f"✨ XP: <b>{u['xp']}</b> (L{u['level']})\n"
        f"📨 پیام: <b>{msgs}</b>\n"
        f"🔗 لینک: <b>{u['link_count']}</b>\n"
        f"📅 {u['created_at'][:10]}\n"
        f"🕐 {u['last_seen'][:16]}")
    if p:
        text += f"\n\n🎭 {p['gender']} | 🎂 {p['age']} | 🏙 {p['province']} - {p['city']}"
    if warns:
        text += "\n\n<b>اخطارها:</b>"
        for w in warns[:3]:
            text += f"\n• {w['created_at'][:16]} — {w['reason'] or '—'}"
    try:
        if p and p["avatar_url"]:
            await message.answer_photo(p["avatar_url"], caption=with_footer(text),
                                        reply_markup=admin_user_actions_kb(uid))
            return
    except Exception:
        pass
    await message.answer(with_footer(text), reply_markup=admin_user_actions_kb(uid))


@admin_router.callback_query(F.data.startswith("adm:"))
async def admin_user_actions(cb: CallbackQuery, state: FSMContext, bot: Bot):
    if not _is_admin(cb.from_user.id):
        return
    parts = cb.data.split(":")
    action, uid_s = parts[1], parts[2]
    uid = int(uid_s)
    u = await user_repo.get(uid)
    if not u:
        await cb.answer("❌", show_alert=True)
        return

    if action == "ban":
        await user_repo.ban(uid, "توسط ادمین")
        await admin_log_repo.log(Config.ADMIN_ID, "ban", uid, "")
        try:
            await bot.send_message(uid, "🚫 بن شدید.")
        except Exception:
            pass
        await cb.answer("🚫")
    elif action == "unban":
        await user_repo.unban(uid)
        await admin_log_repo.log(Config.ADMIN_ID, "unban", uid, "")
        await cb.answer("✅")
    elif action == "warn":
        n = await user_repo.add_warn(uid)
        await warning_repo.add(uid, Config.ADMIN_ID, "ادمین")
        await admin_log_repo.log(Config.ADMIN_ID, "warn", uid, f"#{n}")
        try:
            await bot.send_message(uid, f"⚠️ اخطار ({n})")
        except Exception:
            pass
        await cb.answer(f"⚠️ #{n}")
    elif action == "mute":
        await user_repo.mute(uid, 60)
        await admin_log_repo.log(Config.ADMIN_ID, "mute", uid, "60m")
        await cb.answer("🔇")
    elif action == "unmute":
        await user_repo.unmute(uid)
        await cb.answer("🔊")
    elif action == "clearwarn":
        await user_repo.clear_warns(uid)
        await warning_repo.clear(uid)
        await cb.answer("🗑")
    elif action == "msg":
        await state.set_state(AdminStates.sending_to_user)
        await state.update_data(target_uid=uid)
        await cb.message.answer(with_footer(f"📨 به <code>{uid}</code>: پیام را بفرست."),
                                reply_markup=cancel_kb("global:cancel"))
        await cb.answer()


@admin_router.message(AdminStates.sending_to_user)
async def admin_send_to_user(message: Message, state: FSMContext, bot: Bot):
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    target = data.get("target_uid")
    await state.clear()
    if not target:
        return
    try:
        await bot.copy_message(target, message.chat.id, message.message_id)
        await admin_log_repo.log(Config.ADMIN_ID, "direct_msg", target, "")
        await message.answer(with_footer(f"✅ به <code>{target}</code>."),
                             reply_markup=admin_menu_kb())
    except Exception as e:
        await message.answer(f"❌ {e}", reply_markup=admin_menu_kb())


@admin_router.message(F.text == "🚫 بن‌ها")
async def admin_bans(message: Message):
    if not _is_admin(message.from_user.id):
        return
    rows = await db.fetch_all(
        "SELECT user_id, full_name, ban_reason FROM users WHERE is_banned=1 LIMIT 20")
    lines = ["🚫 <b>بن‌شده‌ها</b>\n"]
    if not rows:
        lines.append("خالی.")
    else:
        for r in rows:
            lines.append(f"• <code>{r['user_id']}</code> — {r['full_name'] or '—'} — {r['ban_reason'] or '—'}")
    lines.append("\n💡 /ban ID دلیل | /unban ID")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_router.message(Command("ban"))
async def admin_ban(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return
    args = (command.args or "").split(maxsplit=1)
    if not args or not args[0].isdigit():
        await message.answer("/ban ID دلیل")
        return
    t = int(args[0])
    reason = args[1] if len(args) > 1 else "بدون دلیل"
    await user_repo.ban(t, reason)
    await admin_log_repo.log(Config.ADMIN_ID, "ban", t, reason)
    await message.answer(f"🚫 {t} بن شد.")


@admin_router.message(Command("unban"))
async def admin_unban(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return
    a = (command.args or "").strip()
    if not a.isdigit():
        await message.answer("/unban ID")
        return
    await user_repo.unban(int(a))
    await admin_log_repo.log(Config.ADMIN_ID, "unban", int(a), "")
    await message.answer("✅")


@admin_router.message(Command("warn"))
async def admin_warn(message: Message, command: CommandObject, bot: Bot):
    if not _is_admin(message.from_user.id):
        return
    args = (command.args or "").split(maxsplit=1)
    if not args or not args[0].isdigit():
        await message.answer("/warn ID [دلیل]")
        return
    t = int(args[0])
    reason = args[1] if len(args) > 1 else "بدون دلیل"
    n = await user_repo.add_warn(t)
    await warning_repo.add(t, Config.ADMIN_ID, reason)
    await admin_log_repo.log(Config.ADMIN_ID, "warn", t, reason)
    try:
        await bot.send_message(t, f"⚠️ اخطار ({n}): {reason}")
    except Exception:
        pass
    await message.answer(f"⚠️ {t} — #{n}")


@admin_router.message(Command("unwarn"))
async def admin_unwarn(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return
    a = (command.args or "").strip()
    if not a.isdigit():
        return
    await user_repo.clear_warns(int(a))
    await warning_repo.clear(int(a))
    await message.answer("✅")


@admin_router.message(Command("mute"))
async def admin_mute(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return
    args = (command.args or "").split()
    if not args or not args[0].isdigit():
        await message.answer("/mute ID [دقیقه]")
        return
    t = int(args[0])
    mins = int(args[1]) if len(args) > 1 and args[1].isdigit() else 60
    await user_repo.mute(t, mins)
    await admin_log_repo.log(Config.ADMIN_ID, "mute", t, f"{mins}m")
    await message.answer(f"🔇 {t} — {mins}د")


@admin_router.message(Command("unmute"))
async def admin_unmute(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return
    a = (command.args or "").strip()
    if not a.isdigit():
        return
    await user_repo.unmute(int(a))
    await message.answer("✅")


@admin_router.message(F.text == "⚠️ اخطارها")
async def admin_warns_menu(message: Message):
    if not _is_admin(message.from_user.id):
        return
    rows = await db.fetch_all(
        "SELECT user_id, full_name, warn_count FROM users WHERE warn_count > 0 ORDER BY warn_count DESC LIMIT 20")
    lines = ["⚠️ <b>اخطاردار</b>\n"]
    if not rows:
        lines.append("خالی.")
    else:
        for r in rows:
            lines.append(f"• <code>{r['user_id']}</code> — {r['full_name'] or '—'} — ⚠️ {r['warn_count']}")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_router.message(F.text == "🔇 سکوت‌ها")
async def admin_mutes(message: Message):
    if not _is_admin(message.from_user.id):
        return
    rows = await db.fetch_all(
        "SELECT user_id, full_name, mute_until FROM users WHERE mute_until IS NOT NULL LIMIT 20")
    lines = ["🔇 <b>سکوت‌ها</b>\n"]
    if not rows:
        lines.append("خالی.")
    else:
        for r in rows:
            lines.append(f"• <code>{r['user_id']}</code> — تا {r['mute_until'][:16]}")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_router.message(F.text == "📝 لاگ‌ها")
async def admin_logs(message: Message):
    if not _is_admin(message.from_user.id):
        return
    logs = await admin_log_repo.recent(15)
    if not logs:
        await message.answer(with_footer("لاگی نیست."), reply_markup=admin_menu_kb())
        return
    lines = ["📝 <b>۱۵ لاگ آخر</b>\n"]
    for r in logs:
        lines.append(f"• [{r['created_at'][11:16]}] {r['action']} → {r['target_id'] or '-'}")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_router.message(Command("logs"))
async def cmd_logs(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await admin_logs(message)


@admin_router.message(F.text == "🧹 پاکسازی")
async def admin_cleanup(message: Message):
    if not _is_admin(message.from_user.id):
        return
    n = await link_repo.cleanup_onetime()
    await admin_log_repo.log(Config.ADMIN_ID, "cleanup", None, str(n))
    await message.answer(with_footer(f"🧹 {n} لینک پاک شد."), reply_markup=admin_menu_kb())


# ─── Channel ───

@admin_router.message(F.text == "🔒 کانال")
async def admin_channel(message: Message):
    if not _is_admin(message.from_user.id):
        return
    ch = await settings_repo.get_required_channel()
    text = f"🔒 <b>کانال:</b>\n<code>{ch}</code>" if ch else "🔒 کانال تنظیم نشده."
    await message.answer(with_footer(text), reply_markup=admin_channel_manage_kb(bool(ch)))


@admin_router.callback_query(F.data == "admin_ch:set")
async def admin_ch_set(cb: CallbackQuery, state: FSMContext):
    if not _is_admin(cb.from_user.id):
        return
    await state.set_state(AdminStates.setting_channel)
    try:
        await cb.message.edit_text(with_footer("🔧 <code>@channel</code> یا <code>-100...</code>"))
    except TelegramBadRequest:
        pass
    await cb.answer()


@admin_router.callback_query(F.data == "admin_ch:remove")
async def admin_ch_remove(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        return
    await settings_repo.clear_required_channel()
    try:
        await cb.message.edit_text(with_footer("🗑 حذف شد."))
    except TelegramBadRequest:
        pass
    await cb.answer("✅")


@admin_router.message(AdminStates.setting_channel)
async def admin_ch_recv(message: Message, state: FSMContext, bot: Bot):
    if not _is_admin(message.from_user.id):
        return
    raw = (message.text or "").strip()
    if re.match(r"^-?\d+$", raw):
        parsed = raw
    elif raw.startswith("@"):
        parsed = raw
    elif re.match(r"^https?://t\.me/([A-Za-z0-9_]+)/?$", raw):
        parsed = f"@{re.match(r'^https?://t\.me/([A-Za-z0-9_]+)/?$', raw).group(1)}"
    else:
        parsed = f"@{raw}" if re.match(r"^[A-Za-z0-9_]{4,}$", raw) else None
    if not parsed:
        await message.answer("❌ نامعتبر.")
        return
    try:
        await bot.get_chat(parsed)
        await bot.get_chat_member(parsed, bot.id)
    except TelegramBadRequest as e:
        await message.answer(f"❌ {e}")
        return
    await settings_repo.set_required_channel(parsed)
    await admin_log_repo.log(Config.ADMIN_ID, "set_channel", None, parsed)
    await state.clear()
    await message.answer(with_footer(f"✅ کانال: <b>{parsed}</b>"),
                         reply_markup=admin_menu_kb())


# ─── Maintenance ───

@admin_router.message(F.text == "🔧 تعمیر")
async def admin_maint(message: Message):
    if not _is_admin(message.from_user.id):
        return
    on = await settings_repo.is_maintenance()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("🟢 خاموش", S_SUCCESS, callback_data="maint:off"),
         _ibtn("🔴 روشن", S_DANGER, callback_data="maint:on")]])
    await message.answer(
        with_footer(f"🔧 تعمیر: <b>{'✅' if on else '❌'}</b>"),
        reply_markup=kb)


@admin_router.callback_query(F.data.startswith("maint:"))
async def admin_maint_toggle(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        return
    val = cb.data.split(":")[1] == "on"
    await settings_repo.set_maintenance(val)
    await admin_log_repo.log(Config.ADMIN_ID, "maintenance", None, "on" if val else "off")
    try:
        await cb.message.edit_text(
            with_footer(f"🔧 تعمیر: <b>{'✅' if val else '❌'}</b>"))
    except TelegramBadRequest:
        pass
    await cb.answer("✅")


@admin_router.message(Command("maintenance"))
async def cmd_maintenance(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return
    arg = (command.args or "").strip().lower()
    if arg not in ("on", "off"):
        await message.answer("/maintenance on|off")
        return
    val = arg == "on"
    await settings_repo.set_maintenance(val)
    await message.answer(with_footer(f"🔧: <b>{'✅' if val else '❌'}</b>"))


# ─── Backup ───

@admin_router.message(F.text == "💾 بکاپ")
async def admin_backup(message: Message, bot: Bot):
    if not _is_admin(message.from_user.id):
        return
    data = await admin_svc.backup()
    if not data:
        await message.answer("❌ خطا.")
        return
    stamp = now_iran().strftime("%Y%m%d_%H%M%S")
    f = BufferedInputFile(data, filename=f"backup_{stamp}.db")
    await bot.send_document(Config.ADMIN_ID, f, caption=with_footer("💾 بکاپ"))
    await admin_log_repo.log(Config.ADMIN_ID, "backup", None, str(len(data)))


@admin_router.message(Command("backup"))
async def cmd_backup(message: Message, bot: Bot):
    if not _is_admin(message.from_user.id):
        return
    await admin_backup(message, bot)


# ─── Broadcast ───

@admin_router.message(F.text == "📢 پیام همگانی")
async def admin_bcast(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.broadcasting)
    await message.answer(with_footer("📢 پیام را بفرست:"))


@admin_router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.broadcasting)
    await message.answer(with_footer("📢 پیام را بفرست:"))


@admin_router.message(AdminStates.broadcasting)
async def admin_bcast_recv(message: Message, state: FSMContext):
    await state.update_data(bc_chat=message.chat.id, bc_msg=message.message_id)
    await state.set_state(AdminStates.broadcasting_confirm)
    n = await user_repo.count()
    await message.answer(with_footer(f"⚠️ ارسال به {n} کاربر؟"),
                         reply_markup=confirm_kb("broadcast"))


@admin_router.callback_query(F.data == "cancel:broadcast")
async def admin_bcast_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.edit_text(with_footer("❌ لغو."))
    except TelegramBadRequest:
        pass
    await cb.answer()


@admin_router.callback_query(F.data == "confirm:broadcast")
async def admin_bcast_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot):
    d = await state.get_data()
    chat, msg = d.get("bc_chat"), d.get("bc_msg")
    await state.clear()
    if not chat or not msg:
        await cb.answer("❌", show_alert=True)
        return
    users = await user_repo.all_ids()
    try:
        await cb.message.edit_text(with_footer(f"⏳ در حال ارسال به {len(users)}..."))
    except TelegramBadRequest:
        pass
    r = await admin_svc.broadcast(bot, chat, msg, users)
    await admin_log_repo.log(Config.ADMIN_ID, "broadcast", None,
                             f"{r['success']}/{r['failed']}")
    try:
        await cb.message.edit_text(with_footer(
            f"✅\nموفق: <b>{r['success']}</b>\nناموفق: <b>{r['failed']}</b>"))
    except TelegramBadRequest:
        pass
    await cb.answer()


@admin_router.message(F.text == "📨 پیام به کاربر")
async def admin_msg_user(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.searching_user)
    await message.answer(with_footer("📨 آیدی کاربر را بفرست:"),
                         reply_markup=cancel_kb("global:cancel"))


@admin_router.message(Command("search"))
async def cmd_search(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return
    q = (command.args or "").strip()
    if not q:
        await message.answer("/search متن")
        return
    rows = await user_repo.search(q, limit=15)
    if not rows:
        await message.answer(with_footer("یافت نشد."))
        return
    lines = [f"🔍 <b>{len(rows)}</b>:\n"]
    for u in rows:
        st = "🚫" if u["is_banned"] else "✅"
        lines.append(f"{st} <code>{u['user_id']}</code> — {u['full_name'] or '—'}")
    await message.answer(with_footer("\n".join(lines)))


# ═══════════════════════════════════════════════════════════════════════
# ۱۹ ── SCHEDULER
# ═══════════════════════════════════════════════════════════════════════

scheduler = AsyncIOScheduler(timezone=IRAN_TZ)


async def job_cleanup():
    try:
        n = await link_repo.cleanup_onetime()
        if n:
            log.info("🧹 cleanup: %s links", n)
    except Exception as e:
        log.exception("cleanup: %s", e)


async def job_last_seen():
    try:
        await db.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP")
    except Exception as e:
        log.exception("last_seen: %s", e)


async def job_scheduled_messages(bot: Bot):
    """ارسال پیام‌های زمان‌بندی‌شده."""
    try:
        due = await scheduled_repo.due()
        for s in due:
            try:
                if s["content_type"] == "text":
                    await bot.send_message(s["owner_id"], with_footer(
                        f"⏰ <b>پیام زمان‌بندی‌شده</b>\n\n{s['content'] or ''}"))
                elif s["content_type"] == "photo":
                    await bot.send_photo(s["owner_id"], s["file_id"],
                                          caption=with_footer("⏰ پیام زمان‌بندی‌شده"))
                else:
                    await bot.send_message(s["owner_id"], with_footer("⏰ پیام زمان‌بندی‌شده"))
                await scheduled_repo.mark_sent(s["id"])
            except Exception:
                pass
    except Exception as e:
        log.exception("scheduled: %s", e)


async def job_daily_stats():
    try:
        active = await user_repo.count_active_24h()
        await stats_repo.bump("active_users", 0)
        today = now_iran().date().isoformat()
        await db.execute(
            """INSERT INTO daily_stats (date, active_users) VALUES (?, ?)
               ON CONFLICT(date) DO UPDATE SET active_users=?""",
            (today, active, active))
    except Exception as e:
        log.exception("daily_stats: %s", e)


# ═══════════════════════════════════════════════════════════════════════
# ۲۰ ── HEALTH CHECK SERVER (asyncio)
# ═══════════════════════════════════════════════════════════════════════

async def health_server():
    """Simple HTTP health check server."""
    async def handle(reader, writer):
        try:
            await reader.read(1024)
            stats = cache.stats()
            body = json.dumps({
                "status": "ok",
                "time": now_iran().isoformat(),
                "cache": stats,
                "match_queue": match_svc.size(),
            })
            resp = (f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n\r\n{body}")
            writer.write(resp.encode())
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    try:
        server = await asyncio.start_server(handle, "0.0.0.0", Config.HEALTH_PORT)
        log.info("🏥 Health: http://0.0.0.0:%d", Config.HEALTH_PORT)
        async with server:
            await server.serve_forever()
    except Exception as e:
        log.error("Health server error: %s", e)


# ═══════════════════════════════════════════════════════════════════════
# ۲۱ ── MAIN
# ═══════════════════════════════════════════════════════════════════════

bot: Optional[Bot] = None
dp: Optional[Dispatcher] = None
health_task: Optional[asyncio.Task] = None


async def on_startup(bot: Bot, **kwargs):
    log.info("🚀 Bot starting...")
    me = await bot.get_me()
    Config.BOT_USERNAME = me.username or Config.BOT_USERNAME
    log.info("🤖 @%s | 👑 Admin: %s", me.username, Config.ADMIN_ID)
    ch = await settings_repo.get_required_channel()
    log.info("🔒 Channel: %s", ch or "—")
    _, _, _, hh, mm, ss, _ = now_shamsi()
    try:
        await bot.send_message(
            Config.ADMIN_ID,
            f"✅ ربات v9.0 راه‌اندازی شد.\n@{me.username}\n"
            f"🕐 {hh:02d}:{mm:02d}:{ss:02d}\n"
            f"🧠 AI Moderation: ON\n"
            f"📊 Analytics: ON\n"
            f"🎖 Gamification: ON")
    except Exception:
        pass


async def on_shutdown(bot: Bot = None, **kwargs):
    log.info("🛑 Shutting down...")
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass
    try:
        if health_task and not health_task.done():
            health_task.cancel()
    except Exception:
        pass
    await db.close()
    if bot:
        try:
            await bot.session.close()
        except Exception:
            pass


async def main():
    global bot, dp, health_task
    Config.validate()
    await db.connect()

    bot = Bot(token=Config.BOT_TOKEN,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares
    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())
    dp.message.middleware(JoinCheckMiddleware())
    dp.callback_query.middleware(JoinCheckMiddleware())
    dp.message.middleware(RateLimitMiddleware())

    # Routers
    dp.include_router(admin_router)
    dp.include_router(lang_router)
    dp.include_router(rules_router)
    dp.include_router(profile_router)
    dp.include_router(avatar_router)
    dp.include_router(settings_router)
    dp.include_router(target_router)
    dp.include_router(match_router)
    dp.include_router(room_router)
    dp.include_router(gamif_router)
    dp.include_router(link_router)
    dp.include_router(anon_router)
    dp.include_router(common_router)

    # Scheduler
    scheduler.add_job(job_cleanup, "interval", hours=1, id="cleanup")
    scheduler.add_job(job_last_seen, "interval", minutes=5, id="last_seen")
    scheduler.add_job(job_scheduled_messages, "interval", minutes=1,
                      args=[bot], id="scheduled_msgs")
    scheduler.add_job(job_daily_stats, "interval", hours=6, id="daily_stats")
    scheduler.start()
    log.info("⏰ Scheduler active (Asia/Tehran)")

    # Health server
    health_task = asyncio.create_task(health_server())

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
        log.info("👋 Bye")
