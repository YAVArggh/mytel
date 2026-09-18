"""
═══════════════════════════════════════════════════════════════════════
🤖 ربات پیام ناشناس — Anonymous Messenger Bot (v7.0)
═══════════════════════════════════════════════════════════════════════
✨ ویژگی‌های v7.0:
   ✅ آواتار لبخندزن و خوشگل (پسر/دختر مجزا)
   ✅ انتخاب سن دقیق 9-99 با گرید 5×5 صفحه‌بندی‌شده
   ✅ ویرایش عکس پروفایل (آپلود سفارشی + تصادفی)
   ✅ قوانین دقیق 7 بند
   ✅ لیست کامل ۳۱ استان ایران
   ✅ پشتیبانی چندزبانه (فارسی، English، العربية)
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
import re
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional

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
# 📌 بخش ۱ — تنظیمات
# ═══════════════════════════════════════════════════════════════════════

class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "8654406992:AAECfMfmYjc9_W8sFG-yNR78kASBh7CRMTs")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "8094551428"))
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "YourBot")
    DB_PATH: str = os.getenv("DB_PATH", "anonymous_bot_v7.db")
    RATE_LIMIT_MESSAGES: int = 15
    RATE_LIMIT_WINDOW: int = 60
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = "logs/bot.log"

    @classmethod
    def validate(cls) -> None:
        errors = []
        if not cls.BOT_TOKEN or cls.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            errors.append("❌ BOT_TOKEN تنظیم نشده است.")
        elif not re.match(r"^\d+:[A-Za-z0-9_-]+$", cls.BOT_TOKEN):
            errors.append("❌ فرمت BOT_TOKEN نامعتبر است.")
        if cls.ADMIN_ID <= 0:
            errors.append("❌ ADMIN_ID نامعتبر است.")
        if errors:
            raise RuntimeError("\n".join(errors))


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۲ — لاگ‌گیری
# ═══════════════════════════════════════════════════════════════════════

def setup_logger() -> logging.Logger:
    os.makedirs(os.path.dirname(Config.LOG_FILE) or ".", exist_ok=True)
    logger = logging.getLogger("anon_bot")
    logger.setLevel(getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))
    logger.propagate = False
    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    if not logger.handlers:
        fh = RotatingFileHandler(Config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger

log = setup_logger()
if not STYLE_SUPPORTED:
    log.warning("⚠️ ButtonStyle موجود نیست. pip install -U 'aiogram>=3.31.0'")


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۳ — تاریخ شمسی
# ═══════════════════════════════════════════════════════════════════════

WEEKDAYS_FA = ["شنبه", "یک‌شنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"]
MONTHS_FA = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
             "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100)
            + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1])
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def now_shamsi():
    now = datetime.now()
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    py_wd = now.weekday()
    fa_wd = (py_wd + 2) % 7
    return jy, jm, jd, now.hour, now.minute, fa_wd


def fa_now_str() -> str:
    jy, jm, jd, hh, mm, wd = now_shamsi()
    return f"🕐 {hh:02d}:{mm:02d}  |  📅 {WEEKDAYS_FA[wd]} {jd} {MONTHS_FA[jm - 1]} {jy}"


def with_footer(text: str) -> str:
    return f"{text}\n\n━━━━━━━━━━━━━━━━━━\n{fa_now_str()}"


def generate_secure_token(length: int = 16) -> str:
    return secrets.token_urlsafe(length)


def sanitize_text(text: str) -> str:
    return re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", text).strip()


def parse_channel_input(raw: str) -> Optional[str]:
    raw = raw.strip()
    if not raw:
        return None
    if re.match(r"^-?\d+$", raw):
        return raw
    m = re.match(r"^https?://t\.me/([A-Za-z0-9_]+)/?$", raw)
    if m:
        return f"@{m.group(1)}"
    if raw.startswith("@"):
        return raw
    if re.match(r"^[A-Za-z0-9_]{4,}$", raw):
        return f"@{raw}"
    return None


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۴ — آواتار خوشگل و لبخندزن 🎨✨
# ═══════════════════════════════════════════════════════════════════════

def avatar_url(gender: str, seed: int | str, size: int = 512) -> str:
    """
    ساخت آواتار PNG خوشگل و لبخندزن از DiceBear Avataaars v9.
    - پسر: موی کوتاه مرتب، بدون ریش، لباس آبی/تیره، لبخند دلنشین
    - دختر: موی بلند/بافته، لباس صورتی/رنگی، لباس رنگی، لبخند دلنشین
    - چشم‌های شاد و ابروهای طبیعی برای بیان گرم
    """
    base = f"https://api.dicebear.com/9.x/avataaars/png?seed={seed}"

    # مشترک بین هر دو: لبخند + چشم‌های شاد
    common = (
        "&mouth=smile,twinkle"
        "&eyes=happy,default,squint"
        "&eyebrow=default,defaultNatural,raisedExcited,raisedExcitedNatural,upDown"
        "&nose=default"
        "&facialHairProbability=0"
        "&skinColor=edb98a,d08b5b,ae5d29,614335,ffdbb4"
        "&style=circle"
        f"&size={size}"
    )

    if gender == "male":
        return (
            f"{base}"
            f"{common}"
            "&top=shortFlat,shortRound,shortWaved,shortCurly,shortDreads,theCaesar,shortShaggy,sides,shaggyMullet"
            "&hairColor=2c1b18,4a312c,724133,a55728,b58143,d6b370"
            "&clothing=blazerAndShirt,blazerAndSweater,graphicShirt,hoodie,shirtCrewNeck,shirtVNeck,overall"
            "&clothingColor=262e33,3c4f5c,65c9ff,5199e4,25557c,929598,262e33"
            "&accessories=prescription01,prescription02,round,wayfarers"
            "&accessoriesColor=262e33,3c4f5c,25557c"
            "&accessoriesProbability=18"
            "&hairColor=2c1b18,4a312c,724133,a55728,b58143,d6b370"
            "&backgroundColor=b6e3f4,c0aede,d1d4f9,ffd5dc,ffdfbf"
        )
    elif gender == "female":
        return (
            f"{base}"
            f"{common}"
            "&top=bigHair,bob,bun,curly,curvy,frida,fro,froBand,longButNotTooLong,miaWallace,straight01,straight02,straightAndStrand"
            "&hairColor=2c1b18,4a312c,724133,a55728,b58143,d6b370,ff5c5c,ff9c9c,ffd5dc,724133"
            "&clothing=blazerAndShirt,collarAndSweater,graphicShirt,hoodie,shirtCrewNeck,shirtScoopNeck,shirtVNeck"
            "&clothingColor=ff5c5c,ff9c9c,ffb0b0,ffd5dc,c0aede,d1d4f9,b6e3f4"
            "&accessories=prescription01,prescription02,round"
            "&accessoriesColor=262e33,3c4f5c,25557c,ff5c5c"
            "&accessoriesProbability=22"
            "&backgroundColor=ffd5dc,ffdfbf,c0aede,d1d4f9,b6e3f4"
        )
    else:
        return (
            f"{base}"
            f"{common}"
            "&top=shortFlat,shortRound,bob,curly,fro"
            "&clothing=graphicShirt,hoodie,shirtCrewNeck"
            "&clothingColor=d1d4f9,b6e3f4,c0aede"
            "&accessoriesProbability=10"
            "&backgroundColor=d1d4f9,b6e3f4,c0aede"
        )


def is_custom_avatar(avatar: str) -> bool:
    """بررسی اینکه آواتار آپلود سفارشی است یا لینک تولیدی."""
    return bool(avatar) and avatar.startswith("file:")


def extract_file_id(avatar: str) -> str:
    """استخراج file_id از آواتار سفارشی."""
    return avatar[5:] if is_custom_avatar(avatar) else avatar


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۵ — لیست کامل استان‌ها و شهرها
# ═══════════════════════════════════════════════════════════════════════

IRAN_DATA: dict[str, list[str]] = {
    "آذربایجان شرقی": ["تبریز","مراغه","مرند","اهر","میانه","بناب","سراب","جلفا","آذرشهر","اسکو","شبستر","هریس","بستان‌آباد","هشترود","ملکان","عجب‌شیر","خداآفرین","ورزقان","کلیبر","هوراند"],
    "آذربایجان غربی": ["ارومیه","خوی","میاندوآب","مهاباد","بوکان","سلماس","پیرانشهر","نقده","اشنویه","شاهین‌دژ","ماکو","چالدران","پلدشت","شوط","تکاب","سردشت","کشاورز","مرگنلر","محمودآباد","نازک‌علیا"],
    "اردبیل": ["اردبیل","پارس‌آباد","مشگین‌شهر","خلخال","گرمی","بیله‌سوار","نمین","نیر","سرعین","کوثر","هیر","لاهرود","قصابه","رضی","فخرآباد","جعفرآباد","کیوی","عنبران","ابی‌بیگلو","اصلاندوز"],
    "اصفهان": ["اصفهان","کاشان","خمینی‌شهر","نجف‌آباد","شهرضا","شاهین‌شهر","فولادشهر","زرین‌شهر","آران و بیدگل","اردستان","نائین","سمیرم","فریدن","فریدون‌شهر","چادگان","بوئین و میاندشت","خوانسار","گلپایگان","دهاقان","برخوار","مبارکه","دلیجان","نطنز","قهرود","قمصر","نوش‌آباد","کوهپایه","هرند","ورزنه","زیار"],
    "البرز": ["کرج","فردیس","هشتگرد","نظرآباد","محمدشهر","ماهدشت","مشکین‌دشت","چهارباغ","اشتهارد","گرمدره","گلسار","کوهسار","طالقان","آسارا","تنکمان","کمال‌شهر"],
    "ایلام": ["ایلام","دهلران","آبدانان","مهران","دره‌شهر","ایوان","چرداول","ملکشاهی","بدره","سیروان","هلیلان","ارکواز","موسیان","دلگشا","ماژین","پهله","زرین‌آباد","لومار"],
    "بوشهر": ["بوشهر","برازجان","بندر گناوه","بندر دیر","کنگان","جم","عسلویه","خورموج","اهرم","دیلم","بندر ریگ","شنبه","کاکی","بردخون","دلوار","آبدان","ریز","سعدآباد","چغادک"],
    "تهران": ["تهران","شهریار","اسلامشهر","قدس","ملارد","پاکدشت","ورامین","پردیس","رباط‌کریم","فیروزکوه","دماوند","شمشک","لواسان","بومهن","رودهن","آبعلی","چهاردانگه","نسیم‌شهر","صباشهر","وحیدیه","باقرشهر","کهریزک","حسن‌آباد","جوادآباد","قرچک","پیشوا","شریف‌آباد","جاجرود","فشم","میگون"],
    "چهارمحال و بختیاری": ["شهرکرد","بروجن","فارسان","لردگان","سامان","بن","سفیددشت","هفشجان","کیار","اردل","دزپارت","فلارد","خانمیرزا","گندمان","بلداجی","نقنه","دستنا","وردنجان"],
    "خراسان جنوبی": ["بیرجند","قائن","فردوس","نهبندان","سربیشه","طبس","بشرویه","خوسف","درمیان","زیرکوه","سرایان","آیسک","اسدیه","حاجی‌آباد","مود","سده","خضری","نیمبلوک"],
    "خراسان رضوی": ["مشهد","نیشابور","سبزوار","تربت حیدریه","قوچان","کاشمر","گناباد","تربت جام","چناران","خواف","تایباد","بردسکن","درگز","سرخس","فریمان","جغتای","جوین","خلیل‌آباد","رشتخوار","زاوه","باخرز","بجستان","فیروزه","مه‌ولات","کوهسرخ","داورزن","صالح‌آباد","طرقبه","شاندیز","گلمکان"],
    "خراسان شمالی": ["بجنورد","شیروان","اسفراین","آشخانه","گرمه","جاجرم","فاروج","راز","صفی‌آباد","سنخواست","قاضی","چناران","لوجلی","حصارگرمخان","تیتکانلو","درق","زیارت"],
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

ALL_AGES = list(range(9, 100))  # 9 تا 99


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۶ — چندزبانه
# ═══════════════════════════════════════════════════════════════════════

TRANSLATIONS: dict[str, dict[str, str]] = {
    "fa": {
        "welcome_title": "🌟 <b>به ربات پیام ناشناس خوش آمدی!</b>",
        "welcome_sub": "✨ دنیای ناشناس، شفاف و امن",
        "rules_title": "📜 <b>قوانین استفاده از ربات:</b>",
        "accept_rules": "✅ قوانین را می‌پذیرم",
        "decline_rules": "❌ انصراف",
        "main_menu": "🏠 <b>منوی اصلی</b>",
    },
    "en": {
        "welcome_title": "🌟 <b>Welcome to Anonymous Messenger!</b>",
        "welcome_sub": "✨ Anonymous world, transparent and secure",
        "rules_title": "📜 <b>Bot Rules:</b>",
        "accept_rules": "✅ I accept the rules",
        "decline_rules": "❌ Decline",
        "main_menu": "🏠 <b>Main Menu</b>",
    },
    "ar": {
        "welcome_title": "🌟 <b>مرحباً بك في الرسائل المجهولة!</b>",
        "welcome_sub": "✨ عالم مجهول، شفاف وآمن",
        "rules_title": "📜 <b>قواعد البوت:</b>",
        "accept_rules": "✅ أوافق على القواعد",
        "decline_rules": "❌ رفض",
        "main_menu": "🏠 <b>القائمة الرئيسية</b>",
    },
}


def t(key: str, lang: str = "fa") -> str:
    return TRANSLATIONS.get(lang, TRANSLATIONS["fa"]).get(key, TRANSLATIONS["fa"].get(key, key))


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۷ — قوانین کامل و دقیق 📜
# ═══════════════════════════════════════════════════════════════════════

RULES_FA = """📜 <b>قوانین و شرایط استفاده از ربات</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>1️⃣ رفتار محترمانه و اخلاقی</b>
• با تمام کاربران با احترام و ادب رفتار کنید.
• هرگونه توهین، فحاشی، تهمت، تمسخر و تحقیر ممنوع است.
• از ایجاد تنش، تفرقه و بحث‌های سیاسی/مذهبی جنجالی خودداری کنید.

<b>2️⃣ محتوای مجاز و ممنوع</b>
• ارسال محتوای مستهجن، خشونت‌آمیز، غیرقانونی، تروریستی و نفرت‌پراکنانه ممنوع است.
• تبلیغات تجاری، لینک‌های خارجی و اسپم بدون اجازه ممنوع است.
• ارسال تصاویر و ویدیوهای نامناسب باعث بن دائمی می‌شود.

<b>3️⃣ حفظ حریم خصوصی</b>
• هویت فرستنده پیام‌های ناشناس نزد ربات محفوظ می‌ماند.
• انتشار اطلاعات شخصی دیگران (شماره، آدرس، عکس) بدون رضایت ممنوع و پیگرد قانونی دارد.
• ارسال تهدید، اخاذی، باج‌گیری و آزار جنسی جرم است و گزارش می‌شود.

<b>4️⃣ آزار و اذیت و سوءاستفاده</b>
• آزار، اذیت، تهدید و آزار جنسی باعث <b>بن دائمی</b> می‌شود.
• سوءاستفاده از ربات برای کلاهبرداری، فیشینگ و جرایم سایبری ممنوع است.

<b>5️⃣ مسئولیت کاربران</b>
• مسئولیت تمام محتوای ارسالی بر عهده کاربر است.
• ربات هیچ‌گونه مسئولیتی در قبال محتوای تولیدشده توسط کاربران ندارد.
• در صورت تخلف، اطلاعات کاربر ممکن است در اختیار مراجع قانونی قرار گیرد.

<b>6️⃣ شرایط سنی</b>
• استفاده از ربات برای افراد <b>زیر ۱۳ سال</b> ممنوع است.
• کاربران زیر ۱۸ سال باید با نظارت والدین استفاده کنند.

<b>7️⃣ گزارش تخلف و پشتیبانی</b>
• برای گزارش تخلف با ادمین در تماس باشید.
• ادمین حق حذف هر پیام و بن هر کاربر متخلف را دارد.

<b>8️⃣ تغییر قوانین</b>
• این قوانین ممکن است بدون اطلاع قبلی به‌روزرسانی شوند.
• ادامه استفاده از ربات به معنای پذیرش قوانین جدید است.

━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ <b>با زدن دکمه «✅ قوانین را می‌پذیرم»، تأیید می‌کنید که:</b>
✔️ تمام قوانین بالا را خوانده و پذیرفته‌اید
✔️ مسئولیت کامل رفتار خود را می‌پذیرید
✔️ در صورت تخلف، ربات حق بن کردن شما را دارد
"""

RULES_EN = """📜 <b>Bot Rules & Terms of Use</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>1️⃣ Respectful Behavior</b>
• Treat all users with respect.
• Insults, profanity, defamation, and mockery are prohibited.

<b>2️⃣ Content Rules</b>
• Obscene, violent, illegal, and hateful content is prohibited.
• Unauthorized advertising and spam are prohibited.

<b>3️⃣ Privacy</b>
• Sender identity of anonymous messages is protected.
• Sharing others' personal info without consent is prohibited.

<b>4️⃣ Harassment</b>
• Harassment, threats, and extortion result in permanent ban.

<b>5️⃣ User Responsibility</b>
• You are responsible for your content.

<b>6️⃣ Age Restriction</b>
• Users under 13 are not allowed.

━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ By tapping "I accept", you agree to all rules.
"""

RULES_AR = """📜 <b>قواعد وشروط الاستخدام</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>1️⃣ السلوك المحترم</b>
• تعامل مع جميع المستخدمين باحترام.

<b>2️⃣ المحتوى</b>
• المحتوى الفاحش والعنيف وغير القانوني محظور.

<b>3️⃣ الخصوصية</b>
• هوية المرسل محمية.

<b>4️⃣ التحرش</b>
• التحرش والتهديد يؤدي إلى حظر دائم.

<b>5️⃣ المسؤولية</b>
• أنت مسؤول عن محتواك.

<b>6️⃣ العمر</b>
• المستخدمون تحت 13 سنة غير مسموح لهم.

━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ بالنقر على "أوافق" فإنك تقبل جميع القواعد.
"""


def get_rules(lang: str) -> str:
    return {"fa": RULES_FA, "en": RULES_EN, "ar": RULES_AR}.get(lang, RULES_FA)


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۸ — دیتابیس
# ═══════════════════════════════════════════════════════════════════════

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    full_name TEXT,
    username TEXT,
    language TEXT DEFAULT 'fa',
    rules_accepted INTEGER DEFAULT 0,
    is_banned INTEGER DEFAULT 0,
    ban_reason TEXT,
    message_count INTEGER DEFAULT 0,
    link_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER PRIMARY KEY,
    gender TEXT NOT NULL,
    age INTEGER NOT NULL,
    province TEXT NOT NULL,
    city TEXT NOT NULL,
    avatar_url TEXT,
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_owner ON messages(owner_id);

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

    def _get_lock(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def connect(self):
        async with self._get_lock():
            if self._conn is not None:
                return
            self._conn = await aiosqlite.connect(Config.DB_PATH)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.executescript(SCHEMA_SQL)
            await self._conn.commit()
            log.info("✅ دیتابیس: %s", Config.DB_PATH)

    async def close(self):
        async with self._get_lock():
            if self._conn is not None:
                try:
                    await self._conn.close()
                except Exception:
                    pass
                self._conn = None

    @property
    def conn(self):
        if self._conn is None:
            raise RuntimeError("دیتابیس متصل نیست.")
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


db = Database()


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۹ — مدل‌ها
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class User:
    user_id: int
    full_name: Optional[str]
    username: Optional[str]
    language: str
    rules_accepted: int
    is_banned: int
    ban_reason: Optional[str]
    message_count: int
    link_count: int
    created_at: str
    last_seen: str

    @classmethod
    def from_row(cls, r): return cls(**{k: r[k] for k in r.keys()})


@dataclass
class Profile:
    user_id: int
    gender: str
    age: int
    province: str
    city: str
    avatar_url: Optional[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, r): return cls(**{k: r[k] for k in r.keys()})


@dataclass
class UserSettings:
    user_id: int
    web_mode: int
    silent_mode: int
    copyright_mode: int
    read_receipt: int

    @classmethod
    def from_row(cls, r): return cls(**{k: r[k] for k in r.keys()})


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
    def from_row(cls, r): return cls(**{k: r[k] for k in r.keys()})


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۱۰ — ریپازیتوری‌ها
# ═══════════════════════════════════════════════════════════════════════

class UserRepo:
    async def create(self, uid, fn, un):
        await db.execute("INSERT OR IGNORE INTO users (user_id, full_name, username) VALUES (?,?,?)", (uid, fn, un))

    async def get(self, uid) -> Optional[User]:
        r = await db.fetch_one("SELECT * FROM users WHERE user_id=?", (uid,))
        return User.from_row(r) if r else None

    async def exists(self, uid) -> bool:
        return (await db.fetch_one("SELECT 1 FROM users WHERE user_id=?", (uid,))) is not None

    async def update_profile(self, uid, fn, un):
        await db.execute("UPDATE users SET full_name=?, username=?, last_seen=CURRENT_TIMESTAMP WHERE user_id=?", (fn, un, uid))

    async def set_language(self, uid, lang):
        await db.execute("UPDATE users SET language=? WHERE user_id=?", (lang, uid))

    async def set_rules_accepted(self, uid):
        await db.execute("UPDATE users SET rules_accepted=1 WHERE user_id=?", (uid,))

    async def ban(self, uid, reason):
        await db.execute("UPDATE users SET is_banned=1, ban_reason=? WHERE user_id=?", (reason, uid))

    async def unban(self, uid):
        await db.execute("UPDATE users SET is_banned=0, ban_reason=NULL WHERE user_id=?", (uid,))

    async def inc_msg(self, uid):
        await db.execute("UPDATE users SET message_count=message_count+1 WHERE user_id=?", (uid,))

    async def inc_link(self, uid):
        await db.execute("UPDATE users SET link_count=link_count+1 WHERE user_id=?", (uid,))

    async def get_all(self, limit=10, offset=0):
        rows = await db.fetch_all("SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
        return [User.from_row(r) for r in rows]

    async def count(self):
        r = await db.fetch_one("SELECT COUNT(*) c FROM users")
        return int(r["c"]) if r else 0

    async def count_banned(self):
        r = await db.fetch_one("SELECT COUNT(*) c FROM users WHERE is_banned=1")
        return int(r["c"]) if r else 0

    async def all_ids(self):
        rows = await db.fetch_all("SELECT user_id FROM users WHERE is_banned=0")
        return [int(r["user_id"]) for r in rows]


class ProfileRepo:
    async def create(self, uid, gender, age, province, city, avatar):
        await db.execute(
            """INSERT INTO profiles (user_id, gender, age, province, city, avatar_url)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 gender=excluded.gender, age=excluded.age,
                 province=excluded.province, city=excluded.city,
                 avatar_url=excluded.avatar_url, updated_at=CURRENT_TIMESTAMP""",
            (uid, gender, age, province, city, avatar),
        )

    async def get(self, uid) -> Optional[Profile]:
        r = await db.fetch_one("SELECT * FROM profiles WHERE user_id=?", (uid,))
        return Profile.from_row(r) if r else None

    async def set_avatar(self, uid, avatar):
        await db.execute("UPDATE profiles SET avatar_url=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (avatar, uid))


class UserSettingsRepo:
    async def ensure(self, uid):
        await db.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (uid,))

    async def get(self, uid):
        await self.ensure(uid)
        r = await db.fetch_one("SELECT * FROM user_settings WHERE user_id=?", (uid,))
        return UserSettings.from_row(r)

    async def toggle(self, uid, field_name):
        await self.ensure(uid)
        if field_name not in ("web_mode", "silent_mode", "copyright_mode", "read_receipt"):
            raise ValueError("invalid")
        await db.execute(f"UPDATE user_settings SET {field_name} = 1 - {field_name} WHERE user_id=?", (uid,))
        r = await db.fetch_one(f"SELECT {field_name} AS v FROM user_settings WHERE user_id=?", (uid,))
        return int(r["v"]) if r else 0


class LinkRepo:
    async def create(self, token, owner, ltype):
        await db.execute("INSERT INTO anonymous_links (token, owner_id, link_type) VALUES (?,?,?)", (token, owner, ltype))

    async def get(self, token):
        r = await db.fetch_one("SELECT * FROM anonymous_links WHERE token=?", (token,))
        return AnonymousLink.from_row(r) if r else None

    async def mark_used(self, token, user):
        await db.execute("UPDATE anonymous_links SET is_used=1, used_at=CURRENT_TIMESTAMP, used_by=? WHERE token=?", (user, token))

    async def delete(self, token):
        await db.execute("DELETE FROM anonymous_links WHERE token=?", (token,))

    async def delete_all_owner(self, uid):
        c = await db.execute("DELETE FROM anonymous_links WHERE owner_id=?", (uid,))
        return c.rowcount or 0

    async def active_of_owner(self, uid):
        rows = await db.fetch_all("SELECT * FROM anonymous_links WHERE owner_id=? ORDER BY created_at DESC", (uid,))
        return [AnonymousLink.from_row(r) for r in rows]

    async def count_active(self):
        r = await db.fetch_one("SELECT COUNT(*) c FROM anonymous_links WHERE link_type='permanent' OR is_used=0")
        return int(r["c"]) if r else 0

    async def count_total(self):
        r = await db.fetch_one("SELECT COUNT(*) c FROM anonymous_links")
        return int(r["c"]) if r else 0

    async def cleanup_onetime(self):
        c = await db.execute("DELETE FROM anonymous_links WHERE link_type='onetime' AND is_used=1")
        return c.rowcount or 0


class MessageRepo:
    async def create(self, owner, sender, token, content, ctype, fid):
        c = await db.execute(
            """INSERT INTO messages (owner_id, sender_id, sender_token, content, content_type, file_id)
               VALUES (?,?,?,?,?,?)""", (owner, sender, token, content, ctype, fid))
        return c.lastrowid or 0

    async def count_total(self):
        r = await db.fetch_one("SELECT COUNT(*) c FROM messages")
        return int(r["c"]) if r else 0

    async def count_for(self, owner):
        r = await db.fetch_one("SELECT COUNT(*) c FROM messages WHERE owner_id=?", (owner,))
        return int(r["c"]) if r else 0


class TargetChatRepo:
    async def create(self, token, creator, target):
        await db.execute("INSERT INTO target_chats (token, creator_id, target_id) VALUES (?,?,?)", (token, creator, target))

    async def get(self, token):
        return await db.fetch_one("SELECT * FROM target_chats WHERE token=? AND active=1", (token,))

    async def deactivate(self, token):
        await db.execute("UPDATE target_chats SET active=0 WHERE token=?", (token,))


class PairingRepo:
    async def create(self, u1, u2):
        c = await db.execute("INSERT INTO pairings (user1_id, user2_id) VALUES (?,?)", (u1, u2))
        return c.lastrowid or 0

    async def active_for(self, uid):
        return await db.fetch_one(
            "SELECT * FROM pairings WHERE active=1 AND (user1_id=? OR user2_id=?) ORDER BY id DESC LIMIT 1",
            (uid, uid))

    async def end(self, pid):
        await db.execute("UPDATE pairings SET active=0, ended_at=CURRENT_TIMESTAMP WHERE id=?", (pid,))

    async def count_total(self):
        r = await db.fetch_one("SELECT COUNT(*) c FROM pairings")
        return int(r["c"]) if r else 0


class AdminLogRepo:
    async def log(self, admin, action, target=None, details=""):
        await db.execute("INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?,?,?,?)",
                         (admin, action, target, details))

    async def recent(self, limit=15):
        return await db.fetch_all("SELECT * FROM admin_logs ORDER BY id DESC LIMIT ?", (limit,))


class SettingsRepo:
    KEY_CH = "required_channel"

    async def get(self, key):
        r = await db.fetch_one("SELECT value FROM settings WHERE key=?", (key,))
        return r["value"] if r else None

    async def set(self, key, value):
        await db.execute(
            """INSERT INTO settings (key, value, updated_at) VALUES (?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP""", (key, value))

    async def delete(self, key):
        await db.execute("DELETE FROM settings WHERE key=?", (key,))

    async def get_required_channel(self): return await self.get(self.KEY_CH)
    async def set_required_channel(self, ch): await self.set(self.KEY_CH, ch)
    async def clear_required_channel(self): await self.delete(self.KEY_CH)


user_repo = UserRepo()
profile_repo = ProfileRepo()
usettings_repo = UserSettingsRepo()
link_repo = LinkRepo()
message_repo = MessageRepo()
target_repo = TargetChatRepo()
pairing_repo = PairingRepo()
admin_log_repo = AdminLogRepo()
settings_repo = SettingsRepo()


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۱۱ — کیبوردها
# ═══════════════════════════════════════════════════════════════════════

def _btn(t, style=None, **kw):
    if STYLE_SUPPORTED and style is not None:
        return KeyboardButton(text=t, style=style, **kw)
    return KeyboardButton(text=t, **kw)


def _ibtn(t, style=None, **kw):
    if STYLE_SUPPORTED and style is not None:
        return InlineKeyboardButton(text=t, style=style, **kw)
    return InlineKeyboardButton(text=t, **kw)


S_PRIMARY = ButtonStyle.PRIMARY if STYLE_SUPPORTED else None
S_SUCCESS = ButtonStyle.SUCCESS if STYLE_SUPPORTED else None
S_DANGER = ButtonStyle.DANGER if STYLE_SUPPORTED else None


def language_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("🇮🇷 فارسی", S_PRIMARY, callback_data="lang:fa")],
        [_ibtn("🇬🇧 English", S_PRIMARY, callback_data="lang:en")],
        [_ibtn("🇸🇦 العربية", S_PRIMARY, callback_data="lang:ar")],
    ])


def rules_kb(lang="fa"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn(t("accept_rules", lang), S_SUCCESS, callback_data="rules:accept")],
        [_ibtn(t("decline_rules", lang), S_DANGER, callback_data="rules:decline")],
    ])


def main_menu_kb(is_admin=False, lang="fa"):
    kb = [
        [_btn("🔗 دریافت لینک ناشناس", S_PRIMARY)],
        [_btn("🎭 اتصال به یک ناشناس", S_PRIMARY)],
        [_btn("👤 اتصال به مخاطب خاص", S_PRIMARY)],
        [_btn("📊 آمار من", S_PRIMARY), _btn("⚙️ تنظیمات من", S_PRIMARY)],
        [_btn("👤 پروفایل من", S_PRIMARY), _btn("🗑 حذف همه لینک‌ها", S_DANGER)],
    ]
    if is_admin:
        kb.append([_btn("👑 پنل ادمین", S_PRIMARY)])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, input_field_placeholder="یک گزینه...")


def admin_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [_btn("📊 آمار کلی", S_PRIMARY), _btn("👥 کاربران", S_PRIMARY)],
        [_btn("📢 پیام همگانی", S_PRIMARY), _btn("📝 لاگ‌ها", S_PRIMARY)],
        [_btn("🔒 کانال اجباری", S_PRIMARY)],
        [_btn("🚫 مدیریت بن‌ها", S_DANGER)],
        [_btn("🗑 پاکسازی لینک‌ها", S_DANGER)],
        [_btn("◀️ بازگشت", S_PRIMARY)],
    ], resize_keyboard=True)


def cancel_kb(cb="global:cancel"):
    return InlineKeyboardMarkup(inline_keyboard=[[_ibtn("❌ لغو", S_DANGER, callback_data=cb)]])


def confirm_kb(action):
    return InlineKeyboardMarkup(inline_keyboard=[[
        _ibtn("✅ بله", S_SUCCESS, callback_data=f"confirm:{action}"),
        _ibtn("❌ انصراف", S_DANGER, callback_data=f"cancel:{action}"),
    ]])


def gender_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("👨 پسر", S_PRIMARY, callback_data="pf:gender:male")],
        [_ibtn("👩 دختر", S_PRIMARY, callback_data="pf:gender:female")],
        [_ibtn("❌ لغو", S_DANGER, callback_data="global:cancel")],
    ])


# ─── انتخاب سن دقیق (بدون دسته‌بندی) ───
AGES_PER_PAGE = 25
AGES_COLS = 5


def age_grid_kb(page: int = 0) -> InlineKeyboardMarkup:
    """
    گرید انتخاب سن دقیق بدون دسته‌بندی.
    هر صفحه ۲۵ سن (۵ ستون × ۵ ردیف).
    صفحه ۰: 9-33 | صفحه ۱: 34-58 | صفحه ۲: 59-83 | صفحه ۳: 84-99
    """
    start = page * AGES_PER_PAGE
    end = min(start + AGES_PER_PAGE, len(ALL_AGES))
    chunk = ALL_AGES[start:end]
    rows = []
    for i in range(0, len(chunk), AGES_COLS):
        row = [_ibtn(str(a), S_PRIMARY, callback_data=f"pf:age:{a}") for a in chunk[i:i + AGES_COLS]]
        rows.append(row)

    # ناوبری صفحه
    nav = []
    if page > 0:
        nav.append(_ibtn("◀️ قبلی", S_PRIMARY, callback_data=f"pf:age_page:{page - 1}"))
    if end < len(ALL_AGES):
        nav.append(_ibtn("بعدی ▶️", S_PRIMARY, callback_data=f"pf:age_page:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([_ibtn("❌ لغو", S_DANGER, callback_data="global:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def provinces_kb(page: int = 0):
    per_page = 8
    total = len(PROVINCES)
    start = page * per_page
    end = min(start + per_page, total)
    rows = []
    for p in PROVINCES[start:end]:
        rows.append([_ibtn(p, S_PRIMARY, callback_data=f"pf:prov:{p}")])
    nav = []
    if page > 0:
        nav.append(_ibtn("◀️ قبلی", S_PRIMARY, callback_data=f"pf:prov_page:{page - 1}"))
    if end < total:
        nav.append(_ibtn("بعدی ▶️", S_PRIMARY, callback_data=f"pf:prov_page:{page + 1}"))
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
    rows = []
    for c in cities[start:end]:
        rows.append([_ibtn(c, S_PRIMARY, callback_data=f"pf:city:{c}")])
    nav = []
    if page > 0:
        nav.append(_ibtn("◀️ قبلی", S_PRIMARY, callback_data=f"pf:city_page:{page - 1}"))
    if end < total:
        nav.append(_ibtn("بعدی ▶️", S_PRIMARY, callback_data=f"pf:city_page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([_ibtn("◀️ بازگشت به استان‌ها", S_PRIMARY, callback_data="pf:back_prov")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── ویرایش آواتار ───
def avatar_edit_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📸 آپلود عکس دلخواه", S_SUCCESS, callback_data="av:upload")],
        [_ibtn("🎲 عکس تصادفی جدید", S_PRIMARY, callback_data="av:random")],
        [_ibtn("◀️ بازگشت", S_PRIMARY, callback_data="av:back")],
    ])


def link_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("♾ لینک دائمی (چندبارمصرف)", S_PRIMARY, callback_data="linktype:permanent")],
        [_ibtn("1️⃣ لینک یکبارمصرف", S_SUCCESS, callback_data="linktype:onetime")],
        [_ibtn("❌ لغو", S_DANGER, callback_data="global:cancel")],
    ])


def link_actions_kb(token, ltype):
    share = f"https://t.me/share/url?url=https://t.me/{Config.BOT_USERNAME}?start={token}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📤 اشتراک‌گذاری", S_SUCCESS, url=share)],
        [_ibtn("🗑 حذف لینک", S_DANGER, callback_data=f"link:del:{token}")],
    ])


def settings_kb(s):
    def m(v): return "🟢" if v else "⚪"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn(f"{m(s.web_mode)} حالت وب", S_PRIMARY, callback_data="uset:toggle:web_mode")],
        [_ibtn(f"{m(s.silent_mode)} حالت سایلنت", S_PRIMARY, callback_data="uset:toggle:silent_mode")],
        [_ibtn(f"{m(s.copyright_mode)} حالت کپی‌رایت", S_PRIMARY, callback_data="uset:toggle:copyright_mode")],
        [_ibtn(f"{m(s.read_receipt)} اعلان مشاهده پیام", S_PRIMARY, callback_data="uset:toggle:read_receipt")],
    ])


def match_menu_kb(filters):
    g = {"male": "👨 پسر", "female": "👩 دختر", "any": "🤷 فرقی ندارد"}[filters["gender"]]
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("🔍 شروع جستجو", S_SUCCESS, callback_data="match:start")],
        [_ibtn(f"🎂 سن: {filters['min_age']}-{filters['max_age']}", S_PRIMARY, callback_data="filter:age")],
        [_ibtn(f"🎭 جنسیت: {g}", S_PRIMARY, callback_data="filter:gender")],
        [_ibtn(f"🏙 همشهری: {'🟢 روشن' if filters['same_city'] else '⚪ خاموش'}", S_PRIMARY, callback_data="filter:city")],
        [_ibtn("❌ لغو", S_DANGER, callback_data="global:cancel")],
    ])


def filter_gender_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("👨 پسر", S_PRIMARY, callback_data="filter:gender:male")],
        [_ibtn("👩 دختر", S_PRIMARY, callback_data="filter:gender:female")],
        [_ibtn("🤷 فرقی ندارد", S_PRIMARY, callback_data="filter:gender:any")],
        [_ibtn("◀️ بازگشت", S_PRIMARY, callback_data="filter:menu")],
    ])


def target_chat_kb(token):
    share = (f"https://t.me/share/url?url=https://t.me/{Config.BOT_USERNAME}?start=tc_{token}"
             f"&text=یک پیام ناشناس برایت دارم")
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📤 اشتراک‌گذاری لینک با مخاطب", S_SUCCESS, url=share)],
        [_ibtn("🗑 لغو این اتصال", S_DANGER, callback_data=f"tc:cancel:{token}")],
    ])


def join_channel_kb(invite_url):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("📢 عضویت در کانال", S_PRIMARY, url=invite_url)],
        [_ibtn("✅ بررسی عضویت", S_SUCCESS, callback_data="check_join")],
    ])


def admin_channel_manage_kb(has):
    rows = [[_ibtn("🔧 تغییر / تنظیم کانال", S_PRIMARY, callback_data="admin_ch:set")]]
    if has:
        rows.append([_ibtn("🗑 حذف کانال", S_DANGER, callback_data="admin_ch:remove")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۱۲ — States
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


class TargetChatStates(StatesGroup):
    waiting_target = State()
    chat_active = State()


class TargetCreatorStates(StatesGroup):
    chatting = State()


class MatchStates(StatesGroup):
    configuring = State()
    searching = State()
    chatting = State()


class AdminStates(StatesGroup):
    broadcasting = State()
    broadcasting_confirm = State()
    setting_channel = State()


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۱۳ — Middlewares
# ═══════════════════════════════════════════════════════════════════════

class BanCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        uid = None
        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            uid = event.from_user.id
        if uid and uid != Config.ADMIN_ID:
            u = await user_repo.get(uid)
            if u and u.is_banned:
                reason = u.ban_reason or "بدون دلیل"
                if isinstance(event, Message):
                    await event.answer(f"🚫 شما بن شده‌اید.\nدلیل: {reason}")
                else:
                    await event.answer("🚫 شما بن شده‌اید.", show_alert=True)
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
        required = await settings_repo.get_required_channel()
        if not required:
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data == "check_join":
            ok = await check_membership(bot, required, uid)
            await event.answer("✅ تأیید شد! حالا /start بزنید." if ok else "❌ هنوز عضو نیستید!", show_alert=True)
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
        text = f"🔒 <b>ورود محدود!</b>\n\nبرای استفاده از ربات، ابتدا در کانال زیر عضو شوید:\n\n📢 <b>{required}</b>"
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
    def __init__(self, max_m, window):
        self.max_m = max_m
        self.window = window
        self._buckets: dict[int, list[datetime]] = {}

    async def __call__(self, handler, event, data):
        state = data.get("state")
        allow_states = {
            AnonymousStates.waiting_message.state,
            MatchStates.chatting.state,
            TargetChatStates.chat_active.state,
            TargetCreatorStates.chatting.state,
        }
        if state is not None:
            try:
                cur = await state.get_state()
                if cur not in allow_states:
                    return await handler(event, data)
            except Exception:
                return await handler(event, data)
        uid = None
        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
        if uid and uid != Config.ADMIN_ID:
            now = datetime.now()
            b = self._buckets.setdefault(uid, [])
            b[:] = [t for t in b if (now - t).total_seconds() < self.window]
            if len(b) >= self.max_m:
                if isinstance(event, Message):
                    await event.answer("⏳ خیلی سریع! چند لحظه صبر کن.")
                return None
            b.append(now)
        return await handler(event, data)


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۱۴ — سرویس‌ها
# ═══════════════════════════════════════════════════════════════════════

class AuthService:
    async def ensure(self, uid, fn, un):
        if not await user_repo.exists(uid):
            await user_repo.create(uid, fn, un)
            return True
        await user_repo.update_profile(uid, fn, un)
        return False


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
        if link.link_type == "onetime" and link.is_used:
            return False, None, "این لینک قبلاً استفاده شده"
        return True, link, ""

    async def consume(self, token, uid, ltype):
        if ltype == "onetime":
            await link_repo.mark_used(token, uid)


class MessageService:
    async def send(self, bot, owner, sender, token, ctype, content, fid):
        await message_repo.create(owner, sender, token, content, ctype, fid)
        await user_repo.inc_msg(owner)
        header = f"📩 <b>پیام ناشناس جدید</b>\n🕐 {fa_now_str()}\n────────────\n"
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
            return {"ok": False, "error": "مالک ربات را بلاک کرده"}
        except Exception as e:
            log.exception("send_anon: %s", e)
            return {"ok": False, "error": "خطای ارسال"}
        return {"ok": True}


class MatchService:
    def __init__(self):
        self.queue: list[dict] = []

    async def find_or_queue(self, uid, filters, profile):
        self.queue = [q for q in self.queue if q["user_id"] != uid]
        for i, q in enumerate(self.queue):
            if self._compatible(filters, profile, q["filters"], q["profile"]):
                partner = self.queue.pop(i)
                return partner["user_id"]
        self.queue.append({"user_id": uid, "filters": filters, "profile": profile})
        return None

    def cancel(self, uid):
        self.queue = [q for q in self.queue if q["user_id"] != uid]

    @staticmethod
    def _compatible(f1, p1, f2, p2):
        if not (f1["min_age"] <= p2["age"] <= f1["max_age"]): return False
        if not (f2["min_age"] <= p1["age"] <= f2["max_age"]): return False
        if f1["gender"] != "any" and f1["gender"] != p2["gender"]: return False
        if f2["gender"] != "any" and f2["gender"] != p1["gender"]: return False
        if f1["same_city"] and p1["city"] != p2["city"]: return False
        if f2["same_city"] and p1["city"] != p2["city"]: return False
        return True


class AdminService:
    async def stats(self):
        return {
            "users": await user_repo.count(),
            "banned": await user_repo.count_banned(),
            "links": await link_repo.count_total(),
            "active_links": await link_repo.count_active(),
            "messages": await message_repo.count_total(),
            "pairings": await pairing_repo.count_total(),
            "channel": (await settings_repo.get_required_channel()) or "—",
        }

    async def broadcast(self, bot, chat_id, msg_id, users):
        s, f = 0, 0
        for uid in users:
            try:
                await bot.copy_message(uid, chat_id, msg_id)
                s += 1
            except Exception:
                f += 1
            await asyncio.sleep(0.05)
        return {"success": s, "failed": f}


auth_svc = AuthService()
link_svc = LinkService()
message_svc = MessageService()
match_svc = MatchService()
admin_svc = AdminService()


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۱۵ — Routers و هندلرها
# ═══════════════════════════════════════════════════════════════════════

common_router = Router()
lang_router = Router()
rules_router = Router()
profile_router = Router()
avatar_router = Router()
settings_router = Router()
link_router = Router()
anon_router = Router()
target_router = Router()
match_router = Router()
admin_router = Router()


# ─────────────────────────────────────────────────────────────────────
# زبان و قوانین
# ─────────────────────────────────────────────────────────────────────

@lang_router.callback_query(F.data.startswith("lang:"))
async def cb_lang(cb: CallbackQuery, state: FSMContext):
    lang = cb.data.split(":")[1]
    await user_repo.set_language(cb.from_user.id, lang)
    await state.update_data(lang=lang)
    await cb.answer(t("lang_set", lang) if "lang_set" in TRANSLATIONS.get(lang, {}) else "✅")

    text = with_footer(f"{t('welcome_title', lang)}\n<i>{t('welcome_sub', lang)}</i>\n\n{get_rules(lang)}")
    try:
        await cb.message.edit_text(text, reply_markup=rules_kb(lang))
    except TelegramBadRequest:
        pass
    await state.set_state(RulesStates.showing)


@rules_router.callback_query(F.data == "rules:accept", RulesStates.showing)
async def cb_rules_accept(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "fa")
    await user_repo.set_rules_accepted(cb.from_user.id)
    await state.clear()

    profile = await profile_repo.get(cb.from_user.id)
    if not profile:
        await state.set_state(ProfileStates.gender)
        try:
            await cb.message.edit_text(
                with_footer("👋 <b>خوش آمدی!</b>\n\n1️⃣ <b>جنسیتت را انتخاب کن:</b>"),
                reply_markup=gender_kb(),
            )
        except TelegramBadRequest:
            pass
    else:
        try:
            await cb.message.edit_text(
                with_footer(t("main_menu", lang)),
                reply_markup=main_menu_kb(cb.from_user.id == Config.ADMIN_ID, lang),
            )
        except TelegramBadRequest:
            pass
    await cb.answer("✅")


@rules_router.callback_query(F.data == "rules:decline", RulesStates.showing)
async def cb_rules_decline(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "fa")
    await state.clear()
    try:
        await cb.message.edit_text(with_footer("😔 برای استفاده باید قوانین را بپذیری. /start"))
    except TelegramBadRequest:
        pass
    await cb.answer("😔")


# ─────────────────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────────────────

@common_router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext, bot: Bot):
    await state.clear()
    uid = message.from_user.id
    await auth_svc.ensure(uid, message.from_user.full_name, message.from_user.username)
    payload = (command.args or "").strip()
    user = await user_repo.get(uid)
    lang = user.language if user else "fa"

    if not user or not user.rules_accepted:
        await state.set_state(LangStates.choosing)
        await message.answer(
            with_footer("🌍 <b>زبان خود را انتخاب کنید / Choose language / اختر لغتك:</b>"),
            reply_markup=language_kb(),
        )
        return

    if payload.startswith("tc_"):
        token = payload[3:]
        tc = await target_repo.get(token)
        if not tc:
            await message.answer(with_footer("❌ این لینک منقضی یا نامعتبر است."))
            return
        if tc["target_id"] != uid:
            await message.answer("❌ این لینک برای شما نیست.")
            return
        profile = await profile_repo.get(uid)
        if not profile:
            await message.answer("⚠️ ابتدا باید پروفایل بسازی. /start")
            return
        await state.update_data(tc_creator=tc["creator_id"], tc_token=token)
        await state.set_state(TargetChatStates.chat_active)
        await message.answer(
            with_footer("🔒 <b>چت ناشناس با مخاطب خاص</b>\n\nبرای پایان: /endchat"),
            reply_markup=ReplyKeyboardRemove(),
        )
        try:
            await bot.send_message(tc["creator_id"], with_footer("🔔 <b>مخاطب خاص شما وارد چت شد!</b>"))
        except Exception:
            pass
        return

    if payload:
        ok, link, err = await link_svc.validate(payload)
        if not ok:
            await message.answer(with_footer(f"❌ {err}"), reply_markup=ReplyKeyboardRemove())
            return
        if link.owner_id == uid:
            await message.answer("🙂 نمی‌توانی به خودت پیام بفرستی.")
            return
        profile = await profile_repo.get(uid)
        if not profile:
            await message.answer("⚠️ ابتدا باید پروفایل بسازی. /start")
            return
        await state.update_data(token=payload, owner_id=link.owner_id, link_type=link.link_type)
        await state.set_state(AnonymousStates.waiting_message)
        await message.answer(
            with_footer("📩 <b>ارسال پیام ناشناس</b>\n\nپیام خود را بفرست:"),
            reply_markup=cancel_kb("anon:cancel"),
        )
        return

    profile = await profile_repo.get(uid)
    if not profile:
        await state.set_state(ProfileStates.gender)
        await message.answer(
            with_footer(
                "👋 <b>خوش آمدی!</b> 🎉\n\n"
                "برای شروع، پروفایلت را بساز:\n\n"
                "1️⃣ <b>جنسیتت را انتخاب کن:</b>"
            ),
            reply_markup=gender_kb(),
        )
        return

    await message.answer(
        with_footer(t("main_menu", lang)),
        reply_markup=main_menu_kb(uid == Config.ADMIN_ID, lang),
    )


@common_router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(with_footer(
        "❓ <b>راهنما</b>\n\n"
        "🔗 <b>لینک ناشناس:</b> لینک دائمی یا یکبارمصرف بساز.\n"
        "🎭 <b>اتصال به ناشناس:</b> با فیلتر سن/جنسیت/همشهری چت کن.\n"
        "👤 <b>مخاطب خاص:</b> به یک نفر خاص ناشناس پیام بده.\n"
        "⚙️ <b>تنظیمات:</b> حالت وب، سایلنت، کپی‌رایت، اعلان.\n"
        "👤 <b>پروفایل:</b> مشاهده/ویرایش پروفایل + عکس.\n\n"
        "دستورات: /start /help /cancel /profile /endchat"
    ))


@common_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    match_svc.cancel(message.from_user.id)
    await state.clear()
    user = await user_repo.get(message.from_user.id)
    lang = user.language if user else "fa"
    await message.answer(
        with_footer("❌ عملیات لغو شد."),
        reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID, lang),
    )


@common_router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext):
    await state.clear()
    await _show_profile(message)


@common_router.message(Command("endchat"))
async def cmd_endchat(message: Message, state: FSMContext, bot: Bot):
    uid = message.from_user.id
    cur = await state.get_state()
    data = await state.get_data()
    user = await user_repo.get(uid)
    lang = user.language if user else "fa"

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
        await message.answer(with_footer("🚪 چت پایان یافت."), reply_markup=main_menu_kb(uid == Config.ADMIN_ID, lang))
        return

    if cur == TargetChatStates.chat_active.state:
        token = data.get("tc_token")
        creator = data.get("tc_creator")
        if token: await target_repo.deactivate(token)
        if creator:
            try:
                await bot.send_message(creator, with_footer("🚪 مخاطب چت را پایان داد."))
            except Exception:
                pass
        await state.clear()
        await message.answer(with_footer("🚪 چت پایان یافت."), reply_markup=main_menu_kb(uid == Config.ADMIN_ID, lang))
        return

    if cur == TargetCreatorStates.chatting.state:
        token = data.get("tc_token_creator")
        target = data.get("tc_target")
        if token: await target_repo.deactivate(token)
        if target:
            try:
                await bot.send_message(target, with_footer("🚪 سازنده چت را پایان داد."))
            except Exception:
                pass
        await state.clear()
        await message.answer(with_footer("🚪 چت پایان یافت."), reply_markup=main_menu_kb(uid == Config.ADMIN_ID, lang))
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


# ─────────────────────────────────────────────────────────────────────
# پروفایل — انتخاب جنسیت، سن دقیق، استان، شهر
# ─────────────────────────────────────────────────────────────────────

@profile_router.callback_query(F.data.startswith("pf:gender:"), ProfileStates.gender)
async def pf_gender(cb: CallbackQuery, state: FSMContext):
    g = cb.data.split(":")[2]
    await state.update_data(gender=g)
    await state.set_state(ProfileStates.age)
    try:
        await cb.message.edit_text(
            with_footer(
                "2️⃣ <b>سن دقیق خود را انتخاب کن</b>\n\n"
                "👆 از بین دکمه‌های زیر، سن واقعی خودت را انتخاب کن (۹ تا ۹۹ سال)."
            ),
            reply_markup=age_grid_kb(0),
        )
    except TelegramBadRequest:
        pass
    await cb.answer()


@profile_router.callback_query(F.data.startswith("pf:age_page:"), ProfileStates.age)
async def pf_age_page(cb: CallbackQuery, state: FSMContext):
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
            with_footer(f"✅ سن: <b>{age} سال</b>\n\n3️⃣ <b>استان خود را انتخاب کن:</b>"),
            reply_markup=provinces_kb(0),
        )
    except TelegramBadRequest:
        pass
    await cb.answer()


@profile_router.callback_query(F.data.startswith("pf:prov_page:"), ProfileStates.province)
async def pf_prov_page(cb: CallbackQuery, state: FSMContext):
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
        await cb.message.edit_text(
            with_footer("3️⃣ <b>استان خود را انتخاب کن:</b>"),
            reply_markup=provinces_kb(0),
        )
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
            with_footer(f"4️⃣ <b>شهر خود را انتخاب کن</b> ({province}):"),
            reply_markup=cities_kb(province, 0),
        )
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
    # ساخت آواتار خوشگل با seed اختصاصی
    seed = f"{cb.from_user.id}-{random.randint(1, 999999)}"
    avatar = avatar_url(gender, seed)

    await profile_repo.create(cb.from_user.id, gender, age, province, city, avatar)
    await state.clear()

    gender_fa = "پسر 👨" if gender == "male" else "دختر 👩"
    user = await user_repo.get(cb.from_user.id)
    lang = user.language if user else "fa"

    caption = with_footer(
        f"🎉 <b>پروفایل شما با موفقیت ساخته شد!</b> ✨\n\n"
        f"👤 جنسیت: <b>{gender_fa}</b>\n"
        f"🎂 سن: <b>{age} سال</b>\n"
        f"🗺 استان: <b>{province}</b>\n"
        f"🏙 شهر: <b>{city}</b>\n\n"
        f"💡 برای تغییر عکس پروفایل، به «👤 پروفایل من» برو."
    )

    try:
        await bot.send_photo(cb.from_user.id, avatar, caption=caption)
    except Exception:
        await cb.message.answer(caption)

    try:
        await cb.message.delete()
    except Exception:
        pass

    await cb.message.answer(
        with_footer(t("main_menu", lang)),
        reply_markup=main_menu_kb(cb.from_user.id == Config.ADMIN_ID, lang),
    )
    await cb.answer("✅")


# ─────────────────────────────────────────────────────────────────────
# نمایش پروفایل + ویرایش آواتار
# ─────────────────────────────────────────────────────────────────────

async def _show_profile(message: Message):
    uid = message.from_user.id
    p = await profile_repo.get(uid)
    if not p:
        await message.answer(with_footer("❌ هنوز پروفایل نساختی. /start بزن."))
        return
    gender_fa = "پسر 👨" if p.gender == "male" else "دختر 👩"
    text = with_footer(
        "👤 <b>پروفایل شما</b>\n\n"
        f"🎭 جنسیت: <b>{gender_fa}</b>\n"
        f"🎂 سن: <b>{p.age} سال</b>\n"
        f"🗺 استان: <b>{p.province}</b>\n"
        f"🏙 شهر: <b>{p.city}</b>\n"
        f"📅 ساخت: <b>{p.created_at[:10]}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [_ibtn("✏️ ویرایش اطلاعات", S_PRIMARY, callback_data="pf:edit")],
        [_ibtn("🎨 تغییر عکس پروفایل", S_SUCCESS, callback_data="av:edit")],
    ])

    # ارسال آواتار
    if p.avatar_url:
        try:
            if is_custom_avatar(p.avatar_url):
                fid = extract_file_id(p.avatar_url)
                await message.answer_photo(fid, caption=text, reply_markup=kb)
            else:
                await message.answer_photo(p.avatar_url, caption=text, reply_markup=kb)
            return
        except Exception as e:
            log.warning("خطا در ارسال آواتار: %s", e)
    await message.answer(text, reply_markup=kb)


@common_router.message(F.text == "👤 پروفایل من")
async def show_profile_btn(message: Message):
    await _show_profile(message)


@common_router.callback_query(F.data == "pf:edit")
async def cb_pf_edit(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileStates.gender)
    await cb.message.answer(
        with_footer("✏️ <b>ویرایش پروفایل</b>\n\n1️⃣ جنسیت را انتخاب کن:"),
        reply_markup=gender_kb(),
    )
    await cb.answer()


# ─── ویرایش آواتار ───
@avatar_router.callback_query(F.data == "av:edit")
async def cb_av_edit(cb: CallbackQuery):
    await cb.message.answer(
        with_footer(
            "🎨 <b>تغییر عکس پروفایل</b>\n\n"
            "💡 یک روش را انتخاب کن:\n\n"
            "📸 <b>آپلود عکس دلخواه:</b> هر عکسی که دوست داری آپلود کن.\n"
            "🎲 <b>عکس تصادفی جدید:</b> یک کاراکتر کارتونی تازه بساز."
        ),
        reply_markup=avatar_edit_kb(),
    )
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
    new_avatar = avatar_url(p.gender, seed)
    await profile_repo.set_avatar(cb.from_user.id, new_avatar)
    try:
        await cb.message.delete()
    except Exception:
        pass
    try:
        await bot.send_photo(
            cb.from_user.id, new_avatar,
            caption=with_footer("🎲 <b>عکس پروفایل جدید ساخته شد!</b> ✨"),
        )
    except Exception:
        pass
    await cb.answer("✅ عکس جدید ساخته شد")


@avatar_router.callback_query(F.data == "av:upload")
async def cb_av_upload(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarStates.uploading)
    try:
        await cb.message.edit_text(
            with_footer(
                "📸 <b>آپلود عکس پروفایل</b>\n\n"
                "عکس مورد نظرت را به‌صورت عکس (نه فایل) بفرست.\n"
                "⚠️ فقط عکس‌ها پذیرفته می‌شوند.\n\n"
                "برای لغو: /cancel"
            ),
            reply_markup=cancel_kb("global:cancel"),
        )
    except TelegramBadRequest:
        pass
    await cb.answer()


@avatar_router.message(AvatarStates.uploading, F.photo)
async def av_upload_photo(message: Message, state: FSMContext):
    fid = message.photo[-1].file_id
    await profile_repo.set_avatar(message.from_user.id, f"file:{fid}")
    await state.clear()
    try:
        await message.answer_photo(
            fid,
            caption=with_footer("✅ <b>عکس پروفایل شما با موفقیت تغییر کرد!</b> 🎉"),
        )
    except Exception:
        await message.answer(with_footer("✅ عکس پروفایل تغییر کرد."))


@avatar_router.message(AvatarStates.uploading)
async def av_upload_invalid(message: Message):
    await message.answer("⚠️ فقط عکس بفرست (به‌صورت Photo، نه فایل).")


# ─────────────────────────────────────────────────────────────────────
# تنظیمات کاربر
# ─────────────────────────────────────────────────────────────────────

@settings_router.message(F.text == "⚙️ تنظیمات من")
async def user_settings_menu(message: Message):
    s = await usettings_repo.get(message.from_user.id)
    await message.answer(
        with_footer("⚙️ <b>تنظیمات من</b>\n\nهر گزینه را لمس کن:"),
        reply_markup=settings_kb(s),
    )


@settings_router.callback_query(F.data.startswith("uset:toggle:"))
async def cb_uset_toggle(cb: CallbackQuery):
    field = cb.data.split(":")[2]
    await usettings_repo.toggle(cb.from_user.id, field)
    s = await usettings_repo.get(cb.from_user.id)
    try:
        await cb.message.edit_reply_markup(reply_markup=settings_kb(s))
    except TelegramBadRequest:
        pass
    labels = {"web_mode": "حالت وب", "silent_mode": "حالت سایلنت",
              "copyright_mode": "حالت کپی‌رایت", "read_receipt": "اعلان مشاهده"}
    val = getattr(s, field)
    await cb.answer(f"{labels[field]}: {'روشن ✅' if val else 'خاموش ❌'}")


# ─────────────────────────────────────────────────────────────────────
# لینک ناشناس
# ─────────────────────────────────────────────────────────────────────

@link_router.message(F.text == "🔗 دریافت لینک ناشناس")
async def link_menu(message: Message, state: FSMContext):
    await state.set_state(LinkStates.choosing_type)
    await message.answer(
        with_footer("🔗 <b>نوع لینک را انتخاب کن:</b>\n\n♾ دائمی | 1️⃣ یکبارمصرف"),
        reply_markup=link_type_kb(),
    )


@link_router.callback_query(F.data.startswith("linktype:"), LinkStates.choosing_type)
async def cb_linktype(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    v = cb.data.split(":")[1]
    ltype = "permanent" if v == "permanent" else "onetime"
    r = await link_svc.create(cb.from_user.id, ltype)
    if not r["ok"]:
        await cb.answer(r["error"], show_alert=True)
        return
    label = "♾ دائمی" if ltype == "permanent" else "1️⃣ یکبارمصرف"
    warn = "🔓 چندبارمصرف" if ltype == "permanent" else "⚠️ فقط یکبار"
    text = with_footer(f"✅ <b>لینک آماده ({label})</b>\n\n🔗 <code>{r['link']}</code>\n\n{warn}")
    try:
        await cb.message.edit_text(text, reply_markup=link_actions_kb(r["token"], ltype))
    except TelegramBadRequest:
        await cb.message.answer(text, reply_markup=link_actions_kb(r["token"], ltype))
    await cb.answer("✅")


@link_router.callback_query(F.data.startswith("link:del:"))
async def cb_link_del(cb: CallbackQuery):
    token = cb.data.split(":", 2)[2]
    l = await link_repo.get(token)
    if not l or l.owner_id != cb.from_user.id:
        await cb.answer("❌ دسترسی ندارید", show_alert=True)
        return
    await link_repo.delete(token)
    try:
        await cb.message.edit_text(with_footer("🗑 لینک حذف شد."), reply_markup=None)
    except TelegramBadRequest:
        pass
    await cb.answer("✅")


@common_router.message(F.text == "🗑 حذف همه لینک‌ها")
async def del_all_links(message: Message):
    n = await link_repo.delete_all_owner(message.from_user.id)
    user = await user_repo.get(message.from_user.id)
    lang = user.language if user else "fa"
    await message.answer(
        with_footer(f"🗑 <b>{n}</b> لینک حذف شد."),
        reply_markup=main_menu_kb(message.from_user.id == Config.ADMIN_ID, lang),
    )


@common_router.message(F.text == "📊 آمار من")
async def my_stats(message: Message):
    uid = message.from_user.id
    p = await profile_repo.get(uid)
    msgs = await message_repo.count_for(uid)
    links = await link_repo.active_of_owner(uid)
    perm = sum(1 for l in links if l.link_type == "permanent")
    once = sum(1 for l in links if l.link_type == "onetime")
    text = with_footer(
        "📊 <b>آمار شما</b>\n\n"
        f"📨 پیام‌های دریافتی: <b>{msgs}</b>\n"
        f"♾ لینک‌های دائمی: <b>{perm}</b>\n"
        f"1️⃣ لینک‌های یکبارمصرف: <b>{once}</b>\n"
        + (f"\n🎂 سن: {p.age} | 🏙 {p.city}" if p else "")
    )
    user = await user_repo.get(uid)
    lang = user.language if user else "fa"
    await message.answer(text, reply_markup=main_menu_kb(uid == Config.ADMIN_ID, lang))


# ─────────────────────────────────────────────────────────────────────
# پیام ناشناس
# ─────────────────────────────────────────────────────────────────────

@anon_router.message(AnonymousStates.waiting_message)
async def anon_recv(message: Message, state: FSMContext):
    ctype, fid, content = "text", None, None
    if message.text:
        content = sanitize_text(message.text)
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
    await state.update_data(prev_t=ctype, prev_f=fid, prev_c=content)
    await state.set_state(AnonymousStates.confirm_send)
    await message.answer(
        with_footer("📝 پیش‌نمایش آماده است. ارسال شود؟"),
        reply_markup=confirm_kb("anon"),
    )


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
        await cb.answer("❌ خطا", show_alert=True)
        return
    ok, l, err = await link_svc.validate(token)
    if not ok:
        await state.clear()
        await cb.answer(f"❌ {err}", show_alert=True)
        return
    r = await message_svc.send(bot, owner, cb.from_user.id, token, data["prev_t"], data["prev_c"], data["prev_f"])
    if not r["ok"]:
        await cb.answer(f"❌ {r['error']}", show_alert=True)
        return
    await link_svc.consume(token, cb.from_user.id, ltype)
    await state.clear()
    txt = "✅ پیام ارسال شد."
    if ltype == "permanent":
        txt += "\n♾ لینک همچنان فعال است."
    try:
        await cb.message.edit_text(with_footer(txt))
    except TelegramBadRequest:
        await cb.message.answer(with_footer(txt))
    await cb.answer("✅")


# ─────────────────────────────────────────────────────────────────────
# مخاطب خاص
# ─────────────────────────────────────────────────────────────────────

@target_router.message(F.text == "👤 اتصال به مخاطب خاص")
async def target_start(message: Message, state: FSMContext):
    await state.set_state(TargetChatStates.waiting_target)
    await message.answer(
        with_footer(
            "👤 <b>اتصال به مخاطب خاص</b>\n\n"
            "1️⃣ <b>آیدی عددی</b> مخاطب را بفرست\n"
            "2️⃣ یا <b>یک پیام از مخاطبت را فوروارد کن</b>"
        ),
        reply_markup=cancel_kb("global:cancel"),
    )


@target_router.message(TargetChatStates.waiting_target)
async def target_receive(message: Message, state: FSMContext):
    target_id = None
    if message.forward_from:
        target_id = message.forward_from.id
    elif message.forward_from_chat:
        await message.answer("⚠️ فوروارد از کانال پشتیبانی نمی‌شود.")
        return
    elif message.text and re.match(r"^\d{5,15}$", message.text.strip()):
        target_id = int(message.text.strip())
    else:
        await message.answer("⚠️ فرمت نامعتبر.")
        return
    if target_id == message.from_user.id:
        await message.answer("🙂 نمی‌توانی به خودت پیام بفرستی.")
        return
    token = generate_secure_token()
    await target_repo.create(token, message.from_user.id, target_id)
    await state.update_data(tc_token_creator=token, tc_target=target_id)
    await state.set_state(TargetCreatorStates.chatting)
    await message.answer(
        with_footer(
            f"✅ <b>اتصال ساخته شد!</b>\n\n"
            f"این لینک را بفرست:\n\n"
            f"🔗 <code>https://t.me/{Config.BOT_USERNAME}?start=tc_{token}</code>"
        ),
        reply_markup=target_chat_kb(token),
    )


@target_router.callback_query(F.data.startswith("tc:cancel:"))
async def cb_tc_cancel(cb: CallbackQuery, state: FSMContext):
    token = cb.data.split(":", 2)[2]
    await target_repo.deactivate(token)
    await state.clear()
    try:
        await cb.message.edit_text(with_footer("🗑 اتصال لغو شد."), reply_markup=None)
    except TelegramBadRequest:
        pass
    await cb.answer("✅")


@target_router.message(TargetChatStates.chat_active, F.text | F.photo | F.voice | F.video | F.document | F.sticker)
async def target_chat_msg(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    creator = data.get("tc_creator")
    if not creator:
        await state.clear()
        return
    try:
        await message.copy_to(creator)
    except Exception as e:
        log.exception("target_chat: %s", e)


@target_router.message(TargetCreatorStates.chatting, F.text | F.photo | F.voice | F.video | F.document | F.sticker)
async def target_creator_msg(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target = data.get("tc_target")
    token = data.get("tc_token_creator")
    if not target or not token:
        await state.clear()
        return
    tc = await target_repo.get(token)
    if not tc:
        await message.answer("⚠️ این اتصال منقضی شده.")
        await state.clear()
        return
    try:
        await message.copy_to(target)
    except Exception as e:
        log.exception("target_creator: %s", e)


# ─────────────────────────────────────────────────────────────────────
# اتصال به ناشناس
# ─────────────────────────────────────────────────────────────────────

async def _ensure_filters(state: FSMContext, uid: int):
    data = await state.get_data()
    if "filters" not in data:
        p = await profile_repo.get(uid)
        age = p.age if p else 25
        data["filters"] = {
            "min_age": max(9, age - 10),
            "max_age": min(99, age + 10),
            "gender": "any",
            "same_city": False,
        }
        await state.update_data(filters=data["filters"])
    return data["filters"]


@match_router.message(F.text == "🎭 اتصال به یک ناشناس")
async def match_menu(message: Message, state: FSMContext):
    uid = message.from_user.id
    p = await profile_repo.get(uid)
    if not p:
        await message.answer("⚠️ ابتدا پروفایل بساز. /start")
        return
    filters = await _ensure_filters(state, uid)
    await state.set_state(MatchStates.configuring)
    await message.answer(
        with_footer("🎭 <b>اتصال به یک ناشناس</b>\n\nفیلترها را تنظیم کن:"),
        reply_markup=match_menu_kb(filters),
    )


@match_router.callback_query(F.data == "filter:age")
async def cb_filter_age(cb: CallbackQuery, state: FSMContext):
    await state.update_data(awaiting_age=True)
    await cb.message.edit_text(
        with_footer("🎂 <b>محدوده سنی</b>\n\n<code>20-30</code> بفرست."),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [_ibtn("◀️ بازگشت", S_PRIMARY, callback_data="filter:menu")]]),
    )
    await cb.answer()


@match_router.message(MatchStates.configuring, F.text.regexp(r"^\d{1,2}\s*-\s*\d{1,2}$"))
async def match_age_input(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("awaiting_age"):
        return
    lo_s, hi_s = re.split(r"\s*-\s*", message.text.strip())
    lo, hi = int(lo_s), int(hi_s)
    if not (9 <= lo <= 99 and 9 <= hi <= 99 and lo <= hi):
        await message.answer("⚠️ محدوده نامعتبر. مثال: <code>20-30</code>")
        return
    filters = data.get("filters") or {}
    filters["min_age"] = lo
    filters["max_age"] = hi
    await state.update_data(filters=filters, awaiting_age=False)
    await message.answer(with_footer(f"✅ سن: <b>{lo} تا {hi}</b>"), reply_markup=match_menu_kb(filters))


@match_router.callback_query(F.data == "filter:gender")
async def cb_filter_gender(cb: CallbackQuery):
    await cb.message.edit_text(with_footer("🎭 <b>جنسیت مورد نظر:</b>"), reply_markup=filter_gender_kb())
    await cb.answer()


@match_router.callback_query(F.data.startswith("filter:gender:"))
async def cb_filter_gender_set(cb: CallbackQuery, state: FSMContext):
    g = cb.data.split(":")[2]
    filters = await _ensure_filters(state, cb.from_user.id)
    filters["gender"] = g
    await state.update_data(filters=filters)
    await cb.message.edit_text(with_footer("🎭 <b>اتصال به یک ناشناس</b>"), reply_markup=match_menu_kb(filters))
    await cb.answer()


@match_router.callback_query(F.data == "filter:city")
async def cb_filter_city(cb: CallbackQuery, state: FSMContext):
    filters = await _ensure_filters(state, cb.from_user.id)
    filters["same_city"] = not filters["same_city"]
    await state.update_data(filters=filters)
    await cb.message.edit_text(with_footer("🎭 <b>اتصال به یک ناشناس</b>"), reply_markup=match_menu_kb(filters))
    await cb.answer(f"همشهری: {'روشن' if filters['same_city'] else 'خاموش'}")


@match_router.callback_query(F.data == "filter:menu")
async def cb_filter_menu(cb: CallbackQuery, state: FSMContext):
    filters = await _ensure_filters(state, cb.from_user.id)
    await state.update_data(awaiting_age=False)
    await cb.message.edit_text(with_footer("🎭 <b>اتصال به یک ناشناس</b>"), reply_markup=match_menu_kb(filters))
    await cb.answer()


@match_router.callback_query(F.data == "match:start")
async def cb_match_start(cb: CallbackQuery, state: FSMContext, bot: Bot):
    uid = cb.from_user.id
    p = await profile_repo.get(uid)
    if not p:
        await cb.answer("❌ ابتدا پروفایل بساز.", show_alert=True)
        return
    filters = await _ensure_filters(state, uid)
    profile_dict = {"gender": p.gender, "age": p.age, "city": p.city}
    partner_id = await match_svc.find_or_queue(uid, filters, profile_dict)
    if partner_id is None:
        await state.set_state(MatchStates.searching)
        try:
            await cb.message.edit_text(
                with_footer("🔍 <b>در حال جستجو...</b>"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [_ibtn("❌ لغو جستجو", S_DANGER, callback_data="match:cancel_search")]]),
            )
        except TelegramBadRequest:
            pass
        await cb.answer("🔍")
        return
    pid = await pairing_repo.create(uid, partner_id)
    await state.set_state(MatchStates.chatting)
    await state.update_data(pairing_id=pid, partner_id=partner_id)
    for target_uid in (uid, partner_id):
        try:
            await bot.send_message(target_uid, with_footer("🎉 <b>یک ناشناس پیدا شد!</b>\n\n/endchat برای پایان"),
                                    reply_markup=ReplyKeyboardRemove())
        except Exception:
            pass
    try:
        await cb.message.edit_text(with_footer("✅ <b>یک ناشناس پیدا شد!</b>"))
    except TelegramBadRequest:
        pass
    await cb.answer("🎉")


@match_router.callback_query(F.data == "match:cancel_search")
async def cb_match_cancel(cb: CallbackQuery, state: FSMContext):
    match_svc.cancel(cb.from_user.id)
    filters = await _ensure_filters(state, cb.from_user.id)
    await state.set_state(MatchStates.configuring)
    try:
        await cb.message.edit_text(with_footer("❌ جستجو لغو شد."), reply_markup=match_menu_kb(filters))
    except TelegramBadRequest:
        pass
    await cb.answer()


@match_router.message(MatchStates.chatting, F.text | F.photo | F.voice | F.video | F.document | F.sticker)
async def match_chat_relay(message: Message, state: FSMContext, bot: Bot):
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


# ─────────────────────────────────────────────────────────────────────
# ادمین
# ─────────────────────────────────────────────────────────────────────

@admin_router.message(F.text == "👑 پنل ادمین")
async def admin_panel(message: Message):
    if message.from_user.id != Config.ADMIN_ID: return
    await message.answer(with_footer("👑 <b>پنل مدیریت</b>"), reply_markup=admin_menu_kb())


@admin_router.message(F.text == "◀️ بازگشت")
async def admin_back(message: Message):
    if message.from_user.id != Config.ADMIN_ID: return
    await message.answer(with_footer("🏠 منوی اصلی"), reply_markup=main_menu_kb(True))


@admin_router.message(F.text == "📊 آمار کلی")
async def admin_stats(message: Message):
    if message.from_user.id != Config.ADMIN_ID: return
    s = await admin_svc.stats()
    await message.answer(
        with_footer(
            "📊 <b>آمار کلی</b>\n\n"
            f"👥 کاربران: <b>{s['users']}</b>\n"
            f"🚫 بن: <b>{s['banned']}</b>\n"
            f"🔗 لینک: <b>{s['links']}</b> (فعال: {s['active_links']})\n"
            f"📨 پیام: <b>{s['messages']}</b>\n"
            f"🤝 مچ: <b>{s['pairings']}</b>\n"
            f"🔒 کانال: <b>{s['channel']}</b>"
        ),
        reply_markup=admin_menu_kb(),
    )


@admin_router.message(F.text == "👥 کاربران")
async def admin_users(message: Message):
    if message.from_user.id != Config.ADMIN_ID: return
    users = await user_repo.get_all(10)
    lines = ["👥 <b>آخرین ۱۰ کاربر</b>\n"]
    for u in users:
        st = "🚫" if u.is_banned else "✅"
        lines.append(f"{st} <code>{u.user_id}</code> — {u.full_name or '—'}")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_router.message(F.text == "📝 لاگ‌ها")
async def admin_logs(message: Message):
    if message.from_user.id != Config.ADMIN_ID: return
    logs = await admin_log_repo.recent(10)
    if not logs:
        await message.answer(with_footer("لاگی نیست."), reply_markup=admin_menu_kb())
        return
    lines = ["📝 <b>۱۰ لاگ آخر</b>\n"]
    for r in logs:
        lines.append(f"• [{r['created_at'][11:16]}] {r['action']} → {r['target_id'] or '-'}")
    await message.answer(with_footer("\n".join(lines)), reply_markup=admin_menu_kb())


@admin_router.message(F.text == "🗑 پاکسازی لینک‌ها")
async def admin_cleanup(message: Message):
    if message.from_user.id != Config.ADMIN_ID: return
    n = await link_repo.cleanup_onetime()
    await admin_log_repo.log(Config.ADMIN_ID, "cleanup_links", None, str(n))
    await message.answer(with_footer(f"🗑 <b>{n}</b> لینک حذف شد."), reply_markup=admin_menu_kb())


@admin_router.message(F.text == "🔒 کانال اجباری")
async def admin_channel(message: Message):
    if message.from_user.id != Config.ADMIN_ID: return
    ch = await settings_repo.get_required_channel()
    text = f"🔒 <b>کانال اجباری</b>\n\nکانال: <code>{ch}</code>" if ch else "🔒 <b>کانال اجباری</b>\n\n❗ تنظیم نشده"
    await message.answer(with_footer(text), reply_markup=admin_channel_manage_kb(bool(ch)))


@admin_router.callback_query(F.data == "admin_ch:set")
async def admin_ch_set(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != Config.ADMIN_ID: return
    await state.set_state(AdminStates.setting_channel)
    try:
        await cb.message.edit_text(with_footer("🔧 <b>تنظیم کانال</b>\n\n<code>@channel</code> یا <code>-100...</code>"))
    except TelegramBadRequest:
        pass
    await cb.answer()


@admin_router.callback_query(F.data == "admin_ch:remove")
async def admin_ch_remove(cb: CallbackQuery):
    if cb.from_user.id != Config.ADMIN_ID: return
    await settings_repo.clear_required_channel()
    try:
        await cb.message.edit_text(with_footer("🗑 کانال حذف شد."))
    except TelegramBadRequest:
        pass
    await cb.answer("✅")


@admin_router.message(AdminStates.setting_channel)
async def admin_ch_recv(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id != Config.ADMIN_ID: return
    parsed = parse_channel_input(message.text or "")
    if not parsed:
        await message.answer("❌ فرمت نامعتبر.")
        return
    try:
        await bot.get_chat(parsed)
        await bot.get_chat_member(parsed, bot.id)
    except TelegramBadRequest as e:
        await message.answer(f"❌ خطا: {e}")
        return
    await settings_repo.set_required_channel(parsed)
    await admin_log_repo.log(Config.ADMIN_ID, "set_channel", None, parsed)
    await state.clear()
    await message.answer(with_footer(f"✅ کانال تنظیم شد: <b>{parsed}</b>"), reply_markup=admin_menu_kb())


@admin_router.message(F.text == "📢 پیام همگانی")
async def admin_bcast(message: Message, state: FSMContext):
    if message.from_user.id != Config.ADMIN_ID: return
    await state.set_state(AdminStates.broadcasting)
    await message.answer(with_footer("📢 پیام همگانی — پیام را بفرست."))


@admin_router.message(AdminStates.broadcasting)
async def admin_bcast_recv(message: Message, state: FSMContext):
    await state.update_data(bc_chat=message.chat.id, bc_msg=message.message_id)
    await state.set_state(AdminStates.broadcasting_confirm)
    n = await user_repo.count()
    await message.answer(with_footer(f"⚠️ ارسال به <b>{n}</b> کاربر؟"), reply_markup=confirm_kb("broadcast"))


@admin_router.callback_query(F.data == "cancel:broadcast")
async def admin_bcast_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.edit_text(with_footer("❌ لغو شد."))
    except TelegramBadRequest:
        pass
    await cb.answer()


@admin_router.callback_query(F.data == "confirm:broadcast")
async def admin_bcast_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot):
    d = await state.get_data()
    chat, msg = d.get("bc_chat"), d.get("bc_msg")
    await state.clear()
    if not chat or not msg:
        await cb.answer("❌ خطا", show_alert=True)
        return
    users = await user_repo.all_ids()
    try:
        await cb.message.edit_text(with_footer(f"⏳ ارسال به {len(users)} کاربر..."))
    except TelegramBadRequest:
        pass
    r = await admin_svc.broadcast(bot, chat, msg, users)
    await admin_log_repo.log(Config.ADMIN_ID, "broadcast", None, f"{r['success']}/{r['failed']}")
    try:
        await cb.message.edit_text(with_footer(f"✅ پایان\nموفق: <b>{r['success']}</b>\nناموفق: <b>{r['failed']}</b>"))
    except TelegramBadRequest:
        pass
    await cb.answer()


@admin_router.message(F.text == "🚫 مدیریت بن‌ها")
async def admin_ban_menu(message: Message):
    if message.from_user.id != Config.ADMIN_ID: return
    await message.answer(
        with_footer("🚫 <b>مدیریت بن</b>\n\n<code>/ban ID دلیل</code>\n<code>/unban ID</code>"),
        reply_markup=admin_menu_kb(),
    )


@admin_router.message(Command("ban"))
async def admin_ban(message: Message, command: CommandObject):
    if message.from_user.id != Config.ADMIN_ID: return
    args = (command.args or "").split(maxsplit=1)
    if not args or not args[0].isdigit():
        await message.answer("فرمت: <code>/ban ID دلیل</code>")
        return
    t = int(args[0])
    reason = args[1] if len(args) > 1 else "بدون دلیل"
    await user_repo.ban(t, reason)
    await admin_log_repo.log(Config.ADMIN_ID, "ban", t, reason)
    await message.answer(f"🚫 کاربر <code>{t}</code> بن شد.")


@admin_router.message(Command("unban"))
async def admin_unban(message: Message, command: CommandObject):
    if message.from_user.id != Config.ADMIN_ID: return
    a = (command.args or "").strip()
    if not a.isdigit():
        await message.answer("فرمت: <code>/unban ID</code>")
        return
    await user_repo.unban(int(a))
    await admin_log_repo.log(Config.ADMIN_ID, "unban", int(a), "")
    await message.answer("✅ آنبن شد.")


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۱۶ — Scheduler
# ═══════════════════════════════════════════════════════════════════════

scheduler = AsyncIOScheduler()


async def job_cleanup():
    try:
        n = await link_repo.cleanup_onetime()
        if n:
            log.info("🧹 پاکسازی: %s لینک حذف شد.", n)
    except Exception as e:
        log.exception("cleanup: %s", e)


async def job_last_seen():
    try:
        await db.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP")
    except Exception as e:
        log.exception("last_seen: %s", e)


# ═══════════════════════════════════════════════════════════════════════
# 📌 بخش ۱۷ — Main
# ═══════════════════════════════════════════════════════════════════════

bot: Optional[Bot] = None
dp: Optional[Dispatcher] = None


async def on_startup(bot: Bot, **kwargs):
    log.info("🚀 ربات اجرا شد...")
    me = await bot.get_me()
    Config.BOT_USERNAME = me.username or Config.BOT_USERNAME
    log.info("🤖 @%s | 👑 Admin: %s", me.username, Config.ADMIN_ID)
    ch = await settings_repo.get_required_channel()
    log.info("🔒 کانال: %s", ch or "تنظیم نشده")
    try:
        await bot.send_message(Config.ADMIN_ID, f"✅ ربات راه‌اندازی شد.\n@{me.username}")
    except Exception:
        pass


async def on_shutdown(bot: Bot = None, **kwargs):
    log.info("🛑 خاموش شدن...")
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass
    await db.close()
    if bot:
        try:
            await bot.session.close()
        except Exception:
            pass


async def main():
    global bot, dp
    Config.validate()
    await db.connect()

    bot = Bot(token=Config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())
    dp.message.middleware(JoinCheckMiddleware())
    dp.callback_query.middleware(JoinCheckMiddleware())
    dp.message.middleware(RateLimitMiddleware(Config.RATE_LIMIT_MESSAGES, Config.RATE_LIMIT_WINDOW))

    dp.include_router(admin_router)
    dp.include_router(lang_router)
    dp.include_router(rules_router)
    dp.include_router(profile_router)
    dp.include_router(avatar_router)
    dp.include_router(settings_router)
    dp.include_router(target_router)
    dp.include_router(match_router)
    dp.include_router(link_router)
    dp.include_router(anon_router)
    dp.include_router(common_router)

    scheduler.add_job(job_cleanup, "interval", hours=1, id="cleanup")
    scheduler.add_job(job_last_seen, "interval", minutes=5, id="last_seen")
    scheduler.start()
    log.info("⏰ Scheduler فعال")

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
        log.info("👋 خروج")
