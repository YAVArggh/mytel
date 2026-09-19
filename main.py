"""
═══════════════════════════════════════════════════════════════════════════
🧠 ANONYMOUS AI BOT — v11.1 FINAL ULTRA
═══════════════════════════════════════════════════════════════════════════
Complete Features:
  • Welcome Experience with user name + Iran time + greeting
  • Age grid (9-99) all Success style with color-coded emojis
  • Complete Iran Data (31 provinces, 700+ cities) with search + pagination
  • Complete Admin Panel with 30+ actions
  • Daily Bonus, Achievements, Level System, Leaderboard, Coins
  • Bidirectional Anonymous Chat + Reply + Block List
  • Dating (دوستیابی) with swipe UI + Match System + Chat
  • Mini Games: Dice, Coinflip, Guess, Dart, RPS
  • Feedback, Report, Favorites, Profile Views
  • Smart Match, Rooms, Target-Chat, Referral, Analytics
  • Local AI Moderation (Persian + English)
  • Health Check + Metrics + Backup
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import asyncio
import hashlib
import math
import os
import random
import re
import secrets
import sys
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
import logging
from typing import Any, Optional
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
    STYLE_OK = True
except ImportError:
    ButtonStyle = None
    STYLE_OK = False


# ═══════════════════════════════════════════════════════════════════════
# ۱ ── CONFIG
# ═══════════════════════════════════════════════════════════════════════

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "8885016188:AAHCwWCG7B7_CbJ5Tk4bDY70vn3hws-H6ek")
    ADMIN_ID = int(os.getenv("ADMIN_ID", "8094551428"))
    BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBot")
    DB_PATH = os.getenv("DB_PATH", "anon_v11.db")
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-please-32chars")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = "logs/bot_v11.log"
    HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8080"))

    RATE_CAPACITY = 40
    RATE_REFILL = 0.7
    CACHE_SIZE = 20_000
    CACHE_TTL = 300
    TOXICITY_THRESHOLD = 0.6
    SPAM_THRESHOLD = 0.7

    XP_MSG_RECEIVED = 2
    XP_MSG_SENT = 1
    XP_REFERRAL = 25
    XP_LIKE = 3
    XP_MATCH = 10
    XP_DAILY = 15

    DAILY_REWARDS = [10, 15, 20, 25, 30, 50, 100]

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
# ۲ ── LOGGER
# ═══════════════════════════════════════════════════════════════════════

def setup_logger():
    os.makedirs(os.path.dirname(Config.LOG_FILE) or ".", exist_ok=True)
    lg = logging.getLogger("anon_v11")
    lg.setLevel(getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))
    lg.propagate = False
    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    if not lg.handlers:
        fh = RotatingFileHandler(Config.LOG_FILE, maxBytes=10 * 1024 * 1024,
                                 backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        lg.addHandler(fh)
        lg.addHandler(ch)
    return lg


log = setup_logger()


# ═══════════════════════════════════════════════════════════════════════
# ۳ ── TIME / JALALI
# ═══════════════════════════════════════════════════════════════════════

IRAN_TZ = ZoneInfo("Asia/Tehran")
WEEKDAYS_FA = ["شنبه", "یک‌شنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"]
MONTHS_FA = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
             "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]


def now_iran() -> datetime:
    return datetime.now(IRAN_TZ)


def to_jalali(gy, gm, gd):
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
    jy, jm, jd = to_jalali(n.year, n.month, n.day)
    fa_wd = (n.weekday() + 2) % 7
    return jy, jm, jd, n.hour, n.minute, n.second, fa_wd


def fa_now_str():
    jy, jm, jd, hh, mm, ss, wd = now_shamsi()
    return f"🕐 {hh:02d}:{mm:02d}  |  📅 {WEEKDAYS_FA[wd]} {jd} {MONTHS_FA[jm - 1]} {jy}"


def fa_now_full():
    jy, jm, jd, hh, mm, ss, wd = now_shamsi()
    return (f"🇮🇷 <b>ساعت ایران</b>\n"
            f"🕐 <code>{hh:02d}:{mm:02d}:{ss:02d}</code>\n"
            f"📅 {WEEKDAYS_FA[wd]} {jd} {MONTHS_FA[jm - 1]} {jy}")


def with_footer(t):
    return f"{t}\n\n━━━━━━━━━━━━━━━━━━\n{fa_now_str()}"


def greeting_by_hour():
    h = now_iran().hour
    if 5 <= h < 12:
        return "صبح‌ بخیر ☀️"
    if 12 <= h < 17:
        return "ظهر بخیر 🌤"
    if 17 <= h < 20:
        return "عصر بخیر 🌆"
    return "شب بخیر 🌙"


# ═══════════════════════════════════════════════════════════════════════
# ۴ ── CACHE
# ═══════════════════════════════════════════════════════════════════════

class TTLCache:
    def __init__(self, max_size, default_ttl):
        self._d: dict[str, tuple[Any, float]] = {}
        self._max = max_size
        self._ttl = default_ttl
        self._hits = self._misses = self._evict = 0
        self._lock = asyncio.Lock()

    async def get(self, k):
        async with self._lock:
            item = self._d.get(k)
            if not item:
                self._misses += 1
                return None
            v, exp = item
            if exp < time.monotonic():
                self._d.pop(k, None)
                self._misses += 1
                return None
            self._hits += 1
            return v

    async def set(self, k, v, ttl=None):
        async with self._lock:
            if len(self._d) >= self._max:
                oldest = min(self._d.items(), key=lambda x: x[1][1])
                self._d.pop(oldest[0], None)
                self._evict += 1
            self._d[k] = (v, time.monotonic() + (ttl or self._ttl))

    async def delete(self, k):
        async with self._lock:
            self._d.pop(k, None)

    async def flush(self):
        async with self._lock:
            self._d.clear()

    def stats(self):
        t = self._hits + self._misses
        return {"size": len(self._d), "hits": self._hits, "misses": self._misses,
                "evictions": self._evict,
                "hit_rate": round(self._hits / t, 3) if t else 0.0}


cache = TTLCache(Config.CACHE_SIZE, Config.CACHE_TTL)


# ═══════════════════════════════════════════════════════════════════════
# ۵ ── SECURITY
# ═══════════════════════════════════════════════════════════════════════

def gen_token(n=16):
    return secrets.token_urlsafe(n)


def hash_uid(uid):
    return hashlib.sha256(f"{Config.SECRET_KEY}:{uid}".encode()).hexdigest()[:12]


# ═══════════════════════════════════════════════════════════════════════
# ۶ ── MODERATION
# ═══════════════════════════════════════════════════════════════════════

class ModerationEngine:
    PROF_EN = {"fuck", "fucking", "shit", "bitch", "asshole", "bastard",
               "cunt", "dick", "pussy", "whore", "slut"}
    PROF_FA = [
        re.compile(r"ک[\u200c]?ی[\u200c]?ر", re.I),
        re.compile(r"ج[\u200c]?ا[\u200c]?ق", re.I),
        re.compile(r"خ[\u200c]?ر", re.I),
        re.compile(r"ع[\u200c]?و[\u200c]?ض", re.I),
        re.compile(r"م[\u200c]?ا[\u200c]?د[\u200c]?ر", re.I),
        re.compile(r"ل[\u200c]?ا[\u200c]?ط", re.I),
    ]
    URL_RE = re.compile(r"(https?://\S+|t\.me/\S+|@\w{4,})")
    REP_RE = re.compile(r"(.)\1{7,}")
    PHONE_RE = re.compile(r"\b09\d{9}\b|\b\+98\d{10}\b")

    def analyze(self, text):
        if not text:
            return self._empty()
        low = text.lower()
        flags = []
        prof = sum(1 for w in self.PROF_EN if w in low) + \
               sum(1 for p in self.PROF_FA if p.search(text))
        if prof:
            flags.append("profanity")
        urls = self.URL_RE.findall(text)
        if len(urls) >= 5:
            flags.append("url_flood")
        elif len(urls) >= 3:
            flags.append("url_many")
        if self.PHONE_RE.search(text):
            flags.append("phone")
        if self.REP_RE.search(text):
            flags.append("repetition")
        if len(text) > 15 and text.isascii() and text.isupper():
            flags.append("caps")
        tox = min(1.0, prof * 0.35 + (0.2 if "phone" in flags else 0))
        spam = 0.0
        if "url_flood" in flags:
            spam += 0.6
        elif "url_many" in flags:
            spam += 0.3
        if "repetition" in flags:
            spam += 0.3
        if "caps" in flags:
            spam += 0.15
        return {"toxicity": round(tox, 3), "spam": round(min(1.0, spam), 3),
                "flags": flags, "word_count": len(text.split())}

    def _empty(self):
        return {"toxicity": 0.0, "spam": 0.0, "flags": [], "word_count": 0}

    def is_flagged(self, a):
        return (a["toxicity"] >= Config.TOXICITY_THRESHOLD or
                a["spam"] >= Config.SPAM_THRESHOLD)


moderation = ModerationEngine()


# ═══════════════════════════════════════════════════════════════════════
# ۷ ── GAMIFICATION
# ═══════════════════════════════════════════════════════════════════════

class Badges:
    EARLY = ("🌱", "Early Adopter", "از اولین کاربران")
    CHATTER = ("💬", "Chatter", "بیش از 100 پیام")
    POPULAR = ("⭐", "Popular", "بیش از 50 پیام دریافتی")
    MATCHMAKER = ("🎯", "Matchmaker", "بیش از 20 مچ")
    SOCIAL = ("🤝", "Social", "بیش از 10 دعوت موفق")
    VERIFIED = ("✅", "Verified", "پروفایل کامل")
    LOVER = ("💖", "Lover", "بیش از 10 لایک دوستیابی")
    GAMER = ("🎮", "Gamer", "بیش از 20 برد در بازی‌ها")
    RICH = ("💰", "Rich", "بیش از 1000 XP")
    LEGEND = ("👑", "Legend", "سطح 20 یا بالاتر")
    ALL = [EARLY, CHATTER, POPULAR, MATCHMAKER, SOCIAL, VERIFIED, LOVER, GAMER, RICH, LEGEND]


def level_from_xp(xp):
    return int(math.sqrt(max(0, xp) / 100)) + 1


def xp_for_level(lvl):
    return max(0, (lvl - 1) ** 2 * 100)


def progress_bar(cur, total, w=12):
    if total <= 0:
        return "▱" * w
    filled = min(w, int(w * cur / total))
    return "▰" * filled + "▱" * (w - filled)


# ═══════════════════════════════════════════════════════════════════════
# ۸ ── DATABASE
# ═══════════════════════════════════════════════════════════════════════

SCHEMA_VERSION = 7

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    full_name TEXT, username TEXT, language TEXT DEFAULT 'fa',
    rules_accepted INTEGER DEFAULT 0,
    is_banned INTEGER DEFAULT 0, ban_reason TEXT,
    warn_count INTEGER DEFAULT 0, mute_until TIMESTAMP,
    message_count INTEGER DEFAULT 0, link_count INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, coins INTEGER DEFAULT 0,
    karma INTEGER DEFAULT 0, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
    referrer_id INTEGER, referral_code TEXT UNIQUE,
    last_daily_bonus DATE, daily_streak INTEGER DEFAULT 0,
    games_played INTEGER DEFAULT 0, profile_views INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_referrer ON users(referrer_id);
CREATE INDEX IF NOT EXISTS idx_users_xp ON users(xp DESC);

CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER PRIMARY KEY,
    gender TEXT NOT NULL, age INTEGER NOT NULL,
    province TEXT NOT NULL, city TEXT NOT NULL,
    avatar_url TEXT, bio TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    web_mode INTEGER DEFAULT 0, silent_mode INTEGER DEFAULT 0,
    copyright_mode INTEGER DEFAULT 0, read_receipt INTEGER DEFAULT 1,
    auto_translate INTEGER DEFAULT 0, hide_online INTEGER DEFAULT 0,
    auto_delete INTEGER DEFAULT 0, notify_match INTEGER DEFAULT 1,
    notify_msg INTEGER DEFAULT 1, notify_dating INTEGER DEFAULT 1,
    theme TEXT DEFAULT 'dark',
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS anonymous_links (
    token TEXT PRIMARY KEY, owner_id INTEGER NOT NULL,
    link_type TEXT NOT NULL DEFAULT 'onetime',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_used INTEGER DEFAULT 0, used_at TIMESTAMP,
    used_by INTEGER, use_count INTEGER DEFAULT 0,
    FOREIGN KEY(owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_links_owner ON anonymous_links(owner_id);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL, sender_id INTEGER NOT NULL,
    sender_token TEXT, content TEXT, content_type TEXT DEFAULT 'text',
    file_id TEXT, toxicity REAL DEFAULT 0, sentiment REAL DEFAULT 0,
    conversation_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_msg_owner ON messages(owner_id);

CREATE TABLE IF NOT EXISTS anon_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL, sender_id INTEGER NOT NULL,
    token TEXT, active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner_id, sender_id)
);

CREATE TABLE IF NOT EXISTS blocked_users (
    user_id INTEGER NOT NULL, blocked_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id, blocked_id)
);

CREATE TABLE IF NOT EXISTS favorites (
    user_id INTEGER NOT NULL, fav_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id, fav_id)
);

CREATE TABLE IF NOT EXISTS target_chats (
    token TEXT PRIMARY KEY, creator_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL, active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pairings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user1_id INTEGER NOT NULL, user2_id INTEGER NOT NULL,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, ended_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL, action TEXT NOT NULL,
    target_id INTEGER, details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, admin_id INTEGER NOT NULL,
    reason TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id INTEGER NOT NULL, reported_id INTEGER,
    message_id INTEGER, reason TEXT,
    status TEXT DEFAULT 'pending',
    reviewed_by INTEGER, reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, badge TEXT NOT NULL,
    earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, badge)
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date DATE PRIMARY KEY,
    new_users INTEGER DEFAULT 0, messages_sent INTEGER DEFAULT 0,
    matches INTEGER DEFAULT 0, active_users INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0, games INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rooms (
    id TEXT PRIMARY KEY, name TEXT NOT NULL,
    owner_id INTEGER NOT NULL, max_members INTEGER DEFAULT 10,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS room_members (
    room_id TEXT NOT NULL, user_id INTEGER NOT NULL,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(room_id, user_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY, value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dating_likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    liker_id INTEGER NOT NULL, target_id INTEGER NOT NULL,
    is_like INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(liker_id, target_id)
);

CREATE TABLE IF NOT EXISTS dating_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user1_id INTEGER NOT NULL, user2_id INTEGER NOT NULL,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dating_prefs (
    user_id INTEGER PRIMARY KEY,
    pref_gender TEXT DEFAULT 'any',
    pref_min_age INTEGER DEFAULT 18,
    pref_max_age INTEGER DEFAULT 40,
    pref_same_city INTEGER DEFAULT 0,
    pref_same_province INTEGER DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, text TEXT NOT NULL,
    status TEXT DEFAULT 'new',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    _instance = None
    _conn = None
    _lock = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _l(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def _col_exists(self, t, c):
        try:
            cur = await self._conn.execute(f"PRAGMA table_info({t})")
            rows = await cur.fetchall()
            await cur.close()
            return any(r[1] == c for r in rows)
        except Exception:
            return False

    async def connect(self):
        async with self._l():
            if self._conn is not None:
                return
            self._conn = await aiosqlite.connect(Config.DB_PATH)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.executescript(SCHEMA_SQL)
            await self._conn.commit()
            await self._migrate()
            log.info("✅ DB ready: %s (v%d)", Config.DB_PATH, SCHEMA_VERSION)

    async def _migrate(self):
        cur = await self._conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = await cur.fetchone()
        await cur.close()
        cur_v = row["version"] if row else 0
        if cur_v == 0:
            await self._conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        elif cur_v < SCHEMA_VERSION:
            log.info("🔧 migrate %d → %d", cur_v, SCHEMA_VERSION)
        await self._ensure_columns()
        if cur_v < SCHEMA_VERSION:
            await self._conn.execute("UPDATE schema_version SET version=?", (SCHEMA_VERSION,))
        await self._conn.commit()

    async def _ensure_columns(self):
        cols_users = [("coins", 0), ("karma", 0), ("wins", 0), ("losses", 0),
                      ("games_played", 0), ("daily_streak", 0), ("profile_views", 0)]
        for c, d in cols_users:
            if not await self._col_exists("users", c):
                try:
                    await self._conn.execute(f"ALTER TABLE users ADD COLUMN {c} INTEGER DEFAULT {d}")
                except Exception:
                    pass
        cols_set = [("notify_dating", 1), ("hide_online", 0), ("auto_delete", 0)]
        for c, d in cols_set:
            if not await self._col_exists("user_settings", c):
                try:
                    await self._conn.execute(
                        f"ALTER TABLE user_settings ADD COLUMN {c} INTEGER DEFAULT {d}")
                except Exception:
                    pass
        if not await self._col_exists("user_settings", "theme"):
            try:
                await self._conn.execute(
                    "ALTER TABLE user_settings ADD COLUMN theme TEXT DEFAULT 'dark'")
            except Exception:
                pass
        if not await self._col_exists("messages", "conversation_id"):
            try:
                await self._conn.execute(
                    "ALTER TABLE messages ADD COLUMN conversation_id INTEGER")
            except Exception:
                pass
        if not await self._col_exists("daily_stats", "likes"):
            try:
                await self._conn.execute(
                    "ALTER TABLE daily_stats ADD COLUMN likes INTEGER DEFAULT 0")
            except Exception:
                pass
        if not await self._col_exists("daily_stats", "games"):
            try:
                await self._conn.execute(
                    "ALTER TABLE daily_stats ADD COLUMN games INTEGER DEFAULT 0")
            except Exception:
                pass

    async def close(self):
        async with self._l():
            if self._conn:
                try:
                    await self._conn.close()
                except Exception:
                    pass
                self._conn = None

    @property
    def conn(self):
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
        return default if not r else list(r)[0]


db = Database()


# ═══════════════════════════════════════════════════════════════════════
# ۹ ── REPOSITORIES
# ═══════════════════════════════════════════════════════════════════════

class UserRepo:
    async def create(self, uid, fn, un, ref_id=None):
        code = secrets.token_urlsafe(8)
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, full_name, username, referral_code, referrer_id) VALUES (?,?,?,?,?)",
            (uid, fn, un, code, ref_id))

    async def get(self, uid):
        c = await cache.get(f"u:{uid}")
        if c is not None:
            return c
        r = await db.fetch_one("SELECT * FROM users WHERE user_id=?", (uid,))
        if r:
            await cache.set(f"u:{uid}", r, 60)
        return r

    async def invalidate(self, uid):
        await cache.delete(f"u:{uid}")

    async def exists(self, uid):
        return bool(await db.fetch_one("SELECT 1 FROM users WHERE user_id=?", (uid,)))

    async def update_profile(self, uid, fn, un):
        await db.execute(
            "UPDATE users SET full_name=?, username=?, last_seen=CURRENT_TIMESTAMP WHERE user_id=?",
            (fn, un, uid))
        await self.invalidate(uid)

    async def set_language(self, uid, lang):
        await db.execute("UPDATE users SET language=? WHERE user_id=?", (lang, uid))
        await self.invalidate(uid)

    async def accept_rules(self, uid):
        await db.execute("UPDATE users SET rules_accepted=1 WHERE user_id=?", (uid,))
        await self.invalidate(uid)

    async def ban(self, uid, reason):
        await db.execute("UPDATE users SET is_banned=1, ban_reason=? WHERE user_id=?",
                         (reason, uid))
        await self.invalidate(uid)

    async def unban(self, uid):
        await db.execute("UPDATE users SET is_banned=0, ban_reason=NULL WHERE user_id=?",
                         (uid,))
        await self.invalidate(uid)

    async def add_warn(self, uid):
        await db.execute("UPDATE users SET warn_count=warn_count+1 WHERE user_id=?", (uid,))
        await self.invalidate(uid)
        return int(await db.fetch_val("SELECT warn_count FROM users WHERE user_id=?", (uid,), 0))

    async def clear_warns(self, uid):
        await db.execute("UPDATE users SET warn_count=0 WHERE user_id=?", (uid,))
        await self.invalidate(uid)

    async def mute(self, uid, mins):
        until = (now_iran() + timedelta(minutes=mins)).isoformat()
        await db.execute("UPDATE users SET mute_until=? WHERE user_id=?", (until, uid))
        await self.invalidate(uid)

    async def unmute(self, uid):
        await db.execute("UPDATE users SET mute_until=NULL WHERE user_id=?", (uid,))
        await self.invalidate(uid)

    async def is_muted(self, uid):
        r = await db.fetch_one("SELECT mute_until FROM users WHERE user_id=?", (uid,))
        if not r or not r["mute_until"]:
            return False, None
        try:
            u = datetime.fromisoformat(r["mute_until"])
            if u.tzinfo is None:
                u = u.replace(tzinfo=IRAN_TZ)
            if now_iran() < u:
                return True, r["mute_until"]
        except Exception:
            pass
        return False, None

    async def add_xp(self, uid, amount):
        cur = await db.fetch_one("SELECT xp, level FROM users WHERE user_id=?", (uid,))
        if not cur:
            return 0, 1, False
        new_xp = cur["xp"] + amount
        new_lvl = level_from_xp(new_xp)
        leveled = new_lvl > cur["level"]
        await db.execute("UPDATE users SET xp=?, level=? WHERE user_id=?",
                         (new_xp, new_lvl, uid))
        await self.invalidate(uid)
        return new_xp, new_lvl, leveled

    async def add_coins(self, uid, amount):
        await db.execute(
            "UPDATE users SET coins = MAX(0, coins + ?) WHERE user_id=?", (amount, uid))
        await self.invalidate(uid)
        return int(await db.fetch_val("SELECT coins FROM users WHERE user_id=?", (uid,), 0))

    async def inc_msg(self, uid):
        await db.execute(
            "UPDATE users SET message_count=message_count+1 WHERE user_id=?", (uid,))
        await self.invalidate(uid)

    async def inc_link(self, uid):
        await db.execute(
            "UPDATE users SET link_count=link_count+1 WHERE user_id=?", (uid,))
        await self.invalidate(uid)

    async def inc_views(self, uid):
        await db.execute(
            "UPDATE users SET profile_views=profile_views+1 WHERE user_id=?", (uid,))
        await self.invalidate(uid)

    async def inc_wins(self, uid):
        await db.execute(
            "UPDATE users SET wins=wins+1, games_played=games_played+1 WHERE user_id=?",
            (uid,))
        await self.invalidate(uid)

    async def inc_losses(self, uid):
        await db.execute(
            "UPDATE users SET losses=losses+1, games_played=games_played+1 WHERE user_id=?",
            (uid,))
        await self.invalidate(uid)

    async def claim_daily(self, uid):
        today = now_iran().date().isoformat()
        u = await self.get(uid)
        if not u:
            return None
        if u["last_daily_bonus"] == today:
            return "already"
        streak = u["daily_streak"] or 0
        try:
            last = datetime.fromisoformat(u["last_daily_bonus"]) if u["last_daily_bonus"] else None
            if last and (now_iran().date() - last.date()).days == 1:
                streak += 1
            else:
                streak = 1
        except Exception:
            streak = 1
        reward = random.choice(Config.DAILY_REWARDS) + (streak * 2)
        await db.execute(
            "UPDATE users SET last_daily_bonus=?, daily_streak=?, coins=coins+? WHERE user_id=?",
            (today, streak, reward, uid))
        await self.invalidate(uid)
        return {"reward": reward, "streak": streak}

    async def all_ids(self):
        rows = await db.fetch_all("SELECT user_id FROM users WHERE is_banned=0")
        return [int(r["user_id"]) for r in rows]

    async def count(self):
        return int(await db.fetch_val("SELECT COUNT(*) FROM users", (), 0))

    async def count_banned(self):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM users WHERE is_banned=1", (), 0))

    async def count_today(self):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM users WHERE date(created_at)=date('now')", (), 0))

    async def count_active_24h(self):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM users WHERE datetime(last_seen) > datetime('now','-1 day')",
            (), 0))

    async def count_muted(self):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM users WHERE mute_until IS NOT NULL AND mute_until > CURRENT_TIMESTAMP",
            (), 0))

    async def get_all(self, limit=20, offset=0):
        return await db.fetch_all(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset))

    async def search(self, q, limit=15):
        qq = f"%{q}%"
        return await db.fetch_all(
            "SELECT * FROM users WHERE CAST(user_id AS TEXT) LIKE ? OR full_name LIKE ? OR username LIKE ? ORDER BY last_seen DESC LIMIT ?",
            (qq, qq, qq, limit))

    async def top_xp(self, n=10):
        return await db.fetch_all(
            "SELECT user_id, full_name, xp, level, coins FROM users WHERE is_banned=0 ORDER BY xp DESC LIMIT ?",
            (n,))

    async def top_coins(self, n=10):
        return await db.fetch_all(
            "SELECT user_id, full_name, coins FROM users WHERE is_banned=0 ORDER BY coins DESC LIMIT ?",
            (n,))

    async def top_wins(self, n=10):
        return await db.fetch_all(
            "SELECT user_id, full_name, wins FROM users WHERE is_banned=0 ORDER BY wins DESC LIMIT ?",
            (n,))


class ProfileRepo:
    async def create(self, uid, gender, age, province, city, avatar):
        await db.execute(
            """INSERT INTO profiles (user_id, gender, age, province, city, avatar_url) VALUES (?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET gender=excluded.gender, age=excluded.age,
                 province=excluded.province, city=excluded.city,
                 avatar_url=excluded.avatar_url, updated_at=CURRENT_TIMESTAMP""",
            (uid, gender, age, province, city, avatar))

    async def get(self, uid):
        return await db.fetch_one("SELECT * FROM profiles WHERE user_id=?", (uid,))

    async def set_avatar(self, uid, a):
        await db.execute(
            "UPDATE profiles SET avatar_url=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
            (a, uid))

    async def random_discover(self, my_uid, pref_g, min_a, max_a, same_city,
                              same_prov, my_city, my_prov, limit=20):
        cond = ["p.user_id != ?", "p.age BETWEEN ? AND ?", "u.is_banned = 0",
                "p.user_id NOT IN (SELECT target_id FROM dating_likes WHERE liker_id = ?)"]
        p = [my_uid, min_a, max_a, my_uid]
        if pref_g != "any":
            cond.append("p.gender = ?")
            p.append(pref_g)
        if same_city:
            cond.append("p.city = ?")
            p.append(my_city)
        elif same_prov:
            cond.append("p.province = ?")
            p.append(my_prov)
        sql = f"""SELECT p.*, u.full_name, u.xp, u.level FROM profiles p
                  JOIN users u ON u.user_id = p.user_id WHERE {' AND '.join(cond)}
                  ORDER BY RANDOM() LIMIT ?"""
        p.append(limit)
        return await db.fetch_all(sql, tuple(p))


class UserSettingsRepo:
    ALLOWED = ("web_mode", "silent_mode", "copyright_mode", "read_receipt",
               "auto_translate", "hide_online", "auto_delete", "notify_match",
               "notify_msg", "notify_dating")

    async def ensure(self, uid):
        await db.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (uid,))

    async def get(self, uid):
        await self.ensure(uid)
        return await db.fetch_one("SELECT * FROM user_settings WHERE user_id=?", (uid,))

    async def toggle(self, uid, f):
        if f not in self.ALLOWED:
            raise ValueError("invalid")
        await self.ensure(uid)
        await db.execute(f"UPDATE user_settings SET {f} = 1 - {f} WHERE user_id=?", (uid,))
        return int(await db.fetch_val(
            f"SELECT {f} FROM user_settings WHERE user_id=?", (uid,), 0))

    async def set_theme(self, uid, theme):
        if theme not in ("dark", "light"):
            return
        await self.ensure(uid)
        await db.execute("UPDATE user_settings SET theme=? WHERE user_id=?", (theme, uid))


class LinkRepo:
    async def create(self, token, owner, ltype):
        await db.execute(
            "INSERT INTO anonymous_links (token, owner_id, link_type) VALUES (?,?,?)",
            (token, owner, ltype))

    async def get(self, token):
        return await db.fetch_one("SELECT * FROM anonymous_links WHERE token=?", (token,))

    async def mark_used(self, token, user):
        await db.execute(
            "UPDATE anonymous_links SET is_used=1, used_at=CURRENT_TIMESTAMP, used_by=?, use_count=use_count+1 WHERE token=?",
            (user, token))

    async def delete(self, token):
        await db.execute("DELETE FROM anonymous_links WHERE token=?", (token,))

    async def of_owner(self, uid):
        return await db.fetch_all(
            "SELECT * FROM anonymous_links WHERE owner_id=? ORDER BY created_at DESC", (uid,))

    async def count_active(self):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM anonymous_links WHERE link_type='permanent' OR is_used=0",
            (), 0))

    async def count_total(self):
        return int(await db.fetch_val("SELECT COUNT(*) FROM anonymous_links", (), 0))

    async def cleanup(self):
        c = await db.execute(
            "DELETE FROM anonymous_links WHERE link_type='onetime' AND is_used=1")
        return c.rowcount or 0


class MessageRepo:
    async def create(self, owner, sender, token, content, ctype, fid,
                     tox=0.0, sent=0.0, cid=None):
        c = await db.execute(
            "INSERT INTO messages (owner_id, sender_id, sender_token, content, content_type, file_id, toxicity, sentiment, conversation_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (owner, sender, token, content, ctype, fid, tox, sent, cid))
        return c.lastrowid or 0

    async def count_total(self):
        return int(await db.fetch_val("SELECT COUNT(*) FROM messages", (), 0))

    async def count_for(self, owner):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM messages WHERE owner_id=?", (owner,), 0))

    async def count_today(self):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM messages WHERE date(created_at)=date('now')", (), 0))

    async def count_flagged(self):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM messages WHERE date(created_at)=date('now') AND toxicity >= ?",
            (Config.TOXICITY_THRESHOLD,), 0))


class ConversationRepo:
    async def get_or_create(self, owner, sender, token):
        r = await db.fetch_one(
            "SELECT id FROM anon_conversations WHERE owner_id=? AND sender_id=?",
            (owner, sender))
        if r:
            await db.execute(
                "UPDATE anon_conversations SET last_activity=CURRENT_TIMESTAMP WHERE id=?",
                (r["id"],))
            return int(r["id"])
        c = await db.execute(
            "INSERT INTO anon_conversations (owner_id, sender_id, token) VALUES (?,?,?)",
            (owner, sender, token))
        return int(c.lastrowid or 0)

    async def get(self, cid):
        return await db.fetch_one("SELECT * FROM anon_conversations WHERE id=?", (cid,))

    async def end(self, cid):
        await db.execute("UPDATE anon_conversations SET active=0 WHERE id=?", (cid,))

    async def count_total(self):
        return int(await db.fetch_val("SELECT COUNT(*) FROM anon_conversations", (), 0))

    async def count_active(self):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM anon_conversations WHERE active=1", (), 0))


class BlockRepo:
    async def block(self, uid, target):
        try:
            await db.execute(
                "INSERT INTO blocked_users (user_id, blocked_id) VALUES (?,?)", (uid, target))
            return True
        except aiosqlite.IntegrityError:
            return False

    async def unblock(self, uid, target):
        await db.execute("DELETE FROM blocked_users WHERE user_id=? AND blocked_id=?",
                         (uid, target))

    async def is_blocked(self, uid, target):
        return bool(await db.fetch_one(
            "SELECT 1 FROM blocked_users WHERE user_id=? AND blocked_id=?", (uid, target)))

    async def list(self, uid):
        return await db.fetch_all("SELECT blocked_id FROM blocked_users WHERE user_id=?", (uid,))


class FavRepo:
    async def add(self, uid, target):
        try:
            await db.execute("INSERT INTO favorites (user_id, fav_id) VALUES (?,?)",
                             (uid, target))
            return True
        except aiosqlite.IntegrityError:
            return False

    async def remove(self, uid, target):
        await db.execute("DELETE FROM favorites WHERE user_id=? AND fav_id=?", (uid, target))

    async def list(self, uid):
        return await db.fetch_all("SELECT fav_id FROM favorites WHERE user_id=?", (uid,))


class TargetRepo:
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
    async def create(self, u1, u2):
        c = await db.execute(
            "INSERT INTO pairings (user1_id, user2_id) VALUES (?,?)", (u1, u2))
        return c.lastrowid or 0

    async def active_for(self, uid):
        return await db.fetch_one(
            "SELECT * FROM pairings WHERE active=1 AND (user1_id=? OR user2_id=?) ORDER BY id DESC LIMIT 1",
            (uid, uid))

    async def end(self, pid):
        await db.execute(
            "UPDATE pairings SET active=0, ended_at=CURRENT_TIMESTAMP WHERE id=?", (pid,))

    async def count_total(self):
        return int(await db.fetch_val("SELECT COUNT(*) FROM pairings", (), 0))

    async def count_active(self):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM pairings WHERE active=1", (), 0))


class AdminLogRepo:
    async def log(self, admin, action, target=None, details=""):
        await db.execute(
            "INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?,?,?,?)",
            (admin, action, target, details))

    async def recent(self, n=20):
        return await db.fetch_all("SELECT * FROM admin_logs ORDER BY id DESC LIMIT ?", (n,))

    async def count(self):
        return int(await db.fetch_val("SELECT COUNT(*) FROM admin_logs", (), 0))


class WarnRepo:
    async def add(self, uid, admin, reason):
        await db.execute("INSERT INTO warnings (user_id, admin_id, reason) VALUES (?,?,?)",
                         (uid, admin, reason))

    async def list_for(self, uid, n=10):
        return await db.fetch_all(
            "SELECT * FROM warnings WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, n))

    async def clear(self, uid):
        await db.execute("DELETE FROM warnings WHERE user_id=?", (uid,))

    async def count(self):
        return int(await db.fetch_val("SELECT COUNT(*) FROM warnings", (), 0))


class ReportRepo:
    async def create(self, reporter, reported, mid, reason):
        c = await db.execute(
            "INSERT INTO reports (reporter_id, reported_id, message_id, reason) VALUES (?,?,?,?)",
            (reporter, reported, mid, reason))
        return c.lastrowid or 0

    async def pending(self, n=20):
        return await db.fetch_all(
            "SELECT * FROM reports WHERE status='pending' ORDER BY id DESC LIMIT ?", (n,))

    async def count_pending(self):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM reports WHERE status='pending'", (), 0))

    async def mark(self, rid, status, admin):
        await db.execute(
            "UPDATE reports SET status=?, reviewed_by=?, reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, admin, rid))


class AchRepo:
    async def grant(self, uid, badge):
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


class StatsRepo:
    async def bump(self, f, amount=1):
        if f not in ("new_users", "messages_sent", "matches", "active_users",
                     "likes", "games"):
            return
        today = now_iran().date().isoformat()
        await db.execute(
            f"""INSERT INTO daily_stats (date, {f}) VALUES (?, ?)
                ON CONFLICT(date) DO UPDATE SET {f} = {f} + ?""",
            (today, amount, amount))

    async def last(self, n=7):
        return await db.fetch_all(
            "SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?", (n,))


class RoomRepo:
    async def create(self, name, owner, mx=10):
        rid = secrets.token_urlsafe(8)
        await db.execute(
            "INSERT INTO rooms (id, name, owner_id, max_members) VALUES (?,?,?,?)",
            (rid, name, owner, mx))
        await db.execute(
            "INSERT OR IGNORE INTO room_members (room_id, user_id) VALUES (?,?)",
            (rid, owner))
        return rid

    async def get(self, rid):
        return await db.fetch_one("SELECT * FROM rooms WHERE id=? AND active=1", (rid,))

    async def members(self, rid):
        return await db.fetch_all("SELECT user_id FROM room_members WHERE room_id=?", (rid,))

    async def join(self, rid, uid):
        try:
            await db.execute(
                "INSERT OR IGNORE INTO room_members (room_id, user_id) VALUES (?,?)",
                (rid, uid))
            return True
        except Exception:
            return False

    async def leave(self, rid, uid):
        await db.execute("DELETE FROM room_members WHERE room_id=? AND user_id=?", (rid, uid))

    async def count(self):
        return int(await db.fetch_val("SELECT COUNT(*) FROM rooms WHERE active=1", (), 0))


class SettingsRepo:
    KEY_CH = "required_channel"
    KEY_MAINT = "maintenance"

    async def get(self, k):
        return await db.fetch_val("SELECT value FROM settings WHERE key=?", (k,))

    async def set(self, k, v):
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
            (k, v))

    async def delete(self, k):
        await db.execute("DELETE FROM settings WHERE key=?", (k,))

    async def get_channel(self):
        return await self.get(self.KEY_CH)

    async def set_channel(self, ch):
        await self.set(self.KEY_CH, ch)

    async def clear_channel(self):
        await self.delete(self.KEY_CH)

    async def is_maint(self):
        return (await self.get(self.KEY_MAINT)) == "1"

    async def set_maint(self, on):
        await self.set(self.KEY_MAINT, "1" if on else "0")


class DatingRepo:
    async def get_prefs(self, uid):
        r = await db.fetch_one("SELECT * FROM dating_prefs WHERE user_id=?", (uid,))
        if not r:
            await db.execute(
                "INSERT OR IGNORE INTO dating_prefs (user_id) VALUES (?)", (uid,))
            r = await db.fetch_one("SELECT * FROM dating_prefs WHERE user_id=?", (uid,))
        return r

    async def set_pref(self, uid, f, v):
        if f not in ("pref_gender", "pref_min_age", "pref_max_age",
                     "pref_same_city", "pref_same_province"):
            return
        await self.get_prefs(uid)
        await db.execute(f"UPDATE dating_prefs SET {f}=? WHERE user_id=?", (v, uid))

    async def add_like(self, a, b, is_like=True):
        try:
            await db.execute(
                "INSERT INTO dating_likes (liker_id, target_id, is_like) VALUES (?,?,?)",
                (a, b, 1 if is_like else 0))
            return True
        except aiosqlite.IntegrityError:
            return False

    async def check_mutual(self, a, b):
        return bool(await db.fetch_one(
            "SELECT 1 FROM dating_likes WHERE liker_id=? AND target_id=? AND is_like=1",
            (b, a)))

    async def add_match(self, a, b):
        c = await db.execute(
            "INSERT INTO dating_matches (user1_id, user2_id) VALUES (?,?)", (a, b))
        return c.lastrowid or 0

    async def active_match(self, uid):
        return await db.fetch_one(
            "SELECT * FROM dating_matches WHERE active=1 AND (user1_id=? OR user2_id=?) ORDER BY id DESC LIMIT 1",
            (uid, uid))

    async def end_match(self, mid):
        await db.execute("UPDATE dating_matches SET active=0 WHERE id=?", (mid,))

    async def likes_of(self, uid):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM dating_likes WHERE liker_id=? AND is_like=1", (uid,), 0))

    async def matches_of(self, uid):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM dating_matches WHERE user1_id=? OR user2_id=?",
            (uid, uid), 0))

    async def total_matches(self):
        return int(await db.fetch_val("SELECT COUNT(*) FROM dating_matches", (), 0))

    async def total_likes(self):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM dating_likes WHERE is_like=1", (), 0))


class FeedbackRepo:
    async def create(self, uid, text):
        c = await db.execute(
            "INSERT INTO feedback (user_id, text) VALUES (?,?)", (uid, text))
        return c.lastrowid or 0

    async def recent(self, n=10):
        return await db.fetch_all("SELECT * FROM feedback ORDER BY id DESC LIMIT ?", (n,))

    async def count_new(self):
        return int(await db.fetch_val(
            "SELECT COUNT(*) FROM feedback WHERE status='new'", (), 0))

    async def mark_read(self, fid):
        await db.execute("UPDATE feedback SET status='read' WHERE id=?", (fid,))


user_repo = UserRepo()
profile_repo = ProfileRepo()
usettings_repo = UserSettingsRepo()
link_repo = LinkRepo()
msg_repo = MessageRepo()
conv_repo = ConversationRepo()
block_repo = BlockRepo()
fav_repo = FavRepo()
target_repo = TargetRepo()
pairing_repo = PairingRepo()
admin_log_repo = AdminLogRepo()
warn_repo = WarnRepo()
report_repo = ReportRepo()
ach_repo = AchRepo()
stats_repo = StatsRepo()
room_repo = RoomRepo()
settings_repo = SettingsRepo()
dating_repo = DatingRepo()
feedback_repo = FeedbackRepo()


# ═══════════════════════════════════════════════════════════════════════
# ۱۰ ── IRAN DATA (کامل — ۳۱ استان، ۷۰۰+ شهر)
# ═══════════════════════════════════════════════════════════════════════

IRAN_DATA: dict[str, list[str]] = {
    "آذربایجان شرقی": [
        "تبریز","مراغه","مرند","اهر","میانه","بناب","سراب","جلفا","آذرشهر","اسکو",
        "شبستر","هریس","بستان‌آباد","هشترود","ملکان","عجب‌شیر","خداآفرین","ورزقان",
        "کلیبر","هوراند","چاراویماق","ترکمانچای","مهربان","نظرکهریزی","خسروشاه",
        "صوفیان","تسوج","خامنه","شرفخانه","دوزدوزان","سیس","شندآباد","کوزه‌کنان",
        "باسمنج","ایلخچی","ممقان","گوگان","تیمورلو","سردرود","زرنق","لیلان","ترک",
        "قره‌آغاج","آچاچی","یکان کهریز","کردکندی","زنوز","یامچی","مبارک‌شهر",
    ],
    "آذربایجان غربی": [
        "ارومیه","خوی","میاندوآب","مهاباد","بوکان","سلماس","پیرانشهر","نقده","اشنویه",
        "شاهین‌دژ","ماکو","چالدران","پلدشت","شوط","تکاب","سردشت","کشاورز","مرگنلر",
        "محمودآباد","نازک‌علیا","چایپاره","چهاربرج","فیرورق","قره‌ضیاءالدین",
        "ایواوغلی","سیه‌چشمه","زورآباد","ربط","کاشتر","میرآباد","سیلوانا","نالوس",
        "باروق","یولاگلدی","بازرگان","دیزج دیز","زرآباد","حاجیلار","نوشین","سیه‌باز",
        "گوگ‌تپه","تازه‌شهر","خلیفان","بیله‌سوار","دیزج","کشاورز","شهرک میرآباد",
    ],
    "اردبیل": [
        "اردبیل","پارس‌آباد","مشگین‌شهر","خلخال","گرمی","بیله‌سوار","نمین","نیر",
        "سرعین","کوثر","هیر","لاهرود","قصابه","رضی","فخرآباد","جعفرآباد","کیوی",
        "عنبران","ابی‌بیگلو","اصلاندوز","آلنی","مرادلو","ارشق","لنگان","نیارق",
        "تازه‌کند انگوت","موران","شهرک شهید غفاری","بران علیا","قصابه سفلی",
        "کوراییم","هشتجین","اسلام‌آباد","مهماندوست","گلستان","اردی","ثمرین",
    ],
    "اصفهان": [
        "اصفهان","کاشان","خمینی‌شهر","نجف‌آباد","شهرضا","شاهین‌شهر","فولادشهر",
        "زرین‌شهر","آران و بیدگل","اردستان","نائین","سمیرم","فریدن","فریدون‌شهر",
        "چادگان","خوانسار","گلپایگان","دهاقان","مبارکه","نطنز","نوش‌آباد","کوهپایه",
        "هرند","ورزنه","بادرود","نصرآباد","قمصر","برزک","جوشقان","وزوان","میمه",
        "دهق","علویجه","بهارستان","قهجاورستان","خورزوق","دولت‌آباد","گزبرخوار",
        "سین","حبیب‌آباد","کلیشاد","رزوه","زواره","ابوزیدآباد","محمدآباد","نیک‌آباد",
        "ایمان‌شهر","زیار","گرگاب","سجزی","افوس","بوئین میاندشت","دامنه","گلدشت",
        "رحمت‌آباد","اسفرجان","کهریزسنگ","تیران","عسگران","رضوانشهر","چادگان",
        "فلاورجان","پیربکران","ابریشم","قهدریان","کلیشاد و سودرجان","زازران",
    ],
    "البرز": [
        "کرج","فردیس","هشتگرد","نظرآباد","محمدشهر","ماهدشت","مشکین‌دشت","اشتهارد",
        "گرمدره","کوهسار","طالقان","آسارا","کمال‌شهر","چهاردانگه","تنکمان","چهارباغ",
        "شهرک ظفر","مهرشهر","وردآورد","چیتگر","گوهردشت","کیانمهر","محمدآباد",
        "هیو","برغان","کردان","ولیت","رامجرد","خرمدشت","شهرجدیدهشتگرد",
        "ماهدشت","مشکین‌دشت","نظرآباد","اشتهارد","فردیس","محمدشهر","گرمدره",
    ],
    "ایلام": [
        "ایلام","دهلران","آبدانان","مهران","دره‌شهر","ایوان","چرداول","ملکشاهی",
        "بدره","سیروان","هلیلان","ارکواز","موسیان","دلگشا","ماژین","پهله",
        "زرین‌آباد","لومار","آسمان‌آباد","سراب‌باغ","بولی","میمه","گچی",
        "صالح‌آباد","چوار","بلاوه","شباب","سراب میمه","چشمه شیرین","چمن سورگه",
        "مهر","مورموری","بان‌قلعه","ملکشاهی","آسمان آباد","ایوان","شیروان",
    ],
    "بوشهر": [
        "بوشهر","برازجان","گناوه","دیر","کنگان","جم","عسلویه","خورموج","اهرم",
        "دیلم","بندر ریگ","شنبه","کاکی","بردخون","دلوار","آبدان","ریز","سعدآباد",
        "چغادک","عالیشهر","بندر دیر","بندر کنگان","نخل تقی","بندر طاهری","امام حسن",
        "بندر عامری","بنک","بوالخیر","گلستان","تنگستان","ناژ","مل گنزه","بندر ریگ",
        "بردستان","کاکی","بندر دیلم","دوراهک","بندر دیر","آب‌پخش","چاه‌مبارک",
    ],
    "تهران": [
        "تهران","شهریار","اسلامشهر","قدس","ملارد","پاکدشت","ورامین","پردیس",
        "رباط‌کریم","فیروزکوه","دماوند","شمشک","لواسان","بومهن","رودهن","آبعلی",
        "چهاردانگه","نسیم‌شهر","صباشهر","وحیدیه","باقرشهر","کهریزک","حسن‌آباد",
        "جوادآباد","قرچک","پیشوا","شریف‌آباد","جاجرود","فشم","میگون","شهرری",
        "بهارستان","گلستان","صفادشت","نصیرشهر","صالحیه","اندیشه","کیانشهر",
        "خاورشهر","شاهدشهر","پرند","چهاردانگه","چهاردانگه","افجه","فشم","شمشک",
        "امیریه","کهن‌آباد","فیروزکوه","دماوند","پردیس","بومهن","رودهن","لواسان",
        "نسیم‌شهر","وحیدیه","صباشهر","رباط‌کریم","گلستان","چهاردانگه","نسیم شهر",
    ],
    "چهارمحال و بختیاری": [
        "شهرکرد","بروجن","فارسان","لردگان","سامان","بن","سفیددشت","هفشجان",
        "کیار","اردل","دزپارت","فلارد","خانمیرزا","گندمان","بلداجی","نقنه",
        "دستنا","وردنجان","فرخشهر","طاقانک","نافچ","سورشجان","هارونی","بازفت",
        "منج","دوپلان","چلگرد","شلمزار","گهرو","باباحیدر","جونقان","سودجان",
        "هوره","آلونی","دیناران","کاج","شمس‌آباد","امام‌قیس","دستگرد","سردشت",
    ],
    "خراسان جنوبی": [
        "بیرجند","قائن","فردوس","نهبندان","سربیشه","طبس","بشرویه","خوسف",
        "درمیان","زیرکوه","سرایان","آیسک","اسدیه","حاجی‌آباد","مود","سده",
        "خضری","نیمبلوک","سه‌قلعه","عشق‌آباد","یونسی","گزیک","درح","شوسف",
        "دیهوک","ارسک","طبس مسینا","اسفدن","قهستان","آرین‌شهر","زهان","آبیز",
        "دستگردان","محمدیه","سر بیشه","خوسف","گزوک","چنشت","مسک","کریمو",
    ],
    "خراسان رضوی": [
        "مشهد","نیشابور","سبزوار","تربت حیدریه","قوچان","کاشمر","گناباد",
        "تربت جام","چناران","خواف","تایباد","بردسکن","درگز","سرخس","فریمان",
        "جغتای","جوین","خلیل‌آباد","رشتخوار","زاوه","باخرز","بجستان","فیروزه",
        "مه‌ولات","کوهسرخ","داورزن","صالح‌آباد","طرقبه","شاندیز","گلمکان",
        "چکنه","ریوش","کدکن","رخ","کاخک","بیدخت","ششتمد","سنگان","فیض‌آباد",
        "قلندرآباد","شهرزو","سلطان‌آباد","نصرآباد","مزداوند","قدمگاه","بینالود",
        "جغتای","جنگل","بردسکن","کوهسرخ","مه ولات","زبرخان","باخرز",
    ],
    "خراسان شمالی": [
        "بجنورد","شیروان","اسفراین","آشخانه","گرمه","جاجرم","فاروج","راز",
        "صفی‌آباد","سنخواست","قاضی","لوجلی","حصارگرمخان","تیتکانلو","درق",
        "زیارت","شوقان","پیش‌قلعه","چناران","ایور","قوشخانه","بام","روئین",
        "اسفیدان","حصار","تیتکانلو","شیروان","فاروج","گرمه","راز","جاجرم",
    ],
    "خوزستان": [
        "اهواز","آبادان","خرمشهر","دزفول","اندیمشک","بهبهان","ماهشهر","شوشتر",
        "ایذه","شوش","مسجد سلیمان","رامهرمز","باغ‌ملک","امیدیه","هندیجان",
        "لالی","هفتکل","آغاجاری","رامشیر","حمیدیه","دشت آزادگان","کارون",
        "باوی","گتوند","کرخه","شادگان","هویزه","بستان","سوسنگرد","رفیع",
        "اروندکنار","مینوشهر","چمران","بندر امام","شاوور","صفی‌آباد","ترکالکی",
        "قلعه تل","گوریه","جنت‌مکان","ملاثانی","ویس","تراز","شمس‌آباد",
        "ابوحمیظه","کوت سیدنعیم","چعب","بیدروبه","هفتگل","مسجدسلیمان",
        "قلعه خواجه","اندیکا","شهیون","دهدز",
    ],
    "زنجان": [
        "زنجان","ابهر","خرمدره","قیدار","صائین‌قلعه","ماه‌نشان","هیدج","صومعه",
        "سجاس","چورزق","گرماب","ارمغانخانه","زری‌آباد","نوربهار","خدابنده",
        "سهرورد","زرین‌رود","حلب","نیک‌پی","فارسجین","کرسف","سعیدآباد",
        "قره‌پشتلو","بوغداکندی","دندی","چای‌پاره","گیلوان","شریف‌آباد",
        "پیرزاغا","قلتوق","نوربهار","ارمغانخانه","خرمدره","آب‌بر","زرین آباد",
    ],
    "سمنان": [
        "سمنان","شاهرود","دامغان","گرمسار","مهدی‌شهر","میامی","بسطام","مجن",
        "بیارجمند","رودیان","امیریه","ایوانکی","آرادان","کهن‌آباد","شهمیرزاد",
        "درجزین","دیباج","کلاته خیج","رضوان","سرخه","ده‌نمک","لاسجرد","افتر",
        "بیابانک","ارادات","طرود","چاشم","فولادمحله","دامغان","میامی","شاهرود",
    ],
    "سیستان و بلوچستان": [
        "زاهدان","زابل","چابهار","ایرانشهر","سراوان","خاش","میرجاوه","نیک‌شهر",
        "کنارک","زهک","هیرمند","قصرقند","سرباز","راسک","مهرستان","سیب و سوران",
        "فنوج","بمپور","جالق","پیشین","بن‌جار","نصرت‌آباد","بزمان","محمدآباد",
        "دوست‌محمد","ادیمی","جزینک","بندر بریس","زرآباد","گشت","دشتیاری",
        "هیدوچ","پارود","کشتگان","نوک‌آباد","تفتان","کورین","چگرد","بنت",
        "اسپکه","گلمورتی","سنگان","کرباسک","میرجاوه","ریگ ملک",
    ],
    "فارس": [
        "شیراز","مرودشت","کازرون","جهرم","فسا","داراب","لار","آباده","نی‌ریز",
        "اقلید","سپیدان","استهبان","زرین‌دشت","خرامه","سروستان","کوار",
        "فیروزآباد","قیر و کارزین","مهر","لامرد","خنج","گراش","اوز","جویم",
        "بنارویه","بیرم","بالاده","کامفیروز","رونیز","ایج","ارسنجان","بوانات",
        "خرم‌بید","سرچهان","کوهچنار","زرقان","صدرا","داریان","سعدی","دوزه",
        "جنت‌شهر","میمند","افزر","کنارتخته","دهرم","قیر","کاریز","خشت",
        "دشمن‌زیاری","مصیری","خانه زنیان","کره‌ای","دشت ارژن","بابامنیر",
        "نورآباد ممسنی","ماهور","رستم","دوکوهک","قائمیه","نودان","بیضا",
        "هماشهر","خانیمن","مشکان","دبیران","پاسخن","کوهنجان","ششده",
    ],
    "قزوین": [
        "قزوین","الوند","تاکستان","آبیک","بوئین‌زهرا","محمدیه","آوج","شال",
        "اسفرورین","ضیاءآباد","خرمدشت","نرجه","معلم‌کلایه","رازمیان","کوهین",
        "بیدستان","شریفیه","سیردان","دانسفهان","آبگرم","الموت","ارداق",
        "زیاران","سگزآباد","خاکعلی","قشلاق","شهرک صنعتی","ناصرآباد","کوهگیر",
        "آقابابا","شترک","یانس‌آباد","آبیک","محمدیه","کهک","رازمیان","الوند",
    ],
    "قم": [
        "قم","قنوات","جعفریه","دستجرد","سلفچگان","کهک","خلجستان","راهجرد",
        "ورجان","قاهان","فردو","قمرود","طرق","ملک‌آباد","کرمجگان","سیدان",
        "میان‌کهک","ونارچ","خاوه","خورهه","دستجرد","سلفچگان","قم","قنوات",
    ],
    "کردستان": [
        "سنندج","سقز","مریوان","بانه","قروه","بیجار","کامیاران","دیواندره",
        "دهگلان","سروآباد","چناره","شویشه","مالوجه","زرینه","دلبران",
        "بابارشانی","سریش‌آباد","اورامان","بوالحسن","آرمرده","کانی‌سور",
        "یاسوکند","توپ‌آغاج","موچش","پیران","کانی‌دینار","حسین‌آباد",
        "برده‌رشه","اورامان تخت","بلبان‌آباد","چراغ‌آباد","بانه","بیجار",
    ],
    "کرمان": [
        "کرمان","رفسنجان","سیرجان","جیرفت","بم","زرند","کهنوج","بردسیر",
        "شهربابک","انار","ریگان","فهرج","منوجان","رودبار جنوب","قلعه‌گنج",
        "عنبرآباد","فاریاب","ارزوئیه","راور","کوهبنان","رابر","بافت",
        "نرماشیر","گلباف","شهداد","ماهان","چترود","نجف‌شهر","خواجو","جوپار",
        "اختیارآباد","زنگی‌آباد","نودژ","دوساری","هجدک","خانم‌سور","بروات",
        "یزدان‌شهر","راین","نگار","دهج","هرجند","جوزم","پاریز","خاتون‌آباد",
        "میمند","لاله‌زار","گلباف","شهداد","بردسیر","راین","فهرج",
    ],
    "کرمانشاه": [
        "کرمانشاه","اسلام‌آباد غرب","هرسین","کنگاور","سنقر","پاوه","جوانرود",
        "صحنه","قصر شیرین","گیلانغرب","سرپل ذهاب","روانسر","دالاهو",
        "ثلاث باباجانی","باینگان","نوسود","ازگله","کرند غرب","رباط","بیستون",
        "ماهیدشت","شریف‌آباد","هلشی","بیلوار","گهواره","گودین","میان‌راهان",
        "سومار","قره‌بلاغ","نوده","شاهو","بان‌زرده","ریجاب","سراب ذهاب",
        "قره‌سو","حمیل","کرند","صحنه","اسلام آباد غرب",
    ],
    "کهگیلویه و بویراحمد": [
        "یاسوج","دوگنبدان","دهدشت","سی‌سخت","لیکک","چرام","باشت","مارگون",
        "دنا","لنده","سوق","قلعه رئیسی","پاتاوه","سرفاریاب","دیشموک","چیتاب",
        "گراب","مادوان","سرآسیاب یوسفی","گچساران","بویراحمد","کهگیلویه",
        "سادات محمودی","لنده","مارگون","دنا","سپیدار","دهدشت","دوگنبدان",
    ],
    "گلستان": [
        "گرگان","گنبد کاووس","علی‌آباد کتول","بندر ترکمن","آق‌قلا","کردکوی",
        "مینودشت","آزادشهر","رامیان","مراوه‌تپه","گمیشان","بندر گز","نوکنده",
        "خالدنبی","اینچه‌برون","دلند","فاضل‌آباد","سیمین‌شهر","نگین‌شهر",
        "خان‌ببین","سرخنکلاته","قرق","نصرآباد","فندرسک","کلاله","گالیکش",
        "پیشکمر","تاتارعلیا","بالاجاده","یساقی","سنگدوین","قازان‌قایه",
        "تقی‌آباد","چناران","آق‌تقه","صوفیان","گمیشان","بندر ترکمن",
    ],
    "گیلان": [
        "رشت","انزلی","لاهیجان","لنگرود","آستارا","تالش","رودسر","فومن",
        "صومعه‌سرا","رودبار","آستانه اشرفیه","املش","رضوانشهر","ماسال",
        "شفت","سیاهکل","خمام","منجیل","لوشان","بره‌سر","کومله","چابکسر",
        "واجارگاه","کیاشهر","لشت نشاء","خشکبیجار","سنگر","کوچصفهان","کلاچای",
        "رحیم‌آباد","جیرنده","اسالم","حویق","لیسار","گیسوم","دیلمان",
        "بازارجمعه","ماسوله","تولم شهر","احمدسرگوراب","چوکام","بلترک",
        "اطاقور","سیاه‌اسطلخ","رشتجان","خشکبیجار","لاهیجان","رودسر",
    ],
    "لرستان": [
        "خرم‌آباد","بروجرد","دورود","الیگودرز","کوهدشت","نورآباد","ازنا",
        "پل‌دختر","چگنی","رومشکان","سلسله","دلفان","معمولان","بی‌بی‌سید",
        "اشترینان","چالانچولان","سپیددشت","زاغه","بربرود","فیروزآباد",
        "ویسیان","الشتر","کونانی","گریت","درب گنبد","چقم","هفت چشمه",
        "سرابدوره","بیرانوند","شول‌آباد","چراغ‌آباد","برخوردار","ملاوی",
        "گراب","کیان","ززم","دره گرم","دورود","بروجرد","ازنا","الیگودرز",
    ],
    "مازندران": [
        "ساری","بابل","آمل","قائم‌شهر","بهشهر","چالوس","نوشهر","تنکابن",
        "رامسر","نکا","جویبار","فریدونکنار","محمودآباد","نور","عباس‌آباد",
        "گلوگاه","کلاردشت","پل سفید","سوادکوه","زیراب","شیرگاه","بلده",
        "کجور","بابلسر","سلمانشهر","رویان","کتالم","نشتارود","خرم‌آباد",
        "هچیرود","مرزن‌آباد","دو هزار","ایزدشهر","سورک","بهنمیر","امیرکلا",
        "بابلکنار","کیاسر","کیاکلا","لاریم","گتاب","دابودشت","میاندرود",
        "پایین هولار","زرگر","شیرود","کلارآباد","نمک‌آبرود","پول","کوهستان",
        "رامسر","تنکابن","عباس آباد","نوشهر","چالوس","ساری","بابل","آمل",
    ],
    "مرکزی": [
        "اراک","ساوه","خمین","محلات","دلیجان","تفرش","شازند","زرندیه",
        "کمیجان","آشتیان","فرمهین","خنداب","مأمونیه","غرق‌آباد","پرندک",
        "نراق","جاسب","آستانه","هندودر","توره","مهاجران","زاویه","نوبران",
        "آوه","ساروق","قره‌چای","خرقان","بیات","قورچی‌باشی","جاورسیان",
        "خشکرود","شهباز","نراق","جاسب","دوزج","خمین","محلات","دلیجان",
    ],
    "هرمزگان": [
        "بندرعباس","میناب","بندر لنگه","قشم","کیش","بندر خمیر","حاجی‌آباد",
        "رودان","بستک","پارسیان","جاسک","سیریک","ابوموسی","بندر جاسک",
        "گاوبندی","کوهستک","هشتبندی","بندر کنگ","جناح","دشتی","فین",
        "قلعه قاضی","تخت","سوزا","هرمز","لارک","هنگام","فارور","سیری",
        "تنگه","رویدر","کوشکنار","دیوان","دهبارز","رودخانه","کمشک","تیاب",
        "بیکاه","فارغان","بندزرک","قشم","کیش","ابوموسی","سیری",
    ],
    "همدان": [
        "همدان","ملایر","نهاوند","تویسرکان","اسدآباد","بهار","کبودراهنگ",
        "رزن","فامنین","لالجین","مریانج","جورقان","قهاوند","دمق","سامن",
        "برزول","فیروزان","گل‌تپه","صالح‌آباد","شیرین‌سو","جوکار","زنگنه",
        "سردرود","قهورد","مهاجران","ازندریان","اسلام‌آباد","دمق","رزن",
        "گل تپه","لالجین","مریانج","تویسرکان","نهاوند","اسدآباد",
    ],
    "یزد": [
        "یزد","میبد","اردکان","بافق","مهریز","ابرکوه","تفت","اشکذر",
        "خاتم","بهاباد","مروست","هرات","زارچ","شاهدیه","حمیدیا","ندوشن",
        "نیر","عقدا","خرانق","ساغند","احمدآباد","رضوانشهر","مزرعه نو",
        "دربید","فراغه","شمس","بیده","دهشیر","بنادکوک","نصرآباد","گاریز",
        "اسفندآباد","بفروئیه","خضرآباد","مهریز","ابرکوه","تفت","میبد",
    ],
}

PROVINCES = list(IRAN_DATA.keys())

PROVINCE_EMOJI = {
    "آذربایجان شرقی": "🏔", "آذربایجان غربی": "🌋", "اردبیل": "❄️",
    "اصفهان": "🏛", "البرز": "⛰", "ایلام": "🌲",
    "بوشهر": "🌊", "تهران": "🏙", "چهارمحال و بختیاری": "🦁",
    "خراسان جنوبی": "🏜", "خراسان رضوی": "🕌", "خراسان شمالی": "🐎",
    "خوزستان": "🌴", "زنجان": "🔪", "سمنان": "🦎",
    "سیستان و بلوچستان": "🏜", "فارس": "🦚", "قزوین": "🍇",
    "قم": "🕌", "کردستان": "🎵", "کرمان": "🌾",
    "کرمانشاه": "⛰", "کهگیلویه و بویراحمد": "🏞", "گلستان": "🐎",
    "گیلان": "🌧", "لرستان": "🏞", "مازندران": "🌳",
    "مرکزی": "🏭", "هرمزگان": "⛵", "همدان": "📜", "یزد": "🏜",
}

POPULAR_CITIES = {
    "تهران", "مشهد", "اصفهان", "کرج", "شیراز", "تبریز", "قم", "اهواز",
    "کرمانشاه", "ارومیه", "رشت", "زاهدان", "همدان", "کرمان", "یزد",
    "اردبیل", "بندرعباس", "اراک", "ساری", "بابل", "گرگان", "قزوین",
    "سنندج", "خرم‌آباد", "بجنورد", "بیرجند", "زنجان", "سمنان", "بوشهر",
    "شهرکرد", "یاسوج", "ایلام",
}

POPULAR_PROVINCES = [
    "تهران", "خراسان رضوی", "اصفهان", "فارس", "البرز",
    "آذربایجان شرقی", "خوزستان", "گیلان", "مازندران", "کرمانشاه",
]

ALL_AGES = list(range(9, 100))
PROVINCES_PER_PAGE = 8
CITIES_PER_PAGE = 10


def _prov_page_count():
    return (len(PROVINCES) + PROVINCES_PER_PAGE - 1) // PROVINCES_PER_PAGE


def _city_page_count(province):
    return (len(IRAN_DATA.get(province, [])) + CITIES_PER_PAGE - 1) // CITIES_PER_PAGE


# ═══════════════════════════════════════════════════════════════════════
# ۱۱ ── AVATAR
# ═══════════════════════════════════════════════════════════════════════

def avatar_url(gender, seed, size=512):
    base = f"https://api.dicebear.com/9.x/adventurer/png?seed={seed}&size={size}&style=circle"
    if gender == "male":
        return (base +
                "&backgroundColor=b6e3f4,c0aede,d1d4f9,ffd5dc,ffdfbf"
                "&hairColor=0e0e0e,2c1b18,4a312c,724133,a55728,b58143,d6b370"
                "&hair=short01,short02,short03,short04,short05,short06,short07,short08,"
                "short09,short10,short11,short12,short13,short14,short15,short16,short17,short18,short19"
                "&eyes=variant01,variant02,variant03,variant04,variant05,variant07,variant08,"
                "variant09,variant10,variant11,variant12,variant13,variant15,variant16,variant17"
                "&mouth=variant01,variant02,variant03,variant04,variant05,variant07,variant08,"
                "variant09,variant10,variant12,variant13,variant14,variant15,variant16"
                "&skinColor=ecad80,f2d3b1,9e5622,763900"
                "&featuresProbability=12&earringsProbability=0"
                "&glassesProbability=10&glasses=variant01,variant02,variant03,variant04"
                "&clothing=variant01,variant02,variant03,variant04,variant05,variant06,variant07,"
                "variant08,variant09,variant10,variant11,variant12,variant13,variant14,variant15"
                "&clothingColor=262e33,3c4f5c,65c9ff,5199e4,25557c,929598,a7a7a7")
    elif gender == "female":
        return (base +
                "&backgroundColor=ffd5dc,ffdfbf,c0aede,d1d4f9,b6e3f4"
                "&hairColor=0e0e0e,2c1b18,4a312c,724133,a55728,b58143,d6b370,ff5c5c,ff9c9c,ffd5dc"
                "&hair=long01,long02,long03,long04,long05,long06,long07,long08,long09,long10,"
                "long11,long12,long13,long14,long15,long16,long17,long18,long19,long20,"
                "long21,long22,long23,long24,long25,long26"
                "&eyes=variant01,variant02,variant03,variant04,variant05,variant07,variant08,"
                "variant09,variant10,variant11,variant12,variant13,variant15,variant16,variant17"
                "&mouth=variant01,variant02,variant03,variant04,variant05,variant07,variant08,"
                "variant09,variant10,variant12,variant13,variant14,variant15,variant16"
                "&skinColor=ecad80,f2d3b1,9e5622,763900"
                "&featuresProbability=10&earringsProbability=20"
                "&glassesProbability=8&glasses=variant01,variant02,variant03,variant04"
                "&clothing=variant01,variant02,variant03,variant04,variant05,variant06,variant07,"
                "variant08,variant09,variant10,variant11,variant12,variant13,variant14,variant15"
                "&clothingColor=ff5c5c,ff9c9c,ffb0b0,ffd5dc,c0aede,d1d4f9,b6e3f4")
    return base + "&backgroundColor=d1d4f9,b6e3f4,c0aede"


def is_custom_avatar(a):
    return bool(a) and a.startswith("file:")


def extract_fid(a):
    return a[5:] if is_custom_avatar(a) else a


def gender_fa(g):
    return {"male": "👨 پسر", "female": "👩 دختر"}.get(g, "🏳️")


# ═══════════════════════════════════════════════════════════════════════
# ۱۲ ── RULES
# ═══════════════════════════════════════════════════════════════════════

RULES_FA = """📜 <b>قوانین و شرایط استفاده</b>

╔══════════════════════════════╗
║  لطفاً با دقت مطالعه کنید  ║
╚══════════════════════════════╝

<b>1️⃣ احترام متقابل</b>
• توهین، فحاشی، تهمت ← <b>ممنوع</b>

<b>2️⃣ محتوای مناسب</b>
• محتوای مستهجن، خشونت‌آمیز ← <b>ممنوع</b>
• تبلیغات و اسپم ← <b>ممنوع</b>

<b>3️⃣ حریم خصوصی</b>
• هویت شما محفوظ است 🔒
• انتشار اطلاعات دیگران ← <b>ممنوع</b>

<b>4️⃣ آزار و اذیت</b>
• تهدید، باج‌گیری ← <b>بن دائمی</b> 🚫

<b>5️⃣ سن قانونی</b>
• زیر ۱۳ سال ← <b>ممنوع</b>

<b>6️⃣ مسئولیت</b>
• مسئولیت محتوای ارسالی بر عهده شماست

━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ با زدن دکمه «✅ می‌پذیرم»، تأیید می‌کنید تمام قوانین را خوانده و پذیرفته‌اید."""


# ═══════════════════════════════════════════════════════════════════════
# ۱۳ ── KEYBOARDS
# ═══════════════════════════════════════════════════════════════════════

def _ibtn(t, style=None, **kw):
    if STYLE_OK and style is not None:
        return InlineKeyboardButton(text=t, style=style, **kw)
    return InlineKeyboardButton(text=t, **kw)


def _btn(t, style=None, **kw):
    if STYLE_OK and style is not None:
        return KeyboardButton(text=t, style=style, **kw)
    return KeyboardButton(text=t, **kw)


S_P = ButtonStyle.PRIMARY if STYLE_OK else None
S_S = ButtonStyle.SUCCESS if STYLE_OK else None
S_D = ButtonStyle.DANGER if STYLE_OK else None


def _m(v):
    return "🟢" if v else "⚪"


def language_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("🇮🇷 فارسی", S_P, callback_data="lang:fa")],
        [_ibtn("🇬🇧 English", S_P, callback_data="lang:en")],
        [_ibtn("🇸🇦 العربية", S_P, callback_data="lang:ar")],
    ])


def rules_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("✅ می‌پذیرم", S_S, callback_data="rules:accept")],
        [_ibtn("❌ انصراف", S_D, callback_data="rules:decline")],
    ])


def main_menu_kb(is_admin=False):
    kb = [
        [_btn("🔗 لینک ناشناس", S_P), _btn("🎭 چت ناشناس", S_P)],
        [_btn("💖 دوستیابی", S_D), _btn("👤 مخاطب خاص", S_P)],
        [_btn("👥 اتاق گروهی", S_P), _btn("🎮 بازی‌ها", S_S)],
        [_btn("🎁 پاداش روزانه", S_S), _btn("⭐ علاقه‌مندی‌ها", S_S)],
        [_btn("🎖 سطح من", S_S), _btn("🏆 لیدربورد", S_S)],
        [_btn("📊 آمار من", S_P), _btn("👤 پروفایل من", S_P)],
        [_btn("⚙️ تنظیمات", S_P), _btn("🔒 لیست بلاک", S_D)],
        [_btn("📣 بازخورد", S_P), _btn("🎁 دعوت", S_S)],
        [_btn("🕐 ساعت", S_P), _btn("📜 قوانین", S_P)],
        [_btn("❓ راهنما", S_P)],
    ]
    if is_admin:
        kb.append([_btn("👑 پنل ادمین", S_S)])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def admin_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [_btn("📊 داشبورد", S_P), _btn("📈 آنالیتیکس", S_P)],
        [_btn("👥 کاربران", S_P), _btn("🔍 جستجو", S_P)],
        [_btn("🚨 گزارش‌ها", S_D), _btn("⚠️ اخطارها", S_D)],
        [_btn("🚫 بن‌ها", S_D), _btn("🔇 سکوت‌ها", S_D)],
        [_btn("📢 پیام همگانی", S_P), _btn("📨 پیام به کاربر", S_P)],
        [_btn("🔒 کانال", S_P), _btn("🔧 تعمیر", S_P)],
        [_btn("💾 بکاپ", S_S), _btn("🧹 پاکسازی", S_D)],
        [_btn("📝 لاگ‌ها", S_P), _btn("💬 فیدبک‌ها", S_P)],
        [_btn("🎮 آمار بازی‌ها", S_S), _btn("💰 مدیریت سکه", S_S)],
        [_btn("🗑 پاک کردن کش", S_D), _btn("🏓 پینگ", S_P)],
        [_btn("◀️ بازگشت", S_P)],
    ], resize_keyboard=True)


def cancel_kb(cb="global:cancel"):
    return InlineKeyboardMarkup(inline_keyboard=[[_ibtn("❌ لغو", S_D, callback_data=cb)]])


def confirm_kb(action):
    return InlineKeyboardMarkup(inline_keyboard=[[
        _ibtn("✅ بله", S_S, callback_data=f"confirm:{action}"),
        _ibtn("❌ انصراف", S_D, callback_data=f"cancel:{action}")]])


def profile_gender_rkb():
    return ReplyKeyboardMarkup(keyboard=[
        [_btn("👨 پسر", S_P), _btn("👩 دختر", S_P)],
        [_btn("❌ لغو", S_D)],
    ], resize_keyboard=True, one_time_keyboard=True,
       input_field_placeholder="جنسیتت رو انتخاب کن...")


def profile_age_rkb():
    rows = []
    for i in range(0, len(ALL_AGES), 6):
        chunk = ALL_AGES[i:i + 6]
        row = []
        for a in chunk:
            if a < 15:
                emoji = "🔞"
            elif a < 18:
                emoji = "👦"
            elif a < 25:
                emoji = "🧑"
            elif a < 35:
                emoji = "👨"
            elif a < 45:
                emoji = "🧔"
            elif a < 55:
                emoji = "👴"
            elif a < 65:
                emoji = "🧓"
            else:
                emoji = "👵"
            row.append(_btn(f"{emoji} {a}", S_S))
        rows.append(row)
    rows.append([_btn("◀️ بازگشت", S_P), _btn("❌ لغو", S_D)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True,
                               one_time_keyboard=True,
                               input_field_placeholder="سنت رو از ۹ تا ۹۹ انتخاب کن...")


def profile_province_rkb(page=0):
    total = len(PROVINCES)
    start = page * PROVINCES_PER_PAGE
    end = min(start + PROVINCES_PER_PAGE, total)
    chunk = PROVINCES[start:end]
    rows = []
    rows.append([
        _btn(f"📖 صفحه {page + 1} از {_prov_page_count()}", S_P),
        _btn(f"🏙 {start + 1}-{end}", S_P),
    ])
    for i in range(0, len(chunk), 2):
        row = []
        for p in chunk[i:i + 2]:
            emoji = PROVINCE_EMOJI.get(p, "🏙")
            star = "⭐ " if p in POPULAR_PROVINCES else ""
            label = f"{star}{emoji} {p}"
            row.append(_btn(label, S_S if p in POPULAR_PROVINCES else S_P))
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(_btn("◀️ قبلی", S_P))
    if end < total:
        nav.append(_btn("بعدی ▶️", S_P))
    if nav:
        rows.append(nav)
    rows.append([_btn("🔍 جستجوی استان", S_P), _btn("❌ لغو", S_D)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True,
                               one_time_keyboard=True,
                               input_field_placeholder="استانت رو انتخاب کن...")


def profile_city_rkb(province, page=0):
    cities = IRAN_DATA.get(province, [])
    total = len(cities)
    start = page * CITIES_PER_PAGE
    end = min(start + CITIES_PER_PAGE, total)
    chunk = cities[start:end]
    rows = []
    emoji = PROVINCE_EMOJI.get(province, "🏙")
    rows.append([
        _btn(f"{emoji} {province[:18]}", S_P),
        _btn(f"📖 {page + 1}/{_city_page_count(province)}", S_P),
    ])
    for i in range(0, len(chunk), 2):
        row = []
        for c in chunk[i:i + 2]:
            star = "⭐ " if c in POPULAR_CITIES else ""
            row.append(_btn(f"{star}{c}", S_S if c in POPULAR_CITIES else S_P))
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(_btn("◀️ قبلی", S_P))
    if end < total:
        nav.append(_btn("بعدی ▶️", S_P))
    if nav:
        rows.append(nav)
    rows.append([_btn("🔍 جستجوی شهر", S_P)])
    rows.append([_btn("◀️ استان‌ها", S_P), _btn("❌ لغو", S_D)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True,
                               one_time_keyboard=True,
                               input_field_placeholder="شهرت رو انتخاب کن...")


def settings_rkb():
    return ReplyKeyboardMarkup(keyboard=[
        [_btn("🔔 اعلان‌ها", S_P), _btn("🛡 حریم خصوصی", S_P)],
        [_btn("💬 چت و پیام", S_P), _btn("🎨 ظاهر", S_P)],
        [_btn("💖 دوستیابی", S_D), _btn("📊 اطلاعات حساب", S_S)],
        [_btn("◀️ بازگشت", S_P)],
    ], resize_keyboard=True, input_field_placeholder="تنظیمات پیشرفته...")


def settings_notif_kb(s):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn(f"{_m(s['notify_msg'])} پیام ناشناس", S_S if s['notify_msg'] else S_P,
               callback_data="uset:t:notify_msg")],
        [_ibtn(f"{_m(s['notify_match'])} مچ ناشناس", S_S if s['notify_match'] else S_P,
               callback_data="uset:t:notify_match")],
        [_ibtn(f"{_m(s['notify_dating'])} مچ دوستیابی", S_S if s['notify_dating'] else S_P,
               callback_data="uset:t:notify_dating")],
        [_ibtn(f"{_m(s['silent_mode'])} سایلنت", S_S if s['silent_mode'] else S_P,
               callback_data="uset:t:silent_mode")],
        [_ibtn("◀️ بازگشت", S_P, callback_data="uset:menu")],
    ])


def settings_priv_kb(s):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn(f"{_m(s['hide_online'])} مخفی آنلاین", S_S if s['hide_online'] else S_P,
               callback_data="uset:t:hide_online")],
        [_ibtn(f"{_m(s['read_receipt'])} تیک خوانده‌شدن", S_S if s['read_receipt'] else S_P,
               callback_data="uset:t:read_receipt")],
        [_ibtn(f"{_m(s['web_mode'])} حالت وب", S_S if s['web_mode'] else S_P,
               callback_data="uset:t:web_mode")],
        [_ibtn("◀️ بازگشت", S_P, callback_data="uset:menu")],
    ])


def settings_chat_kb(s):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn(f"{_m(s['auto_delete'])} حذف خودکار", S_S if s['auto_delete'] else S_P,
               callback_data="uset:t:auto_delete")],
        [_ibtn(f"{_m(s['auto_translate'])} ترجمه خودکار", S_S if s['auto_translate'] else S_P,
               callback_data="uset:t:auto_translate")],
        [_ibtn(f"{_m(s['copyright_mode'])} کپی‌رایت", S_S if s['copyright_mode'] else S_P,
               callback_data="uset:t:copyright_mode")],
        [_ibtn("◀️ بازگشت", S_P, callback_data="uset:menu")],
    ])


def settings_app_kb(s):
    cur = s["theme"] if "theme" in s.keys() else "dark"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn(f"{'🟢' if cur == 'dark' else '⚪'} تم تاریک",
               S_S if cur == 'dark' else S_P, callback_data="uset:theme:dark")],
        [_ibtn(f"{'🟢' if cur == 'light' else '⚪'} تم روشن",
               S_S if cur == 'light' else S_P, callback_data="uset:theme:light")],
        [_ibtn("◀️ بازگشت", S_P, callback_data="uset:menu")],
    ])


def dating_menu_kb(p):
    g = {"male": "👨 پسر", "female": "👩 دختر", "any": "🤷 هر دو"}[p["pref_gender"]]
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("🔍 شروع گشت", S_S, callback_data="dating:next")],
        [_ibtn(f"🎭 {g}", S_P, callback_data="dating:pref:gender")],
        [_ibtn(f"🎂 {p['pref_min_age']}-{p['pref_max_age']}", S_P, callback_data="dating:pref:age")],
        [_ibtn(f"🏙 هم‌شهر {_m(p['pref_same_city'])}", S_P, callback_data="dating:pref:city")],
        [_ibtn(f"🗺 هم‌استان {_m(p['pref_same_province'])}", S_P, callback_data="dating:pref:province")],
        [_ibtn("📊 آمار", S_S, callback_data="dating:stats")],
        [_ibtn("❌ بستن", S_D, callback_data="global:cancel")],
    ])


def dating_card_kb(tid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("❤️ لایک", S_S, callback_data=f"dating:like:{tid}"),
         _ibtn("👎 رد", S_D, callback_data=f"dating:dislike:{tid}")],
        [_ibtn("⏭ بعدی", S_P, callback_data="dating:next"),
         _ibtn("❌ بستن", S_D, callback_data="dating:close")],
    ])


def dating_gender_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("👨 پسر", S_P, callback_data="dating:setg:male")],
        [_ibtn("👩 دختر", S_P, callback_data="dating:setg:female")],
        [_ibtn("🤷 هر دو", S_P, callback_data="dating:setg:any")],
        [_ibtn("◀️ بازگشت", S_P, callback_data="dating:back")],
    ])


def games_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("🎲 تاس", S_P, callback_data="game:dice")],
        [_ibtn("🪙 شیر یا خط", S_P, callback_data="game:coin")],
        [_ibtn("🧠 حدس عدد", S_S, callback_data="game:guess")],
        [_ibtn("🎯 هدف", S_P, callback_data="game:dart")],
        [_ibtn("✂️ سنگ کاغذ قیچی", S_P, callback_data="game:rps")],
        [_ibtn("🏆 لیدربورد برد", S_S, callback_data="game:top")],
        [_ibtn("❌ بستن", S_D, callback_data="global:cancel")],
    ])


def rps_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("✂️ قیچی", S_P, callback_data="rps:scissors")],
        [_ibtn("📄 کاغذ", S_P, callback_data="rps:paper")],
        [_ibtn("🪨 سنگ", S_P, callback_data="rps:rock")],
    ])


def avatar_edit_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📸 آپلود عکس", S_S, callback_data="av:upload")],
        [_ibtn("🎲 عکس جدید", S_P, callback_data="av:random")],
        [_ibtn("👨 پسرونه", S_P, callback_data="av:style:male")],
        [_ibtn("👩 دخترونه", S_P, callback_data="av:style:female")],
        [_ibtn("◀️ بازگشت", S_P, callback_data="av:back")]])


def link_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("♾ دائمی", S_P, callback_data="linktype:permanent")],
        [_ibtn("1️⃣ یکبارمصرف", S_S, callback_data="linktype:onetime")],
        [_ibtn("❌ لغو", S_D, callback_data="global:cancel")]])


def link_actions_kb(token):
    share = f"https://t.me/share/url?url=https://t.me/{Config.BOT_USERNAME}?start={token}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📤 اشتراک‌گذاری", S_S, url=share)],
        [_ibtn("🗑 حذف", S_D, callback_data=f"link:del:{token}")]])


def match_menu_kb(f):
    g = {"male": "👨", "female": "👩", "any": "🤷"}[f["gender"]]
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("🔍 شروع جستجو", S_S, callback_data="match:start")],
        [_ibtn(f"🎂 {f['min_age']}-{f['max_age']}", S_P, callback_data="filter:age")],
        [_ibtn(f"🎭 {g}", S_P, callback_data="filter:gender")],
        [_ibtn(f"🏙 هم‌شهر {_m(f['same_city'])}", S_P, callback_data="filter:city")],
        [_ibtn("❌ لغو", S_D, callback_data="global:cancel")]])


def filter_gender_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("👨 پسر", S_P, callback_data="filter:g:male")],
        [_ibtn("👩 دختر", S_P, callback_data="filter:g:female")],
        [_ibtn("🤷 فرقی ندارد", S_P, callback_data="filter:g:any")],
        [_ibtn("◀️ بازگشت", S_P, callback_data="filter:menu")]])


def target_chat_kb(token):
    share = (f"https://t.me/share/url?url=https://t.me/{Config.BOT_USERNAME}?start=tc_{token}"
             f"&text=یک پیام ناشناس برایت دارم")
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📤 اشتراک‌گذاری", S_S, url=share)],
        [_ibtn("🗑 لغو", S_D, callback_data=f"tc:cancel:{token}")]])


def join_channel_kb(url):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📢 عضویت در کانال", S_P, url=url)],
        [_ibtn("✅ تایید عضویت", S_S, callback_data="check_join")]])


def admin_channel_kb(has):
    rows = [[_ibtn("🔧 تنظیم کانال", S_P, callback_data="admin_ch:set")]]
    if has:
        rows.append([_ibtn("🗑 حذف", S_D, callback_data="admin_ch:remove")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("🚫 بن", S_D, callback_data=f"adm:ban:{uid}"),
         _ibtn("✅ آنبن", S_S, callback_data=f"adm:unban:{uid}")],
        [_ibtn("⚠️ اخطار", S_D, callback_data=f"adm:warn:{uid}"),
         _ibtn("🔇 سکوت ۱س", S_D, callback_data=f"adm:mute:{uid}")],
        [_ibtn("🔊 رفع سکوت", S_S, callback_data=f"adm:unmute:{uid}")],
        [_ibtn("📨 پیام", S_P, callback_data=f"adm:msg:{uid}")],
        [_ibtn("💰 +سکه", S_S, callback_data=f"adm:coins:{uid}")],
        [_ibtn("🗑 پاک اخطار", S_D, callback_data=f"adm:clearwarn:{uid}")]])


def report_review_kb(rid, uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("✅ تأیید", S_S, callback_data=f"rep:ok:{rid}:{uid}"),
         _ibtn("❌ رد", S_D, callback_data=f"rep:no:{rid}:{uid}")]])


def room_kb(rid):
    share = f"https://t.me/{Config.BOT_USERNAME}?start=room_{rid}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📤 دعوت", S_S, url=f"https://t.me/share/url?url={share}")],
        [_ibtn("🚪 خروج", S_D, callback_data=f"room:leave:{rid}")]])


def reply_btn_kb(cid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        _ibtn("💬 پاسخ ناشناس", S_P, callback_data=f"areply:{cid}"),
        _ibtn("🚫 بلاک", S_D, callback_data=f"ablock:{cid}")]])


def feedback_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("✍️ ارسال بازخورد", S_S, callback_data="fb:new")],
        [_ibtn("📋 بازخوردهای من", S_P, callback_data="fb:mine")],
    ])


# ═══════════════════════════════════════════════════════════════════════
# ۱۴ ── STATES
# ═══════════════════════════════════════════════════════════════════════

class LangS(StatesGroup):
    choosing = State()


class RulesS(StatesGroup):
    showing = State()


class ProfileS(StatesGroup):
    gender = State()
    age = State()
    province = State()
    city = State()
    search_province = State()
    search_city = State()


class AvatarS(StatesGroup):
    uploading = State()


class LinkS(StatesGroup):
    choosing_type = State()


class AnonS(StatesGroup):
    waiting = State()
    confirm = State()


class ReplyS(StatesGroup):
    waiting = State()


class TargetS(StatesGroup):
    waiting = State()
    active = State()


class TargetCreatorS(StatesGroup):
    chatting = State()


class MatchS(StatesGroup):
    configuring = State()
    searching = State()
    chatting = State()


class RoomS(StatesGroup):
    creating = State()
    chatting = State()


class DatingS(StatesGroup):
    browsing = State()
    waiting_age = State()
    chatting = State()


class GameS(StatesGroup):
    guessing = State()


class FeedbackS(StatesGroup):
    waiting = State()


class AdminS(StatesGroup):
    broadcasting = State()
    broadcasting_confirm = State()
    setting_channel = State()
    searching_user = State()
    sending_to_user = State()
    sending_coins = State()


# ═══════════════════════════════════════════════════════════════════════
# ۱۵ ── MIDDLEWARES
# ═══════════════════════════════════════════════════════════════════════

class TokenBucket:
    def __init__(self, cap, refill):
        self.cap = cap
        self.refill = refill
        self._b: dict[int, tuple[float, float]] = {}
        self._lk = asyncio.Lock()

    async def consume(self, uid, cost=1.0):
        async with self._lk:
            now = time.monotonic()
            t, last = self._b.get(uid, (float(self.cap), now))
            t = min(self.cap, t + (now - last) * self.refill)
            if t >= cost:
                self._b[uid] = (t - cost, now)
                return True, t - cost
            self._b[uid] = (t, now)
            return False, t


rate_limiter = TokenBucket(Config.RATE_CAPACITY, Config.RATE_REFILL)


class BanCheck(BaseMiddleware):
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
                    await event.answer(f"🚫 بن شده‌اید.\nدلیل: {reason}")
                else:
                    await event.answer("🚫 بن.", show_alert=True)
                return None
            muted, until = await user_repo.is_muted(uid)
            if muted:
                if isinstance(event, Message):
                    await event.answer(f"🔇 تا {until[:16]} سکوت.")
                else:
                    await event.answer("🔇 سکوت.", show_alert=True)
                return None
        return await handler(event, data)


async def check_membership(bot, channel, uid):
    try:
        m = await bot.get_chat_member(chat_id=channel, user_id=uid)
        return m.status not in ("left", "kicked")
    except Exception:
        return True


class JoinCheck(BaseMiddleware):
    async def __call__(self, handler, event, data):
        bot: Bot = data.get("bot")
        uid = None
        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            uid = event.from_user.id
        if not uid or uid == Config.ADMIN_ID:
            return await handler(event, data)
        if await settings_repo.is_maint():
            if isinstance(event, Message):
                await event.answer("🔧 در تعمیر.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🔧 در تعمیر.", show_alert=True)
            return None
        req = await settings_repo.get_channel()
        if not req:
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data == "check_join":
            ok = await check_membership(bot, req, uid)
            if ok:
                await event.answer("✅ تایید شد!", show_alert=True)
                try:
                    await event.message.delete()
                except Exception:
                    pass
                try:
                    await bot.send_message(uid, with_footer(
                        "✅ <b>عضویت تایید شد!</b>\n\n🚀 روی دکمه زیر بزن تا وارد شوی."),
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                            _ibtn("🚀 شروع", S_S, callback_data="go_start")]]))
                except Exception:
                    pass
            else:
                await event.answer("❌ هنوز عضو نشدی!", show_alert=True)
            return None
        if await check_membership(bot, req, uid):
            return await handler(event, data)
        if req.startswith("@"):
            url = f"https://t.me/{req.lstrip('@')}"
        else:
            try:
                url = await bot.export_chat_invite_link(req)
            except Exception:
                url = "https://t.me/"
        txt = ("🔒 <b>ورود محدود!</b>\n\n"
               "برای استفاده ابتدا در کانال زیر عضو شوید:\n\n"
               f"📢 <b>{req}</b>\n\n"
               "سپس روی «✅ تایید عضویت» بزنید.")
        try:
            if isinstance(event, Message):
                await event.answer(txt, reply_markup=join_channel_kb(url))
            else:
                await event.message.answer(txt, reply_markup=join_channel_kb(url))
                await event.answer()
        except Exception:
            pass
        return None


class RateLimit(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
            if uid != Config.ADMIN_ID:
                st = data.get("state")
                skip = {
                    AnonS.waiting.state, MatchS.chatting.state,
                    TargetS.active.state, TargetCreatorS.chatting.state,
                    RoomS.chatting.state, ReplyS.waiting.state,
                    DatingS.browsing.state, DatingS.chatting.state,
                    GameS.guessing.state, FeedbackS.waiting.state,
                    ProfileS.gender.state, ProfileS.age.state,
                    ProfileS.province.state, ProfileS.city.state,
                    ProfileS.search_province.state, ProfileS.search_city.state,
                }
                cur = None
                if st is not None:
                    try:
                        cur = await st.get_state()
                    except Exception:
                        pass
                if cur not in skip:
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
        token = gen_token()
        while await link_repo.get(token):
            token = gen_token()
        await link_repo.create(token, owner, ltype)
        await user_repo.inc_link(owner)
        return {"ok": True, "token": token, "type": ltype,
                "link": f"https://t.me/{Config.BOT_USERNAME}?start={token}"}

    async def validate(self, token):
        if not token or len(token) < 10:
            return False, None, "توکن نامعتبر"
        l = await link_repo.get(token)
        if not l:
            return False, None, "لینک وجود ندارد"
        if l["link_type"] == "onetime" and l["is_used"]:
            return False, None, "استفاده شده"
        return True, l, ""

    async def consume(self, token, uid, ltype):
        if ltype == "onetime":
            await link_repo.mark_used(token, uid)


class MessageService:
    @staticmethod
    def _kb(cid):
        return reply_btn_kb(cid)

    async def send(self, bot, owner, sender, token, ctype, content, fid, analysis=None):
        tox = analysis["toxicity"] if analysis else 0.0
        cid = await conv_repo.get_or_create(owner, sender, token)
        await msg_repo.create(owner, sender, token, content, ctype, fid, tox, 0.0, cid)
        await user_repo.inc_msg(owner)
        h = (f"📩 <b>پیام ناشناس جدید</b>\n"
             f"{fa_now_str()}\n"
             f"━━━━━━━━━━━━━━━━\n"
             f"🔒 برای پاسخ روی دکمه زیر بزن:")
        try:
            if ctype == "text":
                await bot.send_message(owner, h + "\n\n" + (content or ""),
                                       reply_markup=self._kb(cid))
            elif ctype == "photo":
                await bot.send_photo(owner, fid, caption=h + "\n\n" + (content or ""),
                                     reply_markup=self._kb(cid))
            elif ctype == "voice":
                await bot.send_voice(owner, fid, caption=h + "\n\n" + (content or ""),
                                     reply_markup=self._kb(cid))
            elif ctype == "video":
                await bot.send_video(owner, fid, caption=h + "\n\n" + (content or ""),
                                     reply_markup=self._kb(cid))
            elif ctype == "document":
                await bot.send_document(owner, fid, caption=h + "\n\n" + (content or ""),
                                        reply_markup=self._kb(cid))
            elif ctype == "sticker":
                await bot.send_sticker(owner, fid, reply_markup=self._kb(cid))
            else:
                return {"ok": False, "error": "نوع پشتیبانی نمی‌شود"}
        except TelegramForbiddenError:
            return {"ok": False, "error": "بلاک کرده"}
        except Exception as e:
            log.exception("send: %s", e)
            return {"ok": False, "error": "خطا"}
        return {"ok": True, "conversation_id": cid}

    async def send_reply(self, bot, cid, from_uid, ctype, content, fid, analysis=None):
        conv = await conv_repo.get(cid)
        if not conv or not conv["active"]:
            return {"ok": False, "error": "بسته است."}
        if from_uid == conv["owner_id"]:
            target = conv["sender_id"]
            label = "💬 <b>پاسخ از طرف مالک</b>"
        elif from_uid == conv["sender_id"]:
            target = conv["owner_id"]
            label = "💬 <b>پاسخ جدید از فرستنده</b>"
        else:
            return {"ok": False, "error": "دسترسی ندارید."}
        tox = analysis["toxicity"] if analysis else 0.0
        await msg_repo.create(target, from_uid, None, content, ctype, fid, tox, 0.0, cid)
        h = f"{label}\n{fa_now_str()}\n━━━━━━━━━━━━━━━━"
        kb = self._kb(cid)
        try:
            if ctype == "text":
                await bot.send_message(target, h + "\n\n" + (content or ""), reply_markup=kb)
            elif ctype == "photo":
                await bot.send_photo(target, fid, caption=h + "\n\n" + (content or ""),
                                     reply_markup=kb)
            elif ctype == "voice":
                await bot.send_voice(target, fid, caption=h + "\n\n" + (content or ""),
                                     reply_markup=kb)
            elif ctype == "video":
                await bot.send_video(target, fid, caption=h + "\n\n" + (content or ""),
                                     reply_markup=kb)
            elif ctype == "document":
                await bot.send_document(target, fid, caption=h + "\n\n" + (content or ""),
                                        reply_markup=kb)
            elif ctype == "sticker":
                await bot.send_sticker(target, fid, reply_markup=kb)
            else:
                return {"ok": False, "error": "نوع پشتیبانی نمی‌شود"}
        except Exception as e:
            log.exception("reply: %s", e)
            return {"ok": False, "error": "خطا"}
        return {"ok": True}


class SmartMatcher:
    W = {"age": 0.35, "city": 0.25, "level": 0.20, "activity": 0.20}

    def __init__(self):
        self.queue = []

    async def find_best(self, uid, f, p, m):
        self.queue = [q for q in self.queue if q["user_id"] != uid]
        best, bs, bi = None, -1.0, -1
        for i, q in enumerate(self.queue):
            if not self._pass(f, p, q["filters"], q["profile"]):
                continue
            s = self._score(p, m, q["profile"], q["meta"])
            if s > bs:
                bs, best, bi = s, q, i
        if best is not None:
            self.queue.pop(bi)
            return best["user_id"], bs
        self.queue.append({"user_id": uid, "filters": f, "profile": p, "meta": m})
        return None, 0.0

    @staticmethod
    def _pass(f1, p1, f2, p2):
        if not (f1["min_age"] <= p2["age"] <= f1["max_age"]):
            return False
        if not (f2["min_age"] <= p1["age"] <= f2["max_age"]):
            return False
        if f1["gender"] != "any" and f1["gender"] != p2["gender"]:
            return False
        if f2["gender"] != "any" and f2["gender"] != p1["gender"]:
            return False
        if f1["same_city"] and p1["city"] != p2["city"]:
            return False
        if f2["same_city"] and p1["city"] != p2["city"]:
            return False
        return True

    def _score(self, p1, m1, p2, m2):
        a = max(0.0, 1.0 - abs(p1["age"] - p2["age"]) / 20.0)
        c = 1.0 if p1["city"] == p2["city"] else (
            0.5 if p1["province"] == p2["province"] else 0.0)
        l = max(0.0, 1.0 - abs(m1.get("level", 1) - m2.get("level", 1)) / 10.0)

        def rec(ls):
            try:
                dt = datetime.fromisoformat(ls)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=IRAN_TZ)
                return max(0.0, 1.0 - (now_iran() - dt).total_seconds() / 3600 / 72.0)
            except Exception:
                return 0.5

        act = (rec(m1.get("last_seen", "")) + rec(m2.get("last_seen", ""))) / 2.0
        return (self.W["age"] * a + self.W["city"] * c +
                self.W["level"] * l + self.W["activity"] * act)

    def cancel(self, uid):
        self.queue = [q for q in self.queue if q["user_id"] != uid]

    def size(self):
        return len(self.queue)


class AdminService:
    async def dashboard(self):
        return {
            "users": await user_repo.count(),
            "users_today": await user_repo.count_today(),
            "active_24h": await user_repo.count_active_24h(),
            "banned": await user_repo.count_banned(),
            "muted": await user_repo.count_muted(),
            "links_total": await link_repo.count_total(),
            "links_active": await link_repo.count_active(),
            "messages_total": await msg_repo.count_total(),
            "messages_today": await msg_repo.count_today(),
            "flagged_today": await msg_repo.count_flagged(),
            "pairings_total": await pairing_repo.count_total(),
            "pairings_active": await pairing_repo.count_active(),
            "reports_pending": await report_repo.count_pending(),
            "warnings": await warn_repo.count(),
            "rooms": await room_repo.count(),
            "conv_total": await conv_repo.count_total(),
            "conv_active": await conv_repo.count_active(),
            "dating_matches": await dating_repo.total_matches(),
            "dating_likes": await dating_repo.total_likes(),
            "feedback_new": await feedback_repo.count_new(),
            "queue": match_svc.size(),
            "channel": (await settings_repo.get_channel()) or "—",
            "maintenance": await settings_repo.is_maint(),
            "cache": cache.stats(),
            "logs": await admin_log_repo.count(),
        }

    async def broadcast(self, bot, chat_id, msg_id, users):
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

    async def backup(self):
        try:
            with open(Config.DB_PATH, "rb") as fp:
                return fp.read()
        except Exception:
            return b""


class GamificationService:
    async def award_xp(self, bot, uid, amount, reason=""):
        if amount <= 0:
            return None
        xp, lvl, leveled = await user_repo.add_xp(uid, amount)
        if leveled:
            try:
                await bot.send_message(uid, with_footer(
                    f"🎉 <b>سطح جدید!</b>\n\n🎖 سطح: <b>{lvl}</b>\n✨ XP: <b>{xp}</b>"))
            except Exception:
                pass
            return {"leveled": True, "new_level": lvl}
        return None

    async def check_badges(self, bot, uid):
        granted = []
        u = await user_repo.get(uid)
        if not u:
            return granted
        p = await profile_repo.get(uid)
        if await user_repo.count() <= 100:
            if await ach_repo.grant(uid, Badges.EARLY[1]):
                granted.append(Badges.EARLY[1])
        if u["message_count"] >= 100:
            if await ach_repo.grant(uid, Badges.CHATTER[1]):
                granted.append(Badges.CHATTER[1])
        if (await msg_repo.count_for(uid)) >= 50:
            if await ach_repo.grant(uid, Badges.POPULAR[1]):
                granted.append(Badges.POPULAR[1])
        if p and p["avatar_url"] and is_custom_avatar(p["avatar_url"]):
            if await ach_repo.grant(uid, Badges.VERIFIED[1]):
                granted.append(Badges.VERIFIED[1])
        if (await dating_repo.likes_of(uid)) >= 10:
            if await ach_repo.grant(uid, Badges.LOVER[1]):
                granted.append(Badges.LOVER[1])
        if (u["wins"] or 0) >= 20:
            if await ach_repo.grant(uid, Badges.GAMER[1]):
                granted.append(Badges.GAMER[1])
        if u["xp"] >= 1000:
            if await ach_repo.grant(uid, Badges.RICH[1]):
                granted.append(Badges.RICH[1])
        if u["level"] >= 20:
            if await ach_repo.grant(uid, Badges.LEGEND[1]):
                granted.append(Badges.LEGEND[1])
        for b in granted:
            try:
                await bot.send_message(uid, with_footer(f"🏅 بج جدید: <b>{b}</b>"))
            except Exception:
                pass
        return granted


class Analytics:
    async def funnel(self):
        return {
            "total": await user_repo.count(),
            "rules": int(await db.fetch_val(
                "SELECT COUNT(*) FROM users WHERE rules_accepted=1", (), 0)),
            "profile": int(await db.fetch_val("SELECT COUNT(*) FROM profiles", (), 0)),
            "link": int(await db.fetch_val(
                "SELECT COUNT(DISTINCT owner_id) FROM anonymous_links", (), 0)),
            "msg": int(await db.fetch_val(
                "SELECT COUNT(DISTINCT owner_id) FROM messages", (), 0)),
        }

    async def dwm(self):
        d = int(await db.fetch_val(
            "SELECT COUNT(*) FROM users WHERE date(last_seen)=date('now')", (), 0))
        w = int(await db.fetch_val(
            "SELECT COUNT(*) FROM users WHERE datetime(last_seen) > datetime('now','-7 day')",
            (), 0))
        m = int(await db.fetch_val(
            "SELECT COUNT(*) FROM users WHERE datetime(last_seen) > datetime('now','-30 day')",
            (), 0))
        return {"dau": d, "wau": w, "mau": m}

    async def top_prov(self, n=5):
        return await db.fetch_all(
            "SELECT province, COUNT(*) AS c FROM profiles GROUP BY province ORDER BY c DESC LIMIT ?",
            (n,))

    async def last_7(self):
        return await stats_repo.last(7)


def rbar(v, m, w=20):
    if m <= 0:
        return ""
    f = min(w, int(w * v / m))
    return "█" * f + "░" * (w - f)


link_svc = LinkService()
message_svc = MessageService()
match_svc = SmartMatcher()
admin_svc = AdminService()
gamif_svc = GamificationService()
analytics = Analytics()


# ═══════════════════════════════════════════════════════════════════════
# ۱۷ ── ROUTERS
# ═══════════════════════════════════════════════════════════════════════

lang_r = Router()
rules_r = Router()
profile_r = Router()
avatar_r = Router()
settings_r = Router()
link_r = Router()
anon_r = Router()
reply_r = Router()
target_r = Router()
match_r = Router()
room_r = Router()
gamif_r = Router()
dating_r = Router()
game_r = Router()
fb_r = Router()
admin_r = Router()
common_r = Router()


# ═══════════════════ LANG / RULES ═══════════════════

@lang_r.callback_query(F.data.startswith("lang:"))
async def cb_lang(cb: CallbackQuery, state: FSMContext):
    lang = cb.data.split(":")[1]
    await user_repo.set_language(cb.from_user.id, lang)
    await state.update_data(lang=lang)
    await cb.answer("✅")
    try:
        await cb.message.edit_text(with_footer(f"🌍 <b>خوش آمدی!</b>\n\n{RULES_FA}"),
                                   reply_markup=rules_kb())
    except TelegramBadRequest:
        pass
    await state.set_state(RulesS.showing)


@rules_r.callback_query(F.data == "rules:accept", RulesS.showing)
async def cb_rules_accept(cb: CallbackQuery, state: FSMContext):
    await user_repo.accept_rules(cb.from_user.id)
    await state.clear()
    p = await profile_repo.get(cb.from_user.id)
    if not p:
        try:
            await cb.message.delete()
        except Exception:
            pass
        await start_profile_flow(cb.message, state)
    else:
        try:
            await cb.message.edit_text(with_footer("🏠 <b>منوی اصلی</b>"),
                                       reply_markup=main_menu_kb(
                                           cb.from_user.id == Config.ADMIN_ID))
        except TelegramBadRequest:
            pass
    await cb.answer("✅")


@rules_r.callback_query(F.data == "rules:decline", RulesS.showing)
async def cb_rules_decline(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.edit_text(with_footer("😔 برای استفاده باید بپذیری. /start"))
    except Exception:
        pass
    await cb.answer("😔")


# ═══════════════════ WELCOME ═══════════════════

def welcome_message(name: str) -> str:
    g = greeting_by_hour()
    return with_footer(
        "╔══════════════════════════════════╗\n"
        f"║   ✨ <b>خوش آمدی {name} عزیز</b> ✨   ║\n"
        "╚══════════════════════════════════╝\n"
        "\n"
        f"{g}\n\n"
        "🎯 <b>ربات ناشناس پیشرفته</b> در خدمت شماست\n\n"
        "🌟 <b>قابلیت‌های من:</b>\n"
        "  🔗 دریافت لینک ناشناس\n"
        "  💬 چت دوطرفه ناشناس\n"
        "  💖 دوستیابی با مچ هوشمند\n"
        "  🎮 بازی‌های متنوع و سرگرم‌کننده\n"
        "  🏆 سیستم سطح، سکه و دستاورد\n"
        "  🎁 پاداش روزانه و لینک دعوت\n\n"
        "💡 <b>نکته:</b> از منوی پایین شروع کن!")


# ═══════════════════ /START ═══════════════════

@common_r.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext, bot: Bot):
    await state.clear()
    uid = message.from_user.id
    payload = (command.args or "").strip()

    if payload.startswith("ref_"):
        code = payload[4:]
        existing = await user_repo.get(uid)
        if not existing:
            ref = await db.fetch_one(
                "SELECT user_id FROM users WHERE referral_code=?", (code,))
            if ref and ref["user_id"] != uid:
                await user_repo.create(uid, message.from_user.full_name,
                                       message.from_user.username,
                                       ref_id=ref["user_id"])
                await user_repo.add_xp(ref["user_id"], Config.XP_REFERRAL)
                await user_repo.add_coins(ref["user_id"], 20)
                try:
                    await bot.send_message(ref["user_id"], with_footer(
                        f"🎁 <b>یک نفر با لینک تو عضو شد!</b>\n"
                        f"✨ +{Config.XP_REFERRAL} XP\n💰 +20 سکه"))
                except Exception:
                    pass
        payload = ""

    if not await user_repo.exists(uid):
        await user_repo.create(uid, message.from_user.full_name,
                               message.from_user.username)
        await stats_repo.bump("new_users")
    else:
        await user_repo.update_profile(uid, message.from_user.full_name,
                                       message.from_user.username)

    user = await user_repo.get(uid)
    if not user or not user["rules_accepted"]:
        await state.set_state(LangS.choosing)
        await message.answer(
            with_footer(
                "╔══════════════════════════╗\n"
                "║  🌍 <b>انتخاب زبان</b>   ║\n"
                "╚══════════════════════════╝\n\n"
                "زبان خود را انتخاب کنید:"),
            reply_markup=language_kb())
        return

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
        await state.set_state(TargetS.active)
        await message.answer(with_footer("🔒 <b>چت با مخاطب خاص</b>\n\n/endchat برای پایان"),
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
        await state.set_state(RoomS.chatting)
        await state.update_data(room_id=rid)
        await message.answer(
            with_footer(f"🏠 به اتاق «<b>{room['name']}</b>» خوش آمدی!\n\n"
                        f"/endchat برای خروج"),
            reply_markup=ReplyKeyboardRemove())
        for m in await room_repo.members(rid):
            if m["user_id"] != uid:
                try:
                    await bot.send_message(m["user_id"], with_footer("👤 یک نفر جدید پیوست!"))
                except Exception:
                    pass
        return

    if payload:
        ok, l, err = await link_svc.validate(payload)
        if not ok:
            await message.answer(with_footer(f"❌ {err}"))
            return
        if l["owner_id"] == uid:
            await message.answer("🙂 نمی‌توانی به خودت پیام بفرستی.")
            return
        if not await profile_repo.get(uid):
            await message.answer("⚠️ ابتدا پروفایل بساز. /start")
            return
        await state.update_data(token=payload, owner_id=l["owner_id"],
                                link_type=l["link_type"])
        await state.set_state(AnonS.waiting)
        await message.answer(with_footer("📩 <b>ارسال پیام ناشناس</b>\n\nپیامت رو بفرست:"),
                             reply_markup=cancel_kb("anon:cancel"))
        return

    if not await profile_repo.get(uid):
        await start_profile_flow(message, state)
        return

    await message.answer(welcome_message(message.from_user.first_name or "کاربر"),
                         reply_markup=main_menu_kb(uid == Config.ADMIN_ID))


@common_r.callback_query(F.data == "go_start")
async def cb_go_start(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    try:
        await cb.message.delete()
    except Exception:
        pass
    uid = cb.from_user.id
    if not await user_repo.exists(uid):
        await user_repo.create(uid, cb.from_user.full_name, cb.from_user.username)
    user = await user_repo.get(uid)
    if not user or not user["rules_accepted"]:
        await state.set_state(LangS.choosing)
        await cb.message.answer(with_footer("🌍 <b>انتخاب زبان:</b>"),
                                reply_markup=language_kb())
        return
    if not await profile_repo.get(uid):
        await start_profile_flow(cb.message, state)
        return
    await cb.message.answer(welcome_message(cb.from_user.first_name or "کاربر"),
                            reply_markup=main_menu_kb(uid == Config.ADMIN_ID))


# ═══════════════════ COMMANDS ═══════════════════

@common_r.message(Command("help"))
async def cmd_help(message: Message):
    is_admin = message.from_user.id == Config.ADMIN_ID
    base = (
        "╔══════════════════════════════════╗\n"
        "║      🤖 <b>راهنمای کامل</b>      ║\n"
        "╚══════════════════════════════════╝\n\n"
        "🎯 <b>دستورات اصلی</b>\n"
        "┌─────────────────────────\n"
        "│ /start      🚀 شروع\n"
        "│ /help       ❓ همین راهنما\n"
        "│ /profile    👤 پروفایل من\n"
        "│ /me         🎖 سطح و XP\n"
        "│ /top        🏆 ۱۰ نفر برتر\n"
        "│ /invite     🎁 لینک دعوت\n"
        "│ /time       🕐 ساعت ایران\n"
        "│ /rules      📜 قوانین\n"
        "│ /stats      📊 آمار ربات\n"
        "│ /myid       🆔 آیدی من\n"
        "└─────────────────────────\n\n"
        "💖 <b>دوستیابی</b>\n"
        "┌─────────────────────────\n"
        "│ /dating     💘 شروع گشت\n"
        "│ /likes      ❤️ لایک‌های من\n"
        "│ /matches    💞 مچ‌های من\n"
        "└─────────────────────────\n\n"
        "🎮 <b>سرگرمی</b>\n"
        "┌─────────────────────────\n"
        "│ /games      🎲 منوی بازی‌ها\n"
        "│ /daily      🎁 پاداش روزانه\n"
        "│ /coins      💰 موجودی سکه\n"
        "│ /feedback   📣 ارسال بازخورد\n"
        "└─────────────────────────\n\n"
        "🔧 <b>ابزارها</b>\n"
        "┌─────────────────────────\n"
        "│ /settings   ⚙️ تنظیمات\n"
        "│ /cancel     ❌ لغو\n"
        "│ /endchat    🚪 پایان چت\n"
        "└─────────────────────────\n"
    )
    if is_admin:
        base += (
            "\n👑 <b>ادمین</b>\n"
            "┌─────────────────────────\n"
            "│ /admin            🎛 پنل\n"
            "│ /ping             🏓 پینگ\n"
            "│ /userinfo ID      👤 اطلاعات\n"
            "│ /ban /unban       🚫 / ✅\n"
            "│ /warn /unwarn     ⚠️\n"
            "│ /mute /unmute     🔇 / 🔊\n"
            "│ /broadcast        📢 همگانی\n"
            "│ /search متن       🔍\n"
            "│ /maintenance on|off 🔧\n"
            "│ /backup           💾\n"
            "└─────────────────────────"
        )
    await message.answer(with_footer(base))


@common_r.message(Command("myid"))
async def cmd_myid(message: Message):
    uid = message.from_user.id
    u = await user_repo.get(uid)
    ref = u["referral_code"] if u else "—"
    await message.answer(with_footer(
        f"╭─ 🆔 <b>هویت شما</b>\n"
        f"│ 🔑 آیدی: <code>{uid}</code>\n"
        f"│ 🔗 کد دعوت: <code>{ref}</code>\n"
        f"╰─ 💾 ذخیره کن!"))


@common_r.message(Command("time"))
async def cmd_time(message: Message):
    await message.answer(fa_now_full())


@common_r.message(Command("rules"))
async def cmd_rules(message: Message):
    await message.answer(with_footer(RULES_FA))


@common_r.message(Command("me"))
async def cmd_me(message: Message):
    uid = message.from_user.id
    u = await user_repo.get(uid)
    if not u:
        await message.answer("❌")
        return
    xp, lvl = u["xp"], u["level"]
    nx, px = xp_for_level(lvl + 1), xp_for_level(lvl)
    bar = progress_bar(xp - px, nx - px)
    badges = await ach_repo.list_for(uid)
    bl = [b for b in Badges.ALL if b[1] in [x["badge"] for x in badges]]
    bstr = " ".join(f"{b[0]}" for b in bl) or "—"
    await message.answer(with_footer(
        f"╭─ 🎖 <b>سطح من</b>\n"
        f"│ 🏅 سطح: <b>{lvl}</b>\n"
        f"│ ✨ XP: <b>{xp}</b> / {nx}\n"
        f"│ {bar}\n"
        f"│ 💰 سکه: <b>{u['coins']}</b>\n"
        f"│ 🏆 بج‌ها: {bstr}\n"
        f"│ 💬 پیام: <b>{u['message_count']}</b>\n"
        f"│ 🎮 برد/باخت: <b>{u['wins']}/{u['losses']}</b>\n"
        f"╰─ 🚀 ادامه بده!"))


@common_r.message(Command("top"))
async def cmd_top(message: Message):
    top = await user_repo.top_xp(10)
    lines = ["╔══ 🏆 <b>لیدربورد</b> ══╗\n"]
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    for i, r in enumerate(top):
        lines.append(
            f"{medals[i]} {(r['full_name'] or '—')[:18]}\n   ✨ {r['xp']} XP | L{r['level']}")
    lines.append("\n╚══════════════════╝")
    await message.answer(with_footer("\n".join(lines)))


@common_r.message(Command("invite"))
async def cmd_invite(message: Message, bot: Bot):
    uid = message.from_user.id
    u = await user_repo.get(uid)
    if not u:
        return
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{u['referral_code']}"
    share = f"https://t.me/share/url?url={link}&text=بیا با هم چت ناشناس کنیم!"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        _ibtn("📤 اشتراک‌گذاری", S_S, url=share)]])
    cnt = int(await db.fetch_val(
        "SELECT COUNT(*) FROM users WHERE referrer_id=?", (uid,), 0))
    await message.answer(
        with_footer(
            f"🎁 <b>دعوت دوستان</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🔗 لینک:\n<code>{link}</code>\n\n"
            f"👥 دعوت موفق: <b>{cnt}</b>\n"
            f"✨ پاداش: <b>{Config.XP_REFERRAL} XP</b> + <b>20 سکه</b>"),
        reply_markup=kb)


@common_r.message(Command("stats"))
async def cmd_stats(message: Message):
    s = await admin_svc.dashboard()
    if message.from_user.id == Config.ADMIN_ID:
        text = (
            "📊 <b>داشبورد</b>\n\n"
            f"👥 کاربران: <b>{s['users']}</b> (+{s['users_today']})\n"
            f"🟢 فعال ۲۴س: <b>{s['active_24h']}</b>\n"
            f"🚫 بن: <b>{s['banned']}</b> | 🔇 سکوت: <b>{s['muted']}</b>\n"
            f"🔗 لینک: <b>{s['links_total']}</b>\n"
            f"📨 پیام: <b>{s['messages_total']}</b>\n"
            f"💬 مکالمات: <b>{s['conv_total']}</b>\n"
            f"💖 دوستیابی: <b>{s['dating_matches']}</b> مچ\n"
            f"🚨 گزارش: <b>{s['reports_pending']}</b>\n"
            f"⚠️ اخطار: <b>{s['warnings']}</b>\n"
            f"💬 فیدبک: <b>{s['feedback_new']}</b>\n"
            f"🏠 اتاق: <b>{s['rooms']}</b>\n"
            f"🔒 کانال: <b>{s['channel']}</b>")
    else:
        text = (
            "📊 <b>آمار ربات</b>\n\n"
            f"👥 کاربران: <b>{s['users']}</b>\n"
            f"📨 پیام‌ها: <b>{s['messages_total']}</b>\n"
            f"💖 مچ دوستیابی: <b>{s['dating_matches']}</b>")
    await message.answer(with_footer(text))


@common_r.message(Command("daily"))
async def cmd_daily(message: Message, bot: Bot):
    uid = message.from_user.id
    r = await user_repo.claim_daily(uid)
    if r == "already":
        await message.answer(with_footer(
            "⏰ <b>امروز پاداش گرفتی!</b>\n\nفردا دوباره سر بزن. 😊"))
        return
    if not r:
        await message.answer("❌")
        return
    await gamif_svc.award_xp(bot, uid, Config.XP_DAILY)
    await message.answer(with_footer(
        f"🎉 <b>پاداش روزانه!</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 سکه: <b>+{r['reward']}</b>\n"
        f"✨ XP: <b>+{Config.XP_DAILY}</b>\n"
        f"🔥 استریک: <b>{r['streak']} روز</b>"))


@common_r.message(Command("coins"))
async def cmd_coins(message: Message):
    u = await user_repo.get(message.from_user.id)
    if not u:
        return
    await message.answer(with_footer(
        f"💰 <b>موجودی سکه</b>\n\n"
        f"🪙 سکه: <b>{u['coins']}</b>\n"
        f"🏅 سطح: <b>{u['level']}</b>"))


@common_r.message(Command("games"))
async def cmd_games(message: Message):
    await message.answer(with_footer("🎮 <b>منوی بازی‌ها</b>\n\nیه بازی انتخاب کن:"),
                         reply_markup=games_menu_kb())


@common_r.message(Command("feedback"))
async def cmd_feedback(message: Message, state: FSMContext):
    await state.set_state(FeedbackS.waiting)
    await message.answer(with_footer(
        "📣 <b>بازخورد شما</b>\n\n"
        "نظر، پیشنهاد یا انتقادت رو بفرست.\n"
        "تیم ما حتماً می‌خونه! 💙"),
        reply_markup=cancel_kb("global:cancel"))


@common_r.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    match_svc.cancel(message.from_user.id)
    await state.clear()
    await message.answer(with_footer("❌ لغو شد."),
                         reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID))


@common_r.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext):
    await state.clear()
    await show_profile(message)


@common_r.message(Command("settings"))
async def cmd_settings(message: Message):
    await message.answer(with_footer("⚙️ <b>تنظیمات پیشرفته</b>"),
                         reply_markup=settings_rkb())


@common_r.message(Command("endchat"))
async def cmd_endchat(message: Message, state: FSMContext, bot: Bot):
    uid = message.from_user.id
    cur = await state.get_state()
    data = await state.get_data()
    if cur == MatchS.chatting.state:
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
    if cur == TargetS.active.state:
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
    if cur == TargetCreatorS.chatting.state:
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
    if cur == RoomS.chatting.state:
        rid = data.get("room_id")
        if rid:
            await room_repo.leave(rid, uid)
            for m in await room_repo.members(rid):
                if m["user_id"] != uid:
                    try:
                        await bot.send_message(m["user_id"], with_footer("👋 یک نفر خارج شد."))
                    except Exception:
                        pass
        await state.clear()
        await message.answer(with_footer("🚪 خارج شدی."),
                             reply_markup=main_menu_kb(uid == Config.ADMIN_ID))
        return
    if cur == DatingS.chatting.state:
        m = await dating_repo.active_match(uid)
        if m:
            await dating_repo.end_match(m["id"])
            partner = m["user2_id"] if m["user1_id"] == uid else m["user1_id"]
            try:
                await bot.send_message(partner, with_footer("🚪 چت دوستیابی پایان یافت."))
            except Exception:
                pass
        await state.clear()
        await message.answer(with_footer("🚪 پایان."),
                             reply_markup=main_menu_kb(uid == Config.ADMIN_ID))
        return
    await message.answer("چت فعالی نداری.")


# ═══════════════════ COMMON CALLBACKS ═══════════════════

@common_r.callback_query(F.data == "global:cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    match_svc.cancel(cb.from_user.id)
    await state.clear()
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer(with_footer("🏠 <b>منوی اصلی</b>"),
                            reply_markup=main_menu_kb(cb.from_user.id == Config.ADMIN_ID))
    await cb.answer("❌")


@common_r.message(F.text == "🕐 ساعت")
async def btn_time(message: Message):
    await message.answer(fa_now_full())


@common_r.message(F.text == "📜 قوانین")
async def btn_rules(message: Message):
    await message.answer(with_footer(RULES_FA))


@common_r.message(F.text == "❓ راهنما")
async def btn_help(message: Message):
    await cmd_help(message)


# ═══════════════════ PROFILE FLOW ═══════════════════

async def start_profile_flow(message: Message, state: FSMContext, edit=False):
    await state.set_state(ProfileS.gender)
    text = with_footer(
        "╔══════════════════════════════╗\n"
        "║     🎨 <b>ساخت پروفایل</b>      ║\n"
        "╚══════════════════════════════╝\n"
        "🟢 ① جنسیت   →  انتخاب کن\n"
        "⚪ ② سن\n"
        "⚪ ③ استان\n"
        "⚪ ④ شهر\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "👤 <b>جنسیتت رو انتخاب کن:</b>")
    kb = profile_gender_rkb()
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb)
            return
        except TelegramBadRequest:
            pass
    await message.answer(text, reply_markup=kb)


@profile_r.message(ProfileS.gender)
async def pf_gender(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if txt in ("❌ لغو", "/cancel"):
        await state.clear()
        await message.answer(with_footer("❌ لغو."),
                             reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID))
        return
    if "پسر" in txt or "👨" in txt:
        gender = "male"
    elif "دختر" in txt or "👩" in txt:
        gender = "female"
    else:
        await message.answer("⚠️ یکی از دکمه‌ها رو بزن.", reply_markup=profile_gender_rkb())
        return
    await state.update_data(gender=gender)
    await state.set_state(ProfileS.age)
    await message.answer(
        with_footer(
            "🎨 <b>ساخت پروفایل</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"✅ ① جنسیت  →  <b>{gender_fa(gender)}</b>\n"
            "🟢 ② سن  →  انتخاب کن (۹ تا ۹۹)\n"
            "⚪ ③ استان\n"
            "⚪ ④ شهر\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "🎂 <b>سنت رو از جدول زیر انتخاب کن:</b>\n"
            "💡 همه دکمه‌ها سبز = فعال"),
        reply_markup=profile_age_rkb())


@profile_r.message(ProfileS.age)
async def pf_age(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if txt in ("❌ لغو", "/cancel", "◀️ بازگشت"):
        if txt == "◀️ بازگشت":
            await state.set_state(ProfileS.gender)
            await message.answer(with_footer("👤 <b>جنسیتت رو انتخاب کن:</b>"),
                                 reply_markup=profile_gender_rkb())
            return
        await state.clear()
        await message.answer(with_footer("❌ لغو."),
                             reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID))
        return
    m = re.search(r"\d+", txt)
    if not m:
        await message.answer("⚠️ از دکمه‌ها انتخاب کن.", reply_markup=profile_age_rkb())
        return
    age = int(m.group())
    if not (9 <= age <= 99):
        await message.answer("⚠️ عدد بین ۹ تا ۹۹.", reply_markup=profile_age_rkb())
        return
    await state.update_data(age=age, prov_page=0)
    await state.set_state(ProfileS.province)
    data = await state.get_data()
    await message.answer(
        with_footer(
            "🎨 <b>ساخت پروفایل</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"✅ ① جنسیت  →  <b>{gender_fa(data.get('gender'))}</b>\n"
            f"✅ ② سن  →  <b>{age}</b>\n"
            "🟢 ③ استان  →  انتخاب کن\n"
            "⚪ ④ شهر\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"🗺 <b>استانت رو انتخاب کن</b> ({len(PROVINCES)} استان)\n"
            "⭐ = استان پرطرفدار\n"
            "📖 = برای دیدن صفحه‌های بعد"),
        reply_markup=profile_province_rkb(0))


@profile_r.message(ProfileS.province)
async def pf_province(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    data = await state.get_data()
    cur_page = data.get("prov_page", 0)

    if txt in ("❌ لغو", "/cancel"):
        await state.clear()
        await message.answer(with_footer("❌ لغو."),
                             reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID))
        return

    if txt == "🔍 جستجوی استان":
        await state.set_state(ProfileS.search_province)
        await message.answer(
            with_footer("🔍 <b>جستجوی استان</b>\n\n"
                        "اسم استان رو تایپ کن:\n"
                        "💡 مثال: تهران، فارس، گیلان"),
            reply_markup=ReplyKeyboardMarkup(keyboard=[[_btn("❌ لغو", S_D)]],
                                             resize_keyboard=True,
                                             input_field_placeholder="نام استان..."))
        return

    if txt == "بعدی ▶️":
        new_page = min(cur_page + 1, _prov_page_count() - 1)
        await state.update_data(prov_page=new_page)
        await message.answer(
            with_footer(f"📖 صفحه <b>{new_page + 1}</b> از {_prov_page_count()}"),
            reply_markup=profile_province_rkb(new_page))
        return

    if txt == "◀️ قبلی":
        new_page = max(cur_page - 1, 0)
        await state.update_data(prov_page=new_page)
        await message.answer(
            with_footer(f"📖 صفحه <b>{new_page + 1}</b> از {_prov_page_count()}"),
            reply_markup=profile_province_rkb(new_page))
        return

    clean = re.sub(r"[⭐🏔🌋❄️🏛⛰🌲🌊🏙🦁🏜🕌🐎🌴🔪🦎🦚🍇🎵🌾🏞🐎🌧🏭⛵📜]", "", txt).strip()

    if clean not in PROVINCES:
        await message.answer("⚠️ از لیست انتخاب کن یا 🔍 جستجو بزن.",
                             reply_markup=profile_province_rkb(cur_page))
        return

    await state.update_data(province=clean, city_page=0)
    await state.set_state(ProfileS.city)
    cities_count = len(IRAN_DATA.get(clean, []))
    emoji = PROVINCE_EMOJI.get(clean, "🏙")
    await message.answer(
        with_footer(
            "🎨 <b>ساخت پروفایل</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✅ ① جنسیت\n"
            f"✅ ② سن  →  <b>{data.get('age')}</b>\n"
            f"✅ ③ استان  →  <b>{emoji} {clean}</b>\n"
            "🟢 ④ شهر  →  انتخاب کن\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"🏙 <b>شهرت رو انتخاب کن</b> ({cities_count} شهر)\n"
            "⭐ = شهر پرطرفدار\n"
            "📖 = برای صفحه‌های بعد"),
        reply_markup=profile_city_rkb(clean, 0))


@profile_r.message(ProfileS.search_province)
async def pf_search_province(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if txt in ("❌ لغو", "/cancel"):
        await state.set_state(ProfileS.province)
        await message.answer(with_footer("🗺 <b>استانت رو انتخاب کن:</b>"),
                             reply_markup=profile_province_rkb(0))
        return
    query = txt.strip()
    matches = [p for p in PROVINCES if query in p]
    if not matches:
        await message.answer(with_footer(
            f"❌ استانی با نام «{txt}» پیدا نشد.\n"
            "دوباره امتحان کن یا ❌ لغو بزن."))
        return
    if len(matches) == 1:
        p = matches[0]
        await state.update_data(province=p, city_page=0)
        await state.set_state(ProfileS.city)
        emoji = PROVINCE_EMOJI.get(p, "🏙")
        cities_count = len(IRAN_DATA.get(p, []))
        await message.answer(
            with_footer(f"✅ استان: <b>{emoji} {p}</b>\n\n"
                        f"🏙 حالا شهرت رو انتخاب کن ({cities_count} شهر):"),
            reply_markup=profile_city_rkb(p, 0))
        return
    rows = [[_btn(f"🏙 {p}", S_P)] for p in matches[:12]]
    rows.append([_btn("🔍 جستجوی دوباره", S_P), _btn("❌ لغو", S_D)])
    await message.answer(
        with_footer(f"🔍 <b>{len(matches)}</b> استان پیدا شد.\nیکی رو انتخاب کن:"),
        reply_markup=ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True,
                                         one_time_keyboard=True))


@profile_r.message(ProfileS.city)
async def pf_city(message: Message, state: FSMContext, bot: Bot):
    txt = (message.text or "").strip()
    data = await state.get_data()
    province = data.get("province")
    cur_page = data.get("city_page", 0)

    if txt in ("❌ لغو", "/cancel"):
        await state.clear()
        await message.answer(with_footer("❌ لغو."),
                             reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID))
        return

    if txt == "◀️ استان‌ها":
        await state.set_state(ProfileS.province)
        await state.update_data(prov_page=0)
        await message.answer(with_footer("🗺 <b>استانت رو انتخاب کن:</b>"),
                             reply_markup=profile_province_rkb(0))
        return

    if txt == "🔍 جستجوی شهر":
        await state.set_state(ProfileS.search_city)
        await message.answer(
            with_footer(f"🔍 <b>جستجوی شهر در {province}</b>\n\n"
                        "اسم شهرت رو تایپ کن:"),
            reply_markup=ReplyKeyboardMarkup(keyboard=[[_btn("❌ لغو", S_D)]],
                                             resize_keyboard=True,
                                             input_field_placeholder="نام شهر..."))
        return

    if txt == "بعدی ▶️":
        new_page = min(cur_page + 1, _city_page_count(province) - 1)
        await state.update_data(city_page=new_page)
        await message.answer(
            with_footer(f"📖 صفحه <b>{new_page + 1}</b> از {_city_page_count(province)}"),
            reply_markup=profile_city_rkb(province, new_page))
        return

    if txt == "◀️ قبلی":
        new_page = max(cur_page - 1, 0)
        await state.update_data(city_page=new_page)
        await message.answer(
            with_footer(f"📖 صفحه <b>{new_page + 1}</b> از {_city_page_count(province)}"),
            reply_markup=profile_city_rkb(province, new_page))
        return

    clean = re.sub(r"[⭐🏙📖]", "", txt).strip()

    if clean not in IRAN_DATA.get(province, []):
        await message.answer("⚠️ از لیست انتخاب کن یا 🔍 جستجو بزن.",
                             reply_markup=profile_city_rkb(province, cur_page))
        return

    await _finalize_profile(message, state, bot, clean)


@profile_r.message(ProfileS.search_city)
async def pf_search_city(message: Message, state: FSMContext, bot: Bot):
    txt = (message.text or "").strip()
    data = await state.get_data()
    province = data.get("province")

    if txt in ("❌ لغو", "/cancel"):
        await state.set_state(ProfileS.city)
        await message.answer(with_footer("🏙 <b>شهرت رو انتخاب کن:</b>"),
                             reply_markup=profile_city_rkb(province, 0))
        return

    cities = IRAN_DATA.get(province, [])
    matches = [c for c in cities if txt in c]
    if not matches:
        await message.answer(with_footer(
            f"❌ شهری با نام «{txt}» پیدا نشد.\n"
            "دوباره امتحان کن یا ❌ لغو بزن."))
        return
    if len(matches) == 1:
        await _finalize_profile(message, state, bot, matches[0])
        return
    rows = [[_btn(f"🏙 {c}", S_P)] for c in matches[:15]]
    rows.append([_btn("🔍 جستجوی دوباره", S_P), _btn("❌ لغو", S_D)])
    await message.answer(
        with_footer(f"🔍 <b>{len(matches)}</b> شهر پیدا شد.\nیکی رو انتخاب کن:"),
        reply_markup=ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True,
                                         one_time_keyboard=True))


async def _finalize_profile(message: Message, state: FSMContext, bot: Bot, city: str):
    data = await state.get_data()
    province = data.get("province")
    gender = data.get("gender")
    age = data.get("age")

    seed = f"{message.from_user.id}-{random.randint(1, 999999)}"
    avatar = avatar_url(gender, seed)
    await profile_repo.create(message.from_user.id, gender, age, province, city, avatar)
    await state.clear()

    emoji = PROVINCE_EMOJI.get(province, "🏙")
    caption = with_footer(
        "╔══════════════════════════════╗\n"
        "║   🎉 <b>پروفایل ساخته شد!</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"🎭 {gender_fa(gender)}\n"
        f"🎂 {age} سال\n"
        f"{emoji} {province}\n"
        f"🏙 {city}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>حالا از همه امکانات استفاده کن!</b>\n\n"
        "💡 /help برای دیدن دستورات")
    try:
        await bot.send_photo(message.from_user.id, avatar, caption=caption)
    except Exception:
        await message.answer(caption)
    await message.answer(
        welcome_message(message.from_user.first_name or "کاربر"),
        reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID))


async def show_profile(message: Message):
    uid = message.from_user.id
    p = await profile_repo.get(uid)
    if not p:
        await message.answer(with_footer("❌ پروفایل نداری. /start"))
        return
    u = await user_repo.get(uid)
    await user_repo.inc_views(uid)
    emoji = PROVINCE_EMOJI.get(p["province"], "🏙")
    text = with_footer(
        f"👤 <b>پروفایل من</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎭 {gender_fa(p['gender'])}\n"
        f"🎂 {p['age']} سال\n"
        f"{emoji} {p['province']}\n"
        f"🏙 {p['city']}\n"
        f"🎖 سطح: <b>{u['level'] if u else 1}</b>\n"
        f"✨ XP: <b>{u['xp'] if u else 0}</b>\n"
        f"💰 سکه: <b>{u['coins'] if u else 0}</b>\n"
        f"👁 بازدید: <b>{u['profile_views'] if u else 0}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📅 عضویت: {p['created_at'][:10]}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("✏️ ویرایش", S_P, callback_data="pf:edit")],
        [_ibtn("🎨 عکس", S_S, callback_data="av:edit")]])
    if p["avatar_url"]:
        try:
            fid = extract_fid(p["avatar_url"])
            await message.answer_photo(fid, caption=text, reply_markup=kb)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb)


@common_r.message(F.text == "👤 پروفایل من")
async def btn_profile(message: Message):
    await show_profile(message)


@common_r.callback_query(F.data == "pf:edit")
async def cb_pf_edit(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    try:
        await cb.message.delete()
    except Exception:
        pass
    await start_profile_flow(cb.message, state)


# ═══════════════════ AVATAR ═══════════════════

@avatar_r.callback_query(F.data == "av:edit")
async def cb_av_edit(cb: CallbackQuery):
    await cb.message.answer(with_footer("🎨 <b>تغییر عکس</b>"), reply_markup=avatar_edit_kb())
    await cb.answer()


@avatar_r.callback_query(F.data == "av:back")
async def cb_av_back(cb: CallbackQuery):
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.answer("بازگشت")


@avatar_r.callback_query(F.data == "av:random")
async def cb_av_random(cb: CallbackQuery, bot: Bot):
    p = await profile_repo.get(cb.from_user.id)
    if not p:
        await cb.answer("❌", show_alert=True)
        return
    seed = f"{cb.from_user.id}-{random.randint(1, 999999999)}"
    av = avatar_url(p["gender"], seed)
    await profile_repo.set_avatar(cb.from_user.id, av)
    try:
        await cb.message.delete()
    except Exception:
        pass
    try:
        await bot.send_photo(cb.from_user.id, av, caption=with_footer("🎲 عکس جدید!"))
    except Exception:
        pass
    await cb.answer("✅")


@avatar_r.callback_query(F.data.startswith("av:style:"))
async def cb_av_style(cb: CallbackQuery, bot: Bot):
    style = cb.data.split(":")[2]
    if style not in ("male", "female"):
        await cb.answer("❌")
        return
    p = await profile_repo.get(cb.from_user.id)
    if not p:
        await cb.answer("❌", show_alert=True)
        return
    seed = f"{cb.from_user.id}-{style}-{random.randint(1, 999999)}"
    av = avatar_url(style, seed)
    await profile_repo.set_avatar(cb.from_user.id, av)
    try:
        await cb.message.delete()
    except Exception:
        pass
    try:
        await bot.send_photo(cb.from_user.id, av,
                             caption=with_footer(f"🎨 {gender_fa(style)} جدید!"))
    except Exception:
        pass
    await cb.answer("✅")


@avatar_r.callback_query(F.data == "av:upload")
async def cb_av_upload(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarS.uploading)
    try:
        await cb.message.edit_text(with_footer("📸 <b>عکس را بفرست:</b>"),
                                   reply_markup=cancel_kb("global:cancel"))
    except Exception:
        pass
    await cb.answer()


@avatar_r.message(AvatarS.uploading, F.photo)
async def av_upload(message: Message, state: FSMContext, bot: Bot):
    fid = message.photo[-1].file_id
    await profile_repo.set_avatar(message.from_user.id, f"file:{fid}")
    await state.clear()
    await gamif_svc.check_badges(bot, message.from_user.id)
    try:
        await message.answer_photo(fid, caption=with_footer("✅ عکس تغییر کرد!"))
    except Exception:
        await message.answer(with_footer("✅"))


@avatar_r.message(AvatarS.uploading)
async def av_invalid(message: Message):
    await message.answer("⚠️ فقط عکس.")


# ═══════════════════ SETTINGS ═══════════════════

@settings_r.message(F.text == "⚙️ تنظیمات")
async def settings_menu(message: Message):
    await message.answer(
        with_footer(
            "⚙️ <b>تنظیمات پیشرفته</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔔 اعلان‌ها\n"
            "🛡 حریم خصوصی\n"
            "💬 چت و پیام\n"
            "🎨 ظاهر\n"
            "💖 دوستیابی\n"
            "📊 اطلاعات حساب\n"
            "━━━━━━━━━━━━━━━━"),
        reply_markup=settings_rkb())


@settings_r.message(F.text == "🔔 اعلان‌ها")
async def set_notif(message: Message):
    s = await usettings_repo.get(message.from_user.id)
    await message.answer(with_footer("🔔 <b>اعلان‌ها</b>"),
                         reply_markup=settings_notif_kb(s))


@settings_r.message(F.text == "🛡 حریم خصوصی")
async def set_priv(message: Message):
    s = await usettings_repo.get(message.from_user.id)
    await message.answer(with_footer("🛡 <b>حریم خصوصی</b>"),
                         reply_markup=settings_priv_kb(s))


@settings_r.message(F.text == "💬 چت و پیام")
async def set_chat(message: Message):
    s = await usettings_repo.get(message.from_user.id)
    await message.answer(with_footer("💬 <b>چت و پیام</b>"),
                         reply_markup=settings_chat_kb(s))


@settings_r.message(F.text == "🎨 ظاهر")
async def set_app(message: Message):
    s = await usettings_repo.get(message.from_user.id)
    await message.answer(with_footer("🎨 <b>ظاهر</b>"), reply_markup=settings_app_kb(s))


@settings_r.message(F.text == "💖 دوستیابی")
async def set_dating(message: Message, state: FSMContext):
    uid = message.from_user.id
    prefs = await dating_repo.get_prefs(uid)
    await state.set_state(DatingS.browsing)
    await message.answer(with_footer("💖 <b>دوستیابی</b>\n\nفیلترها رو تنظیم کن:"),
                         reply_markup=dating_menu_kb(prefs))


@settings_r.message(F.text == "📊 اطلاعات حساب")
async def set_account(message: Message, bot: Bot):
    uid = message.from_user.id
    u = await user_repo.get(uid)
    p = await profile_repo.get(uid)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{u['referral_code']}" if u else "—"
    likes = await dating_repo.likes_of(uid)
    matches = await dating_repo.matches_of(uid)
    text = (
        "📊 <b>اطلاعات حساب</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🆔 <code>{uid}</code>\n"
        f"👤 {u['full_name'] if u else '—'}\n"
        f"🌍 زبان: <b>{u['language'] if u else '—'}</b>\n"
        f"✨ XP: <b>{u['xp'] if u else 0}</b> (L{u['level'] if u else 1})\n"
        f"💰 سکه: <b>{u['coins'] if u else 0}</b>\n"
        f"💬 پیام: <b>{u['message_count'] if u else 0}</b>\n"
        f"🎮 برد/باخت: <b>{u['wins'] if u else 0}/{u['losses'] if u else 0}</b>\n"
        f"⚠️ اخطار: <b>{u['warn_count'] if u else 0}</b>\n"
        f"💖 لایک/مچ: <b>{likes}/{matches}</b>\n"
        f"👁 بازدید: <b>{u['profile_views'] if u else 0}</b>\n"
        f"📅 عضویت: {u['created_at'][:10] if u else '—'}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🔗 کد دعوت:\n<code>{link}</code>")
    if p:
        emoji = PROVINCE_EMOJI.get(p["province"], "🏙")
        text += f"\n\n🎭 {gender_fa(p['gender'])} | 🎂 {p['age']} | {emoji} {p['city']}"
    await message.answer(with_footer(text), reply_markup=settings_rkb())


@settings_r.message(F.text == "◀️ بازگشت")
async def set_back(message: Message):
    await message.answer(with_footer("🏠 <b>منوی اصلی</b>"),
                         reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID))


@settings_r.callback_query(F.data == "uset:menu")
async def cb_uset_menu(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer(with_footer("⚙️ <b>تنظیمات پیشرفته</b>"),
                            reply_markup=settings_rkb())


@settings_r.callback_query(F.data.startswith("uset:t:"))
async def cb_uset_toggle(cb: CallbackQuery):
    field = cb.data.split(":")[2]
    try:
        await usettings_repo.toggle(cb.from_user.id, field)
    except ValueError:
        await cb.answer("❌")
        return
    s = await usettings_repo.get(cb.from_user.id)
    if field in ("notify_msg", "notify_match", "notify_dating", "silent_mode"):
        kb, h = settings_notif_kb(s), "🔔 <b>اعلان‌ها</b>"
    elif field in ("hide_online", "read_receipt", "web_mode"):
        kb, h = settings_priv_kb(s), "🛡 <b>حریم خصوصی</b>"
    elif field in ("auto_delete", "auto_translate", "copyright_mode"):
        kb, h = settings_chat_kb(s), "💬 <b>چت و پیام</b>"
    else:
        kb, h = None, ""
    if kb:
        try:
            await cb.message.edit_text(with_footer(h), reply_markup=kb)
        except Exception:
            pass
    await cb.answer("✅" if s[field] else "❌")


@settings_r.callback_query(F.data.startswith("uset:theme:"))
async def cb_uset_theme(cb: CallbackQuery):
    theme = cb.data.split(":")[2]
    await usettings_repo.set_theme(cb.from_user.id, theme)
    s = await usettings_repo.get(cb.from_user.id)
    try:
        await cb.message.edit_reply_markup(reply_markup=settings_app_kb(s))
    except Exception:
        pass
    await cb.answer(f"🎨 {theme}")


# ═══════════════════ LINKS ═══════════════════

@link_r.message(F.text == "🔗 لینک ناشناس")
async def link_menu(message: Message, state: FSMContext):
    await state.set_state(LinkS.choosing_type)
    await message.answer(with_footer("🔗 <b>نوع لینک:</b>"), reply_markup=link_type_kb())


@link_r.callback_query(F.data.startswith("linktype:"), LinkS.choosing_type)
async def cb_linktype(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    ltype = cb.data.split(":")[1]
    ltype = "permanent" if ltype == "permanent" else "onetime"
    r = await link_svc.create(cb.from_user.id, ltype)
    if not r["ok"]:
        await cb.answer(r["error"], show_alert=True)
        return
    label = "♾ دائمی" if ltype == "permanent" else "1️⃣ یکبار"
    t = with_footer(f"✅ <b>لینک {label}</b>\n\n🔗 <code>{r['link']}</code>")
    try:
        await cb.message.edit_text(t, reply_markup=link_actions_kb(r["token"]))
    except Exception:
        await cb.message.answer(t, reply_markup=link_actions_kb(r["token"]))
    await cb.answer("✅")


@link_r.callback_query(F.data.startswith("link:del:"))
async def cb_link_del(cb: CallbackQuery):
    token = cb.data.split(":", 2)[2]
    l = await link_repo.get(token)
    if not l or l["owner_id"] != cb.from_user.id:
        await cb.answer("❌", show_alert=True)
        return
    await link_repo.delete(token)
    try:
        await cb.message.edit_text(with_footer("🗑 حذف شد."), reply_markup=None)
    except Exception:
        pass
    await cb.answer("✅")


@common_r.message(F.text == "📊 آمار من")
async def my_stats(message: Message):
    uid = message.from_user.id
    p = await profile_repo.get(uid)
    msgs = await msg_repo.count_for(uid)
    links = await link_repo.of_owner(uid)
    perm = sum(1 for l in links if l["link_type"] == "permanent")
    once = sum(1 for l in links if l["link_type"] == "onetime")
    u = await user_repo.get(uid)
    likes = await dating_repo.likes_of(uid)
    matches = await dating_repo.matches_of(uid)
    await message.answer(with_footer(
        "📊 <b>آمار من</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📨 پیام دریافتی: <b>{msgs}</b>\n"
        f"♾ لینک دائمی: <b>{perm}</b>\n"
        f"1️⃣ لینک یکبار: <b>{once}</b>\n"
        f"💖 لایک دوستیابی: <b>{likes}</b>\n"
        f"💞 مچ دوستیابی: <b>{matches}</b>\n"
        f"🎮 برد/باخت: <b>{u['wins'] if u else 0}/{u['losses'] if u else 0}</b>\n"
        f"💰 سکه: <b>{u['coins'] if u else 0}</b>\n"
        f"⚠️ اخطار: <b>{u['warn_count'] if u else 0}</b>\n"
        f"✨ XP: <b>{u['xp'] if u else 0}</b> (L{u['level'] if u else 1})\n"
        + (f"━━━━━━━━━━━━━━━━\n🎂 {p['age']} | 🏙 {p['city']}" if p else "")),
        reply_markup=main_menu_kb(uid == Config.ADMIN_ID))


# ═══════════════════ GAMIFICATION BUTTONS ═══════════════════

@gamif_r.message(F.text == "🎖 سطح من")
async def btn_me(message: Message):
    await cmd_me(message)


@gamif_r.message(F.text == "🏆 لیدربورد")
async def btn_top(message: Message):
    await cmd_top(message)


@gamif_r.message(F.text == "🎁 دعوت")
async def btn_invite(message: Message, bot: Bot):
    await cmd_invite(message, bot)


@gamif_r.message(F.text == "🎁 پاداش روزانه")
async def btn_daily(message: Message, bot: Bot):
    await cmd_daily(message, bot)


@gamif_r.message(F.text == "🎮 بازی‌ها")
async def btn_games(message: Message):
    await cmd_games(message)


@gamif_r.message(F.text == "⭐ علاقه‌مندی‌ها")
async def btn_favs(message: Message):
    uid = message.from_user.id
    favs = await fav_repo.list(uid)
    if not favs:
        await message.answer(with_footer("⭐ هنوز کسی رو ذخیره نکردی."))
        return
    lines = ["⭐ <b>علاقه‌مندی‌ها</b>\n"]
    for f in favs[:20]:
        u = await user_repo.get(f["fav_id"])
        lines.append(f"• <code>{f['fav_id']}</code> — {u['full_name'] if u else '—'}")
    await message.answer(with_footer("\n".join(lines)))


@gamif_r.message(F.text == "🔒 لیست بلاک")
async def btn_blocks(message: Message):
    uid = message.from_user.id
    blocks = await block_repo.list(uid)
    if not blocks:
        await message.answer(with_footer("🔒 لیست بلاک خالیه."))
        return
    lines = ["🔒 <b>لیست بلاک</b>\n"]
    for b in blocks[:20]:
        u = await user_repo.get(b["blocked_id"])
        lines.append(f"• <code>{b['blocked_id']}</code> — {u['full_name'] if u else '—'}")
    await message.answer(with_footer("\n".join(lines)),
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                             _ibtn("🗑 پاک کردن همه", S_D, callback_data="block:clear")]]))


@gamif_r.callback_query(F.data == "block:clear")
async def cb_block_clear(cb: CallbackQuery):
    await db.execute("DELETE FROM blocked_users WHERE user_id=?", (cb.from_user.id,))
    await cb.answer("✅ پاک شد", show_alert=True)
    try:
        await cb.message.delete()
    except Exception:
        pass


# ═══════════════════ ANONYMOUS ═══════════════════

@anon_r.message(AnonS.waiting)
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
    elif message.sticker:
        ctype, fid = "sticker", message.sticker.file_id
    else:
        await message.answer("⚠️ نوع پشتیبانی نمی‌شود.")
        return
    a = moderation.analyze(content or "") if content else None
    if a and moderation.is_flagged(a):
        owner_id = (await state.get_data()).get("owner_id")
        rid = await report_repo.create(message.from_user.id, owner_id, None,
                                       f"auto:{','.join(a['flags'])}")
        try:
            await message.bot.send_message(Config.ADMIN_ID, with_footer(
                f"🚨 <b>محتوای مشکوک</b>\n"
                f"👤 <code>{message.from_user.id}</code>\n"
                f"⚠️ {', '.join(a['flags'])}\n"
                f"📊 tox: {a['toxicity']}"),
                reply_markup=report_review_kb(rid, message.from_user.id))
        except Exception:
            pass
    await state.update_data(prev_t=ctype, prev_f=fid, prev_c=content, analysis=a)
    await state.set_state(AnonS.confirm)
    warn = ""
    if a and a["flags"]:
        warn = f"\n\n⚠️ <i>هشدار: {', '.join(a['flags'])}</i>"
    await message.answer(with_footer(f"📝 پیش‌نمایش. ارسال شود؟{warn}"),
                         reply_markup=confirm_kb("anon"))


@anon_r.callback_query(F.data == "cancel:anon")
async def cb_anon_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.edit_text(with_footer("❌ لغو."))
    except Exception:
        pass
    await cb.answer()


@anon_r.callback_query(F.data == "confirm:anon")
async def cb_anon_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot):
    d = await state.get_data()
    token = d.get("token")
    owner = d.get("owner_id")
    ltype = d.get("link_type", "onetime")
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
                               d["prev_t"], d["prev_c"], d["prev_f"], d.get("analysis"))
    if not r["ok"]:
        await cb.answer(f"❌ {r['error']}", show_alert=True)
        return
    await link_svc.consume(token, cb.from_user.id, ltype)
    await gamif_svc.award_xp(bot, cb.from_user.id, Config.XP_MSG_SENT)
    await gamif_svc.award_xp(bot, owner, Config.XP_MSG_RECEIVED)
    await stats_repo.bump("messages_sent")
    await state.clear()
    t = "✅ ارسال شد.\n💬 اگر طرف پاسخ بده، می‌تونی جواب بدی."
    if ltype == "permanent":
        t += "\n♾ لینک فعاله."
    try:
        await cb.message.edit_text(with_footer(t))
    except Exception:
        await cb.message.answer(with_footer(t))
    await cb.answer("✅")


# ═══════════════════ REPLY ═══════════════════

@reply_r.callback_query(F.data.startswith("areply:"))
async def cb_reply(cb: CallbackQuery, state: FSMContext):
    try:
        cid = int(cb.data.split(":")[1])
    except Exception:
        await cb.answer("❌", show_alert=True)
        return
    conv = await conv_repo.get(cid)
    if not conv or not conv["active"]:
        await cb.answer("❌ بسته شده.", show_alert=True)
        return
    if cb.from_user.id not in (conv["owner_id"], conv["sender_id"]):
        await cb.answer("❌ دسترسی نداری.", show_alert=True)
        return
    await state.set_state(ReplyS.waiting)
    await state.update_data(reply_cid=cid)
    try:
        await cb.message.answer(
            with_footer("💬 <b>حالت پاسخ ناشناس</b>\n\n"
                        "✍️ پاسخ خود را بفرست.\n"
                        "🔒 هویتت مخفی می‌مونه."),
            reply_markup=cancel_kb("global:cancel"))
    except Exception:
        pass
    await cb.answer("✍️")


@reply_r.callback_query(F.data.startswith("ablock:"))
async def cb_block(cb: CallbackQuery):
    try:
        cid = int(cb.data.split(":")[1])
    except Exception:
        await cb.answer("❌", show_alert=True)
        return
    conv = await conv_repo.get(cid)
    if not conv:
        await cb.answer("❌", show_alert=True)
        return
    if cb.from_user.id not in (conv["owner_id"], conv["sender_id"]):
        await cb.answer("❌", show_alert=True)
        return
    await conv_repo.end(cid)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.answer("🚫 بسته شد.", show_alert=True)


@reply_r.message(ReplyS.waiting)
async def reply_recv(message: Message, state: FSMContext, bot: Bot):
    d = await state.get_data()
    cid = d.get("reply_cid")
    if not cid:
        await state.clear()
        return
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
    elif message.sticker:
        ctype, fid = "sticker", message.sticker.file_id
    else:
        await message.answer("⚠️ نامعتبر.")
        return
    a = moderation.analyze(content or "") if content else None
    if a and moderation.is_flagged(a):
        await message.answer("⚠️ محتوای نامناسب.")
        await state.clear()
        return
    r = await message_svc.send_reply(bot, cid, message.from_user.id,
                                     ctype, content, fid, a)
    if not r["ok"]:
        await message.answer(f"❌ {r['error']}")
        return
    await gamif_svc.award_xp(bot, message.from_user.id, 1)
    await stats_repo.bump("messages_sent")
    await state.clear()
    await message.answer(with_footer("✅ پاسخ ارسال شد."),
                         reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID))


# ═══════════════════ TARGET CHAT ═══════════════════

@target_r.message(F.text == "👤 مخاطب خاص")
async def target_start(message: Message, state: FSMContext):
    await state.set_state(TargetS.waiting)
    await message.answer(with_footer("👤 <b>مخاطب خاص</b>\n\nآیدی عددی یا فوروارد:"),
                         reply_markup=cancel_kb("global:cancel"))


@target_r.message(TargetS.waiting)
async def target_recv(message: Message, state: FSMContext):
    tid = None
    if message.forward_from:
        tid = message.forward_from.id
    elif message.text and re.match(r"^\d{5,15}$", message.text.strip()):
        tid = int(message.text.strip())
    else:
        await message.answer("⚠️ نامعتبر.")
        return
    if tid == message.from_user.id:
        await message.answer("🙂 به خودت؟")
        return
    token = gen_token()
    await target_repo.create(token, message.from_user.id, tid)
    await state.update_data(tc_token_creator=token, tc_target=tid)
    await state.set_state(TargetCreatorS.chatting)
    await message.answer(
        with_footer(f"✅ لینک:\n\n<code>https://t.me/{Config.BOT_USERNAME}?start=tc_{token}</code>"),
        reply_markup=target_chat_kb(token))


@target_r.callback_query(F.data.startswith("tc:cancel:"))
async def cb_tc_cancel(cb: CallbackQuery, state: FSMContext):
    token = cb.data.split(":", 2)[2]
    await target_repo.deactivate(token)
    await state.clear()
    try:
        await cb.message.edit_text(with_footer("🗑 لغو."), reply_markup=None)
    except Exception:
        pass
    await cb.answer("✅")


@target_r.message(TargetS.active,
                  F.text | F.photo | F.voice | F.video | F.document | F.sticker)
async def target_msg(message: Message, state: FSMContext):
    d = await state.get_data()
    creator = d.get("tc_creator")
    if not creator:
        await state.clear()
        return
    try:
        await message.copy_to(creator)
    except Exception as e:
        log.exception("target: %s", e)


@target_r.message(TargetCreatorS.chatting,
                  F.text | F.photo | F.voice | F.video | F.document | F.sticker)
async def target_creator_msg(message: Message, state: FSMContext):
    d = await state.get_data()
    target = d.get("tc_target")
    token = d.get("tc_token_creator")
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
        log.exception("target_c: %s", e)


# ═══════════════════ MATCH ═══════════════════

async def _filters(state, uid):
    d = await state.get_data()
    if "filters" not in d:
        p = await profile_repo.get(uid)
        age = p["age"] if p else 25
        d["filters"] = {"min_age": max(9, age - 10), "max_age": min(99, age + 10),
                        "gender": "any", "same_city": False}
        await state.update_data(filters=d["filters"])
    return d["filters"]


@match_r.message(F.text == "🎭 چت ناشناس")
async def match_menu(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not await profile_repo.get(uid):
        await message.answer("⚠️ پروفایل بساز.")
        return
    f = await _filters(state, uid)
    await state.set_state(MatchS.configuring)
    await message.answer(with_footer("🎭 <b>فیلترها:</b>"), reply_markup=match_menu_kb(f))


@match_r.callback_query(F.data == "filter:age")
async def cb_fa(cb: CallbackQuery, state: FSMContext):
    await state.update_data(awaiting_age=True)
    await cb.message.edit_text(
        with_footer("🎂 <code>20-30</code>"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            _ibtn("◀️ بازگشت", S_P, callback_data="filter:menu")]]))
    await cb.answer()


@match_r.message(MatchS.configuring, F.text.regexp(r"^\d{1,2}\s*-\s*\d{1,2}$"))
async def match_age_input(message: Message, state: FSMContext):
    d = await state.get_data()
    if not d.get("awaiting_age"):
        return
    lo, hi = map(int, re.split(r"\s*-\s*", message.text.strip()))
    if not (9 <= lo <= 99 and 9 <= hi <= 99 and lo <= hi):
        await message.answer("⚠️ نامعتبر.")
        return
    f = d.get("filters") or {}
    f["min_age"], f["max_age"] = lo, hi
    await state.update_data(filters=f, awaiting_age=False)
    await message.answer(with_footer(f"✅ {lo}-{hi}"), reply_markup=match_menu_kb(f))


@match_r.callback_query(F.data == "filter:gender")
async def cb_fg(cb: CallbackQuery):
    await cb.message.edit_text(with_footer("🎭 جنسیت:"), reply_markup=filter_gender_kb())
    await cb.answer()


@match_r.callback_query(F.data.startswith("filter:g:"))
async def cb_fgs(cb: CallbackQuery, state: FSMContext):
    g = cb.data.split(":")[2]
    f = await _filters(state, cb.from_user.id)
    f["gender"] = g
    await state.update_data(filters=f)
    await cb.message.edit_text(with_footer("🎭"), reply_markup=match_menu_kb(f))
    await cb.answer()


@match_r.callback_query(F.data == "filter:city")
async def cb_fc(cb: CallbackQuery, state: FSMContext):
    f = await _filters(state, cb.from_user.id)
    f["same_city"] = not f["same_city"]
    await state.update_data(filters=f)
    await cb.message.edit_text(with_footer("🎭"), reply_markup=match_menu_kb(f))
    await cb.answer()


@match_r.callback_query(F.data == "filter:menu")
async def cb_fm(cb: CallbackQuery, state: FSMContext):
    f = await _filters(state, cb.from_user.id)
    await state.update_data(awaiting_age=False)
    await cb.message.edit_text(with_footer("🎭"), reply_markup=match_menu_kb(f))
    await cb.answer()


@match_r.callback_query(F.data == "match:start")
async def cb_match_start(cb: CallbackQuery, state: FSMContext, bot: Bot):
    uid = cb.from_user.id
    p = await profile_repo.get(uid)
    if not p:
        await cb.answer("❌ پروفایل بساز.", show_alert=True)
        return
    u = await user_repo.get(uid)
    f = await _filters(state, uid)
    pd = {"gender": p["gender"], "age": p["age"], "city": p["city"],
          "province": p["province"]}
    md = {"level": u["level"] if u else 1, "last_seen": u["last_seen"] if u else ""}
    pid, score = await match_svc.find_best(uid, f, pd, md)
    if pid is None:
        await state.set_state(MatchS.searching)
        try:
            await cb.message.edit_text(
                with_footer("🔍 <b>در جستجو...</b>"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    _ibtn("❌ لغو", S_D, callback_data="match:cancel_search")]]))
        except Exception:
            pass
        await cb.answer("🔍")
        return
    pairing_id = await pairing_repo.create(uid, pid)
    await state.set_state(MatchS.chatting)
    await state.update_data(pairing_id=pairing_id, partner_id=pid)
    await stats_repo.bump("matches")
    for t in (uid, pid):
        try:
            await bot.send_message(t, with_footer(
                f"🎉 <b>مچ پیدا شد!</b>\n"
                f"امتیاز: <b>{int(score * 100)}%</b>\n\n/endchat برای پایان"),
                reply_markup=ReplyKeyboardRemove())
        except Exception:
            pass
    try:
        await cb.message.edit_text(with_footer(f"✅ مچ شد! ({int(score * 100)}%)"))
    except Exception:
        pass
    await cb.answer("🎉")


@match_r.callback_query(F.data == "match:cancel_search")
async def cb_mcs(cb: CallbackQuery, state: FSMContext):
    match_svc.cancel(cb.from_user.id)
    f = await _filters(state, cb.from_user.id)
    await state.set_state(MatchS.configuring)
    try:
        await cb.message.edit_text(with_footer("❌ لغو."), reply_markup=match_menu_kb(f))
    except Exception:
        pass
    await cb.answer()


@match_r.message(MatchS.chatting,
                 F.text | F.photo | F.voice | F.video | F.document | F.sticker)
async def match_relay(message: Message, state: FSMContext):
    d = await state.get_data()
    partner = d.get("partner_id")
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


# ═══════════════════ DATING ═══════════════════

DATING_Q: dict[int, list] = {}


async def _load_queue(uid):
    p = await profile_repo.get(uid)
    prefs = await dating_repo.get_prefs(uid)
    if not p:
        return []
    return await profile_repo.random_discover(
        uid, prefs["pref_gender"], prefs["pref_min_age"], prefs["pref_max_age"],
        bool(prefs["pref_same_city"]), bool(prefs["pref_same_province"]),
        p["city"], p["province"], limit=30)


async def _show_card(message, state, bot):
    uid = message.chat.id
    q = DATING_Q.get(uid, [])
    if not q:
        q = await _load_queue(uid)
        DATING_Q[uid] = q
    if not q:
        prefs = await dating_repo.get_prefs(uid)
        await message.answer(
            with_footer("💔 <b>کاربر جدیدی پیدا نشد!</b>\n\nفیلترها رو تغییر بده."),
            reply_markup=dating_menu_kb(prefs))
        await state.clear()
        return
    t = q.pop(0)
    DATING_Q[uid] = q
    emoji = PROVINCE_EMOJI.get(t["province"], "🏙")
    caption = with_footer(
        f"💖 <b>کارت دوستیابی</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👤 {t['full_name'] or '—'}\n"
        f"🎭 {gender_fa(t['gender'])}\n"
        f"🎂 {t['age']} سال\n"
        f"{emoji} {t['city']}, {t['province']}\n"
        f"🎖 سطح: <b>{t['level']}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"❤️ لایک یا 👎 رد کن:")
    try:
        await bot.send_photo(uid, t["avatar_url"], caption=caption,
                             reply_markup=dating_card_kb(t["user_id"]))
    except Exception:
        await message.answer(caption, reply_markup=dating_card_kb(t["user_id"]))


@dating_r.message(Command("dating"))
async def cmd_dating(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not await profile_repo.get(uid):
        await message.answer("⚠️ ابتدا پروفایل بساز. /start")
        return
    prefs = await dating_repo.get_prefs(uid)
    await state.set_state(DatingS.browsing)
    await message.answer(
        with_footer("💖 <b>دوستیابی</b>\n\n🔍 گشت بزن، ❤️ لایک کن، 💞 مچ شو!"),
        reply_markup=dating_menu_kb(prefs))


@dating_r.message(F.text == "💖 دوستیابی")
async def btn_dating(message: Message, state: FSMContext):
    await cmd_dating(message, state)


@dating_r.callback_query(F.data == "dating:back")
async def cb_dating_back(cb: CallbackQuery, state: FSMContext):
    prefs = await dating_repo.get_prefs(cb.from_user.id)
    await state.set_state(DatingS.browsing)
    try:
        await cb.message.edit_text(with_footer("💖 <b>دوستیابی</b>"),
                                   reply_markup=dating_menu_kb(prefs))
    except Exception:
        pass
    await cb.answer()


@dating_r.callback_query(F.data == "dating:close")
async def cb_dating_close(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer(with_footer("🏠 <b>منوی اصلی</b>"),
                            reply_markup=main_menu_kb(cb.from_user.id == Config.ADMIN_ID))
    await cb.answer()


@dating_r.callback_query(F.data == "dating:pref:gender")
async def cb_dating_gender(cb: CallbackQuery):
    try:
        await cb.message.edit_text(with_footer("🎭 <b>جنسیت مورد نظر:</b>"),
                                   reply_markup=dating_gender_kb())
    except Exception:
        pass
    await cb.answer()


@dating_r.callback_query(F.data.startswith("dating:setg:"))
async def cb_dating_setg(cb: CallbackQuery):
    g = cb.data.split(":")[2]
    await dating_repo.set_pref(cb.from_user.id, "pref_gender", g)
    prefs = await dating_repo.get_prefs(cb.from_user.id)
    try:
        await cb.message.edit_text(with_footer("💖"), reply_markup=dating_menu_kb(prefs))
    except Exception:
        pass
    await cb.answer("✅")


@dating_r.callback_query(F.data == "dating:pref:age")
async def cb_dating_age(cb: CallbackQuery, state: FSMContext):
    await state.set_state(DatingS.waiting_age)
    try:
        await cb.message.edit_text(
            with_footer("🎂 <b>بازه سنی</b>\n\nمثال: <code>18-35</code>"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                _ibtn("◀️ بازگشت", S_P, callback_data="dating:back")]]))
    except Exception:
        pass
    await cb.answer()


@dating_r.message(DatingS.waiting_age, F.text.regexp(r"^\d{1,2}\s*-\s*\d{1,2}$"))
async def dating_age_input(message: Message, state: FSMContext):
    lo, hi = map(int, re.split(r"\s*-\s*", message.text.strip()))
    if not (9 <= lo <= 99 and 9 <= hi <= 99 and lo <= hi):
        await message.answer("⚠️ نامعتبر.")
        return
    await dating_repo.set_pref(message.from_user.id, "pref_min_age", lo)
    await dating_repo.set_pref(message.from_user.id, "pref_max_age", hi)
    await state.set_state(DatingS.browsing)
    prefs = await dating_repo.get_prefs(message.from_user.id)
    await message.answer(with_footer(f"✅ {lo}-{hi}"), reply_markup=dating_menu_kb(prefs))


@dating_r.message(DatingS.waiting_age)
async def dating_age_invalid(message: Message):
    await message.answer("⚠️ فرمت: <code>18-35</code>")


@dating_r.callback_query(F.data == "dating:pref:city")
async def cb_dc(cb: CallbackQuery):
    prefs = await dating_repo.get_prefs(cb.from_user.id)
    nv = 0 if prefs["pref_same_city"] else 1
    await dating_repo.set_pref(cb.from_user.id, "pref_same_city", nv)
    if nv:
        await dating_repo.set_pref(cb.from_user.id, "pref_same_province", 0)
    prefs = await dating_repo.get_prefs(cb.from_user.id)
    try:
        await cb.message.edit_reply_markup(reply_markup=dating_menu_kb(prefs))
    except Exception:
        pass
    await cb.answer("✅" if nv else "❌")


@dating_r.callback_query(F.data == "dating:pref:province")
async def cb_dp(cb: CallbackQuery):
    prefs = await dating_repo.get_prefs(cb.from_user.id)
    nv = 0 if prefs["pref_same_province"] else 1
    await dating_repo.set_pref(cb.from_user.id, "pref_same_province", nv)
    if nv:
        await dating_repo.set_pref(cb.from_user.id, "pref_same_city", 0)
    prefs = await dating_repo.get_prefs(cb.from_user.id)
    try:
        await cb.message.edit_reply_markup(reply_markup=dating_menu_kb(prefs))
    except Exception:
        pass
    await cb.answer("✅" if nv else "❌")


@dating_r.callback_query(F.data == "dating:next")
async def cb_next(cb: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await cb.message.delete()
    except Exception:
        pass
    await _show_card(cb.message, state, bot)
    await cb.answer()


@dating_r.callback_query(F.data == "dating:stats")
async def cb_dstats(cb: CallbackQuery):
    uid = cb.from_user.id
    likes = await dating_repo.likes_of(uid)
    matches = await dating_repo.matches_of(uid)
    tm = await dating_repo.total_matches()
    tl = await dating_repo.total_likes()
    await cb.answer()
    try:
        await cb.message.edit_text(with_footer(
            f"📊 <b>آمار دوستیابی</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"❤️ لایک‌های تو: <b>{likes}</b>\n"
            f"💞 مچ‌های تو: <b>{matches}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🌍 کل لایک: <b>{tl}</b>\n"
            f"🌍 کل مچ: <b>{tm}</b>"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                _ibtn("◀️ بازگشت", S_P, callback_data="dating:back")]]))
    except Exception:
        pass


@dating_r.callback_query(F.data.startswith("dating:like:"))
async def cb_like(cb: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        tid = int(cb.data.split(":")[2])
    except Exception:
        await cb.answer("❌")
        return
    uid = cb.from_user.id
    if tid == uid:
        await cb.answer("🙂 به خودت؟")
        return
    await dating_repo.add_like(uid, tid, True)
    await stats_repo.bump("likes")
    await gamif_svc.award_xp(bot, uid, Config.XP_LIKE)
    mutual = await dating_repo.check_mutual(tid, uid)
    try:
        await cb.message.delete()
    except Exception:
        pass
    if mutual:
        mid = await dating_repo.add_match(uid, tid)
        await gamif_svc.award_xp(bot, uid, Config.XP_MATCH)
        await gamif_svc.award_xp(bot, tid, Config.XP_MATCH)
        await gamif_svc.check_badges(bot, uid)
        try:
            await bot.send_message(tid, with_footer(
                "💞 <b>مچ جدید در دوستیابی!</b>\n\n"
                "کسی که لایکش کرده بودی، تو رو هم لایک کرد!"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    _ibtn("💖 باز کردن دوستیابی", S_D, callback_data="dating:open")]]))
        except Exception:
            pass
        await cb.message.answer(
            with_footer("💞 <b>مچ شدید!</b>\n\n🎉"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [_ibtn("💬 ارسال پیام", S_S, callback_data=f"dating:msg:{tid}")],
                [_ibtn("⏭ ادامه گشت", S_P, callback_data="dating:next")]]))
        await cb.answer("💞")
    else:
        await cb.message.answer(with_footer("❤️ لایک ثبت شد."))
        await _show_card(cb.message, state, bot)
        await cb.answer("❤️")


@dating_r.callback_query(F.data.startswith("dating:dislike:"))
async def cb_dislike(cb: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        tid = int(cb.data.split(":")[2])
    except Exception:
        await cb.answer("❌")
        return
    await dating_repo.add_like(cb.from_user.id, tid, False)
    try:
        await cb.message.delete()
    except Exception:
        pass
    await _show_card(cb.message, state, bot)
    await cb.answer("👎")


@dating_r.callback_query(F.data.startswith("dating:msg:"))
async def cb_dmsg(cb: CallbackQuery, state: FSMContext):
    try:
        tid = int(cb.data.split(":")[2])
    except Exception:
        await cb.answer("❌")
        return
    uid = cb.from_user.id
    m = await dating_repo.active_match(uid)
    if not m:
        await cb.answer("❌ مچ فعال نداری.", show_alert=True)
        return
    partner = m["user2_id"] if m["user1_id"] == uid else m["user1_id"]
    if partner != tid:
        await cb.answer("❌ مچ فعال نیست.", show_alert=True)
        return
    await state.set_state(DatingS.chatting)
    await state.update_data(dating_partner=partner, dating_match_id=m["id"])
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer(with_footer("💬 <b>چت دوستیابی</b>\n\n/endchat برای پایان"),
                            reply_markup=ReplyKeyboardRemove())
    await cb.answer("💬")


@dating_r.message(DatingS.chatting,
                  F.text | F.photo | F.voice | F.video | F.document | F.sticker)
async def dating_relay(message: Message, state: FSMContext):
    d = await state.get_data()
    partner = d.get("dating_partner")
    if not partner:
        m = await dating_repo.active_match(message.from_user.id)
        if not m:
            await state.clear()
            return
        partner = m["user2_id"] if m["user1_id"] == message.from_user.id else m["user1_id"]
        await state.update_data(dating_partner=partner)
    try:
        await message.copy_to(partner)
    except Exception as e:
        log.exception("dating: %s", e)


@dating_r.message(Command("matches"))
async def cmd_matches(message: Message):
    uid = message.from_user.id
    m = await dating_repo.active_match(uid)
    if not m:
        await message.answer(with_footer("💔 مچ فعال نداری."))
        return
    partner = m["user2_id"] if m["user1_id"] == uid else m["user1_id"]
    p = await profile_repo.get(partner)
    u = await user_repo.get(partner)
    emoji = PROVINCE_EMOJI.get(p["province"] if p else "", "🏙")
    await message.answer(
        with_footer(
            f"💞 <b>مچ فعال</b>\n\n"
            f"👤 {u['full_name'] if u else '—'}\n"
            f"🎂 {p['age'] if p else '—'} | {emoji} {p['city'] if p else '—'}"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            _ibtn("💬 چت", S_S, callback_data=f"dating:msg:{partner}")]]))


@dating_r.message(Command("likes"))
async def cmd_likes(message: Message):
    uid = message.from_user.id
    likes = await dating_repo.likes_of(uid)
    matches = await dating_repo.matches_of(uid)
    await message.answer(with_footer(
        f"❤️ <b>لایک‌های تو</b>\n\n"
        f"تعداد لایک: <b>{likes}</b>\n"
        f"تعداد مچ: <b>{matches}</b>"))


# ═══════════════════ GAMES ═══════════════════

@game_r.callback_query(F.data == "game:dice")
async def cb_dice(cb: CallbackQuery, bot: Bot):
    await cb.answer()
    val = await bot.send_dice(cb.from_user.id, emoji="🎲")
    await asyncio.sleep(3)
    if val.dice.value >= 4:
        await user_repo.inc_wins(cb.from_user.id)
        await user_repo.add_coins(cb.from_user.id, val.dice.value * 2)
        await gamif_svc.award_xp(bot, cb.from_user.id, 3)
        try:
            await bot.send_message(cb.from_user.id, with_footer(
                f"🎲 <b>{val.dice.value}</b>\n\n"
                f"✅ بردی! +{val.dice.value * 2} سکه"))
        except Exception:
            pass
    else:
        await user_repo.inc_losses(cb.from_user.id)
        try:
            await bot.send_message(cb.from_user.id, with_footer(
                f"🎲 <b>{val.dice.value}</b>\n\n❌ باختی!"))
        except Exception:
            pass
    await stats_repo.bump("games")


@game_r.callback_query(F.data == "game:coin")
async def cb_coin(cb: CallbackQuery, bot: Bot):
    await cb.answer()
    result = random.choice(["🪙 شیر", "🪙 خط"])
    win = random.random() > 0.5
    if win:
        await user_repo.inc_wins(cb.from_user.id)
        await user_repo.add_coins(cb.from_user.id, 10)
        await gamif_svc.award_xp(bot, cb.from_user.id, 2)
        await cb.message.answer(with_footer(f"{result}\n\n✅ بردی! +10 سکه"))
    else:
        await user_repo.inc_losses(cb.from_user.id)
        await cb.message.answer(with_footer(f"{result}\n\n❌ باختی!"))
    await stats_repo.bump("games")


@game_r.callback_query(F.data == "game:guess")
async def cb_guess(cb: CallbackQuery, state: FSMContext):
    number = random.randint(1, 10)
    await state.set_state(GameS.guessing)
    await state.update_data(secret=number, tries=0)
    await cb.message.answer(with_footer(
        "🧠 <b>حدس عدد</b>\n\n"
        "عددی بین ۱ تا ۱۰ حدس بزن:\n"
        "تو ۳ تلاش داری!"))
    await cb.answer()


@game_r.message(GameS.guessing)
async def guess_recv(message: Message, state: FSMContext, bot: Bot):
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await message.answer("⚠️ عدد بفرست.")
        return
    n = int(txt)
    d = await state.get_data()
    secret = d.get("secret")
    tries = (d.get("tries") or 0) + 1
    if n == secret:
        await user_repo.inc_wins(message.from_user.id)
        await user_repo.add_coins(message.from_user.id, 30)
        await gamif_svc.award_xp(bot, message.from_user.id, 10)
        await stats_repo.bump("games")
        await state.clear()
        await message.answer(with_footer(f"🎉 <b>درست!</b>\nعدد {secret} بود.\n+30 سکه"))
        return
    if tries >= 3:
        await user_repo.inc_losses(message.from_user.id)
        await state.clear()
        await stats_repo.bump("games")
        await message.answer(with_footer(f"❌ <b>باختی!</b>\nعدد {secret} بود."))
        return
    hint = "بالاتر ⬆️" if n < secret else "پایین‌تر ⬇️"
    await state.update_data(tries=tries)
    await message.answer(with_footer(f"❌ نه!\n\n💡 راهنما: {hint}\n\nتلاش: {tries}/3"))


@game_r.callback_query(F.data == "game:dart")
async def cb_dart(cb: CallbackQuery, bot: Bot):
    await cb.answer()
    val = await bot.send_dice(cb.from_user.id, emoji="🎯")
    await asyncio.sleep(3)
    if val.dice.value == 6:
        await user_repo.inc_wins(cb.from_user.id)
        await user_repo.add_coins(cb.from_user.id, 50)
        await gamif_svc.award_xp(bot, cb.from_user.id, 5)
        try:
            await bot.send_message(cb.from_user.id, with_footer(
                f"🎯 <b>بولزای!</b>\n\n+50 سکه"))
        except Exception:
            pass
    else:
        await user_repo.inc_losses(cb.from_user.id)
        try:
            await bot.send_message(cb.from_user.id, with_footer(
                f"🎯 <b>{val.dice.value}</b>"))
        except Exception:
            pass
    await stats_repo.bump("games")


@game_r.callback_query(F.data == "game:rps")
async def cb_rps(cb: CallbackQuery):
    await cb.message.answer(with_footer("✂️ <b>سنگ کاغذ قیچی</b>\n\nانتخاب کن:"),
                            reply_markup=rps_kb())
    await cb.answer()


@game_r.callback_query(F.data.startswith("rps:"))
async def cb_rps_play(cb: CallbackQuery, bot: Bot):
    user_choice = cb.data.split(":")[1]
    bot_choice = random.choice(["rock", "paper", "scissors"])
    emoji = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
    beats = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
    if user_choice == bot_choice:
        result = "🤝 مساوی"
        await stats_repo.bump("games")
    elif beats[user_choice] == bot_choice:
        result = "🎉 بردی!"
        await user_repo.inc_wins(cb.from_user.id)
        await user_repo.add_coins(cb.from_user.id, 15)
        await gamif_svc.award_xp(bot, cb.from_user.id, 5)
        await stats_repo.bump("games")
    else:
        result = "❌ باختی!"
        await user_repo.inc_losses(cb.from_user.id)
        await stats_repo.bump("games")
    try:
        await cb.message.edit_text(with_footer(
            f"✂️ <b>سنگ کاغذ قیچی</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 تو: {emoji[user_choice]}\n"
            f"🤖 ربات: {emoji[bot_choice]}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{result}"))
    except Exception:
        pass
    await cb.answer(result)


@game_r.callback_query(F.data == "game:top")
async def cb_game_top(cb: CallbackQuery):
    top = await user_repo.top_wins(10)
    lines = ["🏆 <b>بهترین بازیکنان</b>\n"]
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    for i, r in enumerate(top):
        lines.append(f"{medals[i]} {(r['full_name'] or '—')[:18]} — {r['wins']} برد")
    await cb.answer()
    try:
        await cb.message.edit_text(with_footer("\n".join(lines)))
    except Exception:
        pass


# ═══════════════════ FEEDBACK ═══════════════════

@fb_r.message(F.text == "📣 بازخورد")
async def fb_menu(message: Message):
    await message.answer(with_footer("📣 <b>بازخورد و نظرسنجی</b>"),
                         reply_markup=feedback_kb())


@fb_r.callback_query(F.data == "fb:new")
async def cb_fb_new(cb: CallbackQuery, state: FSMContext):
    await state.set_state(FeedbackS.waiting)
    try:
        await cb.message.edit_text(with_footer("✍️ بازخوردت رو بفرست:"))
    except Exception:
        pass
    await cb.answer()


@fb_r.callback_query(F.data == "fb:mine")
async def cb_fb_mine(cb: CallbackQuery):
    await cb.answer("📋 ویژگی در نسخه بعدی!", show_alert=True)


@fb_r.message(FeedbackS.waiting)
async def fb_recv(message: Message, state: FSMContext, bot: Bot):
    text = (message.text or "").strip()
    if len(text) < 5:
        await message.answer("⚠️ حداقل ۵ کاراکتر.")
        return
    fid = await feedback_repo.create(message.from_user.id, text)
    await state.clear()
    try:
        await bot.send_message(Config.ADMIN_ID, with_footer(
            f"📣 <b>بازخورد #{fid}</b>\n\n"
            f"👤 <code>{message.from_user.id}</code>\n"
            f"📝 {text[:1000]}"))
    except Exception:
        pass
    await message.answer(with_footer("✅ ممنون از بازخوردت! 💙"),
                         reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID))


# ═══════════════════ ROOMS ═══════════════════

@room_r.message(F.text == "👥 اتاق گروهی")
async def room_menu(message: Message, state: FSMContext):
    await state.set_state(RoomS.creating)
    await message.answer(with_footer("👥 <b>اتاق گروهی</b>\n\nنام اتاق را بفرست:"),
                         reply_markup=cancel_kb("global:cancel"))


@room_r.message(RoomS.creating)
async def room_create(message: Message, state: FSMContext):
    name = (message.text or "").strip()[:40]
    if not name:
        await message.answer("⚠️ نامعتبر.")
        return
    rid = await room_repo.create(name, message.from_user.id)
    await state.set_state(RoomS.chatting)
    await state.update_data(room_id=rid)
    await message.answer(
        with_footer(f"🏠 اتاق «<b>{name}</b>» ساخته شد!\n\n"
                    f"لینک:\n<code>https://t.me/{Config.BOT_USERNAME}?start=room_{rid}</code>\n\n"
                    f"/endchat برای خروج"),
        reply_markup=room_kb(rid))


@room_r.callback_query(F.data.startswith("room:leave:"))
async def cb_room_leave(cb: CallbackQuery, state: FSMContext):
    rid = cb.data.split(":")[2]
    await room_repo.leave(rid, cb.from_user.id)
    await state.clear()
    try:
        await cb.message.edit_text(with_footer("🚪 خارج شدی."), reply_markup=None)
    except Exception:
        pass
    await cb.answer("✅")


@room_r.message(RoomS.chatting,
                F.text | F.photo | F.voice | F.video | F.document | F.sticker)
async def room_relay(message: Message, state: FSMContext):
    d = await state.get_data()
    rid = d.get("room_id")
    if not rid:
        return
    for m in await room_repo.members(rid):
        if m["user_id"] == message.from_user.id:
            continue
        try:
            await message.copy_to(m["user_id"])
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════
# ۱۸ ── ADMIN PANEL
# ═══════════════════════════════════════════════════════════════════════

def _is_admin(uid):
    return uid == Config.ADMIN_ID


@admin_r.message(Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer(with_footer("👑 <b>پنل مدیریت</b>\n\nاز منوی پایین انتخاب کن:"),
                         reply_markup=admin_menu_kb())


@admin_r.message(F.text == "👑 پنل ادمین")
async def admin_panel(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer(with_footer("👑 <b>پنل مدیریت</b>"), reply_markup=admin_menu_kb())


@admin_r.message(F.text == "◀️ بازگشت")
async def admin_back(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer(with_footer("🏠 منوی اصلی"), reply_markup=main_menu_kb(True))


@admin_r.message(F.text == "🏓 پینگ")
async def admin_ping(message: Message):
    if not _is_admin(message.from_user.id):
        return
    t0 = time.monotonic()
    m = await message.answer("🏓")
    dt = (time.monotonic() - t0) * 1000
    await m.edit_text(with_footer(f"🏓 <b>Pong!</b>\n⚡ <code>{dt:.1f} ms</code>"))


@admin_r.message(Command("ping"))
async def cmd_ping(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await admin_ping(message)


@admin_r.message(F.text == "📊 داشبورد")
async def admin_dash(message: Message):
    if not _is_admin(message.from_user.id):
        return
    s = await admin_svc.dashboard()
    text = (
        "╔══════════════════════════════╗\n"
        "║    📊 <b>داشبورد مدیریت</b>    ║\n"
        "╚══════════════════════════════╝\n\n"
        f"👥 کاربران: <b>{s['users']}</b> (+{s['users_today']})\n"
        f"🟢 فعال ۲۴س: <b>{s['active_24h']}</b>\n"
        f"🚫 بن: <b>{s['banned']}</b> | 🔇 سکوت: <b>{s['muted']}</b>\n"
        f"🔗 لینک: <b>{s['links_total']}</b> (فعال: {s['links_active']})\n"
        f"📨 پیام: <b>{s['messages_total']}</b>\n"
        f"💬 مکالمات: <b>{s['conv_total']}</b>\n"
        f"💖 دوستیابی: <b>{s['dating_matches']}</b> مچ | <b>{s['dating_likes']}</b> لایک\n"
        f"🤝 مچ ناشناس: <b>{s['pairings_total']}</b>\n"
        f"🎯 صف: <b>{s['queue']}</b>\n"
        f"🚨 گزارش: <b>{s['reports_pending']}</b>\n"
        f"⚠️ اخطار: <b>{s['warnings']}</b>\n"
        f"📣 فیدبک: <b>{s['feedback_new']}</b>\n"
        f"🏠 اتاق: <b>{s['rooms']}</b> | 📝 لاگ: <b>{s['logs']}</b>\n"
        f"🔒 کانال: <b>{s['channel']}</b>\n"
        f"🔧 تعمیر: <b>{'✅' if s['maintenance'] else '❌'}</b>\n"
        f"💾 کش: <b>{s['cache']['size']}</b>")
    await message.answer(with_footer(text), reply_markup=admin_menu_kb())


@admin_r.message(F.text == "📈 آنالیتیکس")
async def admin_analytics(message: Message):
    if not _is_admin(message.from_user.id):
        return
    fn = await analytics.funnel()
    dwm = await analytics.dwm()
    days = await analytics.last_7()
    tp = await analytics.top_prov(5)
    lines = ["📈 <b>آنالیتیکس</b>\n", "<b>🔻 قیف:</b>"]
    mv = max(fn.values()) if fn.values() else 1
    labels = {"total": "عضو", "rules": "قوانین", "profile": "پروفایل",
              "link": "لینک", "msg": "پیام"}
    for k, v in fn.items():
        lines.append(f"  {labels[k]}: <b>{v}</b> {rbar(v, mv, 15)}")
    lines.append(f"\n<b>📊 فعال:</b>\n  DAU <b>{dwm['dau']}</b> | "
                 f"WAU <b>{dwm['wau']}</b> | MAU <b>{dwm['mau']}</b>")
    if days:
        lines.append(f"\n<b>📅 ۷ روز:</b>")
        for d in days[:7]:
            lines.append(f"  {d['date']}: 👥{d['new_users']} 📨{d['messages_sent']}")
    if tp:
        lines.append(f"\n<b>🏙 برتر:</b>")
        for p in tp:
            lines.append(f"  {p['province']}: <b>{p['c']}</b>")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_r.message(F.text == "🚨 گزارش‌ها")
async def admin_reports(message: Message):
    if not _is_admin(message.from_user.id):
        return
    reports = await report_repo.pending(20)
    if not reports:
        await message.answer(with_footer("🚨 گزارشی نیست."),
                             reply_markup=admin_menu_kb())
        return
    for r in reports[:10]:
        await message.answer(with_footer(
            f"🚨 <b>گزارش #{r['id']}</b>\n"
            f"👤 <code>{r['reporter_id']}</code>\n"
            f"🎯 <code>{r['reported_id'] or '—'}</code>\n"
            f"📝 {r['reason']}\n"
            f"🕐 {r['created_at'][:16]}"),
            reply_markup=report_review_kb(r["id"], r["reporter_id"]))


@admin_r.callback_query(F.data.startswith("rep:"))
async def admin_rep_action(cb: CallbackQuery, bot: Bot):
    if not _is_admin(cb.from_user.id):
        return
    _, action, rid_s, uid_s = cb.data.split(":")
    rid, uid = int(rid_s), int(uid_s)
    if action == "ok":
        await report_repo.mark(rid, "confirmed", cb.from_user.id)
        n = await user_repo.add_warn(uid)
        await warn_repo.add(uid, cb.from_user.id, f"report#{rid}")
        try:
            await bot.send_message(uid, with_footer(f"⚠️ اخطار! تعداد: {n}"))
        except Exception:
            pass
        await cb.answer("✅", show_alert=True)
    else:
        await report_repo.mark(rid, "rejected", cb.from_user.id)
        await cb.answer("❌", show_alert=True)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@admin_r.message(F.text == "👥 کاربران")
async def admin_users(message: Message):
    if not _is_admin(message.from_user.id):
        return
    users = await user_repo.get_all(20)
    if not users:
        await message.answer("کاربری نیست.")
        return
    lines = ["👥 <b>آخرین ۲۰ کاربر</b>\n"]
    for u in users:
        st = "🚫" if u["is_banned"] else "✅"
        wn = f"⚠️{u['warn_count']}" if u["warn_count"] else ""
        lines.append(
            f"{st} <code>{u['user_id']}</code> — {(u['full_name'] or '—')[:20]} {wn}")
    lines.append("\n💡 /userinfo ID")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_r.message(F.text == "🔍 جستجو")
async def admin_search_prompt(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminS.searching_user)
    await message.answer(with_footer("🔍 <b>جستجو</b>\n\nID / نام / یوزرنیم:"),
                         reply_markup=cancel_kb("global:cancel"))


@admin_r.message(AdminS.searching_user)
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


@admin_r.message(Command("userinfo"))
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
    warns = await warn_repo.list_for(uid, 5)
    msgs = await msg_repo.count_for(uid)
    likes = await dating_repo.likes_of(uid)
    matches = await dating_repo.matches_of(uid)
    text = (
        f"👤 <b>کاربر</b>\n\n"
        f"🆔 <code>{u['user_id']}</code>\n"
        f"👤 {u['full_name'] or '—'}\n"
        f"🔗 @{u['username'] or '—'}\n"
        f"📜 قوانین: {'✅' if u['rules_accepted'] else '❌'}\n"
        f"🚫 بن: {'✅ ' + (u['ban_reason'] or '') if u['is_banned'] else '❌'}\n"
        f"⚠️ اخطار: <b>{u['warn_count']}</b>\n"
        f"✨ XP: <b>{u['xp']}</b> (L{u['level']})\n"
        f"💰 سکه: <b>{u['coins']}</b>\n"
        f"📨 پیام: <b>{msgs}</b>\n"
        f"🎮 برد/باخت: <b>{u['wins']}/{u['losses']}</b>\n"
        f"💖 لایک/مچ: <b>{likes}/{matches}</b>\n"
        f"👁 بازدید: <b>{u['profile_views']}</b>\n"
        f"📅 {u['created_at'][:10]}")
    if p:
        emoji = PROVINCE_EMOJI.get(p["province"], "🏙")
        text += f"\n\n🎭 {gender_fa(p['gender'])} | 🎂 {p['age']} | {emoji} {p['city']}"
    if warns:
        text += "\n\n<b>اخطارها:</b>"
        for w in warns[:3]:
            text += f"\n• {w['created_at'][:16]} — {w['reason'] or '—'}"
    try:
        if p and p["avatar_url"]:
            await message.answer_photo(p["avatar_url"], caption=with_footer(text),
                                        reply_markup=admin_user_kb(uid))
            return
    except Exception:
        pass
    await message.answer(with_footer(text), reply_markup=admin_user_kb(uid))


@admin_r.callback_query(F.data.startswith("adm:"))
async def admin_user_actions(cb: CallbackQuery, state: FSMContext, bot: Bot):
    if not _is_admin(cb.from_user.id):
        return
    _, action, uid_s = cb.data.split(":")
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
        await warn_repo.add(uid, Config.ADMIN_ID, "ادمین")
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
        await warn_repo.clear(uid)
        await cb.answer("🗑")
    elif action == "msg":
        await state.set_state(AdminS.sending_to_user)
        await state.update_data(target_uid=uid)
        await cb.message.answer(
            with_footer(f"📨 به <code>{uid}</code>: پیام را بفرست."),
            reply_markup=cancel_kb("global:cancel"))
        await cb.answer()
    elif action == "coins":
        await state.set_state(AdminS.sending_coins)
        await state.update_data(target_uid=uid)
        await cb.message.answer(
            with_footer(f"💰 مقدار سکه برای <code>{uid}</code>:"),
            reply_markup=cancel_kb("global:cancel"))
        await cb.answer()


@admin_r.message(AdminS.sending_to_user)
async def admin_send_user(message: Message, state: FSMContext, bot: Bot):
    if not _is_admin(message.from_user.id):
        return
    d = await state.get_data()
    target = d.get("target_uid")
    await state.clear()
    if not target:
        return
    try:
        await bot.copy_message(target, message.chat.id, message.message_id)
        await message.answer(with_footer(f"✅ به <code>{target}</code>."),
                             reply_markup=admin_menu_kb())
    except Exception as e:
        await message.answer(f"❌ {e}", reply_markup=admin_menu_kb())


@admin_r.message(AdminS.sending_coins)
async def admin_coins_user(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    d = await state.get_data()
    target = d.get("target_uid")
    await state.clear()
    if not target:
        return
    try:
        amount = int((message.text or "0").strip())
    except Exception:
        await message.answer("❌ عدد نامعتبر.")
        return
    new_total = await user_repo.add_coins(target, amount)
    await message.answer(
        with_footer(
            f"✅ به <code>{target}</code>: <b>{amount:+d}</b> سکه.\n"
            f"💰 موجودی جدید: <b>{new_total}</b>"),
        reply_markup=admin_menu_kb())


@admin_r.message(F.text == "🚫 بن‌ها")
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
            lines.append(
                f"• <code>{r['user_id']}</code> — {r['full_name'] or '—'} — {r['ban_reason'] or '—'}")
    lines.append("\n💡 /ban ID دلیل")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_r.message(Command("ban"))
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


@admin_r.message(Command("unban"))
async def admin_unban(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return
    a = (command.args or "").strip()
    if not a.isdigit():
        await message.answer("/unban ID")
        return
    await user_repo.unban(int(a))
    await message.answer("✅")


@admin_r.message(Command("warn"))
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
    await warn_repo.add(t, Config.ADMIN_ID, reason)
    try:
        await bot.send_message(t, f"⚠️ اخطار ({n}): {reason}")
    except Exception:
        pass
    await message.answer(f"⚠️ {t} — #{n}")


@admin_r.message(Command("unwarn"))
async def admin_unwarn(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return
    a = (command.args or "").strip()
    if not a.isdigit():
        return
    await user_repo.clear_warns(int(a))
    await warn_repo.clear(int(a))
    await message.answer("✅")


@admin_r.message(Command("mute"))
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
    await message.answer(f"🔇 {t} — {mins}د")


@admin_r.message(Command("unmute"))
async def admin_unmute(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return
    a = (command.args or "").strip()
    if not a.isdigit():
        return
    await user_repo.unmute(int(a))
    await message.answer("✅")


@admin_r.message(F.text == "⚠️ اخطارها")
async def admin_warns(message: Message):
    if not _is_admin(message.from_user.id):
        return
    rows = await db.fetch_all(
        "SELECT user_id, full_name, warn_count FROM users WHERE warn_count > 0 ORDER BY warn_count DESC LIMIT 20")
    lines = ["⚠️ <b>اخطاردار</b>\n"]
    if not rows:
        lines.append("خالی.")
    else:
        for r in rows:
            lines.append(
                f"• <code>{r['user_id']}</code> — {r['full_name'] or '—'} — ⚠️ {r['warn_count']}")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_r.message(F.text == "🔇 سکوت‌ها")
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


@admin_r.message(F.text == "📝 لاگ‌ها")
async def admin_logs(message: Message):
    if not _is_admin(message.from_user.id):
        return
    logs = await admin_log_repo.recent(20)
    if not logs:
        await message.answer(with_footer("لاگی نیست."), reply_markup=admin_menu_kb())
        return
    lines = ["📝 <b>۲۰ لاگ آخر</b>\n"]
    for r in logs:
        lines.append(f"• [{r['created_at'][11:16]}] {r['action']} → {r['target_id'] or '-'}")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_r.message(F.text == "💬 فیدبک‌ها")
async def admin_fb(message: Message):
    if not _is_admin(message.from_user.id):
        return
    fbs = await feedback_repo.recent(15)
    if not fbs:
        await message.answer(with_footer("فیدبکی نیست."), reply_markup=admin_menu_kb())
        return
    lines = ["💬 <b>۱۵ فیدبک آخر</b>\n"]
    for f in fbs:
        lines.append(f"• #{f['id']} از <code>{f['user_id']}</code>: {f['text'][:60]}")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_r.message(F.text == "🎮 آمار بازی‌ها")
async def admin_game_stats(message: Message):
    if not _is_admin(message.from_user.id):
        return
    total_games = int(await db.fetch_val(
        "SELECT COALESCE(SUM(games),0) FROM daily_stats", (), 0))
    top = await user_repo.top_wins(5)
    lines = [f"🎮 <b>آمار بازی‌ها</b>\n\n"
             f"🌍 کل بازی: <b>{total_games}</b>\n\n<b>🏆 برترین‌ها:</b>"]
    for i, r in enumerate(top):
        lines.append(f"  {i + 1}. {(r['full_name'] or '—')[:18]} — {r['wins']} برد")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_r.message(F.text == "💰 مدیریت سکه")
async def admin_coins_manage(message: Message):
    if not _is_admin(message.from_user.id):
        return
    top = await user_repo.top_coins(10)
    lines = ["💰 <b>ثروتمندترین کاربران</b>\n"]
    for i, r in enumerate(top):
        lines.append(f"{i + 1}. {(r['full_name'] or '—')[:18]} — <b>{r['coins']}</b>")
    lines.append("\n💡 برای افزایش سکه از /userinfo ID → 💰 +سکه")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_r.message(F.text == "🧹 پاکسازی")
async def admin_cleanup(message: Message):
    if not _is_admin(message.from_user.id):
        return
    n = await link_repo.cleanup()
    await admin_log_repo.log(Config.ADMIN_ID, "cleanup", None, str(n))
    await message.answer(with_footer(f"🧹 {n} لینک پاک شد."),
                         reply_markup=admin_menu_kb())


@admin_r.message(F.text == "🗑 پاک کردن کش")
async def admin_cache_clear(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await cache.flush()
    await message.answer(with_footer("🗑 کش پاک شد."), reply_markup=admin_menu_kb())


@admin_r.message(F.text == "🔒 کانال")
async def admin_channel(message: Message):
    if not _is_admin(message.from_user.id):
        return
    ch = await settings_repo.get_channel()
    text = f"🔒 <b>کانال:</b>\n<code>{ch}</code>" if ch else "🔒 کانال تنظیم نشده."
    await message.answer(with_footer(text), reply_markup=admin_channel_kb(bool(ch)))


@admin_r.callback_query(F.data == "admin_ch:set")
async def admin_ch_set(cb: CallbackQuery, state: FSMContext):
    if not _is_admin(cb.from_user.id):
        return
    await state.set_state(AdminS.setting_channel)
    try:
        await cb.message.edit_text(with_footer(
            "🔧 <b>تنظیم کانال جوین اجباری</b>\n\n"
            "ارسال کن:\n"
            "• <code>@channel</code>\n"
            "• <code>-100...</code>\n"
            "• <code>https://t.me/channel</code>"))
    except Exception:
        pass
    await cb.answer()


@admin_r.callback_query(F.data == "admin_ch:remove")
async def admin_ch_remove(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        return
    await settings_repo.clear_channel()
    try:
        await cb.message.edit_text(with_footer("🗑 حذف شد."))
    except Exception:
        pass
    await cb.answer("✅")


@admin_r.message(AdminS.setting_channel)
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
    await settings_repo.set_channel(parsed)
    await admin_log_repo.log(Config.ADMIN_ID, "set_channel", None, parsed)
    await state.clear()
    await message.answer(with_footer(f"✅ کانال: <b>{parsed}</b>"),
                         reply_markup=admin_menu_kb())


@admin_r.message(F.text == "🔧 تعمیر")
async def admin_maint(message: Message):
    if not _is_admin(message.from_user.id):
        return
    on = await settings_repo.is_maint()
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        _ibtn("🟢 خاموش", S_S, callback_data="maint:off"),
        _ibtn("🔴 روشن", S_D, callback_data="maint:on")]])
    await message.answer(with_footer(f"🔧 تعمیر: <b>{'✅' if on else '❌'}</b>"),
                         reply_markup=kb)


@admin_r.callback_query(F.data.startswith("maint:"))
async def admin_maint_toggle(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        return
    val = cb.data.split(":")[1] == "on"
    await settings_repo.set_maint(val)
    await admin_log_repo.log(Config.ADMIN_ID, "maintenance", None, "on" if val else "off")
    try:
        await cb.message.edit_text(
            with_footer(f"🔧 تعمیر: <b>{'✅' if val else '❌'}</b>"))
    except Exception:
        pass
    await cb.answer("✅")


@admin_r.message(Command("maintenance"))
async def cmd_maintenance(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return
    arg = (command.args or "").strip().lower()
    if arg not in ("on", "off"):
        await message.answer("/maintenance on|off")
        return
    val = arg == "on"
    await settings_repo.set_maint(val)
    await message.answer(with_footer(f"🔧: <b>{'✅' if val else '❌'}</b>"))


@admin_r.message(F.text == "💾 بکاپ")
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


@admin_r.message(Command("backup"))
async def cmd_backup(message: Message, bot: Bot):
    if not _is_admin(message.from_user.id):
        return
    await admin_backup(message, bot)


@admin_r.message(F.text == "📢 پیام همگانی")
async def admin_bcast(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminS.broadcasting)
    await message.answer(with_footer("📢 پیام را بفرست:"))


@admin_r.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminS.broadcasting)
    await message.answer(with_footer("📢 پیام را بفرست:"))


@admin_r.message(AdminS.broadcasting)
async def admin_bcast_recv(message: Message, state: FSMContext):
    await state.update_data(bc_chat=message.chat.id, bc_msg=message.message_id)
    await state.set_state(AdminS.broadcasting_confirm)
    n = await user_repo.count()
    await message.answer(with_footer(f"⚠️ ارسال به {n} کاربر؟"),
                         reply_markup=confirm_kb("broadcast"))


@admin_r.callback_query(F.data == "cancel:broadcast")
async def admin_bcast_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.edit_text(with_footer("❌ لغو."))
    except Exception:
        pass
    await cb.answer()


@admin_r.callback_query(F.data == "confirm:broadcast")
async def admin_bcast_ok(cb: CallbackQuery, state: FSMContext, bot: Bot):
    d = await state.get_data()
    chat, msg = d.get("bc_chat"), d.get("bc_msg")
    await state.clear()
    if not chat or not msg:
        await cb.answer("❌", show_alert=True)
        return
    users = await user_repo.all_ids()
    try:
        await cb.message.edit_text(with_footer(f"⏳ ارسال به {len(users)}..."))
    except Exception:
        pass
    r = await admin_svc.broadcast(bot, chat, msg, users)
    await admin_log_repo.log(Config.ADMIN_ID, "broadcast", None,
                             f"{r['success']}/{r['failed']}")
    try:
        await cb.message.edit_text(with_footer(
            f"✅\nموفق: <b>{r['success']}</b>\nناموفق: <b>{r['failed']}</b>"))
    except Exception:
        pass
    await cb.answer()


@admin_r.message(F.text == "📨 پیام به کاربر")
async def admin_msg_user(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminS.searching_user)
    await message.answer(with_footer("📨 آیدی کاربر را بفرست:"),
                         reply_markup=cancel_kb("global:cancel"))


@admin_r.message(Command("search"))
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
        n = await link_repo.cleanup()
        if n:
            log.info("🧹 cleanup: %s", n)
    except Exception as e:
        log.exception("cleanup: %s", e)


async def job_last_seen():
    try:
        await db.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP")
    except Exception as e:
        log.exception("last_seen: %s", e)


async def job_daily():
    try:
        active = await user_repo.count_active_24h()
        today = now_iran().date().isoformat()
        await db.execute(
            "INSERT INTO daily_stats (date, active_users) VALUES (?, ?) "
            "ON CONFLICT(date) DO UPDATE SET active_users=?",
            (today, active, active))
    except Exception as e:
        log.exception("daily: %s", e)


# ═══════════════════════════════════════════════════════════════════════
# ۲۰ ── HEALTH SERVER
# ═══════════════════════════════════════════════════════════════════════

async def health_server():
    async def handle(reader, writer):
        try:
            await reader.read(1024)
            body = json.dumps({
                "status": "ok",
                "time": now_iran().isoformat(),
                "cache": cache.stats(),
                "queue": match_svc.size(),
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
        srv = await asyncio.start_server(handle, "0.0.0.0", Config.HEALTH_PORT)
        log.info("🏥 Health: http://0.0.0.0:%d", Config.HEALTH_PORT)
        async with srv:
            await srv.serve_forever()
    except Exception as e:
        log.error("health: %s", e)


# ═══════════════════════════════════════════════════════════════════════
# ۲۱ ── MAIN
# ═══════════════════════════════════════════════════════════════════════

bot: Optional[Bot] = None
dp: Optional[Dispatcher] = None
health_task: Optional[asyncio.Task] = None


async def on_startup(bot: Bot, **kwargs):
    log.info("🚀 starting v11.1...")
    me = await bot.get_me()
    Config.BOT_USERNAME = me.username or Config.BOT_USERNAME
    log.info("🤖 @%s | 👑 Admin: %s", me.username, Config.ADMIN_ID)
    ch = await settings_repo.get_channel()
    log.info("🔒 Channel: %s", ch or "—")
    _, _, _, hh, mm, ss, _ = now_shamsi()
    try:
        await bot.send_message(Config.ADMIN_ID,
            f"✅ <b>ربات v11.1 ULTRA راه‌اندازی شد!</b>\n"
            f"@{me.username}\n"
            f"🕐 {hh:02d}:{mm:02d}:{ss:02d}\n\n"
            f"🧠 AI Moderation: ✅\n"
            f"💬 Bidirectional: ✅\n"
            f"💖 Dating: ✅\n"
            f"🎮 Games: ✅\n"
            f"🎨 Avatars: ✅\n"
            f"📊 Analytics: ✅\n"
            f"🎖 Gamification: ✅\n"
            f"🗺 Iran Data: ✅ ({len(PROVINCES)} استان)\n"
            f"🔍 Search: ✅\n"
            f"🔒 Forced-Join: {'✅ ' + ch if ch else '❌'}")
    except Exception:
        pass


async def on_shutdown(bot: Bot = None, **kwargs):
    log.info("🛑 shutdown")
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

    dp.message.middleware(BanCheck())
    dp.callback_query.middleware(BanCheck())
    dp.message.middleware(JoinCheck())
    dp.callback_query.middleware(JoinCheck())
    dp.message.middleware(RateLimit())

    dp.include_router(admin_r)
    dp.include_router(lang_r)
    dp.include_router(rules_r)
    dp.include_router(profile_r)
    dp.include_router(avatar_r)
    dp.include_router(settings_r)
    dp.include_router(dating_r)
    dp.include_router(game_r)
    dp.include_router(fb_r)
    dp.include_router(target_r)
    dp.include_router(match_r)
    dp.include_router(room_r)
    dp.include_router(gamif_r)
    dp.include_router(link_r)
    dp.include_router(reply_r)
    dp.include_router(anon_r)
    dp.include_router(common_r)

    scheduler.add_job(job_cleanup, "interval", hours=1, id="cleanup")
    scheduler.add_job(job_last_seen, "interval", minutes=5, id="last_seen")
    scheduler.add_job(job_daily, "interval", hours=6, id="daily")
    scheduler.start()
    log.info("⏰ Scheduler started")

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
