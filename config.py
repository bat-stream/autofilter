# config.py — minimal change: load/save StringSession from/to MongoDB + file helpers
import os
import pathlib
import uuid
import glob
from dotenv import load_dotenv
from pyrogram import Client
from pymongo import MongoClient

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# existing envs
INDEX_CHANNEL = int(os.getenv("INDEX_CHANNEL")) if os.getenv("INDEX_CHANNEL") else None
GROUP_ID = int(os.getenv("GROUP_ID")) if os.getenv("GROUP_ID") else None
BASE_URL = os.getenv("BASE_URL", "https://yourdomain.com")
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBotUsername")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL")) if os.getenv("LOG_CHANNEL") else None
UPDATES_CHANNEL = os.getenv("UPDATES_CHANNEL")
MOVIES_GROUP = os.getenv("MOVIES_GROUP")
AUTH_CHANNELS = [int(ch.strip()) for ch in os.getenv("AUTH_CHANNELS", "").split(",") if ch.strip()]

DELETE_AFTER = int(os.getenv("DELETE_AFTER", 1800))
DELETE_AFTER_FILE = int(os.getenv("DELETE_AFTER_FILE", 1800))
DELETE_DELAY = int(os.getenv("DELETE_DELAY", 3600))
DELETE_DELAY_REQ = int(os.getenv("DELETE_DELAY_REQ", 3600))

MINI_APP_URL = os.getenv("MINI_APP_URL", "https://yourdomain.com")
PAGE_SIZE = 6

# ---------------- MongoDB ----------------
mongo = None
db = None
files_collection = None
users_collection = None
pending_requests = None
_session_collection = None

if MONGO_URI:
    try:
        mongo = MongoClient(MONGO_URI)
        db = mongo["autofilter"]
    except Exception as e:
        print(f"[MONGO] Warning: could not connect to MongoDB: {e}")
        mongo = None
        db = None

if db is not None:
    try:
        files_collection = db["files"]
        users_collection = db["users"]
        pending_requests = db["pending_requests"]
        _session_collection = db["session"]  # collection to store the string session
    except Exception as e:
        print(f"[MONGO] Warning: could not get collections: {e}")
        files_collection = None
        users_collection = None
        pending_requests = None
        _session_collection = None

# ---------------- StringSession import (robust) ----------------
StringSession = None
try:
    # try modern location
    from pyrogram.types import StringSession as _SS
    StringSession = _SS
except Exception:
    try:
        from pyrogram.session import StringSession as _SS
        StringSession = _SS
    except Exception:
        StringSession = None

# ---------------- Session handling ----------------
# NOTE: We DO NOT auto-load StringSession from MongoDB on startup.
#       Instead, read the session string from environment variable:
#         BOT_STRING_SESSION (preferred) or STRING_SESSION (fallback).
#
STRING_SESSION = os.getenv("BOT_STRING_SESSION") or os.getenv("STRING_SESSION") or None

# Workdir and session name
SESSION_NAME = os.getenv("SESSION_NAME", "autofilter-bot")
WORKDIR = os.getenv("PYRO_WORKDIR", "sessions")
os.makedirs(WORKDIR, exist_ok=True)

# For Pyrogram v2+: if we have an env string and StringSession available, wrap it.
# Otherwise, fallback to using short local session filename (safe).
if STRING_SESSION and StringSession is not None:
    client = Client(StringSession(STRING_SESSION), api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    using_string_session = True
    print("[SESSION] Using StringSession loaded from environment (wrapped).")
elif STRING_SESSION and StringSession is None:
    # We have a string but cannot wrap it -> DO NOT pass raw string as filename
    print("[SESSION] WARNING: Found session string in env but this Pyrogram install lacks StringSession support.")
    print("[SESSION] Falling back to a short local session filename. Upgrade pyrogram to use env string sessions.")
    client = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workdir=WORKDIR)
    using_string_session = False
else:
    # No env string -> use local short session file
    client = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workdir=WORKDIR)
    using_string_session = False
    print(f"[SESSION] Using local session file (workdir={WORKDIR}, name={SESSION_NAME}).")

# ---------------- Helpers to save/load session ----------------
async def save_session_to_db():
    """
    Export the currently-running session as a string and save to MongoDB.
    Call this after client.start() when the client is connected.
    """
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
    """Return stored string session (or None)."""
    if _session_collection is None:
        return None
    try:
        doc = _session_collection.find_one({"_id": "bot_session"})
        return doc["string_session"] if doc and doc.get("string_session") else None
    except Exception as e:
        print("[SESSION] Could not load session from DB:", e)
        return None

# ---------------- New helper: save exported session string to a short file ----------------
async def save_session_string_to_file():
    """
    Export the active session string and save it into WORKDIR/SESSION_NAME.session_string.
    Returns path to file on success, False on failure.
    """
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

# ---------------- New helper: create a real .session file from a string ----------------
async def create_local_session_file_from_string(string_session: str, target_workdir: str = WORKDIR, short_name: str = None):
    """
    Create a real Pyrogram .session file on disk from a StringSession string.
    This starts a temporary Pyrogram client with the StringSession and stops it so Pyrogram writes the file.
    Returns path to created file(s) or False on error.
    """
    if StringSession is None:
        print("[SESSION] StringSession class not available in this Pyrogram installation. Upgrade pyrogram.")
        return False

    if not string_session:
        print("[SESSION] No string session provided.")
        return False

    short_name = short_name or f"{SESSION_NAME}_converted_{uuid.uuid4().hex[:8]}"
    # Create a temp client using the string session and a short session name (workdir controls output)
    try:
        tmp_client = Client(StringSession(string_session), api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workdir=target_workdir)
    except Exception as e:
        # Some pyrogram versions might expect the short name as first positional arg instead
        try:
            tmp_client = Client(short_name, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workdir=target_workdir)
        except Exception as e2:
            print("[SESSION] Failed to construct temporary client:", e2)
            return False

    try:
        await tmp_client.start()
        # stopping will force Pyrogram to persist session file(s)
        await tmp_client.stop()
    except Exception as e:
        print("[SESSION] Failed to start/stop temporary client to persist session file:", e)
        try:
            await tmp_client.stop()
        except Exception:
            pass
        return False

    # Find created files
    pattern = str(pathlib.Path(target_workdir) / f"{short_name}*")
    matches = glob.glob(pattern)
    if matches:
        print(f"[SESSION] Created session file(s): {matches}")
        return matches
    else:
        # Try to list all session-like files in workdir (fallback)
        all_matches = glob.glob(str(pathlib.Path(target_workdir) / f"{SESSION_NAME}*"))
        if all_matches:
            print(f"[SESSION] Found session files related to SESSION_NAME: {all_matches}")
            return all_matches
        print("[SESSION] No session files found after temporary client stop.")
        return False

# ---------------- Helper: write a short marker file ----------------
def write_short_session_marker():
    """
    Create a short, human-friendly marker file in WORKDIR to indicate which short name is used.
    """
    try:
        marker_path = pathlib.Path(WORKDIR) / f"{SESSION_NAME}.session_marker"
        with open(marker_path, "w", encoding="utf-8") as f:
            if using_string_session:
                f.write("STRING_SESSION_IN_USE\n")
                f.write("Session string provided via environment variable (BOT_STRING_SESSION or STRING_SESSION).\n")
                f.write("This file is a short marker to show a friendly filename exists.\n")
            else:
                f.write("FILE_SESSION_IN_USE\n")
                f.write(f"Local Pyrogram session filename: {SESSION_NAME}.session\n")
        print(f"[SESSION] Wrote short session marker: {marker_path}")
        return str(marker_path)
    except Exception as e:
        print("[SESSION] Failed to write session marker:", e)
        return None

# ---------------- Startup preloader (unchanged) ----------------
async def preload_chats():
    """Preload all authorized channels at startup (safe; prints warnings)."""
    for chat_id in AUTH_CHANNELS + [INDEX_CHANNEL]:
        try:
            chat = await client.get_chat(chat_id)
            print(f"[READY] ✅ Loaded chat: {getattr(chat, 'title', chat)} ({chat_id})")
        except Exception as e:
            print(f"[WARN] ⚠️ Could not preload {chat_id}: {e}")

async def start_preloader():
    await preload_chats()
