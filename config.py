import os
import asyncio
from dotenv import load_dotenv
from pyrogram import Client,enums
from pymongo import MongoClient

# ---------------- Load environment ----------------
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
INDEX_CHANNEL = int(os.getenv("INDEX_CHANNEL"))
GROUP_ID = int(os.getenv("GROUP_ID"))
BASE_URL = os.getenv("BASE_URL", "https://yourdomain.com")
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBotUsername")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL"))
UPDATES_CHANNEL = os.getenv("UPDATES_CHANNEL")
MOVIES_GROUP = os.getenv("MOVIES_GROUP")
AUTH_CHANNELS = [int(ch.strip()) for ch in os.getenv("AUTH_CHANNELS", "").split(",") if ch.strip()]

DELETE_AFTER = int(os.getenv("DELETE_AFTER", 1800))
DELETE_AFTER_FILE = int(os.getenv("DELETE_AFTER_FILE", 1800))
DELETE_DELAY = int(os.getenv("DELETE_DELAY", 3600))
DELETE_DELAY_REQ = int(os.getenv("DELETE_DELAY_REQ", 3600))

MINI_APP_URL = os.getenv("MINI_APP_URL", "https://yourdomain.com")
PAGE_SIZE = 6

# ---------------- Pyrogram client ----------------
client = Client("autofilter-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------------- MongoDB ----------------
mongo = MongoClient(MONGO_URI)
db = mongo["autofilter"]
files_collection = db["files"]
users_collection = db["users"]
pending_requests = db["pending_requests"]

# ---------------- Startup preloader ----------------
async def preload_chats():
    """Preload all authorized channels at startup."""
    for chat_id in AUTH_CHANNELS + [INDEX_CHANNEL]:
        try:
            chat = await client.get_chat(chat_id)
            print(f"[READY] ✅ Loaded chat: {chat.title} ({chat_id})")
        except Exception as e:
            print(f"[WARN] ⚠️ Could not preload {chat_id}: {e}")

# ---------------- Helper to start preloader ----------------
async def start_preloader():
    """Call this after client.start() in bot.py"""
    await preload_chats()

# Helper that normalizes candidate raw identifiers
def _candidate_from_raw_or_fallback(name_raw, name_fallback):
    """
    Return a string candidate to try resolving.
    Prefer *_RAW if present, else fall back to existing numeric config var.
    """
    # Try the explicit RAW version if you added it
    raw = globals().get(f"{name_raw}", None)
    if raw:
        return str(raw).strip()

    # Fallback to existing variable (old style)
    fallback = globals().get(name_fallback, None)
    if fallback is None:
        return None

    # If fallback is int, cast to str
    return str(fallback).strip()

async def resolve_chat(identifier):
    """
    Try to resolve a chat identifier (username like @channel or id like -100123...)
    to a proper integer chat id using client.get_chat. Returns resolved id or None.
    """
    if not identifier:
        return None

    # 1) Try direct resolution (username or numeric string)
    try:
        chat = await client.get_chat(identifier)
        return chat.id
    except Exception:
        pass

    # 2) If it's numeric and missing -100 prefix, try adding -100
    try:
        possible = int(identifier)
        if possible > 0 and not str(possible).startswith("-100"):
            try_raw = f"-100{possible}"
            try:
                chat = await client.get_chat(try_raw)
                return chat.id
            except Exception:
                pass
    except Exception:
        pass

    # 3) If identifier looks like digits but negative but not -100..., try to pass as int
    try:
        possible = int(identifier)
        try:
            chat = await client.get_chat(possible)
            return chat.id
        except Exception:
            pass
    except Exception:
        pass

    return None

async def resolve_all_chats():
    """
    Resolve INDEX_CHANNEL, LOG_CHANNEL and AUTH_CHANNELS from environment after client started.
    This function is tolerant: it accepts either *_RAW variables (strings like @name or -100id)
    or the older numeric INDEX_CHANNEL/LOG_CHANNEL values.
    """
    resolved = {}

    # Candidate strings (prefer *_RAW if you created them)
    idx_raw = _candidate_from_raw_or_fallback("INDEX_CHANNEL_RAW", "INDEX_CHANNEL")
    log_raw = _candidate_from_raw_or_fallback("LOG_CHANNEL_RAW", "LOG_CHANNEL")

    auth_raw_list = globals().get("AUTH_CHANNELS_RAW", None)
    if not auth_raw_list:
        # fallback: the older AUTH_CHANNELS might already be a list of ints in config
        old_auth = globals().get("AUTH_CHANNELS", [])
        # convert to strings for resolution attempts
        auth_raw_list = [str(x) for x in old_auth]

    # Resolve INDEX
    if idx_raw:
        idx = await resolve_chat(idx_raw)
        if idx is None:
            print(f"[WARN] Could not resolve INDEX_CHANNEL from '{idx_raw}'. Make sure it's @username or -100<id>.")
        else:
            globals()['INDEX_CHANNEL'] = idx
            resolved['INDEX_CHANNEL'] = idx
            print(f"[READY] INDEX_CHANNEL resolved -> {idx}")
    else:
        print("[INFO] INDEX_CHANNEL not provided in env (no raw or fallback).")

    # Resolve LOG_CHANNEL
    if log_raw:
        logc = await resolve_chat(log_raw)
        if logc is None:
            print(f"[WARN] Could not resolve LOG_CHANNEL from '{log_raw}'. Logging to log-channel will fail.")
        else:
            globals()['LOG_CHANNEL'] = logc
            resolved['LOG_CHANNEL'] = logc
            print(f"[READY] LOG_CHANNEL resolved -> {logc}")
    else:
        print("[INFO] LOG_CHANNEL not provided in env (no raw or fallback).")

    # Resolve AUTH channels list
    new_auth = []
    for raw in auth_raw_list or []:
        if not raw:
            continue
        rid = await resolve_chat(str(raw))
        if rid is None:
            print(f"[WARN] Could not resolve AUTH channel '{raw}'. Skipping it for now.")
        else:
            new_auth.append(rid)

    globals()['AUTH_CHANNELS'] = new_auth
    print(f"[READY] AUTH_CHANNELS resolved -> {new_auth}")

    return resolved

async def check_bot_admin_rights():
    """
    Check whether the bot can access and/or is admin in required chats. Prints diagnostics.
    Call this after resolve_all_chats().
    """
    checks = []
    targets = []

    if globals().get('INDEX_CHANNEL'):
        targets.append(globals()['INDEX_CHANNEL'])
    if globals().get('LOG_CHANNEL'):
        targets.append(globals()['LOG_CHANNEL'])
    targets += globals().get('AUTH_CHANNELS', [])

    # Remove duplicates
    targets = list(dict.fromkeys(targets))

    for t in targets:
        try:
            # use "me" to query bot membership
            member = await client.get_chat_member(t, "me")
            status = member.status
            is_admin = status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
            print(f"[CHECK] Bot membership in {t}: status={status}. Admin={is_admin}")
            checks.append((t, True, status, is_admin))
        except Exception as e:
            print(f"[ERROR] Bot cannot access chat {t}: {e}")
            checks.append((t, False, str(e), False))
    return checks
