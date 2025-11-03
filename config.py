import os
from dotenv import load_dotenv
from pyrogram import Client
from pymongo import MongoClient

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


client = Client("autofilter-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

mongo = MongoClient(MONGO_URI)
db = mongo["autofilter"]
files_collection = db["files"]
users_collection = db["users"]
pending_requests = db["pending_requests"]

PAGE_SIZE = 6

