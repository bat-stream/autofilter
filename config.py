# config.py — validated env loading + MongoDB indexes + StringSession helpers
import os
import sys
import pathlib
import uuid
import glob
import time
import zlib
import sqlite3
import tempfile
from bson.binary import Binary
from dotenv import load_dotenv

# --- Compatibility shim for newer Python (3.12+ / 3.13 / 3.14) ---
# Pyrogram 2.0.106 calls asyncio.get_event_loop() at import time
# (in pyrogram/sync.py) expecting it to silently create a loop if none
# exists. Newer Python versions removed that implicit auto-creation and
# instead raise `RuntimeError: There is no current event loop in thread
# 'MainThread'.` — this must run BEFORE `import pyrogram`.
import asyncio
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client
from pymongo import MongoClient, ASCENDING, TEXT
from pymongo.errors import PyMongoError

load_dotenv()


# ---------------- Helpers for strict env parsing ----------------
def _require(name: str) -> str:
    """Fetch a required env var or exit with a clear, actionable error."""
    val = os.getenv(name)
    if not val:
        sys.exit(
            f"[CONFIG ERROR] Required environment variable '{name}' is missing.\n"
            f"Set it in your .env file or environment and restart the bot."
        )
    return val


def _require_int(name: str) -> int:
    raw = _require(name)
    try:
        return int(raw)
    except ValueError:
        sys.exit(f"[CONFIG ERROR] Environment variable '{name}' must be an integer, got: {raw!r}")


def _optional_int(name: str, default=None):
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[CONFIG WARN] '{name}' is not a valid integer ({raw!r}); ignoring, using default={default}")
        return default


# ---------------- Required core credentials ----------------
API_ID = _require_int("API_ID")
API_HASH = _require("API_HASH")
BOT_TOKEN = _require("BOT_TOKEN")
MONGO_URI = _require("MONGO_URI")

# ---------------- Optional / feature config ----------------
INDEX_CHANNEL = _optional_int("INDEX_CHANNEL")
GROUP_ID = _optional_int("GROUP_ID")
BASE_URL = os.getenv("BASE_URL", "https://yourdomain.com").rstrip("/")
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBotUsername")
ADMIN_ID = _optional_int("ADMIN_ID")
LOG_CHANNEL = _optional_int("LOG_CHANNEL")
UPDATES_CHANNEL = os.getenv("UPDATES_CHANNEL", "https://t.me")
MOVIES_GROUP = os.getenv("MOVIES_GROUP", "https://t.me")
AUTH_CHANNELS = [int(ch.strip()) for ch in os.getenv("AUTH_CHANNELS", "").split(",") if ch.strip()]

if ADMIN_ID is None:
    print("[CONFIG WARN] ADMIN_ID is not set — admin-only commands (/status, /send, /broadcast, /link) will be unusable.")

# ---------------- Admin panel credentials ----------------
# No insecure hardcoded fallback: force the operator to set these explicitly.
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if not ADMIN_USERNAME or not ADMIN_PASSWORD:
    print(
        "[CONFIG WARN] ADMIN_USERNAME / ADMIN_PASSWORD not set in environment. "
        "The web admin dashboard login will be disabled until these are configured."
    )

# Flask session signing key — must be set explicitly in production.
FLASK_SECRET = os.environ.get("FLASK_SECRET")
if not FLASK_SECRET:
    print(
        "[CONFIG WARN] FLASK_SECRET is not set. Generating a random ephemeral secret for this "
        "process — admin sessions will NOT persist across restarts and will invalidate on redeploy. "
        "Set FLASK_SECRET in your environment for stable, secure sessions."
    )
    FLASK_SECRET = uuid.uuid4().hex + uuid.uuid4().hex

# ---------------- Delays / pagination (single source of truth) ----------------
DELETE_AFTER = _optional_int("DELETE_AFTER", 1800)
DELETE_AFTER_FILE = _optional_int("DELETE_AFTER_FILE", 1800)
DELETE_DELAY = _optional_int("DELETE_DELAY", 3600)
DELETE_DELAY_REQ = _optional_int("DELETE_DELAY_REQ", 3600)

MINI_APP_URL = os.getenv("MINI_APP_URL", "https://yourdomain.com")

# Mini App "short name", set via @BotFather -> /newapp (e.g. "app" if your
# bot is @YourBot, this becomes https://t.me/YourBot/app). Needed to build
# direct-link buttons that open the Mini App from GROUP chats — Telegram
# only allows the native `web_app=WebAppInfo(...)` button type in private
# chats, so groups need a plain t.me URL button instead.
MINI_APP_SHORT_NAME = (os.getenv("MINI_APP_SHORT_NAME", "") or "").strip() or None
if not MINI_APP_SHORT_NAME:
    print(
        "[CONFIG WARN] MINI_APP_SHORT_NAME is not set — the 'Open in Mini App' "
        "button on search results will be skipped in groups (and in private, "
        "still uses the WebAppInfo button, unaffected). Set it up via "
        "@BotFather -> /newapp to enable it everywhere."
    )

# Single source of truth for pagination sizes (previously duplicated/inconsistent
# across helpers.py, messages.py and callbacks.py with different hardcoded values).
PAGE_SIZE = _optional_int("PAGE_SIZE", 6)
INDEX_PAGE_SIZE = _optional_int("INDEX_PAGE_SIZE", 20)
WEB_FILES_PER_PAGE = _optional_int("WEB_FILES_PER_PAGE", 10)
WEB_DASHBOARD_PER_PAGE = _optional_int("WEB_DASHBOARD_PER_PAGE", 12)

# Minimum characters before an in-chat text message is treated as a file search.
# Prevents every "hi"/"ok" style message from triggering a full-collection regex scan.
MIN_SEARCH_QUERY_LEN = _optional_int("MIN_SEARCH_QUERY_LEN", 2)

# ---------------- MongoDB ----------------
mongo = None
db = None
files_collection = None
users_collection = None
pending_requests = None
queries_collection = None
_session_collection = None

try:
    mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
    mongo.admin.command("ping")  # fail fast with a clear error instead of a silent, half-working bot
    db = mongo["autofilter"]
except PyMongoError as e:
    sys.exit(f"[CONFIG ERROR] Could not connect to MongoDB at MONGO_URI: {e}")

files_collection = db["files"]
users_collection = db["users"]
pending_requests = db["pending_requests"]
_session_collection = db["session"]
queries_collection = db["queries"]


def ensure_indexes():
    """
    Create indexes required for the queries this bot actually runs.
    Without these, every search/pagination query becomes a full collection
    scan once the files collection grows past a few thousand documents.
    """
    try:
        files_collection.create_index([("message_id", ASCENDING)], unique=True, name="message_id_unique")
    except PyMongoError as e:
        print(f"[MONGO] Warning: could not create message_id index: {e}")

    try:
        # Powers fast, relevance-ranked search instead of unanchored $regex scans.
        files_collection.create_index([("file_name", TEXT)], name="file_name_text")
    except PyMongoError as e:
        print(f"[MONGO] Warning: could not create file_name text index: {e}")

    try:
        # Short tokens for search queries (Telegram limits callback_data to 64
        # bytes, so long/non-ASCII queries can't be embedded in buttons).
        # Auto-expire after 60 days.
        queries_collection.create_index("created_at", expireAfterSeconds=60 * 24 * 3600, name="queries_ttl")
    except PyMongoError as e:
        print(f"[MONGO] Warning: could not create queries TTL index: {e}")

    try:
        users_collection.create_index([("user_id", ASCENDING)], unique=True, name="user_id_unique")
    except PyMongoError as e:
        print(f"[MONGO] Warning: could not create user_id index: {e}")


ensure_indexes()

# ---------------- StringSession import (robust across Pyrogram versions) ----------------
StringSession = None
try:
    from pyrogram.types import StringSession as _SS
    StringSession = _SS
except Exception:
    try:
        from pyrogram.session import StringSession as _SS
        StringSession = _SS
    except Exception:
        StringSession = None

# ---------------- Session handling ----------------
STRING_SESSION = os.getenv("BOT_STRING_SESSION") or os.getenv("STRING_SESSION") or None

SESSION_NAME = os.getenv("SESSION_NAME", "autofilter-bot")

_workdir_env = os.getenv("PYRO_WORKDIR", "sessions")
if os.path.isabs(_workdir_env):
    WORKDIR = _workdir_env
else:
    # Resolve relative to THIS FILE's directory, not the process's current
    # working directory. A plain relative path here is a common source of a
    # very confusing bug: if `python bot.py` is ever launched from a
    # different cwd between restarts (a different terminal tab, a task
    # runner, an IDE "run" button, etc.), a relative workdir silently
    # resolves to a DIFFERENT absolute folder each time — creating a brand
    # new, empty Pyrogram session and losing every cached peer access_hash
    # from the previous run. That forces you to re-promote the bot to admin
    # in every channel just to re-learn their peers, on every single
    # restart. Anchoring to __file__ guarantees the same session (and its
    # cache) is found every time, regardless of where the script is run from.
    WORKDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), _workdir_env)

os.makedirs(WORKDIR, exist_ok=True)
print(f"[SESSION] Resolved session workdir: {WORKDIR}")


# ---------------- Session-file backup in MongoDB ----------------
# Pyrogram keeps every chat's access_hash (its "peer cache") inside the
# local <SESSION_NAME>.session SQLite file. A bot can NOT resolve a private
# channel by numeric ID without that cache, which is why a lost session file
# forces you to re-add the bot as admin after every restart. To make the
# cache survive wiped folders / re-extracted zips / ephemeral hosts, the file
# is snapshotted into MongoDB and restored automatically when it's missing.
SESSION_DB_ID = "pyrogram_session_file"
_BOT_ID = BOT_TOKEN.split(":")[0]


def _session_file_path():
    return pathlib.Path(WORKDIR) / f"{SESSION_NAME}.session"


def restore_session_file_from_db() -> bool:
    """Restore the session file from MongoDB if no local copy exists."""
    path = _session_file_path()
    try:
        if path.exists() and path.stat().st_size > 0:
            return False
        doc = _session_collection.find_one({"_id": SESSION_DB_ID})
        if not doc or doc.get("bot_id") != _BOT_ID or not doc.get("data"):
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(zlib.decompress(bytes(doc["data"])))
        print("[SESSION] Restored session file (incl. cached channel peers) from MongoDB.")
        return True
    except Exception as e:
        print("[SESSION] Could not restore session file from MongoDB:", e)
        return False


def persist_session_file_to_db() -> bool:
    """Snapshot the live session file into MongoDB (safe while it's in use)."""
    path = _session_file_path()
    try:
        if not path.exists():
            return False
        with tempfile.TemporaryDirectory() as tmp:
            snap = pathlib.Path(tmp) / "snapshot.session"
            src = sqlite3.connect(str(path), timeout=5)
            dst = sqlite3.connect(str(snap))
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
            raw = snap.read_bytes()
        _session_collection.update_one(
            {"_id": SESSION_DB_ID},
            {"$set": {"bot_id": _BOT_ID, "data": Binary(zlib.compress(raw, 6)), "updated_at": time.time()}},
            upsert=True,
        )
        return True
    except Exception as e:
        print("[SESSION] Could not back up session file to MongoDB:", e)
        return False


async def session_persist_loop(interval: int = 300):
    """Periodically back up the session file so newly learned peers are kept."""
    while True:
        await asyncio.sleep(interval)
        await asyncio.to_thread(persist_session_file_to_db)


restore_session_file_from_db()

if STRING_SESSION and StringSession is not None:
    client = Client(StringSession(STRING_SESSION), api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    using_string_session = True
    print("[SESSION] Using StringSession loaded from environment (wrapped).")
elif STRING_SESSION and StringSession is None:
    print("[SESSION] WARNING: Found session string in env but this Pyrogram install lacks StringSession support.")
    print("[SESSION] Falling back to a short local session filename. Upgrade pyrogram to use env string sessions.")
    client = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workdir=WORKDIR)
    using_string_session = False
else:
    client = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workdir=WORKDIR)
    using_string_session = False
    print(f"[SESSION] Using local session file (workdir={WORKDIR}, name={SESSION_NAME}).")


# ---------------- Helpers to save/load session ----------------
async def save_session_to_db():
    if _session_collection is None:
        print("[SESSION] Cannot save to DB: MongoDB not configured.")
        return False
    try:
        s = await client.export_session_string()
        _session_collection.update_one({"_id": "bot_session"}, {"$set": {"string_session": s}}, upsert=True)
        print("[SESSION] Saved StringSession to MongoDB.")
        return True
    except Exception as e:
        print("[SESSION] Failed to save session to MongoDB:", e)
        return False


def load_session_from_db():
    if _session_collection is None:
        return None
    try:
        doc = _session_collection.find_one({"_id": "bot_session"})
        return doc["string_session"] if doc and doc.get("string_session") else None
    except Exception as e:
        print("[SESSION] Could not load session from DB:", e)
        return None


async def save_session_string_to_file():
    try:
        s = await client.export_session_string()
    except Exception as e:
        print("[SESSION] Failed to export session string:", e)
        return False

    try:
        pathlib.Path(WORKDIR).mkdir(parents=True, exist_ok=True)
        file_path = pathlib.Path(WORKDIR) / f"{SESSION_NAME}.session_string"
        file_path.write_text(s, encoding="utf-8")
        print(f"[SESSION] Wrote session string to file: {file_path}")
        return str(file_path)
    except Exception as e:
        print("[SESSION] Failed to write session string to file:", e)
        return False


async def create_local_session_file_from_string(string_session: str, target_workdir: str = WORKDIR, short_name: str = None):
    if StringSession is None:
        print("[SESSION] StringSession class not available in this Pyrogram installation. Upgrade pyrogram.")
        return False

    if not string_session:
        print("[SESSION] No string session provided.")
        return False

    short_name = short_name or f"{SESSION_NAME}_converted_{uuid.uuid4().hex[:8]}"
    try:
        tmp_client = Client(StringSession(string_session), api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workdir=target_workdir)
    except Exception:
        try:
            tmp_client = Client(short_name, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workdir=target_workdir)
        except Exception as e2:
            print("[SESSION] Failed to construct temporary client:", e2)
            return False

    try:
        await tmp_client.start()
        await tmp_client.stop()
    except Exception as e:
        print("[SESSION] Failed to start/stop temporary client to persist session file:", e)
        try:
            await tmp_client.stop()
        except Exception:
            pass
        return False

    pattern = str(pathlib.Path(target_workdir) / f"{short_name}*")
    matches = glob.glob(pattern)
    if matches:
        print(f"[SESSION] Created session file(s): {matches}")
        return matches
    all_matches = glob.glob(str(pathlib.Path(target_workdir) / f"{SESSION_NAME}*"))
    if all_matches:
        print(f"[SESSION] Found session files related to SESSION_NAME: {all_matches}")
        return all_matches
    print("[SESSION] No session files found after temporary client stop.")
    return False


def write_short_session_marker():
    try:
        marker_path = pathlib.Path(WORKDIR) / f"{SESSION_NAME}.session_marker"
        with open(marker_path, "w", encoding="utf-8") as f:
            if using_string_session:
                f.write("STRING_SESSION_IN_USE\n")
                f.write("Session string provided via environment variable (BOT_STRING_SESSION or STRING_SESSION).\n")
            else:
                f.write("FILE_SESSION_IN_USE\n")
                f.write(f"Local Pyrogram session filename: {SESSION_NAME}.session\n")
        print(f"[SESSION] Wrote short session marker: {marker_path}")
        return str(marker_path)
    except Exception as e:
        print("[SESSION] Failed to write session marker:", e)
        return None


# ---------------- Startup preloader ----------------
async def preload_chats():
    """
    Preload every channel/group the bot needs at startup, in parallel.

    This also warms Pyrogram's local peer cache (access_hash per chat) for
    each one. As long as the session file at WORKDIR persists across
    restarts (see the WORKDIR resolution above), this only ever needs to
    succeed ONCE per chat, permanently — no repeated "re-add as admin"
    required after that.
    """
    import asyncio

    chat_ids = [c for c in (AUTH_CHANNELS + [INDEX_CHANNEL, LOG_CHANNEL]) if c is not None]

    async def _load(chat_id):
        try:
            chat = await client.get_chat(chat_id)
            print(f"[READY] ✅ Loaded chat: {getattr(chat, 'title', chat)} ({chat_id})")
        except Exception as e:
            print(
                f"[WARN] ⚠️ Could not preload {chat_id}: {e}\n"
                f"        This chat's peer info (access_hash) isn't cached in the bot's "
                f"session yet. Pyrogram learns it the moment the bot receives any update "
                f"from that chat — e.g. being (re)promoted to admin there. If this keeps "
                f"happening on every restart rather than just once, the session file isn't "
                f"actually persisting between runs (check WORKDIR above)."
            )

    await asyncio.gather(*(_load(cid) for cid in chat_ids))


async def start_preloader():
    await preload_chats()
