#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PachPach Replica — ربات چت ناشناس (بازسازی از صفر بر اساس رفتار ظاهری @MeloGap)
============================================================================
Original bot: @MeloGap — anonymous chat / MeloGap
This is a from-scratch replica built only from publicly observed behaviour.
It does NOT contain the original bot's source code, database or tokens.

Stack: python-telegram-bot >= 21 (asyncio) + SQLite (stdlib sqlite3)

REFERRAL INCONSISTENCY (observed in the original, documented here on purpose):
  * /link banner in the original advertises one reward figure, while /help_credit
    and the onboarding flow credit a different split. This replica implements the
    split that was actually observed in the live flow:
      - inviter gets +20 coins as soon as the invited user enters via the link
      - inviter gets +10 MORE coins when the invitee completes their profile
      - total = 30 coins per completed referral.

EXEMPT PRICE DISCREPANCY (observed, see constants below):
  * /Exempt system text advertises 15,000 Toman, but the payment link it
    generated charged 55,000 Toman. Both numbers are kept as separate
    constants so the discrepancy stays visible and configurable.

PREMIUM EMOJI / COLOURED BUTTONS:
  * All inline buttons use Bot API `style` ("success" = green by default,
    "primary" = blue, "danger" = red) — matching the original's §11 look.
  * Premium (custom) emoji on buttons: Bot API supports
    `icon_custom_emoji_id` on InlineKeyboardButton. Telegram Web does NOT
    expose the original bot's custom emoji IDs, so PREMIUM_EMOJI below is
    EMPTY by default (placeholders). Fill in your own custom emoji IDs and
    the helpers gbtn()/pbtn()/dbtn() will attach them automatically.
"""

import os
import re
import time
import random
import string
import sqlite3
import logging
import math
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    BotCommand,
    LabeledPrice,
)
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters,
)

# ============================================================================
# CONFIG
# ============================================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8654406992:AAECfMfmYjc9_W8sFG-yNR78kASBh7CRMTs")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "PachPach")
ADMIN_IDS = {
    int(x) for x in os.environ.get("ADMIN_IDS", "8094551428").replace(",", " ").split() if x.strip().isdigit()
}
REQUIRED_CHANNELS = [
    c.strip() for c in os.environ.get("REQUIRED_CHANNELS", "@Dosti,@MeloGapM").split(",") if c.strip()
]
# STUB payment gateway — do NOT put the original bot's real gateway link here.
PAYMENT_GATEWAY_URL = os.environ.get("PAYMENT_GATEWAY_URL", "https://example.com/payment-gateway-placeholder")
SUPPORT_USERNAME = "@pachpachSupport"
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db"))

# /Exempt — observed discrepancy (see module docstring):
EXEMPT_PRICE_DISPLAY = 15000   # advertised in the /Exempt system text (Toman)
EXEMPT_PRICE_CHARGE = 55000    # actually charged by the generated payment link (Toman)
EXEMPT_DURATION_DAYS = 365     # 1 year
EXEMPT_BONUS_COINS = 20

DELETED_ACCOUNT_PRICE = 30000  # Toman, /deleted_account (stub payment)

# Coin costs (observed)
COST_DIRECT_MESSAGE = 1
COST_CHAT_REQUEST = 2          # charged only when the request is ACCEPTED
COST_SEARCH_GIRL = 2
COST_SEARCH_BOY = 2
COST_NOTIFY_ONLINE = 1
COST_NOTIFY_CHATEND = 1
PROFILE_COMPLETE_BONUS = 5
REFERRAL_ON_ENTRY = 20
REFERRAL_ON_COMPLETE = 10      # total 30
NOTIFY_EXPIRY_DAYS = 10

# Telegram Stars packages: (coins, stars_price, label)
STARS_PACKAGES = [
    (320, 120, "💰 320 سکه — ⭐️ 120 استار"),
    (540, 190, "💰 540 سکه — ⭐️ 190 استار"),
    (1500, 280, "💰 1500 سکه — ⭐️ 280 استار"),
    (2800, 400, "💰 2800 سکه — ⭐️ 400 استار"),
    (6800, 750, "👑 6800 سکه VIP — ⭐️ 750 استار"),
]

# Premium (custom) emoji IDs for buttons — EMPTY placeholders on purpose.
# Telegram Web does not expose the original IDs. Put YOUR bot's custom emoji
# ids here, keyed by any name, and pass emoji="key" to gbtn/pbtn/dbtn,
# e.g. PREMIUM_EMOJI = {"coin": "5368324170671202286", ...}
PREMIUM_EMOJI = {
    # "coin": "",
    # "profile": "",
    # "chat": "",
}

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO)
log = logging.getLogger("pachpach-replica")

# ============================================================================
# BUTTON HELPERS — coloured buttons + optional premium emoji icon
# ============================================================================
def _btn(text, callback_data=None, url=None, style="success", emoji=None):
    kwargs = {"text": text}
    if callback_data:
        kwargs["callback_data"] = callback_data
    if url:
        kwargs["url"] = url
    emoji_id = PREMIUM_EMOJI.get(emoji) if emoji else None
    try:
        if emoji_id:
            kwargs["icon_custom_emoji_id"] = str(emoji_id)
        return InlineKeyboardButton(style=style, **kwargs)
    except TypeError:
        # Older PTB / Bot API without style or icon support — degrade gracefully.
        kwargs.pop("icon_custom_emoji_id", None)
        try:
            return InlineKeyboardButton(**kwargs)
        except TypeError:
            return InlineKeyboardButton(text=text, callback_data=callback_data, url=url)

def gbtn(text, callback_data=None, url=None, emoji=None):
    """Green (success) button — the original bot's default."""
    return _btn(text, callback_data, url, style="success", emoji=emoji)

def pbtn(text, callback_data=None, url=None, emoji=None):
    """Blue (primary) button."""
    return _btn(text, callback_data, url, style="primary", emoji=emoji)

def dbtn(text, callback_data=None, url=None, emoji=None):
    """Red (danger) button."""
    return _btn(text, callback_data, url, style="danger", emoji=emoji)

def kbtn(text, style=None, request_location=False):
    """Reply KeyboardButton with optional Bot API style."""
    try:
        if style:
            return KeyboardButton(text, style=style, request_location=request_location)
        return KeyboardButton(text, request_location=request_location)
    except TypeError:
        return KeyboardButton(text, request_location=request_location)

# ============================================================================
# GEOGRAPHY — provinces & cities
# ============================================================================
PROVINCES = [
    "آذربایجان شرقی", "آذربایجان غربی", "اردبیل", "اصفهان", "البرز", "ایلام",
    "بوشهر", "تهران", "چهارمحال و بختیاری", "خراسان جنوبی", "خراسان رضوی",
    "خراسان شمالی", "خوزستان", "زنجان", "سمنان", "سیستان و بلوچستان", "فارس",
    "قزوین", "قم", "کردستان", "کرمان", "کرمانشاه", "کهگیلویه و بویراحمد",
    "گلستان", "گیلان", "لرستان", "مازندران", "مرکزی", "هرمزگان", "همدان", "یزد",
]

# Full Tehran city list (as observed in the original bot's city keyboard)
TEHRAN_CITIES = [
    "تهران", "ری", "شمیرانات", "اسلامشهر", "پاکدشت", "پردیس", "پیشوا",
    "دماوند", "رباط کریم", "قرچک", "ملارد", "ورامین", "فیروزکوه", "قدس",
    "بهارستان", "شهریار", "اندیشه", "باقرشهر", "حسن آباد", "کهریزک",
    "لواسان", "فشم", "آبسرد", "رودهن", "بومهن", "جاجرود",
]

# Reasonable city lists for other provinces (capital + major cities).
# NOTE (README): only the Tehran list was fully observed live; the rest are
# a generic fallback list so the flow works for every province.
CITIES = {
    "تهران": TEHRAN_CITIES,
    "آذربایجان شرقی": ["تبریز", "مراغه", "مرند", "اهر", "میانه", "بناب", "شبستر", "سراب"],
    "آذربایجان غربی": ["ارومیه", "خوی", "مهاباد", "بوکان", "میاندوآب", "سلماس", "پیرانشهر", "نقده"],
    "اردبیل": ["اردبیل", "پارس آباد", "مشگین شهر", "خلخال", "گرمی", "بیله سوار"],
    "اصفهان": ["اصفهان", "کاشان", "خمینی شهر", "نجف آباد", "شاهین شهر", "شهرضا", "فولادشهر", "مبارکه"],
    "البرز": ["کرج", "فردیس", "کمال شهر", "نظرآباد", "محمدشهر", "ماهدشت", "مشکین دشت", "هشتگرد"],
    "ایلام": ["ایلام", "دهلران", "ایوان", "آبدانان", "دره شهر", "مهران"],
    "بوشهر": ["بوشهر", "برازجان", "گناوه", "خورموج", "کنگان", "عسلویه", "جم", "دیلم"],
    "چهارمحال و بختیاری": ["شهرکرد", "بروجن", "لردگان", "فرخ شهر", "فارسان", "اردل"],
    "خراسان جنوبی": ["بیرجند", "قائن", "طبس", "فردوس", "نهبندان", "سرایان"],
    "خراسان رضوی": ["مشهد", "نیشابور", "سبزوار", "تربت حیدریه", "قوچان", "کاشمر", "تربت جام", "چناران"],
    "خراسان شمالی": ["بجنورد", "شیروان", "اسفراین", "آشخانه", "جاجرم", "فاروج"],
    "خوزستان": ["اهواز", "دزفول", "آبادان", "خرمشهر", "اندیمشک", "ماهشهر", "مسجدسلیمان", "ایذه", "شوشتر", "بهبهان"],
    "زنجان": ["زنجان", "ابهر", "خرمدره", "قیدار", "هیدج", "صائین قلعه"],
    "سمنان": ["سمنان", "شاهرود", "دامغان", "گرمسار", "مهدی شهر", "سرخه"],
    "سیستان و بلوچستان": ["زاهدان", "زابل", "ایرانشهر", "چابهار", "سراوان", "خاش", "کنارک", "نیک شهر"],
    "فارس": ["شیراز", "مرودشت", "جهرم", "فسا", "کازرون", "داراب", "لار", "آباده", "اقلید", "نی ریز"],
    "قزوین": ["قزوین", "تاکستان", "الوند", "آبیک", "اقبالیه", "محمدیه", "بوئین زهرا"],
    "قم": ["قم", "قنوات", "جعفریه", "پردیسان", "کهک", "سلفچگان"],
    "کردستان": ["سنندج", "سقز", "مریوان", "بانه", "قروه", "کامیاران", "بیجار", "دیواندره"],
    "کرمان": ["کرمان", "سیرجان", "رفسنجان", "جیرفت", "بم", "زرند", "کهنوج", "بردسیر"],
    "کرمانشاه": ["کرمانشاه", "اسلام آباد غرب", "جوانرود", "کنگاور", "سنقر", "هرسین", "سرپل ذهاب", "پاوه"],
    "کهگیلویه و بویراحمد": ["یاسوج", "دوگنبدان", "دهدشت", "سی سخت", "چرام", "لنده"],
    "گلستان": ["گرگان", "گنبد کاووس", "علی آباد کتول", "بندرترکمن", "آق قلا", "کردکوی", "کلاله", "مینودشت"],
    "گیلان": ["رشت", "بندر انزلی", "لاهیجان", "لنگرود", "تالش", "آستارا", "صومعه سرا", "رودسر"],
    "لرستان": ["خرم آباد", "بروجرد", "دورود", "الیگودرز", "کوهدشت", "ازنا", "الشتر", "نورآباد"],
    "مازندران": ["ساری", "بابل", "آمل", "قائم شهر", "بهشهر", "چالوس", "نکا", "بابلسر", "تنکابن", "نور"],
    "مرکزی": ["اراک", "ساوه", "خمین", "محلات", "دلیجان", "تفرش", "آشتیان", "شازند"],
    "هرمزگان": ["بندرعباس", "میناب", "دهبارز", "بندر لنگه", "کیش", "قشم", "جاسک", "حاجی آباد"],
    "همدان": ["همدان", "ملایر", "نهاوند", "اسدآباد", "تویسرکان", "بهار", "کبودرآهنگ", "رزن"],
    "یزد": ["یزد", "میبد", "اردکان", "بافق", "مهریز", "ابرکوه", "اشکذر", "تفت"],
}

def cities_for(province):
    return CITIES.get(province, ["مرکز استان", "سایر شهرها"])

# ============================================================================
# TEXTS — onboarding / menus / gate (§1–§3 of the exploration report)
# ============================================================================
WELCOME_NEW = (
    "سلام {name} عزیز 👋\n"
    "به 《پچ پچ 》 خوش اومدی ، توی این ربات می تونی افراد #نزدیک ات رو پیدا کنی و باهاشون آشنا شی و یا به یه نفر بصورت #ناشناس وصل شی و باهاش #چت کنی ❗\n"
    "- استفاده از این ربات رایگانه و اطلاعات تلگرام شما مثل اسم،عکس پروفایل یا موقعیت GPS کاملا محرمانه هست 😎\n"
    "برای شروع جنسیتت رو انتخاب کن 👇"
)
GENDER_ASK = "❓ لطفا جنسیت خود را انتخاب کنید 👇"
PROFILE_INTRO_MSG = "راستی میدونستی توی 《پچ پچ🤖》 یه پروفایل داری؟ برای دیدن پروفایل خودت گزینه 《👤پروفایل》 رو از منو انتخاب کن 👇💥 با تکمیل کردن اطلاعات پروفایلت 💰5 تا سکه رایگان بگیر 😍"
ASK_AGE = "• سنت رو از لیست پایین 👇 انتخاب کن یا خودت تایپ کن"
ASK_PROVINCE = "🏘 استان خود را انتخاب کنید👇"
ASK_CITY = "🏘 شهر خود را انتخاب کنید 👇"
PROFILE_DONE = (
    "آفرین! پروفایلت کامل شد ✅🎉\n"
    "🎁 هدیه تکمیل پروفایل: +{bonus} سکه به حسابت اضافه شد!\n"
    "💰 موجودی سکه تو: {coins} سکه\n\n"
    "حالا می‌تونی از منوی پایین استفاده کنی 👇"
)
START_AGAIN = (
    "خب ، حالا چه کاری برات انجام بدم؟ کانال رسمی پچ پچ 🤖 (اخبار،آپدیت ها و ترفند ها) https://t.me/+UycPasVQbLa10sEC از منوی پایین 👇 انتخاب کن"
)
GATE_TEXT = (
    "⚠️ برای استفاده از ربات، اول باید عضو کانال‌های زیر بشی:\n\n"
    "📢 کانال اول: @Dosti\n"
    "📢 کانال دوم: @MeloGapM\n\n"
    "بعد از عضویت، روی دکمه «♻️ بررسی عضویت و فعال سازی ♻️» بزن تا حسابت فعال بشه 👇"
)
GATE_ALERT = "❌ هنوز عضو همه کانال‌ها نشدی! اول عضو شو و بعد دوباره روی دکمه بررسی بزن."
GATE_OK = "✅ عضویتت تایید شد! حسابت فعال شد، خوش اومدی 🎉"
MAIN_CONNECT = "به یه ناشناس وصلم کن!"
MAIN_SEARCH = "🗨 جستجو کاربران 🗨"
MAIN_NEARBY = "📍 افراد نزدیک"
MAIN_CREDIT = "💰 سکه"
MAIN_PROFILE = "👤 پروفایل"
MAIN_HELP = "🤔 راهنما"
MAIN_REFERRAL = "🔗 معرفی به دوستان (سکه رایگان)"
MAIN_MYLINK = "🎉 لینک ناشناس من"
BACK_TEXT = "🔙 بازگشت"

def main_menu_kb():
    """Main reply keyboard — exact layout of report §2."""
    rows = [
        [kbtn(MAIN_CONNECT, style="success")],
        [kbtn(MAIN_SEARCH), kbtn(MAIN_NEARBY)],
        [kbtn(MAIN_CREDIT), kbtn(MAIN_PROFILE), kbtn(MAIN_HELP)],
        [kbtn(MAIN_REFERRAL)],
        [kbtn(MAIN_MYLINK, style="primary")],
    ]
    try:
        return ReplyKeyboardMarkup(rows, resize_keyboard=True)
    except TypeError:
        plain = [[KeyboardButton(b.text) for b in row] for row in rows]
        return ReplyKeyboardMarkup(plain, resize_keyboard=True)

def age_kb():
    rows, row = [], []
    for a in range(9, 100):
        row.append(KeyboardButton(str(a)))
        if len(row) == 6:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([KeyboardButton(BACK_TEXT)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def province_kb():
    rows, row = [], []
    for p in PROVINCES:
        row.append(KeyboardButton(p))
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([KeyboardButton(BACK_TEXT)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def city_kb(province):
    rows, row = [], []
    for c in cities_for(province):
        row.append(KeyboardButton(c))
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([KeyboardButton(BACK_TEXT)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def gender_kb():
    return InlineKeyboardMarkup([[
        gbtn("من دخترم", "ob:gender:female"),
        gbtn("من پسرم 👦", "ob:gender:male"),
    ]])

# ============================================================================
# TEXTS — /Exempt, /credit, /link, /deleted_account (§4, §7, §9)
# ============================================================================
EXEMPT_TEXT = (
    "🚸 معافیت از عضویت اجباری (Exempt)\n\n"
    f"با خرید اشتراک معافیت به مبلغ {EXEMPT_PRICE_DISPLAY:,} تومان، به مدت ۱ سال "
    "از عضویت اجباری در کانال‌های ربات معاف می‌شی و لازم نیست عضو کانال‌ها بمونی.\n"
    f"🎁 همراه این اشتراک، +{EXEMPT_BONUS_COINS} سکه هم هدیه می‌گیری!\n\n"
    "برای خرید روی دکمه پرداخت بزن 👇"
)
EXEMPT_PAY_NOTES = (
    "📝 نکات پرداخت:\n\n"
    "• بعد از زدن دکمه «ورود به درگاه پرداخت» به صفحه پرداخت هدایت می‌شی.\n"
    "• پرداخت رو با یک کارت بانکی به نام خودت انجام بده.\n"
    "• بعد از پرداخت موفق، معافیت به صورت خودکار روی حسابت فعال می‌شه.\n"
    "• اگه مشکلی پیش اومد، به پشتیبانی پیام بده: " + SUPPORT_USERNAME + "\n\n"
    "⚠️ توجه: تکمیل فراید پرداخت رو با دقت انجام بده."  # original typo «فراید» preserved
)
CREDIT_TEXT = (
    "💰 سکه‌های من\n\n"
    "💎 موجودی فعلی تو: {coins} سکه\n\n"
    "سکه برای چت با جنس مخالف، پیام دایرکت، درخواست چت و فعال‌سازی اطلاع‌رسانی‌ها استفاده می‌شه.\n"
    "می‌تونی با معرفی ربات به دوستات سکه رایگان بگیری، یا با استارز تلگرام سکه بخری 👇"
)
LINK_TEXT = (
    "🎉 لینک ناشناس تو آماده‌ست!\n\n"
    "این لینک رو برای دوستات بفرست؛ هر کسی با لینک تو وارد ربات بشه و پروفایلش رو کامل کنه، "
    "تو سکه رایگان می‌گیری! 💰\n\n"
    "🔗 لینک اختصاصی تو:\n{link}\n\n"
    "📨 لینک پیام ناشناس تو:\n{link}"
)
LINK_FOLLOWUP = "👥 تا الان {count} نفر با لینک تو وارد ربات شدن."
DELETED_ACCOUNT_TEXT = (
    "❌ حذف حساب کاربری\n\n"
    "حذف کامل حساب کاربری و همه اطلاعاتت از ربات، "
    f"{DELETED_ACCOUNT_PRICE:,} تومان هزینه داره.\n"
    "بعد از حذف، پروفایل، سکه‌ها، مخاطبین و چت‌هات به طور کامل پاک می‌شن و قابل برگشت نیستن!\n\n"
    "اگه مطمئنی، روی دکمه پرداخت بزن 👇"
)

# ============================================================================
# HELP TEXTS (§6) — close paraphrase of the originals, facts/costs preserved
# ============================================================================
HELP_INDEX = (
    "🤔 راهنمای ربات پچ پچ\n\n"
    "برای دیدن راهنمای هر بخش، روی دستور مربوطه بزن:\n\n"
    "/help_chat — راهنمای چت ناشناس\n"
    "/help_credit — راهنمای سکه و خرید سکه\n"
    "/help_gps — راهنمای ثبت موقعیت (GPS)\n"
    "/help_profile — راهنمای پروفایل\n"
    "/help_pchat — راهنمای درخواست چت\n"
    "/help_direct — راهنمای پیام دایرکت\n"
    "/help_shortcuts — میانبرها و دستورات درون چت\n"
    "/help_terms — قوانین و شرایط استفاده\n"
    "/help_onw — اطلاع از آنلاین شدن کاربر\n"
    "/help_chw — اطلاع از پایان چت کاربر\n"
    "/help_contacts — راهنمای مخاطبین\n"
    "/help_deleteMessage — حذف پیام‌ها در چت (deletall)\n"
    "/help_search — راهنمای جستجوی کاربران\n\n"
    "🆘 پشتیبانی: " + SUPPORT_USERNAME
)
HELP_TEXTS = {
    "help_chat": (
        "🗨 راهنمای چت ناشناس\n\n"
        "با دکمه «به یه ناشناس وصلم کن!» می‌تونی به یک کاربر تصادفی وصل بشی:\n"
        "• جستجوی شانسی: رایگان\n"
        "• جستجوی دختر 👩: ۲ سکه\n"
        "• جستجوی پسر 👨: ۲ سکه\n"
        "• جستجوی اطراف: رایگان (نیازمند ثبت GPS)\n"
        "• جستجوی همسن: بر اساس سن خودت\n\n"
        "در حین چت، همه نوع پیام (متن، عکس، ویدیو، ویس، استیکر و...) برای طرف مقابل ارسال می‌شه. "
        "با دکمه پایان چت یا دستور /endchat چت تموم می‌شه."
    ),
    "help_credit": (
        "💰 راهنمای سکه\n\n"
        "سکه واحد پول داخل رباته. کاربردها:\n"
        "• جستجوی دختر/پسر: ۲ سکه\n"
        "• پیام دایرکت: ۱ سکه\n"
        "• درخواست چت (فقط در صورت قبول شدن): ۲ سکه\n"
        "• اطلاع از آنلاین شدن / پایان چت یک کاربر: هرکدام ۱ سکه\n\n"
        "روش‌های گرفتن سکه:\n"
        "• معرفی به دوستان: به ازای هر نفری که با لینک تو بیاد و پروفایلش رو کامل کنه ۳۰ سکه می‌گیری.\n"
        "• تکمیل پروفایل: ۵ سکه هدیه.\n"
        "• خرید با استارز تلگرام از بخش /credit\n"
        "• گزارش صحیح کاربر متخلف: ۵ سکه پاداش."
    ),
    "help_gps": (
        "📍 راهنمای ثبت موقعیت GPS\n\n"
        "از بخش پروفایل 👤 «موقعیت GPS من» رو بزن و بعد «✏️ ثبت موقعیت GPS»؛ "
        "موقعیتت رو از طریق تلگرام ارسال کن تا ثبت بشه.\n"
        "با ثبت GPS می‌تونی از «جستجوی اطراف» و «📍 افراد نزدیک» استفاده کنی و فاصله‌ات با بقیه کاربرا نمایش داده می‌شه. "
        "موقعیت دقیق تو به هیچ کاربری نشون داده نمی‌شه، فقط فاصله تقریبی نمایش داده می‌شه."
    ),
    "help_profile": (
        "👤 راهنمای پروفایل\n\n"
        "با دستور /profile یا دکمه «👤 پروفایل» می‌تونی پروفایلت رو ببینی و ویرایش کنی: "
        "تغییر نام، جنسیت، شهر، سن، GPS و عکس پروفایل.\n"
        "هر کاربر یک آیدی یکتا داره (مثل /user_XXXXX) که بقیه با اون می‌تونن پروفایلت رو ببینن، "
        "بهت درخواست چت یا پیام دایرکت بدن و لایکت کنن ❤️\n"
        "از تنظیمات پیشرفته پروفایل می‌تونی حالت سایلنت، فیلتر درخواست چت و آلارام‌ها رو مدیریت کنی."
    ),
    "help_pchat": (
        "💬 راهنمای درخواست چت\n\n"
        "توی پروفایل هر کاربر دکمه «💬 درخواست چت» هست. وقتی درخواست می‌دی، برای اون کاربر ارسال می‌شه "
        "و اگه قبول کنه، به هم وصل می‌شین.\n"
        "• هزینه: ۲ سکه — فقط وقتی کسر می‌شه که طرف مقابل قبول کنه.\n"
        "• اگه کاربر در حالت سایلنت باشه، درخواستش رد می‌شه.\n"
        "• اگه کاربر بیشتر از ۱۵ دقیقه آفلاین باشه، درخواست ارسال نمی‌شه.\n"
        "• از تنظیمات پیشرفته پروفایل می‌تونی فیلتر درخواست چت رو فعال کنی."
    ),
    "help_direct": (
        "📨 راهنمای پیام دایرکت\n\n"
        "توی پروفایل هر کاربر با دکمه «📨 پیام دایرکت» می‌تونی بدون چت، یک پیام مستقیم براش بفرستی.\n"
        "• حداکثر طول پیام: ۲۰۰ کاراکتر\n"
        "• هزینه: ۱ سکه برای هر پیام\n"
        "• با نوشتن «بیخیال» می‌تونی ارسال رو لغو کنی."
    ),
    "help_shortcuts": (
        "⌨️ میانبرها و دستورات\n\n"
        "/start — شروع و منوی اصلی\n"
        "/link — لینک ناشناس و دعوت من\n"
        "/profile — پروفایل من\n"
        "/contacts — مخاطبین من\n"
        "/silent — حالت سایلنت\n"
        "/credit — سکه‌های من و خرید سکه\n"
        "/id — آیدی من در ربات\n"
        "/Exempt — معافیت از عضویت اجباری\n"
        "/endchat — پایان چت فعلی\n"
        "/deleted_account — حذف حساب کاربری\n"
        "/help — راهنما\n\n"
        "دستورات درون چت: deletall یا «حذف همه» — حذف پیام‌های خودت در چت."
    ),
    "help_terms": (
        "⚖️ قوانین و شرایط استفاده\n\n"
        "• توهین، فحاشی، ارسال محتوای غیراخلاقی و مزاحمت برای کاربران ممنوعه و باعث مسدود شدن حساب می‌شه.\n"
        "• ارسال اطلاعات شخصی دیگران بدون رضایتشون ممنوعه.\n"
        "• در چت ناشناس، هویتت برای طرف مقابل فاش نمی‌شه؛ خودت هم نباید اطلاعات حساست رو به اشتراک بذاری.\n"
        "• گزارش صحیح کاربر متخلف ۵ سکه پاداش داره.\n"
        "• مسئولیت پیام‌هایی که ارسال می‌کنی با خودته.\n\n"
        "🆘 پشتیبانی: " + SUPPORT_USERNAME
    ),
    "help_onw": (
        "🔔 اطلاع از آنلاین شدن کاربر\n\n"
        "توی پروفایل هر کاربر دکمه «🔔 به محض آنلاین شدن به من اطلاع بده» هست.\n"
        "• هزینه فعال‌سازی: ۱ سکه\n"
        "• اعتبار: ۱۰ روز\n"
        "به محض اینکه اون کاربر آنلاین بشه (فعالیتی در ربات داشته باشه)، بهت خبر می‌دیم."
    ),
    "help_chw": (
        "🔔 اطلاع از پایان چت کاربر\n\n"
        "توی پروفایل طرف مقابلِ چتت، می‌تونی فعال کنی که وقتی چتش تموم شد بهت خبر بدیم.\n"
        "• هزینه فعال‌سازی: ۱ سکه\n"
        "• اعتبار: ۱۰ روز"
    ),
    "help_contacts": (
        "👥 راهنمای مخاطبین\n\n"
        "توی پروفایل هر کاربر با دکمه «➕ افزودن به مخاطبین» می‌تونی اون رو به لیست مخاطبینت اضافه کنی "
        "تا بعداً راحت‌تر پیداش کنی.\n"
        "لیست مخاطبینت رو با دستور /contacts یا از بخش پروفایل می‌بینی."
    ),
    "help_deleteMessage": (
        "🗑 حذف پیام‌ها در چت (deletall)\n\n"
        "در حین چت ناشناس، اگه بنویسی deletall یا «حذف همه»، "
        "تا ۱۰۰ پیام آخری که در اون چت فرستادی، از چت طرف مقابل هم حذف می‌شن (در صورت امکان فنی تلگرام)."
    ),
    "help_search": (
        "🗨 راهنمای جستجوی کاربران\n\n"
        "از دکمه «🗨 جستجو کاربران 🗨» می‌تونی کاربرا رو پیدا کنی:\n"
        "• هم استانی‌ها: کاربران استان خودت\n"
        "• هم سن‌ها: کاربران هم‌سن خودت\n"
        "• بدون چت‌ها: کاربرانی که الان در چت نیستن\n"
        "• کاربران جدید: تازه‌واردهای ربات\n"
        "• جستجوی پیشرفته: ترکیب فیلترها\n\n"
        "با «📍 افراد نزدیک» هم کاربرانی که GPS ثبت کردن و نزدیکت هستن رو بر اساس فاصله می‌بینی."
    ),
}

# ============================================================================
# DATABASE (SQLite)
# ============================================================================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        code TEXT UNIQUE,
        first_name TEXT DEFAULT '',
        username TEXT DEFAULT '',
        gender TEXT DEFAULT '',
        age INTEGER DEFAULT 0,
        province TEXT DEFAULT '',
        city TEXT DEFAULT '',
        coins INTEGER DEFAULT 0,
        lat REAL, lon REAL,
        photo_file_id TEXT DEFAULT '',
        is_exempt INTEGER DEFAULT 0,
        exempt_until INTEGER DEFAULT 0,
        silent_mode TEXT DEFAULT 'off',       -- off | 30m | 1h | always
        silent_until INTEGER DEFAULT 0,
        like_enabled INTEGER DEFAULT 1,
        alarm_profile_view INTEGER DEFAULT 0,
        alarm_like INTEGER DEFAULT 0,
        chat_filter INTEGER DEFAULT 0,
        inviter_id INTEGER DEFAULT 0,
        referral_entry_paid INTEGER DEFAULT 0,
        referral_complete_paid INTEGER DEFAULT 0,
        invite_count INTEGER DEFAULT 0,
        profile_complete INTEGER DEFAULT 0,
        last_seen INTEGER DEFAULT 0,
        created_at INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS contacts (
        owner_id INTEGER, target_id INTEGER, created_at INTEGER,
        PRIMARY KEY (owner_id, target_id)
    );
    CREATE TABLE IF NOT EXISTS likes (
        from_id INTEGER, to_id INTEGER, created_at INTEGER,
        PRIMARY KEY (from_id, to_id)
    );
    CREATE TABLE IF NOT EXISTS blocks (
        owner_id INTEGER, target_id INTEGER, created_at INTEGER,
        PRIMARY KEY (owner_id, target_id)
    );
    CREATE TABLE IF NOT EXISTS watches (
        watcher_id INTEGER, target_id INTEGER, kind TEXT,  -- online | chatend
        expires_at INTEGER, created_at INTEGER,
        PRIMARY KEY (watcher_id, target_id, kind)
    );
    CREATE TABLE IF NOT EXISTS relay (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER, partner_id INTEGER,
        partner_msg_id INTEGER, created_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS chats_done (
        user_id INTEGER, partner_id INTEGER, created_at INTEGER
    );
    """)
    conn.commit(); conn.close()

def gen_code(conn):
    chars = string.ascii_letters + string.digits
    while True:
        code = "".join(random.choice(chars) for _ in range(5))
        if not conn.execute("SELECT 1 FROM users WHERE code=?", (code,)).fetchone():
            return code

def get_user(user_id):
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_code(code):
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE code=?", (code,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(user_id, first_name, username, inviter_id=0):
    conn = db()
    code = gen_code(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, code, first_name, username, inviter_id, last_seen, created_at) VALUES (?,?,?,?,?,?,?)",
        (user_id, code, first_name or "", username or "", inviter_id, int(time.time()), int(time.time())),
    )
    conn.commit(); conn.close()
    return get_user(user_id)

def update_user(user_id, **fields):
    if not fields:
        return
    conn = db()
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE users SET {cols} WHERE user_id=?", (*fields.values(), user_id))
    conn.commit(); conn.close()

def add_coins(user_id, amount):
    conn = db()
    conn.execute("UPDATE users SET coins = coins + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    row = conn.execute("SELECT coins FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row["coins"] if row else 0

def touch(user_id):
    update_user(user_id, last_seen=int(time.time()))

def profile_is_complete(u):
    return bool(u and u["gender"] and u["age"] and u["province"] and u["city"])

def distance_km(u1, u2):
    if not u1 or not u2 or u1["lat"] is None or u2["lat"] is None:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, [u1["lat"], u1["lon"], u2["lat"], u2["lon"]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return round(6371 * 2 * math.asin(math.sqrt(a)), 1)

def is_silent(u):
    if not u:
        return False
    if u["silent_mode"] == "always":
        return True
    if u["silent_mode"] in ("30m", "1h") and u["silent_until"] > int(time.time()):
        return True
    return False

def silent_text(u):
    if u["silent_mode"] == "always":
        return "🔕 حالت سایلنت: همیشه فعال"
    if u["silent_mode"] in ("30m", "1h") and u["silent_until"] > int(time.time()):
        left = int((u["silent_until"] - int(time.time())) / 60) + 1
        return f"🔕 حالت سایلنت: فعال (حدود {left} دقیقه باقی مونده)"
    return "🔔 حالت سایلنت: غیرفعال"

# ============================================================================
# RUNTIME STATE — waiting states, search queue, active chats
# Waiting-state pattern: ANY new command or main-menu press cancels the
# pending state of that user (see clear_state calls in the routers).
# ============================================================================
user_state = {}    # user_id -> {"state": str, "data": dict}
search_queue = []  # list of {"user_id": int, "kind": str}
partners = {}      # user_id -> partner user_id (active anonymous chat)

def set_state(user_id, state, **data):
    user_state[user_id] = {"state": state, "data": data}

def clear_state(user_id):
    user_state.pop(user_id, None)

def get_state(user_id):
    return user_state.get(user_id, {}).get("state")

# ============================================================================
# FORCED-JOIN GATE (§3)
# ============================================================================
def is_admin(user_id):
    return user_id in ADMIN_IDS

async def is_member(context, user_id):
    if is_admin(user_id):
        return True
    u = get_user(user_id)
    if u and u["is_exempt"] and (u["exempt_until"] == 0 or u["exempt_until"] > int(time.time())):
        return True
    for ch in REQUIRED_CHANNELS:
        try:
            m = await context.bot.get_chat_member(ch, user_id)
            if m.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR,
                            ChatMemberStatus.OWNER, "member", "administrator", "creator"):
                continue
            return False
        except Exception as e:
            # If the bot cannot check (not admin in channel / dev env), do not
            # hard-block the replica — log and treat as member.
            log.warning("getChatMember failed for %s: %s", ch, e)
            continue
    return True

def gate_kb():
    rows = [[gbtn(f"📢 عضویت در {ch}", url=f"https://t.me/{ch.lstrip('@')}")] for ch in REQUIRED_CHANNELS]
    rows.append([gbtn("♻️ بررسی عضویت و فعال سازی ♻️", "gate:check")])
    return InlineKeyboardMarkup(rows)

GATE_BYPASS_COMMANDS = {"help", "credit", "id", "link", "profile", "silent"}  # observed: these bypass the gate

async def gate_or_pass(update, context, user_id):
    """Returns True if the user may proceed, else sends the gate and returns False."""
    if await is_member(context, user_id):
        return True
    target = update.effective_message
    if target:
        await target.reply_text(GATE_TEXT, reply_markup=gate_kb())
    return False

# ============================================================================
# PROFILE RENDERING (§8)
# ============================================================================
def gender_label(g):
    return "دختر 👩" if g == "female" else ("پسر 👨" if g == "male" else "ثبت نشده")

def profile_text(u, viewer=None):
    dist = distance_km(viewer, u) if viewer else None
    gps_line = f"📍 فاصله: {dist} کیلومتر" if dist is not None else "🏁 موقعیت کاربر ثبت نشده!"
    conn = db()
    likes_count = conn.execute("SELECT COUNT(*) c FROM likes WHERE to_id=?", (u["user_id"],)).fetchone()["c"]
    conn.close()
    return (
        f"👤 پروفایل کاربر\n\n"
        f"📛 نام: {u['first_name']}\n"
        f"⚧ جنسیت: {gender_label(u['gender'])}\n"
        f"🎂 سن: {u['age'] or 'ثبت نشده'}\n"
        f"🗺 استان: {u['province'] or 'ثبت نشده'}\n"
        f"🏙 شهر: {u['city'] or 'ثبت نشده'}\n"
        f"{gps_line}\n"
        f"❤️ لایک‌ها: {likes_count}\n"
        f"🆔 آیدی: /user_{u['code']}\n"
        f"💰 سکه: {u['coins']}"
    )

def my_profile_kb(u):
    like_state = "روشن ✅" if u["like_enabled"] else "خاموش ❌"
    return InlineKeyboardMarkup([
        [gbtn("📍 موقعیت GPS من", "prof:gps")],
        [gbtn("❤️ لایک کننده ها", "prof:likers"), gbtn(f"❤️ لایک: {like_state}", "prof:liketoggle")],
        [gbtn("👥 مخاطبین من", "prof:contacts"), gbtn("🚫 بلاک شده ها", "prof:blocked")],
        [gbtn("⚙️ تنظیمات پیشرفته", "prof:advanced")],
        [gbtn("✏️ ویرایش پروفایل", "prof:edit")],
    ])

def advanced_kb():
    return InlineKeyboardMarkup([
        [gbtn("🔕 حالت سایلنت", "adv:silent"), gbtn("⚖️ فیلتر درخواست چت", "adv:filter")],
        [dbtn("❌ حذف حساب کاربری ❌", "adv:delete")],
        [gbtn("⚙️ تنظیم آلارام ها 🔔", "adv:alarms")],
        [gbtn("🔙 بازگشت به پروفایل", "prof:back")],
    ])

def edit_kb():
    return InlineKeyboardMarkup([
        [gbtn("📛 تغییر نام", "edit:name"), gbtn("⚧ تغییر جنسیت", "edit:gender")],
        [gbtn("🏙 تغییر شهر", "edit:city"), gbtn("🎂 تغییر سن", "edit:age")],
        [gbtn("📍 تغییر GPS", "edit:gps"), gbtn("🖼 تغییر عکس", "edit:photo")],
        [gbtn("🔙 بازگشت به پروفایل", "prof:back")],
    ])

def other_profile_kb(target, in_chat=False):
    rows = [
        [gbtn("💬 درخواست چت", f"u:reqchat:{target['code']}"), gbtn("📨 پیام دایرکت", f"u:direct:{target['code']}")],
        [gbtn("🚫 گزارش کاربر", f"u:report:{target['code']}"), gbtn("بلاک کردن کاربر", f"u:block:{target['code']}")],
        [gbtn("➕ افزودن به مخاطبین", f"u:addcontact:{target['code']}"), gbtn("❤️ لایک", f"u:like:{target['code']}")],
        [gbtn("🔔 به محض آنلاین شدن به من اطلاع بده", f"u:notify_online:{target['code']}")],
    ]
    if in_chat:
        rows.append([gbtn("🔔 وقتی چتش تموم شد به من اطلاع بده", f"u:notify_chatend:{target['code']}")])
    return InlineKeyboardMarkup(rows)


# ============================================================================
# /start + ONBOARDING (§1)
# ============================================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    clear_state(user.id)
    touch_needed = get_user(user.id)
    args = context.args or []
    inviter_id = 0
    pending_code = None
    if args and args[0].startswith("inv_"):
        pending_code = args[0][4:]

    if touch_needed is None:
        # --- new user ---
        inviter = get_user_by_code(pending_code) if pending_code else None
        if inviter and inviter["user_id"] != user.id:
            inviter_id = inviter["user_id"]
        u = create_user(user.id, user.first_name, user.username, inviter_id=inviter_id)
        if inviter_id:
            # Referral: +20 on entry (see docstring for the observed split)
            add_coins(inviter_id, REFERRAL_ON_ENTRY)
            conn = db()
            conn.execute("UPDATE users SET invite_count = invite_count + 1, referral_entry_paid=1 WHERE user_id=?", (inviter_id,))
            conn.commit(); conn.close()
            update_user(user.id, referral_entry_paid=1)
            try:
                await context.bot.send_message(inviter_id, "🎉 یک نفر با لینک دعوت تو وارد ربات شد! +۲۰ سکه گرفتی 💰\nاگه پروفایلش رو کامل کنه، ۱۰ سکه دیگه هم می‌گیری.")
            except Exception:
                pass
        await update.effective_message.reply_text(
            WELCOME_NEW.format(name=user.first_name or "دوست"), reply_markup=gender_kb())
        await update.effective_message.reply_text(PROFILE_INTRO_MSG)
        set_state(user.id, "ob_gender")
        return

    # --- registered user ---
    touch(user.id)
    u = get_user(user.id)
    if not profile_is_complete(u):
        await update.effective_message.reply_text(
            WELCOME_NEW.format(name=user.first_name or "دوست"), reply_markup=gender_kb())
        await update.effective_message.reply_text(PROFILE_INTRO_MSG)
        set_state(user.id, "ob_gender")
        return
    await notify_online_watchers(context, user.id)
    await update.effective_message.reply_text(START_AGAIN, reply_markup=main_menu_kb())

async def finish_profile_if_ready(update, context, user_id):
    u = get_user(user_id)
    if u and profile_is_complete(u) and not u["profile_complete"]:
        coins = add_coins(user_id, PROFILE_COMPLETE_BONUS)
        update_user(user_id, profile_complete=1)
        if u["inviter_id"] and not u["referral_complete_paid"]:
            add_coins(u["inviter_id"], REFERRAL_ON_COMPLETE)
            update_user(user_id, referral_complete_paid=1)
            try:
                await context.bot.send_message(u["inviter_id"], "🎉 کاربری که دعوت کرده بودی پروفایلش رو کامل کرد! +۱۰ سکه دیگه گرفتی 💰 (مجموع دعوت: ۳۰ سکه)")
            except Exception:
                pass
        await update.effective_message.reply_text(
            PROFILE_DONE.format(bonus=PROFILE_COMPLETE_BONUS, coins=coins),
            reply_markup=main_menu_kb())
        return True
    if u and profile_is_complete(u):
        await update.effective_message.reply_text(START_AGAIN, reply_markup=main_menu_kb())
        return True
    return False

async def notify_online_watchers(context, user_id):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM watches WHERE target_id=? AND kind='online' AND expires_at>?",
        (user_id, int(time.time()))).fetchall()
    conn.close()
    if not rows:
        return
    target = get_user(user_id)
    for r in rows:
        try:
            await context.bot.send_message(r["watcher_id"], f"🔔 کاربر /user_{target['code']} آنلاین شد!")
        except Exception:
            pass

# ============================================================================
# SIMPLE COMMANDS — /id /link /credit /silent /contacts /Exempt (§4, §7)
# (these bypass the forced-join gate, as observed)
# ============================================================================
async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    clear_state(user.id)
    u = get_user(user.id) or create_user(user.id, user.first_name, user.username)
    await update.effective_message.reply_text(f"🆔 ایدی شما در ربات:\n/user_{u['code']}")

async def cmd_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    clear_state(user.id)
    u = get_user(user.id) or create_user(user.id, user.first_name, user.username)
    link = f"http://t.me/{BOT_USERNAME}?start=inv_{u['code']}"
    kb = InlineKeyboardMarkup([[gbtn("🚸 معرفی به دوستان ( سکه رایگان)", "credit:referral")]])
    await update.effective_message.reply_text(LINK_TEXT.format(link=link), reply_markup=kb)
    await update.effective_message.reply_text(LINK_FOLLOWUP.format(count=u["invite_count"]))

async def cmd_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    clear_state(user.id)
    u = get_user(user.id) or create_user(user.id, user.first_name, user.username)
    kb = InlineKeyboardMarkup([
        [gbtn("🚸 معرفی به دوستان ( سکه رایگان)", "credit:referral")],
        [gbtn("خرید 💰 سکه با 👈🏿 ⭐️ استار", "credit:stars")],
    ])
    await update.effective_message.reply_text(CREDIT_TEXT.format(coins=u["coins"]), reply_markup=kb)

async def cmd_silent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    clear_state(user.id)
    u = get_user(user.id) or create_user(user.id, user.first_name, user.username)
    kb = InlineKeyboardMarkup([
        [gbtn("🔕 سایلنت ۳۰ دقیقه", "silent:30m"), gbtn("🔕 سایلنت ۱ ساعت", "silent:1h")],
        [gbtn("🔕 سایلنت همیشه", "silent:always"), gbtn("🔔 غیرفعال کردن سایلنت", "silent:off")],
    ])
    await update.effective_message.reply_text(
        f"🔕 حالت سایلنت\n\nوضعیت فعلی: {silent_text(u)}\n\n"
        "وقتی سایلنت فعاله، درخواست چت و اعلان‌ها برات ارسال نمی‌شن. مدت رو انتخاب کن 👇",
        reply_markup=kb)

async def cmd_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    clear_state(user.id)
    u = get_user(user.id) or create_user(user.id, user.first_name, user.username)
    conn = db()
    rows = conn.execute("SELECT target_id FROM contacts WHERE owner_id=?", (user.id,)).fetchall()
    conn.close()
    if not rows:
        await update.effective_message.reply_text("👥 لیست مخاطبین تو خالیه!\nاز پروفایل کاربرا می‌تونی اونا رو به مخاطبینت اضافه کنی.")
        return
    lines = ["👥 مخاطبین من:\n"]
    for r in rows:
        t = get_user(r["target_id"])
        if t:
            lines.append(f"• {t['first_name']} — /user_{t['code']}")
    await update.effective_message.reply_text("\n".join(lines))

async def cmd_exempt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    clear_state(user.id)
    kb = InlineKeyboardMarkup([[gbtn("💳 پرداخت", "exempt:pay")]])
    await update.effective_message.reply_text(EXEMPT_TEXT, reply_markup=kb)

async def cmd_deleted_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    clear_state(user.id)
    kb = InlineKeyboardMarkup([[gbtn("💳 پرداخت", "delacc:pay")]])
    await update.effective_message.reply_text(DELETED_ACCOUNT_TEXT, reply_markup=kb)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_state(update.effective_user.id)
    await update.effective_message.reply_text(HELP_INDEX)

def make_help_handler(key):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        clear_state(update.effective_user.id)
        await update.effective_message.reply_text(HELP_TEXTS[key])
    return handler

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    clear_state(user.id)
    u = get_user(user.id) or create_user(user.id, user.first_name, user.username)
    touch(user.id)
    if u["photo_file_id"]:
        try:
            await update.effective_message.reply_photo(u["photo_file_id"], caption=profile_text(u, viewer=u), reply_markup=my_profile_kb(u))
            return
        except Exception:
            pass
    await update.effective_message.reply_text(profile_text(u, viewer=u), reply_markup=my_profile_kb(u))

# ============================================================================
# ANONYMOUS CHAT — queue, matching, relay, end (§11 of task / help_chat)
# ============================================================================
def criteria_match(a_id, b_id, kind):
    a, b = get_user(a_id), get_user(b_id)
    if not a or not b:
        return False
    conn = db()
    blocked = conn.execute("SELECT 1 FROM blocks WHERE (owner_id=? AND target_id=?) OR (owner_id=? AND target_id=?)",
                           (a_id, b_id, b_id, a_id)).fetchone()
    conn.close()
    if blocked:
        return False
    if kind == "girl":
        return b["gender"] == "female"
    if kind == "boy":
        return b["gender"] == "male"
    if kind == "sameage":
        return a["age"] and b["age"] and abs(a["age"] - b["age"]) <= 2
    if kind == "nearby":
        d = distance_km(a, b)
        return d is not None and d <= 50
    return True

def try_match(user_id, kind):
    for entry in list(search_queue):
        other = entry["user_id"]
        if other == user_id or other in partners:
            continue
        # the other user's requested kind must also accept this user (random = any)
        if entry["kind"] in ("girl", "boy", "sameage", "nearby") and not criteria_match(other, user_id, entry["kind"]):
            if not criteria_match(user_id, other, kind):
                continue
        elif not criteria_match(user_id, other, kind):
            continue
        search_queue.remove(entry)
        return other
    return None

CHAT_KB = InlineKeyboardMarkup([
    [gbtn("👤 پروفایل طرف مقابل", "chat:partner"), dbtn("❌ پایان چت", "chat:end")],
    [gbtn("🔔 وقتی چتش تموم شد خبرم کن (۱ سکه)", "chat:notify_end")],
])

async def connect_partners(context, a_id, b_id):
    partners[a_id] = b_id
    partners[b_id] = a_id
    for uid in (a_id, b_id):
        try:
            await context.bot.send_message(uid, "✅ وصل شدی! الان داری با یک ناشناس چت می‌کنی.\nهر پیامی بفرستی براش ارسال می‌شه. برای تموم کردن چت «❌ پایان چت» رو بزن.\n🗑 با نوشتن deletall یا «حذف همه» پیام‌های خودت پاک می‌شن.", reply_markup=CHAT_KB)
        except Exception:
            pass

async def end_chat(context, user_id, notify=True, reason=""):
    partner_id = partners.pop(user_id, None)
    if partner_id:
        partners.pop(partner_id, None)
        conn = db()
        conn.execute("INSERT INTO chats_done (user_id, partner_id, created_at) VALUES (?,?,?)", (user_id, partner_id, int(time.time())))
        conn.execute("INSERT INTO chats_done (user_id, partner_id, created_at) VALUES (?,?,?)", (partner_id, user_id, int(time.time())))
        conn.commit(); conn.close()
        if notify:
            for uid, other in ((user_id, partner_id), (partner_id, user_id)):
                try:
                    await context.bot.send_message(uid, f"❌ چت تموم شد.{reason}", reply_markup=main_menu_kb())
                except Exception:
                    pass
        # notify chat-end watchers of both sides
        now = int(time.time())
        conn = db()
        rows = conn.execute("SELECT * FROM watches WHERE kind='chatend' AND expires_at>? AND target_id IN (?,?)", (now, user_id, partner_id)).fetchall()
        conn.close()
        for r in rows:
            t = get_user(r["target_id"])
            try:
                await context.bot.send_message(r["watcher_id"], f"🔔 چت کاربر /user_{t['code']} تموم شد.")
            except Exception:
                pass
    return partner_id

async def start_search(update, context, user_id, kind, cost=0):
    u = get_user(user_id)
    if user_id in partners:
        await update.effective_message.reply_text("الان توی یک چت هستی! اول چت فعلی رو تموم کن.")
        return
    if kind in ("girl", "boy"):
        if u["coins"] < cost:
            await update.effective_message.reply_text(f"💰 سکه کافی نداری! این جستجو {cost} سکه هزینه داره. موجودی تو: {u['coins']} سکه\nاز /credit سکه بگیر.")
            return
    other = try_match(user_id, kind)
    if other:
        if cost:
            add_coins(user_id, -cost)
            # if the partner also queued a paid search, charge them symmetrically only if their kind was paid
        await connect_partners(context, user_id, other)
    else:
        if not any(e["user_id"] == user_id for e in search_queue):
            search_queue.append({"user_id": user_id, "kind": kind, "cost": cost})
        kb = InlineKeyboardMarkup([[dbtn("❌ لغو جستجو", "search:cancel")]])
        await update.effective_message.reply_text("🔍 در حال جستجو برای یک هم‌صحبت...\nبه محض پیدا شدن، وصلت می‌کنم. منتظر بمون ⏳", reply_markup=kb)

def stranger_submenu_kb():
    return InlineKeyboardMarkup([
        [gbtn("🎲 جستجوی شانسی (رایگان)", "search:random")],
        [gbtn("👩 جستجوی دختر (۲ سکه)", "search:girl"), gbtn("👨 جستجوی پسر (۲ سکه)", "search:boy")],
        [gbtn("📍 جستجوی اطراف (رایگان)", "search:nearby"), gbtn("🎂 جستجوی همسن", "search:sameage")],
    ])

def search_users_kb():
    return InlineKeyboardMarkup([
        [gbtn("🗺 هم استانی ها", "usearch:province"), gbtn("🎂 هم سن ها", "usearch:age")],
        [gbtn("💤 بدون چت ها", "usearch:nochat"), gbtn("🆕 کاربران جدید", "usearch:new")],
        [gbtn("🔎 جستجوی پیشرفته", "usearch:advanced")],
    ])

def list_users_text(viewer, rows, title):
    if not rows:
        return f"{title}\n\nفعلاً کاربری پیدا نشد! 😕"
    lines = [f"{title}\n"]
    for t in rows[:20]:
        d = distance_km(viewer, t)
        dist = f" — 📍 {d} km" if d is not None else ""
        lines.append(f"• {t['first_name']} ({gender_label(t['gender'])}, {t['age'] or '?'} ساله) — /user_{t['code']}{dist}")
    return "\n".join(lines)

def query_users(viewer_id, mode):
    viewer = get_user(viewer_id)
    conn = db()
    if mode == "province":
        rows = conn.execute("SELECT * FROM users WHERE province=? AND user_id!=? AND profile_complete=1 ORDER BY last_seen DESC LIMIT 20", (viewer["province"], viewer_id)).fetchall()
    elif mode == "age":
        rows = conn.execute("SELECT * FROM users WHERE age=? AND user_id!=? AND profile_complete=1 ORDER BY last_seen DESC LIMIT 20", (viewer["age"], viewer_id)).fetchall()
    elif mode == "new":
        rows = conn.execute("SELECT * FROM users WHERE user_id!=? AND profile_complete=1 ORDER BY created_at DESC LIMIT 20", (viewer_id,)).fetchall()
    elif mode == "nochat":
        rows = conn.execute("SELECT * FROM users WHERE user_id!=? AND profile_complete=1 ORDER BY last_seen DESC LIMIT 50", (viewer_id,)).fetchall()
        rows = [r for r in rows if r["user_id"] not in partners][:20]
    elif mode == "nearby":
        rows = conn.execute("SELECT * FROM users WHERE user_id!=? AND lat IS NOT NULL AND profile_complete=1 LIMIT 100", (viewer_id,)).fetchall()
        rows = sorted([dict(r) for r in rows], key=lambda t: distance_km(viewer, t) if distance_km(viewer, t) is not None else 99999)[:20]
        conn.close()
        return [dict(r) if not isinstance(r, dict) else r for r in rows]
    elif mode == "advanced":
        rows = conn.execute("SELECT * FROM users WHERE user_id!=? AND province=? AND profile_complete=1 ORDER BY last_seen DESC LIMIT 20", (viewer_id, viewer["province"])).fetchall()
    else:
        rows = conn.execute("SELECT * FROM users WHERE user_id!=? AND profile_complete=1 ORDER BY last_seen DESC LIMIT 20", (viewer_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ============================================================================
# OTHER USER PROFILE ACTIONS (§10)
# ============================================================================
async def show_other_profile(update, context, viewer_id, target_code, in_chat=False):
    target = get_user_by_code(target_code)
    if not target:
        await update.effective_message.reply_text("❌ کاربری با این آیدی پیدا نشد.")
        return
    if target["user_id"] == viewer_id:
        await cmd_profile(update, context)
        return
    viewer = get_user(viewer_id)
    # profile-view alarm
    if target["alarm_profile_view"]:
        try:
            await context.bot.send_message(target["user_id"], f"👁 کاربر /user_{viewer['code']} پروفایلت رو مشاهده کرد.")
        except Exception:
            pass
    text = profile_text(target, viewer=viewer)
    if target["photo_file_id"]:
        try:
            await update.effective_message.reply_photo(target["photo_file_id"], caption=text, reply_markup=other_profile_kb(target, in_chat=in_chat))
            return
        except Exception:
            pass
    await update.effective_message.reply_text(text, reply_markup=other_profile_kb(target, in_chat=in_chat))

# ============================================================================
# ADMIN (§13)
# ============================================================================
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return
    clear_state(user.id)
    kb = InlineKeyboardMarkup([
        [gbtn("📊 آمار", "admin:stats"), gbtn("📣 ارسال همگانی", "admin:broadcast")],
        [gbtn("➕ افزودن سکه", "admin:addcoins"), gbtn("➖ کم کردن سکه", "admin:removecoins")],
    ])
    await update.effective_message.reply_text("👑 پنل مدیریت پچ پچ", reply_markup=kb)

async def cmd_endchat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    clear_state(user.id)
    if user.id in partners:
        await end_chat(context, user.id)
    else:
        await update.effective_message.reply_text("الان توی چتی نیستی!")

# ============================================================================
# CALLBACK ROUTER
# ============================================================================
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    data = q.data or ""
    u = get_user(user_id) or create_user(user_id, q.from_user.first_name, q.from_user.username)
    touch(user_id)

    # --- forced-join gate re-check ---
    if data == "gate:check":
        if await is_member(context, user_id):
            await q.answer(GATE_OK, show_alert=True)
            try:
                await q.message.edit_text(GATE_OK)
            except Exception:
                pass
            await context.bot.send_message(user_id, START_AGAIN, reply_markup=main_menu_kb())
        else:
            await q.answer(GATE_ALERT, show_alert=True)
        return

    # --- onboarding / edit gender ---
    if data.startswith("ob:gender:"):
        gender = data.split(":")[-1]
        update_user(user_id, gender=gender)
        if get_state(user_id) == "edit_gender":
            clear_state(user_id)
            await q.answer("✅ جنسیتت به‌روزرسانی شد!")
            try:
                await q.message.edit_text("✅ جنسیتت به‌روزرسانی شد!")
            except Exception:
                pass
            await context.bot.send_message(user_id, START_AGAIN, reply_markup=main_menu_kb())
            return
        clear_state(user_id)
        set_state(user_id, "ob_age")
        await q.answer()
        await context.bot.send_message(user_id, ASK_AGE, reply_markup=age_kb())
        return

    # --- /Exempt payment (STUB gateway) ---
    if data == "exempt:pay":
        await q.answer()
        kb = InlineKeyboardMarkup([[gbtn("🌐 ورود به درگاه پرداخت", url=PAYMENT_GATEWAY_URL)]])
        await q.message.reply_text(EXEMPT_PAY_NOTES, reply_markup=kb)
        return

    # --- /deleted_account payment (STUB) ---
    if data == "delacc:pay":
        await q.answer()
        kb = InlineKeyboardMarkup([
            [gbtn("🌐 ورود به درگاه پرداخت", url=PAYMENT_GATEWAY_URL)],
            [dbtn("✅ پرداخت کردم، حسابم را حذف کن (استاب)", "delacc:confirm_stub")],
        ])
        await q.message.reply_text("📝 بعد از پرداخت موفق از درگاه، حذف حساب انجام می‌شه.\n(در این نسخه، درگاه پرداخت استاب است.)", reply_markup=kb)
        return
    if data == "delacc:confirm_stub":
        await q.answer("حساب کاربری حذف شد.", show_alert=True)
        conn = db()
        conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM contacts WHERE owner_id=? OR target_id=?", (user_id, user_id))
        conn.commit(); conn.close()
        clear_state(user_id)
        try:
            await q.message.edit_text("❌ حساب کاربری تو به طور کامل حذف شد. برای استفاده دوباره /start رو بزن.")
        except Exception:
            pass
        return
    if data == "adv:delete":
        await q.answer()
        await context.bot.send_message(user_id, DELETED_ACCOUNT_TEXT,
                                       reply_markup=InlineKeyboardMarkup([[gbtn("💳 پرداخت", "delacc:pay")]]))
        return

    # --- credit ---
    if data == "credit:referral":
        await q.answer()
        await cmd_link(update, context)
        return
    if data == "credit:stars":
        await q.answer()
        rows = [[gbtn(label, f"stars:buy:{coins}:{stars}")] for coins, stars, label in STARS_PACKAGES]
        try:
            await q.message.edit_text("⭐️ خرید سکه با استارز تلگرام\n\nیکی از بسته‌ها رو انتخاب کن 👇", reply_markup=InlineKeyboardMarkup(rows))
        except Exception:
            await context.bot.send_message(user_id, "⭐️ خرید سکه با استارز تلگرام", reply_markup=InlineKeyboardMarkup(rows))
        return
    if data.startswith("stars:buy:"):
        _, _, coins_s, stars_s = data.split(":")
        coins, stars = int(coins_s), int(stars_s)
        await q.answer()
        await context.bot.send_invoice(
            chat_id=user_id,
            title=f"💰 {coins} سکه پچ پچ",
            description=f"خرید {coins} سکه برای ربات چت ناشناس پچ پچ",
            payload=f"coins:{coins}",
            provider_token="",  # Telegram Stars needs no provider token
            currency="XTR",
            prices=[LabeledPrice(label=f"{coins} سکه", amount=stars)],
        )
        return

    # --- silent submenu ---
    if data.startswith("silent:"):
        mode = data.split(":")[1]
        if mode == "30m":
            update_user(user_id, silent_mode="30m", silent_until=int(time.time()) + 1800)
            txt = "🔕 حالت سایلنت برای ۳۰ دقیقه فعال شد."
        elif mode == "1h":
            update_user(user_id, silent_mode="1h", silent_until=int(time.time()) + 3600)
            txt = "🔕 حالت سایلنت برای ۱ ساعت فعال شد."
        elif mode == "always":
            update_user(user_id, silent_mode="always", silent_until=0)
            txt = "🔕 حالت سایلنت همیشه فعال شد."
        else:
            update_user(user_id, silent_mode="off", silent_until=0)
            txt = "🔔 حالت سایلنت غیرفعال شد."
        await q.answer(txt, show_alert=True)
        try:
            await q.message.edit_text(txt)
        except Exception:
            pass
        return

    # --- profile section ---
    if data == "prof:back":
        await q.answer()
        u = get_user(user_id)
        try:
            await q.message.edit_text(profile_text(u, viewer=u), reply_markup=my_profile_kb(u))
        except Exception:
            await context.bot.send_message(user_id, profile_text(u, viewer=u), reply_markup=my_profile_kb(u))
        return
    if data == "prof:gps" or data == "edit:gps":
        await q.answer()
        set_state(user_id, "await_location")
        kb = ReplyKeyboardMarkup([[KeyboardButton("✏️ ثبت موقعیت GPS", request_location=True)], [KeyboardButton(BACK_TEXT)]], resize_keyboard=True)
        await context.bot.send_message(user_id, "📍 موقعیت GPS\n\nبرای ثبت موقعیتت، روی دکمه «✏️ ثبت موقعیت GPS» بزن و موقعیتت رو ارسال کن 👇\n" + HELP_TEXTS["help_gps"], reply_markup=kb)
        return
    if data == "prof:likers":
        conn = db()
        rows = conn.execute("SELECT from_id FROM likes WHERE to_id=? ORDER BY created_at DESC LIMIT 20", (user_id,)).fetchall()
        conn.close()
        if not rows:
            await q.answer("❤️ هنوز کسی لایکت نکرده!", show_alert=True)
        else:
            lines = ["❤️ لایک کننده‌های تو:\n"]
            for r in rows:
                t = get_user(r["from_id"])
                if t:
                    lines.append(f"• {t['first_name']} — /user_{t['code']}")
            await q.answer()
            await context.bot.send_message(user_id, "\n".join(lines))
        return
    if data == "prof:contacts":
        conn = db()
        rows = conn.execute("SELECT target_id FROM contacts WHERE owner_id=?", (user_id,)).fetchall()
        conn.close()
        if not rows:
            await q.answer("👥 لیست مخاطبین تو خالیه!", show_alert=True)
        else:
            await q.answer()
            await cmd_contacts(update, context)
        return
    if data == "prof:blocked":
        conn = db()
        rows = conn.execute("SELECT target_id FROM blocks WHERE owner_id=?", (user_id,)).fetchall()
        conn.close()
        if not rows:
            await q.answer("🚫 هیچ کاربری رو بلاک نکردی!", show_alert=True)
        else:
            lines = ["🚫 کاربران بلاک شده:\n"]
            for r in rows:
                t = get_user(r["target_id"])
                if t:
                    lines.append(f"• {t['first_name']} — /user_{t['code']}")
            await q.answer()
            await context.bot.send_message(user_id, "\n".join(lines))
        return
    if data == "prof:liketoggle":
        u = get_user(user_id)
        new_val = 0 if u["like_enabled"] else 1
        update_user(user_id, like_enabled=new_val)
        u = get_user(user_id)
        await q.answer("❤️ لایک فعال شد ✅" if new_val else "❤️ لایک غیرفعال شد ❌")
        try:
            await q.message.edit_reply_markup(reply_markup=my_profile_kb(u))
        except Exception:
            pass
        return
    if data == "prof:advanced":
        await q.answer()
        try:
            await q.message.edit_text("⚙️ تنظیمات پیشرفته پروفایل", reply_markup=advanced_kb())
        except Exception:
            await context.bot.send_message(user_id, "⚙️ تنظیمات پیشرفته پروفایل", reply_markup=advanced_kb())
        return
    if data == "prof:edit":
        await q.answer()
        try:
            await q.message.edit_text("✏️ ویرایش پروفایل — چی رو می‌خوای تغییر بدی؟", reply_markup=edit_kb())
        except Exception:
            await context.bot.send_message(user_id, "✏️ ویرایش پروفایل", reply_markup=edit_kb())
        return

    # --- advanced settings ---
    if data == "adv:silent":
        await q.answer()
        await cmd_silent(update, context)
        return
    if data == "adv:filter":
        u = get_user(user_id)
        if not profile_is_complete(u):
            await q.answer("⚠️ برای فعال کردن فیلتر درخواست چت، اول باید پروفایلت رو کامل کنی!", show_alert=True)
            return
        new_val = 0 if u["chat_filter"] else 1
        update_user(user_id, chat_filter=new_val)
        await q.answer("⚖️ فیلتر درخواست چت فعال شد ✅" if new_val else "⚖️ فیلتر درخواست چت غیرفعال شد ❌", show_alert=True)
        return
    if data == "adv:alarms":
        await q.answer()
        u = get_user(user_id)
        kb = InlineKeyboardMarkup([
            [gbtn(f"👁 آلارام مشاهده پروفایل: {'روشن ✅' if u['alarm_profile_view'] else 'خاموش ❌'}", "alarm:view")],
            [gbtn(f"❤️ آلارام لایک: {'روشن ✅' if u['alarm_like'] else 'خاموش ❌'}", "alarm:like")],
            [gbtn("🔙 بازگشت", "prof:advanced")],
        ])
        try:
            await q.message.edit_text("⚙️ تنظیم آلارام ها 🔔\n\nبه صورت پیش‌فرض همه آلارام‌ها خاموشن. برای روشن/خاموش کردن روی هرکدوم بزن 👇", reply_markup=kb)
        except Exception:
            await context.bot.send_message(user_id, "⚙️ تنظیم آلارام ها 🔔", reply_markup=kb)
        return
    if data.startswith("alarm:"):
        kind = data.split(":")[1]
        u = get_user(user_id)
        if kind == "view":
            update_user(user_id, alarm_profile_view=0 if u["alarm_profile_view"] else 1)
        else:
            update_user(user_id, alarm_like=0 if u["alarm_like"] else 1)
        await q.answer("🔔 تنظیمات آلارام ذخیره شد.")
        u = get_user(user_id)
        kb = InlineKeyboardMarkup([
            [gbtn(f"👁 آلارام مشاهده پروفایل: {'روشن ✅' if u['alarm_profile_view'] else 'خاموش ❌'}", "alarm:view")],
            [gbtn(f"❤️ آلارام لایک: {'روشن ✅' if u['alarm_like'] else 'خاموش ❌'}", "alarm:like")],
            [gbtn("🔙 بازگشت", "prof:advanced")],
        ])
        try:
            await q.message.edit_reply_markup(reply_markup=kb)
        except Exception:
            pass
        return

    # --- edit profile ---
    if data == "edit:name":
        await q.answer()
        set_state(user_id, "edit_name")
        await context.bot.send_message(user_id, "📛 اسم جدیدت رو بنویس:")
        return
    if data == "edit:gender":
        await q.answer()
        set_state(user_id, "edit_gender")
        await context.bot.send_message(user_id, "⚧ جنسیت جدید رو انتخاب کن:", reply_markup=gender_kb())
        return
    if data == "edit:age":
        await q.answer()
        set_state(user_id, "edit_age")
        await context.bot.send_message(user_id, ASK_AGE, reply_markup=age_kb())
        return
    if data == "edit:city":
        await q.answer()
        set_state(user_id, "edit_province")
        await context.bot.send_message(user_id, ASK_PROVINCE, reply_markup=province_kb())
        return
    if data == "edit:photo":
        await q.answer()
        set_state(user_id, "edit_photo")
        await context.bot.send_message(user_id, "🖼 عکس جدید پروفایلت رو بفرست:")
        return
    # gender re-selection while editing reuses ob:gender — handled above via ob state check below
    if data.startswith("ob:gender:"):
        return  # unreachable safety

    # --- search / connect ---
    if data.startswith("search:"):
        kind = data.split(":")[1]
        await q.answer()
        if kind == "cancel":
            search_queue[:] = [e for e in search_queue if e["user_id"] != user_id]
            await context.bot.send_message(user_id, "❌ جستجو لغو شد.", reply_markup=main_menu_kb())
            return
        cost = COST_SEARCH_GIRL if kind in ("girl", "boy") else 0
        fake_update = update  # start_search uses effective_message
        await start_search(fake_update, context, user_id, kind, cost=cost)
        return
    if data.startswith("usearch:"):
        mode = data.split(":")[1]
        await q.answer()
        titles = {"province": "🗺 هم استانی‌های تو", "age": "🎂 هم سن‌های تو", "nochat": "💤 کاربران بدون چت", "new": "🆕 کاربران جدید", "advanced": "🔎 جستجوی پیشرفته (هم‌استانی‌ها)"}
        viewer = get_user(user_id)
        rows = query_users(user_id, mode)
        await context.bot.send_message(user_id, list_users_text(viewer, rows, titles.get(mode, "جستجو")))
        return

    # --- in-chat buttons ---
    if data == "chat:end":
        await q.answer()
        if user_id in partners:
            await end_chat(context, user_id)
        return
    if data == "chat:partner":
        await q.answer()
        pid = partners.get(user_id)
        if pid:
            p = get_user(pid)
            if p:
                await show_other_profile(update, context, user_id, p["code"], in_chat=True)
        return
    if data == "chat:notify_end":
        pid = partners.get(user_id)
        if not pid:
            await q.answer("الان توی چتی نیستی!", show_alert=True)
            return
        u = get_user(user_id)
        if u["coins"] < COST_NOTIFY_CHATEND:
            await q.answer("💰 سکه کافی نداری! (نیاز: ۱ سکه)", show_alert=True)
            return
        add_coins(user_id, -COST_NOTIFY_CHATEND)
        conn = db()
        conn.execute("INSERT OR REPLACE INTO watches (watcher_id, target_id, kind, expires_at, created_at) VALUES (?,?,?,?,?)",
                     (user_id, pid, "chatend", int(time.time()) + NOTIFY_EXPIRY_DAYS * 86400, int(time.time())))
        conn.commit(); conn.close()
        await q.answer("🔔 فعال شد! وقتی چتش تموم بشه خبرت می‌کنم (اعتبار: ۱۰ روز)", show_alert=True)
        return

    # --- other-user actions ---
    if data.startswith("u:"):
        parts = data.split(":")
        action, code = parts[1], parts[2]
        target = get_user_by_code(code)
        if not target:
            await q.answer("کاربر پیدا نشد!", show_alert=True)
            return
        tid = target["user_id"]
        if action == "direct":
            set_state(user_id, "await_direct", target_code=code)
            await q.answer()
            await context.bot.send_message(user_id, f"📨 پیام دایرکت به {target['first_name']}\n\nپیامت رو بنویس (حداکثر ۲۰۰ کاراکتر، هزینه: ۱ سکه).\nبرای لغو بنویس: بیخیال")
            return
        if action == "reqchat":
            await q.answer()
            # checks per help_pchat
            if is_silent(target):
                await context.bot.send_message(user_id, "🔕 این کاربر در حالت سایلنته و درخواست چت رد شد.")
                return
            if int(time.time()) - target["last_seen"] > 15 * 60:
                await context.bot.send_message(user_id, "💤 این کاربر بیش از ۱۵ دقیقه‌ست آفلاینه؛ درخواست چت ارسال نشد.")
                return
            if tid in partners or user_id in partners:
                await context.bot.send_message(user_id, "یکی از شما در حال حاضر توی چته!")
                return
            kb = InlineKeyboardMarkup([[
                gbtn("✅ قبول درخواست چت", f"req:accept:{u['code']}"),
                dbtn("❌ رد درخواست", f"req:reject:{u['code']}"),
            ]])
            try:
                await context.bot.send_message(tid, f"💬 یک درخواست چت داری!\nاز طرف: {u['first_name']} — /user_{u['code']}\n(هزینه ۲ سکه فقط در صورت قبول، از درخواست‌دهنده کسر می‌شه)", reply_markup=kb)
                await context.bot.send_message(user_id, "📨 درخواست چتت ارسال شد! منتظر قبول طرف مقابل بمون ⏳")
            except Exception:
                await context.bot.send_message(user_id, "❌ ارسال درخواست ناموفق بود.")
            return
        if action == "like":
            if not target["like_enabled"]:
                await q.answer("این کاربر لایک رو غیرفعال کرده!", show_alert=True)
                return
            conn = db()
            cur = conn.execute("INSERT OR IGNORE INTO likes (from_id, to_id, created_at) VALUES (?,?,?)", (user_id, tid, int(time.time())))
            conn.commit(); conn.close()
            if cur.rowcount:
                await q.answer("❤️ لایک شد!")
                if target["alarm_like"]:
                    try:
                        await context.bot.send_message(tid, f"❤️ کاربر /user_{u['code']} لایکت کرد!")
                    except Exception:
                        pass
            else:
                await q.answer("قبلاً لایکش کردی ❤️", show_alert=True)
            return
        if action == "addcontact":
            conn = db()
            conn.execute("INSERT OR IGNORE INTO contacts (owner_id, target_id, created_at) VALUES (?,?,?)", (user_id, tid, int(time.time())))
            conn.commit(); conn.close()
            await q.answer("➕ به مخاطبینت اضافه شد ✅", show_alert=True)
            return
        if action == "block":
            conn = db()
            conn.execute("INSERT OR IGNORE INTO blocks (owner_id, target_id, created_at) VALUES (?,?,?)", (user_id, tid, int(time.time())))
            conn.commit(); conn.close()
            await q.answer("🚫 کاربر بلاک شد.", show_alert=True)
            if partners.get(user_id) == tid:
                await end_chat(context, user_id, reason=" (طرف مقابل بلاک شد)")
            return
        if action == "report":
            await q.answer("🚫 گزارشت ثبت و برای مدیریت ارسال شد. اگه گزارش صحیح باشه ۵ سکه پاداش می‌گیری.", show_alert=True)
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(admin_id, f"🚫 گزارش جدید\nگزارش‌دهنده: /user_{u['code']} ({user_id})\nکاربر گزارش‌شده: /user_{code} ({tid})")
                except Exception:
                    pass
            return
        if action in ("notify_online", "notify_chatend"):
            kind = "online" if action == "notify_online" else "chatend"
            if u["coins"] < COST_NOTIFY_ONLINE:
                await q.answer("💰 سکه کافی نداری! (نیاز: ۱ سکه)", show_alert=True)
                return
            add_coins(user_id, -COST_NOTIFY_ONLINE)
            conn = db()
            conn.execute("INSERT OR REPLACE INTO watches (watcher_id, target_id, kind, expires_at, created_at) VALUES (?,?,?,?,?)",
                         (user_id, tid, kind, int(time.time()) + NOTIFY_EXPIRY_DAYS * 86400, int(time.time())))
            conn.commit(); conn.close()
            await q.answer("🔔 اطلاع‌رسانی فعال شد (اعتبار: ۱۰ روز، هزینه: ۱ سکه)", show_alert=True)
            return

    # --- chat request accept / reject ---
    if data.startswith("req:"):
        parts = data.split(":")
        action, req_code = parts[1], parts[2]
        requester = get_user_by_code(req_code)
        if not requester:
            await q.answer("درخواست‌دهنده پیدا نشد.", show_alert=True)
            return
        if action == "reject":
            await q.answer("درخواست رد شد.")
            try:
                await q.message.edit_text("❌ درخواست چت رو رد کردی.")
            except Exception:
                pass
            try:
                await context.bot.send_message(requester["user_id"], "❌ درخواست چتت رد شد.")
            except Exception:
                pass
            return
        if action == "accept":
            if requester["coins"] < COST_CHAT_REQUEST:
                await q.answer("درخواست‌دهنده سکه کافی نداره!", show_alert=True)
                try:
                    await context.bot.send_message(requester["user_id"], "❌ درخواست چتت قبول شد ولی سکه کافی نداشتی (۲ سکه لازم بود).")
                except Exception:
                    pass
                return
            add_coins(requester["user_id"], -COST_CHAT_REQUEST)
            await q.answer("✅ قبول شد! در حال اتصال...")
            try:
                await q.message.edit_text("✅ درخواست چت قبول شد!")
            except Exception:
                pass
            await connect_partners(context, user_id, requester["user_id"])
            return

    # --- admin ---
    if data.startswith("admin:"):
        if not is_admin(user_id):
            await q.answer("دسترسی نداری!", show_alert=True)
            return
        action = data.split(":")[1]
        await q.answer()
        if action == "stats":
            conn = db()
            total = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
            coins = conn.execute("SELECT COALESCE(SUM(coins),0) s FROM users").fetchone()["s"]
            conn.close()
            await context.bot.send_message(user_id, f"📊 آمار ربات\n\n👥 کل کاربران: {total}\n💰 مجموع سکه‌ها: {coins}\n💬 چت‌های فعال: {len(partners)//2}\n🔍 در صف جستجو: {len(search_queue)}")
        elif action == "broadcast":
            set_state(user_id, "admin_broadcast")
            await context.bot.send_message(user_id, "📣 متن ارسال همگانی رو بفرست:")
        elif action == "addcoins":
            set_state(user_id, "admin_addcoins")
            await context.bot.send_message(user_id, "➕ آیدی کاربر و مقدار سکه رو اینطوری بفرست:\nمثال: AbC12 50\n(کد کاربر همان بخش بعد از /user_ است)")
        elif action == "removecoins":
            set_state(user_id, "admin_removecoins")
            await context.bot.send_message(user_id, "➖ آیدی کاربر و مقدار سکه رو اینطوری بفرست:\nمثال: AbC12 50")
        return

    await q.answer()

# ============================================================================
# PAYMENTS — Telegram Stars successful payment
# ============================================================================
async def on_precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def on_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    payload = update.effective_message.successful_payment.invoice_payload or ""
    if payload.startswith("coins:"):
        coins = int(payload.split(":")[1])
        new_balance = add_coins(user_id, coins)
        await update.effective_message.reply_text(f"✅ پرداخت موفق با استارز ⭐️\n+{coins} سکه به حسابت اضافه شد!\n💰 موجودی جدید: {new_balance} سکه")

# ============================================================================
# MESSAGE ROUTER — states, menu, in-chat relay, /user_ profiles
# ============================================================================
MENU_TEXTS = {MAIN_CONNECT, MAIN_SEARCH, MAIN_NEARBY, MAIN_CREDIT, MAIN_PROFILE, MAIN_HELP, MAIN_REFERRAL, MAIN_MYLINK, BACK_TEXT}

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    user_id = user.id
    u = get_user(user_id)
    if u is None:
        u = create_user(user_id, user.first_name, user.username)
    touch(user_id)
    await notify_online_watchers(context, user_id)
    text = msg.text or msg.caption or ""

    # --- successful Stars payment is a separate content type ---
    if msg.successful_payment:
        await on_successful_payment(update, context)
        return

    # --- location (GPS registration) ---
    if msg.location:
        if get_state(user_id) in ("await_location", "ob_gps", "edit_gps_state"):
            update_user(user_id, lat=msg.location.latitude, lon=msg.location.longitude)
            clear_state(user_id)
            await msg.reply_text("📍 موقعیت GPS تو با موفقیت ثبت شد ✅", reply_markup=main_menu_kb())
        return

    state = get_state(user_id)
    state_data = user_state.get(user_id, {}).get("data", {})

    # Waiting-state rule: a new command or main-menu press cancels pending state.
    if (text.startswith("/") or text in MENU_TEXTS) and state not in (None,):
        # onboarding reply-keyboard steps are the exception (they ARE the state)
        if state not in ("ob_age", "ob_province", "ob_city", "edit_age", "edit_province", "edit_city"):
            clear_state(user_id)
            state = None

    # ---------------- in-chat relay ----------------
    if user_id in partners and state is None:
        if text.strip() in ("deletall", "حذف همه"):
            pid = partners[user_id]
            conn = db()
            rows = conn.execute("SELECT partner_msg_id FROM relay WHERE sender_id=? AND partner_id=? ORDER BY id DESC LIMIT 100", (user_id, pid)).fetchall()
            conn.close()
            deleted = 0
            for r in rows:
                try:
                    await context.bot.delete_message(pid, r["partner_msg_id"])
                    deleted += 1
                except Exception:
                    pass
            await msg.reply_text(f"🗑 {deleted} پیامت از چت حذف شد.")
            return
        pid = partners[user_id]
        try:
            sent = await context.bot.copy_message(chat_id=pid, from_chat_id=msg.chat_id, message_id=msg.message_id)
            conn = db()
            conn.execute("INSERT INTO relay (sender_id, partner_id, partner_msg_id, created_at) VALUES (?,?,?,?)",
                         (user_id, pid, sent.message_id, int(time.time())))
            conn.commit(); conn.close()
        except Exception as e:
            log.warning("relay failed: %s", e)
        return

    # ---------------- onboarding / edit reply-keyboard states ----------------
    if state in ("ob_age", "edit_age"):
        if text == BACK_TEXT:
            clear_state(user_id)
            if state == "ob_age":
                set_state(user_id, "ob_gender")
                await msg.reply_text(WELCOME_NEW.format(name=user.first_name or "دوست"), reply_markup=gender_kb())
            else:
                await msg.reply_text(START_AGAIN, reply_markup=main_menu_kb())
            return
        if text.isdigit() and 9 <= int(text) <= 99:
            update_user(user_id, age=int(text))
            if state == "ob_age":
                set_state(user_id, "ob_province")
                await msg.reply_text(ASK_PROVINCE, reply_markup=province_kb())
            else:
                clear_state(user_id)
                await msg.reply_text("🎂 سنت به‌روزرسانی شد ✅", reply_markup=main_menu_kb())
            return
        await msg.reply_text("لطفاً سنت رو از صفحه‌کلید انتخاب کن (۹ تا ۹۹)")
        return

    if state in ("ob_province", "edit_province"):
        if text == BACK_TEXT:
            clear_state(user_id)
            await msg.reply_text(START_AGAIN, reply_markup=main_menu_kb())
            return
        if text in PROVINCES:
            update_user(user_id, province=text)
            nxt = "ob_city" if state == "ob_province" else "edit_city"
            set_state(user_id, nxt, province=text)
            await msg.reply_text(ASK_CITY, reply_markup=city_kb(text))
            return
        await msg.reply_text("لطفاً استان رو از صفحه‌کلید انتخاب کن")
        return

    if state in ("ob_city", "edit_city"):
        province = state_data.get("province") or get_user(user_id)["province"]
        if text == BACK_TEXT:
            set_state(user_id, "ob_province" if state == "ob_city" else "edit_province")
            await msg.reply_text(ASK_PROVINCE, reply_markup=province_kb())
            return
        if text in cities_for(province):
            update_user(user_id, city=text)
            was_onboarding = state == "ob_city"
            clear_state(user_id)
            if was_onboarding:
                if not await finish_profile_if_ready(update, context, user_id):
                    await msg.reply_text(START_AGAIN, reply_markup=main_menu_kb())
            else:
                await msg.reply_text("🏙 شهرت به‌روزرسانی شد ✅", reply_markup=main_menu_kb())
            return
        await msg.reply_text("لطفاً شهر رو از صفحه‌کلید انتخاب کن")
        return

    # ---------------- text-input states ----------------
    if state == "edit_name" and text:
        update_user(user_id, first_name=text[:64])
        clear_state(user_id)
        await msg.reply_text("📛 اسمت به‌روزرسانی شد ✅", reply_markup=main_menu_kb())
        return
    if state == "edit_photo":
        if msg.photo:
            update_user(user_id, photo_file_id=msg.photo[-1].file_id)
            clear_state(user_id)
            await msg.reply_text("🖼 عکس پروفایلت به‌روزرسانی شد ✅", reply_markup=main_menu_kb())
        else:
            await msg.reply_text("لطفاً یک عکس بفرست:")
        return
    if state == "await_direct":
        if text.strip() == "بیخیال":
            clear_state(user_id)
            await msg.reply_text("📨 ارسال پیام دایرکت لغو شد.", reply_markup=main_menu_kb())
            return
        target = get_user_by_code(state_data.get("target_code", ""))
        if not target:
            clear_state(user_id)
            await msg.reply_text("❌ کاربر پیدا نشد.")
            return
        if len(text) > 200:
            await msg.reply_text("⚠️ پیام دایرکت حداکثر ۲۰۰ کاراکتره! کوتاه‌تر بنویس:")
            return
        if u["coins"] < COST_DIRECT_MESSAGE:
            clear_state(user_id)
            await msg.reply_text("💰 سکه کافی نداری! پیام دایرکت ۱ سکه هزینه داره.", reply_markup=main_menu_kb())
            return
        add_coins(user_id, -COST_DIRECT_MESSAGE)
        clear_state(user_id)
        try:
            await context.bot.send_message(target["user_id"], f"📨 یک پیام دایرکت ناشناس داری:\n\n{text}\n\n— از طرف یک کاربر ناشناس (/user_{u['code']})")
            await msg.reply_text("✅ پیام دایرکتت ارسال شد! (۱ سکه کسر شد)", reply_markup=main_menu_kb())
        except Exception:
            add_coins(user_id, COST_DIRECT_MESSAGE)  # refund on failure
            await msg.reply_text("❌ ارسال ناموفق بود؛ سکه‌ات برگشت داده شد.")
        return
    if state == "admin_broadcast" and is_admin(user_id):
        clear_state(user_id)
        conn = db()
        ids = [r["user_id"] for r in conn.execute("SELECT user_id FROM users").fetchall()]
        conn.close()
        ok = fail = 0
        for tid in ids:
            try:
                await context.bot.send_message(tid, f"📣 پیام مدیریت:\n\n{text}")
                ok += 1
            except Exception:
                fail += 1
        await msg.reply_text(f"📣 ارسال همگانی تموم شد.\n✅ موفق: {ok}\n❌ ناموفق: {fail}")
        return
    if state in ("admin_addcoins", "admin_removecoins") and is_admin(user_id):
        clear_state(user_id)
        m = re.match(r"^\s*/?user_?(\w{5})\s+(-?\d+)\s*$", text) or re.match(r"^\s*(\w{5})\s+(-?\d+)\s*$", text)
        if not m:
            await msg.reply_text("❌ فرمت اشتباهه. مثال: AbC12 50")
            return
        target = get_user_by_code(m.group(1))
        amount = int(m.group(2))
        if not target:
            await msg.reply_text("❌ کاربر پیدا نشد.")
            return
        if state == "admin_removecoins":
            amount = -abs(amount)
        bal = add_coins(target["user_id"], amount)
        await msg.reply_text(f"✅ موجودی /user_{target['code']} به {bal} سکه رسید.")
        return

    # gender edit state: gender chosen via inline keyboard (ob:gender) — when in
    # edit_gender state, the callback above updates gender; nothing to do here.

    # ---------------- /user_<code> profile view ----------------
    m = re.match(r"^/user_(\w{5})$", text.strip())
    if m:
        if not await gate_or_pass(update, context, user_id):
            return
        await show_other_profile(update, context, user_id, m.group(1), in_chat=(partners.get(user_id) == (get_user_by_code(m.group(1)) or {}).get("user_id")))
        return

    # ---------------- main menu (gated) ----------------
    if text == MAIN_CONNECT:
        if not await gate_or_pass(update, context, user_id):
            return
        await msg.reply_text("به کی وصلت کنم؟ 👇 انتخاب کن", reply_markup=stranger_submenu_kb())
        return
    if text == MAIN_SEARCH:
        if not await gate_or_pass(update, context, user_id):
            return
        await msg.reply_text("🗨 جستجو کاربران 🗨\nنوع جستجو رو انتخاب کن 👇", reply_markup=search_users_kb())
        return
    if text == MAIN_NEARBY:
        if not await gate_or_pass(update, context, user_id):
            return
        viewer = get_user(user_id)
        if viewer["lat"] is None:
            set_state(user_id, "await_location")
            kb = ReplyKeyboardMarkup([[KeyboardButton("✏️ ثبت موقعیت GPS", request_location=True)], [KeyboardButton(BACK_TEXT)]], resize_keyboard=True)
            await msg.reply_text("📍 برای دیدن افراد نزدیک، اول باید موقعیت GPS تو ثبت کنی 👇", reply_markup=kb)
            return
        rows = query_users(user_id, "nearby")
        await msg.reply_text(list_users_text(viewer, rows, "📍 افراد نزدیک تو (بر اساس فاصله)"))
        return
    if text == MAIN_CREDIT:
        await cmd_credit(update, context)
        return
    if text == MAIN_PROFILE:
        await cmd_profile(update, context)
        return
    if text == MAIN_HELP:
        await cmd_help(update, context)
        return
    if text == MAIN_REFERRAL or text == MAIN_MYLINK:
        await cmd_link(update, context)
        return
    if text == BACK_TEXT:
        clear_state(user_id)
        await msg.reply_text(START_AGAIN, reply_markup=main_menu_kb())
        return

    # fallback
    if text and not text.startswith("/"):
        await msg.reply_text("از منوی پایین یکی رو انتخاب کن 👇", reply_markup=main_menu_kb())

# ============================================================================
# STARTUP / MAIN
# ============================================================================
async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start", "شروع"),
        BotCommand("link", "لینک ناشناس من"),
        BotCommand("profile", "پروفایل من"),
        BotCommand("contacts", "مخاطبین من"),
        BotCommand("silent", "حالت سایلنت"),
        BotCommand("credit", "سکه‌های من"),
        BotCommand("help", "راهنما"),
    ])
    log.info("PachPach replica started as @%s", BOT_USERNAME)

def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set — copy .env.example to .env and fill it in.")
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("link", cmd_link))
    app.add_handler(CommandHandler("credit", cmd_credit))
    app.add_handler(CommandHandler("silent", cmd_silent))
    app.add_handler(CommandHandler("contacts", cmd_contacts))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("Exempt", cmd_exempt))
    app.add_handler(CommandHandler("exempt", cmd_exempt))
    app.add_handler(CommandHandler("deleted_account", cmd_deleted_account))
    app.add_handler(CommandHandler("help", cmd_help))
    for key in HELP_TEXTS:
        app.add_handler(CommandHandler(key, make_help_handler(key)))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("endchat", cmd_endchat))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(PreCheckoutQueryHandler(on_precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_successful_payment))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, on_message))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
