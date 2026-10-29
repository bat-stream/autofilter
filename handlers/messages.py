import asyncio
import html
import re
import requests
from pyrogram import Client, filters, enums
from pyrogram.types import Message, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from config import (
    client, files_collection, GROUP_ID, BASE_URL, BOT_USERNAME, INDEX_CHANNEL,
    MINI_APP_URL, UPDATES_CHANNEL, MOVIES_GROUP, ADMIN_ID, LOG_CHANNEL,
    DELETE_DELAY, DELETE_AFTER, MIN_SEARCH_QUERY_LEN,
)
from utils.helpers import (
    save_user, delete_after_delay, check_sub_and_send_file,
    get_file_buttons, build_search_regex, fetch_index_page,
)

# NOTE: /help, /report, /status, /send, /link, /broadcast, /uploadsession,
# /showsession, and the `nav:` callback used to ALSO be defined here, exact
# duplicates of commands/admin.py, commands/user.py and handlers/callbacks.py.
# Pyrogram only ever ran the first-registered copy of each, silently making
# these duplicates dead code — they have been removed from this file so each
# command/callback now has exactly one definition.


def _ping_ads_sdk(user_id: int):
    """Runs in a worker thread via asyncio.to_thread so the blocking network
    call never freezes the bot's event loop for other users."""
    try:
        requests.get(
            "https://app.adsgalaxy.online/api/bot/integration/406/UZ5glD9B24PBhVqyWz0f0JS9whLJxA0D_WpdmK8-vTY",
            params={"user_id": user_id},
            timeout=3,
        )
    except requests.RequestException:
        pass


# ------------------ /files command ------------------ #
@client.on_message(filters.command("files"))
async def index_list(c: Client, m: Message):
    command_parts = m.text.split(maxsplit=1)
    query = command_parts[1].strip() if len(command_parts) > 1 else ""

    page = fetch_index_page(query, 0)
    if not page:
        return await m.reply("📂 No matching files found.")

    text, buttons = page
    await m.reply(text, parse_mode=enums.ParseMode.HTML, reply_markup=buttons, disable_web_page_preview=True)


# ------------------ Private/Group /start ------------------ #
@client.on_message(filters.command("start") & (filters.private | filters.group))
async def start(c: Client, m: Message):

    if m.chat.type == enums.ChatType.PRIVATE:
        await save_user(m.from_user.id)
        # Fire-and-forget, off the event loop — was previously a blocking
        # `requests.get()` call made directly inside this async handler,
        # which froze the whole bot for every concurrent user on every /start.
        asyncio.create_task(asyncio.to_thread(_ping_ads_sdk, m.from_user.id))

    args = m.text.split(maxsplit=1)

    # ------------------ Deep link with file ------------------ #
    if (
        len(args) > 1
        and args[1].startswith("file_")
        and m.chat.type == enums.ChatType.PRIVATE
    ):
        try:
            msg_id = int(args[1].split("_", 1)[1])
            await check_sub_and_send_file(c, m, msg_id)
        except Exception as e:
            msg = await m.reply(
                f"❌ Error:\n<code>{e}</code>",
                parse_mode=enums.ParseMode.HTML
            )
            asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))
        return

    # ------------------ Deep link with search ------------------ #
    if (
        len(args) > 1
        and args[1].startswith("search_")
        and m.chat.type == enums.ChatType.PRIVATE
    ):
        query = args[1].replace("search_", "", 1).replace("_", " ").strip()
        regex = build_search_regex(query)
        results = list(
            files_collection.find(
                {"file_name": {"$regex": regex}}
            ).sort("message_id", -1)
        )

        if not results:
            msg = await m.reply(
                f"❗️No results found for <b>{html.escape(query)}</b>",
                parse_mode=enums.ParseMode.HTML
            )
            asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))
            return

        markup = get_file_buttons(results, query, 0)
        msg = await m.reply(
            f"🔍 Search results for <b>{html.escape(query)}</b>:",
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML
        )
        asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))
        return

    # ------------------ Default welcome ------------------ #
    name = m.from_user.first_name if m.from_user else "User"

    if m.chat.type == enums.ChatType.PRIVATE:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Oᴘᴇɴ Mɪɴɪ Aᴘᴘ", web_app=WebAppInfo(url=MINI_APP_URL))],
            [
                InlineKeyboardButton("📢 Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ", url=UPDATES_CHANNEL),
                InlineKeyboardButton("Hᴇʟᴘ❓", callback_data="help_info"),
            ],
            [InlineKeyboardButton("🎬 Mᴏᴠɪᴇ Sᴇᴀʀᴄʜ Gʀᴏᴜᴘ", url=MOVIES_GROUP)],
        ])
    else:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📢 Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ", url=UPDATES_CHANNEL),
                InlineKeyboardButton("Hᴇʟᴘ❓", callback_data="help_info"),
            ],
            [InlineKeyboardButton("🎬 Mᴏᴠɪᴇ Sᴇᴀʀᴄʜ Gʀᴏᴜᴘ", url=MOVIES_GROUP)],
        ])

    msg = await m.reply_text(
        f"<b>😎 ʜᴇʏ {name},</b>\n\n"
        "<b>ɪ ᴀᴍ Bᴀᴛᴍᴀɴ</b>\n\n"
        "<b>ғᴏʀ ɴᴇᴡ ᴍᴏᴠɪᴇs ᴊᴏɪɴ ʜᴇʀᴇ @Batmanlinkz</b>\n\n"
        "<b>Tᴏ Bʀᴏᴡsᴇ Sᴛᴏʀᴇᴅ Fɪʟᴇs Cʟɪᴄᴋ ᴏɴ Oᴘᴇɴ Mɪɴɪ Aᴘᴘ</b>\n\n"
        "<b>ᴛᴏ ᴋɴᴏᴡ ᴍᴏʀᴇ ᴄʟɪᴄᴋ ʜᴇʟᴘ ʙᴜᴛᴛᴏɴ.</b>",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML
    )

    if m.chat.type != enums.ChatType.PRIVATE:
        asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))


# ------------------ Group/Private Text Search ------------------ #
@client.on_message((filters.group | filters.private) & filters.text & ~filters.regex(r"^/"))
async def search(c: Client, m: Message):
    if not m.from_user:
        return  # anonymous admin / channel posts

    query = m.text.strip()

    # Guard against a full unindexed-regex collection scan firing on every
    # single short message ("hi", "ok", "😂"...) sent in a group. Short
    # messages are almost never real search queries anyway.
    if len(query) < MIN_SEARCH_QUERY_LEN:
        return

    regex = build_search_regex(query)
    results = list(
            files_collection.find(
                {"file_name": {"$regex": regex}}
            ).sort("message_id", -1)
        )

    if not results:
        if m.chat.type == enums.ChatType.PRIVATE:
            msg = await m.reply("❗️No Results found.", parse_mode=enums.ParseMode.HTML)
            asyncio.create_task(delete_after_delay(msg, DELETE_DELAY))
        else:
            chat_info = f"🗣 Group: <code>{m.chat.title}</code> ({m.chat.id})"
            log_text = (
                f"🔍 <b>Missing File Request</b>\n\n"
                f"👤 User: <a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>\n"
                f"🆔 User ID: <code>{m.from_user.id}</code>\n"
                f"{chat_info}\n"
                f"💬 Chat ID: <code>{m.chat.id}</code>\n"
                f"🔎 Query: <code>{html.escape(query)}</code>"
            )
            if LOG_CHANNEL:
                try:
                    await client.send_message(LOG_CHANNEL, log_text, parse_mode=enums.ParseMode.HTML)
                except Exception as e:
                    print(f"[WARN] Failed to log missing-file request: {e}")

            msg = await m.reply(
                "<b>Nᴏ Sᴇᴀʀᴄʜ Rᴇsᴜʟᴛ Fᴏᴜɴᴅ. Pᴏssɪʙʟᴇ Sᴘᴇʟʟɪɴɢ Mɪsᴛᴀᴋᴇ ᴏʀ Uɴʀᴇʟᴇᴀsᴇᴅ/Uɴᴀᴠᴀɪʟᴀʙʟᴇ Mᴏᴠɪᴇ ᴏɴ OTT Pʟᴀᴛғᴏʀᴍ (Oɴʟʏ HD Pʀɪɴᴛs).</b>\n"
                "<b>Sᴀᴠᴇᴅ ᴀs Rᴇqᴜᴇsᴛ:Aᴅᴍɪɴ Wɪʟʟ Nᴏᴛɪғʏ ʏᴏᴜ ɪғ ғɪʟᴇs Aᴅᴅᴇᴅ.</b>",
                parse_mode=enums.ParseMode.HTML
            )
            asyncio.create_task(delete_after_delay(msg, DELETE_DELAY))
        return

    try:
        markup = get_file_buttons(results, query, 0)
        if not markup:
            raise ValueError("No buttons built")

        mention = f"<a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>"
        msg = await m.reply(
            f"🔍 Found the following files for {mention}:",
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML
        )
        asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))

    except Exception as e:
        msg = await m.reply(
            f"⚠️ Something went wrong while building file buttons.\n\n<b>Error:</b> <code>{e}</code>",
            parse_mode=enums.ParseMode.HTML
        )
        asyncio.create_task(delete_after_delay(msg, DELETE_DELAY))


# ------------------ Auto-index files posted to INDEX_CHANNEL ------------------ #
@client.on_message(filters.chat(INDEX_CHANNEL) & (filters.document | filters.video | filters.audio))
async def index_files(c: Client, m: Message):
    file_name = None
    file_size = None

    if m.document:
        file_name = m.document.file_name
        file_size = m.document.file_size
    elif m.video:
        file_name = m.video.file_name or m.caption or "Video"
        file_size = m.video.file_size
    elif m.audio:
        file_name = m.audio.file_name or m.caption or "Audio"
        file_size = m.audio.file_size

    if not file_name:
        file_name = m.caption or f"File-{m.id}"

    files_collection.update_one(
        {"message_id": m.id},
        {"$set": {
            "file_name": file_name,
            "file_size": file_size,
            "message_id": m.id
        }},
        upsert=True
    )
