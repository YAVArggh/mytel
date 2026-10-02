# -*- coding: utf-8 -*-
"""
🤖 ربات پچ پچ - Ultra Pro Edition (Fixed)
پیام ناشناس + پنل ادمین + مهاجرت دیتابیس
"""

import asyncio
import base64
import hashlib
import logging
import os
import random
import re
import shutil
import sqlite3
import string
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    BotCommand, BotCommandScopeDefault, BotCommandScopeChat,
    FSInputFile,
)

# ============================================================
#                    تنظیمات اصلی
# ============================================================

BOT_TOKEN = "8654406992:AAECfMfmYjc9_W8sFG-yNR78kASBh7CRMTs"
BOT_ID = "@irPachPachBot"
BOT_NAME = "پچ پچ"
DB_FILE = "users.db"
BACKUP_DIR = "backups"

# ⚠️ آی‌دی عددی خودت را اینجا بگذار (از @userinfobot بگیر)
SUPER_ADMINS = [8094551428]

HOOK = hashlib.md5(BOT_TOKEN.encode()).hexdigest()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("pechpech")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())

os.makedirs(BACKUP_DIR, exist_ok=True)


# ============================================================
#                    نقشه callback کوتاه‌ساز
# ============================================================

CB_MAP = {}
CB_REVERSE = {}
_cb_counter = [0]

def short_cb(long_data):
    """تبدیل callback طولانی به کوتاه (محدودیت ۶۴ بایت تلگرام)"""
    if long_data in CB_MAP:
        return CB_MAP[long_data]
    _cb_counter[0] += 1
    short = f"c{_cb_counter[0]}"
    CB_MAP[long_data] = short
    CB_REVERSE[short] = long_data
    return short


def resolve_cb(short):
    return CB_REVERSE.get(short, short)


# ============================================================
#                    دیتابیس
# ============================================================

def db_init():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_user_id TEXT UNIQUE,
        rkey TEXT,
        target_user TEXT,
        is_blocked INTEGER DEFAULT 0,
        joined_at TEXT,
        last_seen TEXT,
        message_count INTEGER DEFAULT 0,
        points INTEGER DEFAULT 0,
        referred_by TEXT,
        display_name TEXT DEFAULT '',
        show_link INTEGER DEFAULT 1
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS admins (
        telegram_user_id TEXT PRIMARY KEY,
        added_by TEXT, added_at TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS force_channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT, title TEXT, invite_link TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS custom_buttons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT, reply_text TEXT,
        style TEXT DEFAULT 'primary',
        created_at TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS stats (
        key TEXT PRIMARY KEY, value INTEGER DEFAULT 0)""")

    c.execute("""CREATE TABLE IF NOT EXISTS button_styles (
        key TEXT PRIMARY KEY, style TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS coupons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE, amount INTEGER,
        max_uses INTEGER, used INTEGER DEFAULT 0,
        expires_at TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event TEXT, user_id TEXT,
        details TEXT, created_at TEXT)""")

    conn.commit()

    migrate_db(c)

    defaults = {
        "maintenance": "0",
        "maintenance_text": "🔧 ربات در حال تعمیر است.\nلطفاً بعداً مراجعه کنید.",
        "force_join": "0",
        "welcome_text": f"👋 به <b>{BOT_NAME}</b> خوش آمدید!\n\nبا این ربات می‌تونی پیام ناشناس بفرستی و دریافت کنی.",
        "btn_newlink": "🔗 ساخت لینک ناشناس",
        "btn_profile": "👤 پروفایل من",
        "btn_help": "❓ راهنما",
        "btn_cancel": "🗑 لغو ارسال",
        "btn_points": "🎁 امتیاز من",
        "btn_referral": "👥 دعوت دوستان",
        "start_message_sent": "✅ ارسال شد",
        "target_prompt": "👇 این پایین بنویس و ارسال کن:",
        "anonymous_new_msg": "📩 پیام ناشناس جدید داری 👇",
        "not_found": "❌ کاربر یافت نشد",
        "points_per_message": "10",
        "points_per_referral": "50",
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    for k in ["total_messages", "total_links", "total_users", "total_referrals"]:
        c.execute("INSERT OR IGNORE INTO stats (key, value) VALUES (?, ?)", (k, 0))

    default_styles = {
        "btn_newlink": "success",
        "btn_profile": "primary",
        "btn_help": "primary",
        "btn_cancel": "danger",
        "btn_points": "success",
        "btn_referral": "primary",
    }
    for k, v in default_styles.items():
        c.execute("INSERT OR IGNORE INTO button_styles (key, style) VALUES (?, ?)", (k, v))

    conn.commit()
    return conn


def migrate_db(cursor):
    try:
        cursor.execute("PRAGMA table_info(users)")
        cols = [row[1] for row in cursor.fetchall()]
    except Exception as e:
        log.error("خطا در خواندن ساختار جدول users: %s", e)
        return

    needed = {
        "is_blocked": "INTEGER DEFAULT 0",
        "joined_at": "TEXT",
        "last_seen": "TEXT",
        "message_count": "INTEGER DEFAULT 0",
        "points": "INTEGER DEFAULT 0",
        "referred_by": "TEXT",
        "display_name": "TEXT DEFAULT ''",
        "show_link": "INTEGER DEFAULT 1",
    }

    added = []
    for col, definition in needed.items():
        if col not in cols:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
                added.append(col)
            except Exception as e:
                log.warning("خطا در افزودن ستون %s: %s", col, e)

    if added:
        log.info("✅ ستون‌های جدید اضافه شدند: %s", ", ".join(added))

    now = datetime.now().isoformat()
    cursor.execute("UPDATE users SET joined_at = ? WHERE joined_at IS NULL", (now,))
    cursor.execute("UPDATE users SET last_seen = ? WHERE last_seen IS NULL", (now,))
    cursor.execute("UPDATE users SET is_blocked = 0 WHERE is_blocked IS NULL")
    cursor.execute("UPDATE users SET message_count = 0 WHERE message_count IS NULL")
    cursor.execute("UPDATE users SET points = 0 WHERE points IS NULL")
    cursor.execute("UPDATE users SET referred_by = '' WHERE referred_by IS NULL")
    cursor.execute("UPDATE users SET display_name = '' WHERE display_name IS NULL")
    cursor.execute("UPDATE users SET show_link = 1 WHERE show_link IS NULL")


conn = db_init()


# ============================================================
#                    توابع کمکی دیتابیس
# ============================================================

def row_to_dict(cur, row):
    if not row:
        return None
    return dict(zip([c[0] for c in cur.description], row))


def get_setting(key, default=""):
    cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
    r = cur.fetchone()
    return r[0] if r else default


def set_setting(key, value):
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()


def get_stat(key):
    cur = conn.execute("SELECT value FROM stats WHERE key = ?", (key,))
    r = cur.fetchone()
    return r[0] if r else 0


def inc_stat(key, amount=1):
    conn.execute(
        "INSERT INTO stats (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = value + ?",
        (key, amount, amount),
    )
    conn.commit()


def get_btn_style(key):
    cur = conn.execute("SELECT style FROM button_styles WHERE key = ?", (key,))
    r = cur.fetchone()
    return r[0] if r else "primary"


def set_btn_style(key, style):
    conn.execute("INSERT OR REPLACE INTO button_styles (key, style) VALUES (?, ?)", (key, style))
    conn.commit()


def db_get_user_by_tg(tg_id):
    cur = conn.execute("SELECT * FROM users WHERE telegram_user_id = ?", (str(tg_id),))
    return row_to_dict(cur, cur.fetchone())


def db_get_user_by_id(uid):
    cur = conn.execute("SELECT * FROM users WHERE id = ?", (uid,))
    return row_to_dict(cur, cur.fetchone())


def db_get_target_by_rkey(uid, rkey):
    cur = conn.execute("SELECT * FROM users WHERE id = ? AND rkey = ?", (uid, rkey))
    return row_to_dict(cur, cur.fetchone())


def db_insert_user(tg_id, rkey, referred_by=""):
    now = datetime.now().isoformat()
    cur = conn.execute(
        "INSERT OR IGNORE INTO users (telegram_user_id, rkey, target_user, joined_at, last_seen, referred_by) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(tg_id), rkey, "", now, now, referred_by),
    )
    conn.commit()
    if cur.lastrowid:
        inc_stat("total_users")
        if referred_by:
            inc_stat("total_referrals")
    return cur.lastrowid


def db_update_target_by_id(target, uid):
    conn.execute("UPDATE users SET target_user = ? WHERE id = ?", (str(target), uid))
    conn.commit()


def db_update_target_by_tg(target, tg_id):
    conn.execute("UPDATE users SET target_user = ? WHERE telegram_user_id = ?", (str(target), str(tg_id)))
    conn.commit()


def db_set_blocked(tg_id, blocked):
    conn.execute("UPDATE users SET is_blocked = ? WHERE telegram_user_id = ?",
                 (1 if blocked else 0, str(tg_id)))
    conn.commit()


def db_all_users():
    cur = conn.execute("SELECT * FROM users WHERE is_blocked = 0")
    return [row_to_dict(cur, r) for r in cur.fetchall()]


def db_add_points(tg_id, amount):
    conn.execute("UPDATE users SET points = points + ? WHERE telegram_user_id = ?",
                 (amount, str(tg_id)))
    conn.commit()


def db_inc_message_count(tg_id):
    conn.execute("UPDATE users SET message_count = message_count + 1 WHERE telegram_user_id = ?",
                 (str(tg_id),))
    conn.commit()


def db_update_last_seen(tg_id):
    conn.execute("UPDATE users SET last_seen = ? WHERE telegram_user_id = ?",
                 (datetime.now().isoformat(), str(tg_id)))
    conn.commit()


def get_or_create_user(tg_id, referred_by=""):
    u = db_get_user_by_tg(tg_id)
    if not u:
        uid = db_insert_user(tg_id, rndKey(), referred_by)
        u = db_get_user_by_id(uid) if uid else db_get_user_by_tg(tg_id)
    return u


def log_event(event, user_id, details=""):
    conn.execute(
        "INSERT INTO logs (event, user_id, details, created_at) VALUES (?, ?, ?, ?)",
        (event, str(user_id), details, datetime.now().isoformat()),
    )
    conn.commit()


# ----- ادمین‌ها -----
def is_admin(tg_id):
    if tg_id in SUPER_ADMINS:
        return True
    cur = conn.execute("SELECT 1 FROM admins WHERE telegram_user_id = ?", (str(tg_id),))
    return cur.fetchone() is not None


def add_admin(tg_id, by):
    conn.execute(
        "INSERT OR IGNORE INTO admins (telegram_user_id, added_by, added_at) VALUES (?, ?, ?)",
        (str(tg_id), str(by), datetime.now().isoformat()),
    )
    conn.commit()


def remove_admin(tg_id):
    conn.execute("DELETE FROM admins WHERE telegram_user_id = ?", (str(tg_id),))
    conn.commit()


def all_admins():
    cur = conn.execute("SELECT telegram_user_id FROM admins")
    return [r[0] for r in cur.fetchall()]


# ----- کانال‌ها -----
def add_force_channel(chat_id, title, link):
    conn.execute(
        "INSERT INTO force_channels (chat_id, title, invite_link) VALUES (?, ?, ?)",
        (str(chat_id), title, link),
    )
    conn.commit()


def remove_force_channel(cid):
    conn.execute("DELETE FROM force_channels WHERE id = ?", (cid,))
    conn.commit()


def all_force_channels():
    cur = conn.execute("SELECT * FROM force_channels")
    return [row_to_dict(cur, r) for r in cur.fetchall()]


# ----- دکمه‌های سفارشی -----
def add_custom_button(text, reply, style):
    conn.execute(
        "INSERT INTO custom_buttons (text, reply_text, style, created_at) VALUES (?, ?, ?, ?)",
        (text, reply, style, datetime.now().isoformat()),
    )
    conn.commit()


def remove_custom_button(bid):
    conn.execute("DELETE FROM custom_buttons WHERE id = ?", (bid,))
    conn.commit()


def all_custom_buttons():
    cur = conn.execute("SELECT * FROM custom_buttons")
    return [row_to_dict(cur, r) for r in cur.fetchall()]


# ----- کد تخفیف -----
def add_coupon(code, amount, max_uses, days=30):
    exp = (datetime.now() + timedelta(days=days)).isoformat()
    conn.execute(
        "INSERT INTO coupons (code, amount, max_uses, expires_at) VALUES (?, ?, ?, ?)",
        (code, amount, max_uses, exp),
    )
    conn.commit()


def use_coupon(code, tg_id):
    cur = conn.execute("SELECT * FROM coupons WHERE code = ?", (code,))
    c = row_to_dict(cur, cur.fetchone())
    if not c:
        return "❌ کد نامعتبر است."
    if c["used"] >= c["max_uses"]:
        return "❌ ظرفیت این کد پر شده."
    if datetime.fromisoformat(c["expires_at"]) < datetime.now():
        return "❌ این کد منقضی شده."
    conn.execute("UPDATE coupons SET used = used + 1 WHERE id = ?", (c["id"],))
    conn.commit()
    db_add_points(tg_id, c["amount"])
    return f"✅ {c['amount']} امتیاز دریافت کردید!"


def all_coupons():
    cur = conn.execute("SELECT * FROM coupons")
    return [row_to_dict(cur, r) for r in cur.fetchall()]


# ============================================================
#                    توابع کمکی
# ============================================================

def hxId(i):
    return hex(i)[::-1]


def revHxId(h):
    return int(h[::-1], 16)


def encrypt(data):
    key = HOOK
    return base64.b64encode(
        bytes([ord(c) ^ ord(key[i % len(key)]) for i, c in enumerate(data)])
    ).decode()


def decrypt(data):
    key = HOOK
    d = base64.b64decode(data)
    return "".join(chr(d[i] ^ ord(key[i % len(key)])) for i in range(len(d)))


def rndKey():
    return "".join(random.choices(string.ascii_letters + string.digits, k=8))


def make_backup():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(BACKUP_DIR, f"backup_{ts}.db")
    shutil.copy(DB_FILE, path)
    return path


# ============================================================
#                    FSM States
# ============================================================

class AdminStates(StatesGroup):
    broadcast = State()
    add_admin = State()
    add_channel = State()
    edit_text_value = State()
    new_button_text = State()
    new_button_reply = State()
    block_user = State()
    unblock_user = State()
    add_points = State()
    remove_points = State()
    new_coupon_code = State()
    new_coupon_amount = State()
    new_coupon_uses = State()
    send_to_user = State()
    find_user = State()


class ProfileStates(StatesGroup):
    waiting_name = State()


# ============================================================
#                    کیبوردها
# ============================================================

def color_button(text, callback_data, style="primary"):
    return InlineKeyboardButton(
        text=text,
        callback_data=short_cb(callback_data),
        style=style,
    )


def main_reply_keyboard():
    rows = [
        [KeyboardButton(text=get_setting("btn_newlink")),
         KeyboardButton(text=get_setting("btn_profile"))],
        [KeyboardButton(text=get_setting("btn_points")),
         KeyboardButton(text=get_setting("btn_referral"))],
        [KeyboardButton(text=get_setting("btn_help")),
         KeyboardButton(text=get_setting("btn_cancel"))],
    ]
    for cb in all_custom_buttons():
        rows.append([KeyboardButton(text=cb["text"])])

    return ReplyKeyboardMarkup(
        keyboard=rows, resize_keyboard=True, one_time_keyboard=False,
        input_field_placeholder="یک گزینه را انتخاب کن...",
    )


def remove_keyboard():
    return ReplyKeyboardRemove()


def link_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [color_button("✅ ساخت لینک ناشناس", "make_link", "success")],
        [color_button("📤 اشتراک‌گذاری", "share_link", "primary"),
         color_button("🗑 پاک کردن", "delete_msg", "danger")],
    ])


def profile_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [color_button("✏️ تغییر نام", "edit_name", "primary"),
         color_button("🔒 حریم خصوصی", "privacy", "success")],
        [color_button("❌ حذف حساب", "delete_account", "danger")],
    ])


def reply_inline_keyboard(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [color_button("💬 پاسخ", uid, "primary")]
    ])


def join_channels_keyboard(channels):
    rows = []
    for ch in channels:
        rows.append([InlineKeyboardButton(
            text=f"📢 {ch['title']}",
            url=ch["invite_link"] or "https://t.me",
        )])
    rows.append([color_button("✅ عضو شدم", "check_join", "success")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_panel_keyboard():
    maintenance = get_setting("maintenance") == "1"
    force_join = get_setting("force_join") == "1"

    return InlineKeyboardMarkup(inline_keyboard=[
        [color_button("📊 آمار کامل", "adm_stats", "primary"),
         color_button("📢 ارسال همگانی", "adm_broadcast", "primary")],
        [color_button(f"🔧 تعمیر: {'✅ روشن' if maintenance else '❌ خاموش'}",
                      "adm_toggle_maintenance",
                      "danger" if maintenance else "success")],
        [color_button("✏️ ویرایش متن‌ها", "adm_edit_texts", "primary"),
         color_button("🎨 رنگ دکمه‌ها", "adm_button_styles", "success")],
        [color_button("🆕 ساخت دکمه", "adm_new_button", "success"),
         color_button("📋 لیست دکمه‌ها", "adm_list_buttons", "primary")],
        [color_button(f"📢 جوین اجباری: {'✅ روشن' if force_join else '❌ خاموش'}",
                      "adm_toggle_forcejoin",
                      "danger" if force_join else "success")],
        [color_button("➕ افزودن کانال", "adm_add_channel", "success"),
         color_button("📋 لیست کانال‌ها", "adm_list_channels", "primary")],
        [color_button("👤 ادمین‌ها", "adm_admins_menu", "primary")],
        [color_button("🚫 بلاک/آنبلاک", "adm_block_menu", "danger"),
         color_button("💰 مدیریت امتیاز", "adm_points_menu", "success")],
        [color_button("🎟 کد تخفیف", "adm_coupons_menu", "primary"),
         color_button("📨 پیام به کاربر", "adm_send_to_user", "primary")],
        [color_button("🔍 جستجوی کاربر", "adm_find_user", "primary"),
         color_button("📜 لاگ‌ها", "adm_logs", "primary")],
        [color_button("💾 بکاپ دیتابیس", "adm_backup", "success"),
         color_button("📥 دانلود دیتابیس", "adm_download_db", "primary")],
        [color_button("🔄 بازنشانی تنظیمات", "adm_reset_confirm", "danger")],
        [color_button("❌ بستن پنل", "adm_close", "danger")],
    ])


def adm_back_kb(extra=None):
    rows = extra or []
    rows.append([color_button("🔙 بازگشت به پنل", "adm_back", "primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================
#                    منوی دستورات
# ============================================================

async def set_bot_commands():
    user_commands = [
        BotCommand(command="start", description="🚀 شروع / منوی اصلی"),
        BotCommand(command="help", description="📖 راهنمای ربات"),
        BotCommand(command="profile", description="👤 پروفایل من"),
        BotCommand(command="link", description="🔗 ساخت لینک ناشناس"),
        BotCommand(command="points", description="🎁 امتیاز من"),
        BotCommand(command="referral", description="👥 دعوت دوستان"),
        BotCommand(command="coupon", description="🎟 استفاده از کد تخفیف"),
        BotCommand(command="cancel", description="🗑 لغو ارسال"),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    admin_commands = user_commands + [
        BotCommand(command="admin", description="🎛 پنل ادمین"),
        BotCommand(command="stats", description="📊 آمار ربات"),
        BotCommand(command="broadcast", description="📢 ارسال همگانی"),
        BotCommand(command="maintenance", description="🔧 حالت تعمیر"),
        BotCommand(command="backup", description="💾 بکاپ دیتابیس"),
        BotCommand(command="panel", description="⚡ پنل سریع"),
    ]

    for sa in SUPER_ADMINS:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=sa))
        except Exception as e:
            log.warning("خطا در تنظیم دستورات ادمین %s: %s", sa, e)

    for a in all_admins():
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=int(a)))
        except Exception:
            pass


# ============================================================
#                    جوین اجباری
# ============================================================

async def check_force_join(user_id):
    if get_setting("force_join") != "1":
        return True
    channels = all_force_channels()
    if not channels:
        return True
    for ch in channels:
        try:
            m = await bot.get_chat_member(chat_id=ch["chat_id"], user_id=user_id)
            if m.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
                return False
        except Exception:
            continue
    return True


async def send_force_join(message):
    channels = all_force_channels()
    await message.answer(
        "⚠️ برای استفاده از ربات، ابتدا در کانال‌های زیر عضو شوید:\n\n"
        "پس از عضویت، روی دکمه <b>✅ عضو شدم</b> بزنید.",
        reply_markup=join_channels_keyboard(channels),
    )


# ============================================================
#                    /start
# ============================================================

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    chat_id = message.from_user.id

    if get_setting("maintenance") == "1" and not is_admin(chat_id):
        await message.answer(get_setting("maintenance_text"), reply_markup=ReplyKeyboardRemove())
        return

    if not is_admin(chat_id) and not await check_force_join(chat_id):
        await send_force_join(message)
        return

    args = message.text.split(maxsplit=1)
    referred_by = ""
    if len(args) > 1 and args[1].startswith("ref_"):
        referred_by = args[1].replace("ref_", "")

    user = get_or_create_user(chat_id, referred_by)
    if user and user.get("is_blocked"):
        await message.answer("⛔️ شما از ربات بلاک شده‌اید.")
        return

    db_update_last_seen(chat_id)

    if len(args) > 1:
        match = re.search(r"(\w+)_(\w+)", args[1])
        if match:
            param_rkey, param_id = match.groups()
            try:
                tid = revHxId(param_id)
            except Exception:
                tid = -1
            target_user = db_get_target_by_rkey(tid, param_rkey)
            if target_user:
                try:
                    tc = await bot.get_chat(target_user["telegram_user_id"])
                    first_name = tc.first_name or "کاربر"
                except Exception:
                    first_name = "کاربر"
                db_update_target_by_id(target_user["telegram_user_id"], user["id"])
                await message.answer(
                    f"در حال ارسال پیام ناشناس به <b>{first_name}</b> هستی\n"
                    "هرچی بفرستی ناشناس میره براش. این پایین بفرست 👇",
                    reply_markup=remove_keyboard(),
                )
                return
            else:
                await message.answer(get_setting("not_found"),
                                     reply_markup=main_reply_keyboard())
                return

    await message.answer(get_setting("welcome_text"),
                         reply_markup=main_reply_keyboard())


# ============================================================
#                    دستورات کاربران
# ============================================================

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        f"📖 <b>راهنمای {BOT_NAME}</b>\n\n"
        "🔗 <b>ساخت لینک ناشناس</b>\nیک لینک مخصوص خودت بساز.\n\n"
        "👤 <b>پروفایل من</b>\nمشاهده اطلاعات حساب.\n\n"
        "🎁 <b>امتیاز من</b>\nمشاهده امتیازات.\n\n"
        "👥 <b>دعوت دوستان</b>\nلینک ریفرال بساز.\n\n"
        "🎟 <b>کد تخفیف</b>\nاستفاده از کد امتیاز.\n\n"
        "🗑 <b>لغو ارسال</b>\nلغو حالت ارسال ناشناس.",
        reply_markup=main_reply_keyboard(),
    )


@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    user = db_get_user_by_tg(message.from_user.id)
    if not user:
        await message.answer("❌ ابتدا /start را بزنید.")
        return
    link = f"https://t.me/{BOT_ID.lstrip('@')}?start={user['rkey']}_{hxId(user['id'])}"
    display = user.get("display_name") or "—"
    await message.answer(
        f"👤 <b>پروفایل شما</b>\n\n"
        f"🆔 آی‌دی: <code>{user['id']}</code>\n"
        f"📛 نام نمایشی: <b>{display}</b>\n"
        f"🔑 کلید: <code>{user['rkey']}</code>\n"
        f"🎁 امتیاز: <b>{user['points']}</b>\n"
        f"💬 پیام‌های ارسالی: <b>{user['message_count']}</b>\n\n"
        f"🔗 <b>لینک ناشناس:</b>\n<code>{link}</code>",
        reply_markup=profile_inline_keyboard(),
    )


@dp.message(Command("link"))
async def cmd_link(message: Message):
    user = get_or_create_user(message.from_user.id)
    link = f"https://t.me/{BOT_ID.lstrip('@')}?start={user['rkey']}_{hxId(user['id'])}"
    inc_stat("total_links")
    await message.answer(
        f"🔗 <b>لینک ناشناس شما:</b>\n\n<code>{link}</code>",
        reply_markup=link_inline_keyboard(),
    )


@dp.message(Command("points"))
async def cmd_points(message: Message):
    user = db_get_user_by_tg(message.from_user.id)
    if not user:
        await message.answer("❌ ابتدا /start را بزنید.")
        return
    await message.answer(
        f"🎁 <b>امتیاز شما</b>\n\n"
        f"💰 امتیاز فعلی: <b>{user['points']}</b>\n\n"
        f"💡 هر پیام ناشناس = <b>{get_setting('points_per_message')}</b> امتیاز\n"
        f"👥 هر دعوت موفق = <b>{get_setting('points_per_referral')}</b> امتیاز"
    )


@dp.message(Command("referral"))
async def cmd_referral(message: Message):
    user = get_or_create_user(message.from_user.id)
    link = f"https://t.me/{BOT_ID.lstrip('@')}?start=ref_{user['telegram_user_id']}"
    await message.answer(
        f"👥 <b>دعوت دوستان</b>\n\n"
        f"با این لینک دوستات رو دعوت کن و امتیاز بگیر:\n\n"
        f"<code>{link}</code>\n\n"
        f"💰 هر دعوت موفق = <b>{get_setting('points_per_referral')}</b> امتیاز"
    )


@dp.message(Command("coupon"))
async def cmd_coupon(message: Message):
    await message.answer("🎟 کد تخفیف را بفرستید:")


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message):
    user = db_get_user_by_tg(message.from_user.id)
    if user and user["target_user"]:
        db_update_target_by_id("", user["id"])
        await message.answer("✅ لغو شد.", reply_markup=main_reply_keyboard())
    else:
        await message.answer("ℹ️ در حالت ارسال ناشناس نیستی.",
                             reply_markup=main_reply_keyboard())


# ============================================================
#                    دستورات ادمین
# ============================================================

@dp.message(Command("admin", "panel"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ دسترسی ندارید.")
        return
    await message.answer(
        "🎛 <b>پنل ادمین پچ پچ</b>\n\n"
        "⚡️ نسخه Ultra Pro\n"
        "از دکمه‌های زیر برای مدیریت کامل ربات استفاده کنید:",
        reply_markup=admin_panel_keyboard(),
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    await send_stats(message)


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer("📢 پیام مورد نظر را بفرستید:")
    await state.set_state(AdminStates.broadcast)


@dp.message(Command("maintenance"))
async def cmd_maintenance(message: Message):
    if not is_admin(message.from_user.id):
        return
    new_val = "0" if get_setting("maintenance") == "1" else "1"
    set_setting("maintenance", new_val)
    await message.answer(
        f"🔧 حالت تعمیر {'روشن' if new_val == '1' else 'خاموش'} شد.",
        reply_markup=admin_panel_keyboard(),
    )


@dp.message(Command("backup"))
async def cmd_backup(message: Message):
    if not is_admin(message.from_user.id):
        return
    path = make_backup()
    await message.answer(f"💾 بکاپ ساخته شد:\n<code>{path}</code>")


# ============================================================
#                    هندلر متنی اصلی
# ============================================================

@dp.message(F.text)
async def on_text(message: Message, state: FSMContext):
    chat_id = message.from_user.id
    if await state.get_state() is not None:
        return

    if get_setting("maintenance") == "1" and not is_admin(chat_id):
        await message.answer(get_setting("maintenance_text"))
        return

    if not is_admin(chat_id) and not await check_force_join(chat_id):
        await send_force_join(message)
        return

    u = db_get_user_by_tg(chat_id)
    if u and u.get("is_blocked"):
        return

    db_update_last_seen(chat_id)
    text = message.text or ""

    cur = conn.execute("SELECT 1 FROM coupons WHERE code = ?", (text.strip(),))
    if cur.fetchone() and not text.startswith("/"):
        result = use_coupon(text.strip(), chat_id)
        await message.answer(result, reply_markup=main_reply_keyboard())
        return

    for cb in all_custom_buttons():
        if text == cb["text"]:
            await message.answer(cb["reply_text"])
            return

    if text == get_setting("btn_help"):
        await cmd_help(message); return
    if text == get_setting("btn_profile"):
        await cmd_profile(message); return
    if text == get_setting("btn_newlink"):
        await cmd_link(message); return
    if text == get_setting("btn_points"):
        await cmd_points(message); return
    if text == get_setting("btn_referral"):
        await cmd_referral(message); return
    if text == get_setting("btn_cancel"):
        await cmd_cancel(message); return

    me = db_get_user_by_tg(chat_id)
    if me and me["target_user"]:
        await send_anonymous(message, me)
        return

    await message.answer("❓ متوجه نشدم. از منوی زیر استفاده کن 👇",
                         reply_markup=main_reply_keyboard())


async def send_anonymous(message, me):
    try:
        await bot.send_message(int(me["target_user"]), get_setting("anonymous_new_msg"))
        await bot.copy_message(
            chat_id=int(me["target_user"]),
            from_chat_id=message.from_user.id,
            message_id=message.message_id,
            reply_markup=reply_inline_keyboard(encrypt(str(me["id"]))),
        )
        db_update_target_by_id("", me["id"])
        inc_stat("total_messages")
        db_inc_message_count(message.from_user.id)
        points = int(get_setting("points_per_message", "10"))
        db_add_points(message.from_user.id, points)
        await message.answer(
            f"{get_setting('start_message_sent')} (+{points} امتیاز)",
            reply_markup=main_reply_keyboard(),
        )
    except Exception as e:
        log.exception("خطا: %s", e)
        await message.answer("❌ خطا در ارسال.")


# ============================================================
#                    پیام‌های غیرمتنی
# ============================================================

@dp.message()
async def on_other(message: Message):
    chat_id = message.from_user.id
    if get_setting("maintenance") == "1" and not is_admin(chat_id):
        return
    if not is_admin(chat_id) and not await check_force_join(chat_id):
        return
    me = db_get_user_by_tg(chat_id)
    if me and me["target_user"]:
        await send_anonymous(message, me)


# ============================================================
#                    آمار
# ============================================================

async def send_stats(msg_or_cq):
    users = db_all_users()
    today = datetime.now().date().isoformat()
    cur = conn.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{today}%",))
    today_count = cur.fetchone()[0]

    text = (
        "📊 <b>آمار کامل ربات پچ پچ</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"👥 کل کاربران: <b>{len(users)}</b>\n"
        f"🆕 امروز: <b>{today_count}</b>\n"
        f"💬 پیام‌ها: <b>{get_stat('total_messages')}</b>\n"
        f"🔗 لینک‌ها: <b>{get_stat('total_links')}</b>\n"
        f"👥 ریفرال‌ها: <b>{get_stat('total_referrals')}</b>\n"
        f"📢 کانال‌ها: <b>{len(all_force_channels())}</b>\n"
        f"👤 ادمین‌ها: <b>{len(all_admins())}</b>\n"
        f"🎛 دکمه‌های سفارشی: <b>{len(all_custom_buttons())}</b>\n"
        f"🔧 تعمیر: <b>{'✅' if get_setting('maintenance') == '1' else '❌'}</b>\n"
        f"📢 جوین اجباری: <b>{'✅' if get_setting('force_join') == '1' else '❌'}</b>"
    )
    if isinstance(msg_or_cq, CallbackQuery):
        await msg_or_cq.message.edit_text(text, reply_markup=adm_back_kb())
    else:
        await msg_or_cq.answer(text)


# ============================================================
#                    Callback - کاربران
# ============================================================

@dp.callback_query()
async def on_callback(cq: CallbackQuery, state: FSMContext):
    raw = cq.data or ""
    data = resolve_cb(raw)
    chat_id = cq.from_user.id

    # ===== ادمین =====
    if data.startswith("adm_"):
        if not is_admin(chat_id):
            await cq.answer("⛔️ دسترسی ندارید", show_alert=True)
            return
        try:
            await handle_admin_callback(cq, state, data)
        except Exception as e:
            log.exception("خطا در پنل ادمین: %s", e)
            await cq.answer(f"❌ خطا: {e}", show_alert=True)
        return

    if data.startswith("style_"):
        if not is_admin(chat_id):
            await cq.answer("⛔️", show_alert=True)
            return
        try:
            await handle_style_callback(cq, state, data)
        except Exception as e:
            log.exception("خطا در استایل: %s", e)
            await cq.answer(f"❌ {e}", show_alert=True)
        return

    # ===== جوین =====
    if data == "check_join":
        if await check_force_join(chat_id):
            try:
                await cq.message.edit_text("✅ عضویت تأیید شد! حالا /start را بزنید.")
            except Exception:
                await cq.message.answer("✅ عضویت تأیید شد! حالا /start را بزنید.")
        else:
            await cq.answer("❌ هنوز عضو نشده‌اید.", show_alert=True)
        return

    if get_setting("maintenance") == "1" and not is_admin(chat_id):
        await cq.answer(get_setting("maintenance_text"), show_alert=True)
        return

    if not is_admin(chat_id) and not await check_force_join(chat_id):
        await cq.answer("⚠️ ابتدا در کانال‌ها عضو شوید.", show_alert=True)
        return

    # ===== دکمه‌های کاربر =====
    if data == "make_link":
        await cmd_link(cq.message)
        await cq.answer("✅")
        return

    if data == "share_link":
        u = db_get_user_by_tg(chat_id)
        if u:
            link = f"https://t.me/{BOT_ID.lstrip('@')}?start={u['rkey']}_{hxId(u['id'])}"
            await cq.message.answer(
                f"📤 کپی کن:\n\n<code>🔗 به من پیام ناشناس بده:\n{link}</code>"
            )
        await cq.answer("📋")
        return

    if data == "delete_msg":
        try:
            await cq.message.delete()
        except Exception:
            pass
        try:
            await cq.answer("🗑 حذف شد")
        except Exception:
            pass
        return

    # ===== تغییر نام =====
    if data == "edit_name":
        await cq.message.answer("✏️ نام جدید خود را بفرستید (۲ تا ۳۲ کاراکتر):")
        await state.set_state(ProfileStates.waiting_name)
        await cq.answer()
        return

    # ===== حریم خصوصی =====
    if data == "privacy":
        u = db_get_user_by_tg(chat_id)
        show_link = u.get("show_link", 1) if u else 1
        rows = [
            [color_button(
                f"🔗 نمایش لینک: {'✅ روشن' if show_link else '❌ خاموش'}",
                "toggle_show_link",
                "success" if show_link else "danger",
            )],
            [color_button("🔙 بستن", "close_profile_msg", "primary")],
        ]
        try:
            await cq.message.edit_text(
                "🔒 <b>حریم خصوصی</b>\n\n"
                "اگر نمایش لینک خاموش باشد، دیگران نمی‌توانند از لینک ناشناس شما استفاده کنند.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
        except Exception:
            await cq.message.answer(
                "🔒 <b>حریم خصوصی</b>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
        await cq.answer()
        return

    if data == "toggle_show_link":
        u = db_get_user_by_tg(chat_id)
        new = 0 if (u and u.get("show_link", 1)) else 1
        conn.execute("UPDATE users SET show_link = ? WHERE telegram_user_id = ?",
                     (new, str(chat_id)))
        conn.commit()
        show_link = new
        rows = [
            [color_button(
                f"🔗 نمایش لینک: {'✅ روشن' if show_link else '❌ خاموش'}",
                "toggle_show_link",
                "success" if show_link else "danger",
            )],
            [color_button("🔙 بستن", "close_profile_msg", "primary")],
        ]
        try:
            await cq.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
            )
        except Exception:
            pass
        await cq.answer(f"{'✅ روشن' if new else '❌ خاموش'}")
        return

    if data == "close_profile_msg":
        try:
            await cq.message.delete()
        except Exception:
            pass
        await cq.answer()
        return

    # ===== حذف حساب =====
    if data == "delete_account":
        rows = [
            [color_button("⚠️ بله، حذف کن", "confirm_delete_account", "danger")],
            [color_button("🔙 انصراف", "cancel_delete", "primary")],
        ]
        try:
            await cq.message.edit_text(
                "⚠️ <b>هشدار!</b>\n\n"
                "آیا از حذف حساب خود مطمئنی؟\n"
                "تمام امتیازات و اطلاعات از بین می‌رود.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
        except Exception:
            await cq.message.answer("⚠️ مطمئنی؟",
                                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        await cq.answer()
        return

    if data == "confirm_delete_account":
        conn.execute("DELETE FROM users WHERE telegram_user_id = ?", (str(chat_id),))
        conn.commit()
        try:
            await cq.message.edit_text("✅ حساب شما حذف شد.\nبرای شروع مجدد /start بزنید.")
        except Exception:
            await cq.message.answer("✅ حساب حذف شد.")
        await cq.answer("حذف شد")
        return

    if data == "cancel_delete":
        try:
            await cq.message.delete()
        except Exception:
            pass
        await cq.answer("لغو شد")
        return

    # ===== دکمه پاسخ ناشناس =====
    try:
        rid = int(decrypt(data))
    except Exception:
        await cq.answer()
        return

    target = db_get_user_by_id(rid)
    if not target:
        await cq.answer()
        return

    db_update_target_by_tg(target["telegram_user_id"], chat_id)
    await bot.send_message(chat_id, get_setting("target_prompt"),
                           reply_to_message_id=cq.message.message_id)
    await cq.answer("✅ بفرست")


# ============================================================
#                    Callback ادمین
# ============================================================

async def handle_admin_callback(cq: CallbackQuery, state: FSMContext, data: str):
    chat_id = cq.from_user.id

    if data == "adm_stats":
        await send_stats(cq); await cq.answer(); return

    if data == "adm_toggle_maintenance":
        new = "0" if get_setting("maintenance") == "1" else "1"
        set_setting("maintenance", new)
        log_event("maintenance_toggle", chat_id, new)
        try:
            await cq.message.edit_reply_markup(reply_markup=admin_panel_keyboard())
        except Exception:
            pass
        await cq.answer(f"🔧 {'روشن' if new == '1' else 'خاموش'}")
        return

    if data == "adm_toggle_forcejoin":
        new = "0" if get_setting("force_join") == "1" else "1"
        set_setting("force_join", new)
        try:
            await cq.message.edit_reply_markup(reply_markup=admin_panel_keyboard())
        except Exception:
            pass
        await cq.answer(f"📢 {'روشن' if new == '1' else 'خاموش'}")
        return

    if data == "adm_add_channel":
        await cq.message.answer("➕ آی‌دی عددی کانال را بفرستید:\n(مثال: <code>-1001234567890</code>)")
        await state.set_state(AdminStates.add_channel)
        await cq.answer(); return

    if data == "adm_list_channels":
        chs = all_force_channels()
        if not chs:
            await cq.message.answer("📭 خالی."); await cq.answer(); return
        rows = [[color_button(f"🗑 {ch['title']}", f"adm_delch_{ch['id']}", "danger")] for ch in chs]
        rows.append([color_button("🔙 بازگشت", "adm_back", "primary")])
        await cq.message.edit_text(
            "📋 <b>کانال‌ها:</b>\n(برای حذف روی هرکدام بزنید)",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await cq.answer(); return

    if data.startswith("adm_delch_"):
        remove_force_channel(int(data.replace("adm_delch_", "")))
        await cq.answer("🗑 حذف شد")
        await cq.message.edit_text("🎛 پنل:", reply_markup=admin_panel_keyboard())
        return

    if data == "adm_edit_texts":
        texts = {
            "btn_newlink": "🔗 دکمه لینک ناشناس",
            "btn_profile": "👤 دکمه پروفایل",
            "btn_help": "❓ دکمه راهنما",
            "btn_cancel": "🗑 دکمه لغو",
            "btn_points": "🎁 دکمه امتیاز",
            "btn_referral": "👥 دکمه ریفرال",
            "welcome_text": "💬 متن خوش‌آمد",
            "start_message_sent": "✅ متن تأیید ارسال",
            "target_prompt": "📝 متن درخواست",
            "anonymous_new_msg": "📩 متن اعلان پیام",
            "not_found": "❌ متن یافت نشد",
            "maintenance_text": "🔧 متن تعمیر",
        }
        rows = [[color_button(f"✏️ {v}", f"adm_edit_{k}", "primary")] for k, v in texts.items()]
        rows.append([color_button("🔙 بازگشت", "adm_back", "primary")])
        await cq.message.edit_text(
            "✏️ <b>کدام متن؟</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await cq.answer(); return

    if data.startswith("adm_edit_"):
        key = data.replace("adm_edit_", "")
        await state.update_data(edit_key=key)
        cur_val = get_setting(key)
        await cq.message.answer(f"✏️ متن فعلی:\n<code>{cur_val}</code>\n\nمتن جدید را بفرستید:")
        await state.set_state(AdminStates.edit_text_value)
        await cq.answer(); return

    if data == "adm_button_styles":
        keys = {
            "btn_newlink": "🔗 لینک ناشناس",
            "btn_profile": "👤 پروفایل",
            "btn_help": "❓ راهنما",
            "btn_cancel": "🗑 لغو",
            "btn_points": "🎁 امتیاز",
            "btn_referral": "👥 دعوت",
        }
        rows = []
        for k, label in keys.items():
            st = get_btn_style(k)
            emoji = {"primary": "🔵", "success": "🟢", "danger": "🔴"}.get(st, "⚪")
            rows.append([color_button(f"{emoji} {label} ({st})", f"style_edit_{k}", "primary")])
        rows.append([color_button("🔙 بازگشت", "adm_back", "primary")])
        await cq.message.edit_text(
            "🎨 <b>رنگ دکمه‌های اصلی:</b>\nروی هر دکمه بزنید تا رنگش را عوض کنید:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await cq.answer(); return

    if data == "adm_new_button":
        await cq.message.answer("🆕 متن دکمه را بفرستید:")
        await state.set_state(AdminStates.new_button_text)
        await cq.answer(); return

    if data == "adm_list_buttons":
        bts = all_custom_buttons()
        if not bts:
            await cq.message.answer("📭 خالی."); await cq.answer(); return
        rows = [[color_button(f"🗑 {b['text']}", f"adm_delbtn_{b['id']}", "danger")] for b in bts]
        rows.append([color_button("🔙 بازگشت", "adm_back", "primary")])
        await cq.message.edit_text(
            "📋 دکمه‌ها:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await cq.answer(); return

    if data.startswith("adm_delbtn_"):
        remove_custom_button(int(data.replace("adm_delbtn_", "")))
        await cq.answer("🗑")
        await cq.message.edit_text("🎛 پنل:", reply_markup=admin_panel_keyboard())
        return

    if data == "adm_admins_menu":
        rows = [
            [color_button("➕ افزودن ادمین", "adm_add_admin", "success")],
            [color_button("📃 لیست ادمین‌ها", "adm_list_admins", "primary")],
            [color_button("🗑 حذف ادمین", "adm_del_admin", "danger")],
            [color_button("🔙 بازگشت", "adm_back", "primary")],
        ]
        await cq.message.edit_text(
            "👤 <b>مدیریت ادمین‌ها:</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await cq.answer(); return

    if data == "adm_add_admin":
        await cq.message.answer("👤 آی‌دی عددی کاربر را بفرستید:")
        await state.set_state(AdminStates.add_admin)
        await cq.answer(); return

    if data == "adm_del_admin":
        adm = all_admins()
        if not adm:
            await cq.message.answer("📭 ادمینی نیست."); await cq.answer(); return
        rows = [[color_button(f"🗑 {a}", f"adm_deladm_{a}", "danger")] for a in adm]
        rows.append([color_button("🔙 بازگشت", "adm_back", "primary")])
        await cq.message.edit_text(
            "🗑 کدام ادمین؟",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await cq.answer(); return

    if data.startswith("adm_deladm_"):
        aid = int(data.replace("adm_deladm_", ""))
        if aid in SUPER_ADMINS:
            await cq.answer("⛔️ سوپر ادمین!", show_alert=True); return
        remove_admin(aid)
        await cq.answer("🗑")
        await cq.message.edit_text("🎛 پنل:", reply_markup=admin_panel_keyboard())
        return

    if data == "adm_list_admins":
        txt = "📃 <b>ادمین‌ها:</b>\n\n👑 <b>سوپر:</b>\n"
        for s in SUPER_ADMINS:
            txt += f"• <code>{s}</code>\n"
        txt += "\n👤 <b>عادی:</b>\n"
        for a in all_admins():
            txt += f"• <code>{a}</code>\n"
        await cq.message.edit_text(txt, reply_markup=adm_back_kb())
        await cq.answer(); return

    if data == "adm_broadcast":
        await cq.message.answer("📢 پیام را بفرستید:")
        await state.set_state(AdminStates.broadcast)
        await cq.answer(); return

    if data == "adm_block_menu":
        rows = [
            [color_button("🚫 بلاک کاربر", "adm_block_user", "danger")],
            [color_button("✅ آنبلاک کاربر", "adm_unblock_user", "success")],
            [color_button("📋 لیست بلاک‌شده‌ها", "adm_blocked_list", "primary")],
            [color_button("🔙 بازگشت", "adm_back", "primary")],
        ]
        await cq.message.edit_text(
            "🚫 <b>مدیریت بلاک:</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await cq.answer(); return

    if data == "adm_block_user":
        await cq.message.answer("🚫 آی‌دی عددی کاربر برای بلاک:")
        await state.set_state(AdminStates.block_user)
        await cq.answer(); return

    if data == "adm_unblock_user":
        await cq.message.answer("✅ آی‌دی عددی کاربر برای آنبلاک:")
        await state.set_state(AdminStates.unblock_user)
        await cq.answer(); return

    if data == "adm_blocked_list":
        cur = conn.execute("SELECT telegram_user_id FROM users WHERE is_blocked = 1")
        rows_data = cur.fetchall()
        if not rows_data:
            await cq.message.answer("📭 لیست خالی."); await cq.answer(); return
        txt = "🚫 <b>بلاک‌شده‌ها:</b>\n"
        for r in rows_data:
            txt += f"• <code>{r[0]}</code>\n"
        await cq.message.edit_text(txt, reply_markup=adm_back_kb())
        await cq.answer(); return

    if data == "adm_points_menu":
        rows = [
            [color_button("➕ افزودن امتیاز", "adm_add_points", "success")],
            [color_button("➖ کاهش امتیاز", "adm_remove_points", "danger")],
            [color_button("🔙 بازگشت", "adm_back", "primary")],
        ]
        await cq.message.edit_text(
            "💰 <b>مدیریت امتیاز:</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await cq.answer(); return

    if data == "adm_add_points":
        await cq.message.answer("فرمت: <code>user_id amount</code>\nمثال: <code>123456789 100</code>")
        await state.set_state(AdminStates.add_points)
        await cq.answer(); return

    if data == "adm_remove_points":
        await cq.message.answer("فرمت: <code>user_id amount</code>")
        await state.set_state(AdminStates.remove_points)
        await cq.answer(); return

    if data == "adm_coupons_menu":
        rows = [
            [color_button("➕ کد جدید", "adm_new_coupon", "success")],
            [color_button("📋 لیست کدها", "adm_list_coupons", "primary")],
            [color_button("🔙 بازگشت", "adm_back", "primary")],
        ]
        await cq.message.edit_text(
            "🎟 <b>کد تخفیف:</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await cq.answer(); return

    if data == "adm_new_coupon":
        await cq.message.answer("🎟 کد را بفرستید (مثلاً <code>WELCOME50</code>):")
        await state.set_state(AdminStates.new_coupon_code)
        await cq.answer(); return

    if data == "adm_list_coupons":
        cps = all_coupons()
        if not cps:
            await cq.message.answer("📭 خالی."); await cq.answer(); return
        txt = "🎟 <b>کدها:</b>\n\n"
        for c in cps:
            txt += f"• <code>{c['code']}</code> | {c['amount']} | {c['used']}/{c['max_uses']}\n"
        await cq.message.edit_text(txt, reply_markup=adm_back_kb())
        await cq.answer(); return

    if data == "adm_send_to_user":
        await cq.message.answer("📨 فرمت: <code>user_id پیام</code>")
        await state.set_state(AdminStates.send_to_user)
        await cq.answer(); return

    if data == "adm_find_user":
        await cq.message.answer("🔍 آی‌دی عددی کاربر:")
        await state.set_state(AdminStates.find_user)
        await cq.answer(); return

    if data == "adm_logs":
        cur = conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 20")
        rows_data = cur.fetchall()
        if not rows_data:
            await cq.message.answer("📭 لاگی نیست."); await cq.answer(); return
        txt = "📜 <b>آخرین ۲۰ لاگ:</b>\n\n"
        for r in rows_data:
            txt += f"• {r[1]} | {r[2]} | {r[4][:16]}\n"
        await cq.message.edit_text(txt, reply_markup=adm_back_kb())
        await cq.answer(); return

    if data == "adm_backup":
        path = make_backup()
        await cq.message.answer(f"💾 بکاپ ساخته شد:\n<code>{path}</code>")
        await cq.answer("✅"); return

    if data == "adm_download_db":
        try:
            doc = FSInputFile(DB_FILE, filename="users.db")
            await cq.message.answer_document(doc, caption="📥 دیتابیس")
        except Exception as e:
            await cq.message.answer(f"❌ {e}")
        await cq.answer(); return

    if data == "adm_reset_confirm":
        rows = [
            [color_button("⚠️ بله، مطمئنم", "adm_reset_do", "danger")],
            [color_button("🔙 انصراف", "adm_back", "primary")],
        ]
        await cq.message.edit_text(
            "⚠️ <b>هشدار!</b>\nهمه تنظیمات به حالت پیش‌فرض برمی‌گردد.\nمطمئنید؟",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await cq.answer(); return

    if data == "adm_reset_do":
        set_setting("maintenance", "0")
        set_setting("force_join", "0")
        conn.execute("DELETE FROM custom_buttons")
        conn.execute("DELETE FROM force_channels")
        conn.commit()
        await cq.message.edit_text("✅ ریست شد.", reply_markup=admin_panel_keyboard())
        await cq.answer(); return

    if data == "adm_back":
        try:
            await cq.message.edit_text("🎛 <b>پنل ادمین پچ پچ</b>",
                                       reply_markup=admin_panel_keyboard())
        except Exception:
            await cq.message.answer("🎛 <b>پنل ادمین پچ پچ</b>",
                                    reply_markup=admin_panel_keyboard())
        await cq.answer(); return

    if data == "adm_close":
        try:
            await cq.message.delete()
        except Exception:
            pass
        await cq.answer("بسته شد"); return

    await cq.answer()


# ============================================================
#                    Callback استایل
# ============================================================

async def handle_style_callback(cq: CallbackQuery, state: FSMContext, data: str):
    if data.startswith("style_edit_"):
        key = data.replace("style_edit_", "")
        rows = [
            [color_button("🔵 آبی", f"style_set_{key}_primary", "primary")],
            [color_button("🟢 سبز", f"style_set_{key}_success", "success")],
            [color_button("🔴 قرمز", f"style_set_{key}_danger", "danger")],
            [color_button("🔙 انصراف", "adm_button_styles", "primary")],
        ]
        await cq.message.edit_text(
            f"🎨 رنگ جدید برای <code>{key}</code>:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await cq.answer(); return

    if data.startswith("style_set_"):
        rest = data.replace("style_set_", "")
        for st in ("primary", "success", "danger"):
            if rest.endswith("_" + st):
                key = rest[: -(len(st) + 1)]
                set_btn_style(key, st)
                await cq.answer(f"✅ {st}")
                await cq.message.edit_text("🎨 رنگ ذخیره شد.", reply_markup=adm_back_kb())
                return
        await cq.answer(); return

    if data.startswith("style_new_"):
        st = data.replace("style_new_", "")
        d = await state.get_data()
        txt = d.get("btn_text")
        rep = d.get("btn_reply")
        await state.clear()
        if txt and rep:
            add_custom_button(txt, rep, st)
            await cq.message.edit_text(
                f"✅ دکمه <b>{txt}</b> با رنگ <code>{st}</code> ساخته شد.",
                reply_markup=adm_back_kb(),
            )
        await cq.answer("✅"); return

    await cq.answer()


# ============================================================
#                    FSM Handlers
# ============================================================

@dp.message(ProfileStates.waiting_name)
async def st_edit_name(message: Message, state: FSMContext):
    await state.clear()
    name = (message.text or "").strip()
    if len(name) < 2 or len(name) > 32:
        await message.answer("❌ نام باید بین ۲ تا ۳۲ کاراکتر باشد.")
        return
    conn.execute("UPDATE users SET display_name = ? WHERE telegram_user_id = ?",
                 (name, str(message.from_user.id)))
    conn.commit()
    await message.answer(f"✅ نام شما به <b>{name}</b> تغییر کرد.",
                         reply_markup=main_reply_keyboard())


@dp.message(AdminStates.broadcast)
async def st_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    users = db_all_users()
    s = f = 0
    status = await message.answer(f"⏳ ارسال به {len(users)} کاربر...")
    for u in users:
        try:
            await bot.copy_message(
                chat_id=int(u["telegram_user_id"]),
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            s += 1
        except Exception:
            f += 1
        await asyncio.sleep(0.05)
    await status.edit_text(f"✅ انجام شد\n✔️ {s}\n❌ {f}")


@dp.message(AdminStates.add_admin)
async def st_add_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    try:
        nid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ نامعتبر."); return
    if not db_get_user_by_tg(nid):
        await message.answer("❌ کاربر ثبت نشده."); return
    add_admin(nid, message.from_user.id)
    await message.answer(f"✅ <code>{nid}</code> ادمین شد.")


@dp.message(AdminStates.add_channel)
async def st_add_channel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    try:
        cid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ نامعتبر."); return
    try:
        ch = await bot.get_chat(cid)
        title = ch.title or str(cid)
        try:
            inv = await bot.create_chat_invite_link(cid)
            link = inv.invite_link
        except Exception:
            link = ch.invite_link or (f"https://t.me/{ch.username}" if ch.username else "")
        add_force_channel(str(cid), title, link)
        await message.answer(f"✅ <b>{title}</b> اضافه شد.")
    except Exception as e:
        await message.answer(f"❌ {e}")


@dp.message(AdminStates.edit_text_value)
async def st_edit_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    d = await state.get_data()
    key = d.get("edit_key")
    await state.clear()
    if not key:
        return
    set_setting(key, message.text)
    await message.answer(f"✅ <code>{key}</code> ذخیره شد.")


@dp.message(AdminStates.new_button_text)
async def st_new_btn_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(btn_text=message.text)
    await message.answer("2️⃣ متن پاسخ:")
    await state.set_state(AdminStates.new_button_reply)


@dp.message(AdminStates.new_button_reply)
async def st_new_btn_reply(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(btn_reply=message.text)
    rows = [
        [color_button("🔵 آبی", "style_new_primary", "primary")],
        [color_button("🟢 سبز", "style_new_success", "success")],
        [color_button("🔴 قرمز", "style_new_danger", "danger")],
    ]
    await message.answer("3️⃣ رنگ دکمه:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@dp.message(AdminStates.block_user)
async def st_block(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    try:
        uid = int(message.text.strip())
    except ValueError:
        return
    db_set_blocked(uid, True)
    await message.answer(f"🚫 <code>{uid}</code> بلاک شد.")


@dp.message(AdminStates.unblock_user)
async def st_unblock(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    try:
        uid = int(message.text.strip())
    except ValueError:
        return
    db_set_blocked(uid, False)
    await message.answer(f"✅ <code>{uid}</code> آنبلاک شد.")


@dp.message(AdminStates.add_points)
async def st_add_points(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    try:
        uid, amt = message.text.split()
        db_add_points(int(uid), int(amt))
        await message.answer(f"✅ {amt} امتیاز به {uid} اضافه شد.")
    except Exception:
        await message.answer("❌ فرمت نامعتبر.")


@dp.message(AdminStates.remove_points)
async def st_rm_points(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    try:
        uid, amt = message.text.split()
        db_add_points(int(uid), -int(amt))
        await message.answer(f"✅ {amt} امتیاز از {uid} کم شد.")
    except Exception:
        await message.answer("❌ فرمت نامعتبر.")


@dp.message(AdminStates.new_coupon_code)
async def st_coupon_code(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(coupon_code=message.text.strip())
    await message.answer("💰 مقدار امتیاز:")
    await state.set_state(AdminStates.new_coupon_amount)


@dp.message(AdminStates.new_coupon_amount)
async def st_coupon_amount(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        amt = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد نامعتبر."); return
    await state.update_data(coupon_amount=amt)
    await message.answer("👥 حداکثر تعداد استفاده:")
    await state.set_state(AdminStates.new_coupon_uses)


@dp.message(AdminStates.new_coupon_uses)
async def st_coupon_uses(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        uses = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد نامعتبر."); return
    d = await state.get_data()
    await state.clear()
    add_coupon(d["coupon_code"], d["coupon_amount"], uses)
    await message.answer(
        f"✅ کد ساخته شد:\n<code>{d['coupon_code']}</code>\n"
        f"💰 {d['coupon_amount']} امتیاز | 👥 {uses} بار"
    )


@dp.message(AdminStates.send_to_user)
async def st_send_to_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ فرمت: user_id پیام"); return
    try:
        uid = int(parts[0])
    except ValueError:
        await message.answer("❌ آی‌دی نامعتبر."); return
    try:
        await bot.send_message(uid, f"📨 <b>پیام از ادمین:</b>\n\n{parts[1]}")
        await message.answer("✅ ارسال شد.")
    except Exception as e:
        await message.answer(f"❌ {e}")


@dp.message(AdminStates.find_user)
async def st_find_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    try:
        uid = int(message.text.strip())
    except ValueError:
        return
    u = db_get_user_by_tg(uid)
    if not u:
        await message.answer("❌ پیدا نشد."); return
    txt = (
        f"👤 <b>اطلاعات کاربر</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🆔 عددی: <code>{u['telegram_user_id']}</code>\n"
        f"📛 نام نمایشی: <b>{u.get('display_name') or '—'}</b>\n"
        f"🔑 کلید: <code>{u['rkey']}</code>\n"
        f"🎁 امتیاز: <b>{u['points']}</b>\n"
        f"💬 پیام‌ها: <b>{u['message_count']}</b>\n"
        f"📅 عضویت: {u['joined_at'][:10] if u['joined_at'] else '-'}\n"
        f"🕐 آخرین فعالیت: {u['last_seen'][:16] if u['last_seen'] else '-'}\n"
        f"🚫 بلاک: {'✅' if u['is_blocked'] else '❌'}"
    )
    await message.answer(txt)


# ============================================================
#                    اجرا
# ============================================================

async def main():
    me = await bot.get_me()
    log.info("🤖 %s (@%s) راه‌اندازی شد", BOT_NAME, me.username)
    await bot.delete_webhook(drop_pending_updates=False)
    await set_bot_commands()
    log.info("✅ منوی دستورات تنظیم شد")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 متوقف شد.")
