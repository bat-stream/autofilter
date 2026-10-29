
import asyncio
import html
import requests
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    WebAppInfo,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from config import (
    client,
    files_collection,
    GROUP_ID,
    BASE_URL,
    BOT_USERNAME,
    INDEX_CHANNEL,
    MINI_APP_URL,
    UPDATES_CHANNEL,
    MOVIES_GROUP,
    ADMIN_ID,
    LOG_CHANNEL,
    DELETE_DELAY,
    DELETE_AFTER,
    MIN_SEARCH_QUERY_LEN,
)

from utils.helpers import (
    save_user,
    delete_after_delay,
    check_sub_and_send_file,
    get_file_buttons,
    build_search_regex,
    fetch_index_page,
)


# NOTE:
# /help, /report, /status, /send, /link, /broadcast,
# /uploadsession, /showsession, and the nav: callback are
# registered in their dedicated modules, not duplicated here.


def _ping_ads_sdk(user_id: int):
    """Make the blocking request in a worker thread."""
    try:
        requests.get(
            "https://app.adsgalaxy.online/api/bot/integration/406/"
            "UZ5glD9B24PBhVqyWz0f0JS9whLJxA0D_WpdmK8-vTY",
            params={"user_id": user_id},
            timeout=3,
        )
    except requests.RequestException:
        pass


# ------------------ Search Helpers ------------------ #

def fetch_search_results(query: str):
    """
    Fetch search results in a stable order.

    Both the initial search and pagination callbacks should use
    this function so the result order remains consistent.
    """
    regex = build_search_regex(query)

    return list(
        files_collection.find(
            {"file_name": {"$regex": regex}}
        ).sort([
            ("message_id", -1),
            ("_id", -1),
        ])
    )


# ------------------ /files Command ------------------ #

@client.on_message(filters.command("files"))
async def index_list(c: Client, m: Message):
    command_parts = (m.text or "").split(maxsplit=1)
    query = command_parts[1].strip() if len(command_parts) > 1 else ""

    page = fetch_index_page(query, 0)

    if not page:
        await m.reply("📂 No matching files found.")
        return

    text, buttons = page

    await m.reply(
        text,
        parse_mode=enums.ParseMode.HTML,
        reply_markup=buttons,
        disable_web_page_preview=True,
    )


# ------------------ Private/Group /start ------------------ #

@client.on_message(
    filters.command("start") & (filters.private | filters.group)
)
async def start(c: Client, m: Message):

    if m.chat.type == enums.ChatType.PRIVATE:
        await save_user(m.from_user.id)

        asyncio.create_task(
            asyncio.to_thread(_ping_ads_sdk, m.from_user.id)
        )

    args = (m.text or "").split(maxsplit=1)

    # ------------------ Deep Link with File ------------------ #

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
                f"❌ Error:\n<code>{html.escape(str(e))}</code>",
                parse_mode=enums.ParseMode.HTML,
            )

            asyncio.create_task(
                delete_after_delay(msg, DELETE_AFTER)
            )

        return

    # ------------------ Deep Link with Search ------------------ #

    if (
        len(args) > 1
        and args[1].startswith("search_")
        and m.chat.type == enums.ChatType.PRIVATE
    ):
        query = (
            args[1]
            .replace("search_", "", 1)
            .replace("_", " ")
            .strip()
        )

        results = fetch_search_results(query)

        if not results:
            msg = await m.reply(
                f"❗️No results found for "
                f"<b>{html.escape(query)}</b>",
                parse_mode=enums.ParseMode.HTML,
            )

            asyncio.create_task(
                delete_after_delay(msg, DELETE_AFTER)
            )
            return

        markup = get_file_buttons(results, query, 0)

        msg = await m.reply(
            f"🔍 Search results for "
            f"<b>{html.escape(query)}</b>:",
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
        )

        asyncio.create_task(
            delete_after_delay(msg, DELETE_AFTER)
        )
        return

    # ------------------ Default Welcome ------------------ #

    name = (
        m.from_user.first_name
        if m.from_user
        else "User"
    )

    if m.chat.type == enums.ChatType.PRIVATE:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🚀 Oᴘᴇɴ Mɪɴɪ Aᴘᴘ",
                    web_app=WebAppInfo(url=MINI_APP_URL),
                )
            ],
            [
                InlineKeyboardButton(
                    "📢 Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ",
                    url=UPDATES_CHANNEL,
                ),
                InlineKeyboardButton(
                    "Hᴇʟᴘ❓",
                    callback_data="help_info",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🎬 Mᴏᴠɪᴇ Sᴇᴀʀᴄʜ Gʀᴏᴜᴘ",
                    url=MOVIES_GROUP,
                )
            ],
        ])
    else:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📢 Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ",
                    url=UPDATES_CHANNEL,
                ),
                InlineKeyboardButton(
                    "Hᴇʟᴘ❓",
                    callback_data="help_info",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🎬 Mᴏᴠɪᴇ Sᴇᴀʀᴄʜ Gʀᴏᴜᴘ",
                    url=MOVIES_GROUP,
                )
            ],
        ])

    msg = await m.reply_text(
        f"<b>😎 ʜᴇʏ {html.escape(name)},</b>\n\n"
        "<b>ɪ ᴀᴍ Bᴀᴛᴍᴀɴ</b>\n\n"
        "<b>ғᴏʀ ɴᴇᴡ ᴍᴏᴠɪᴇs ᴊᴏɪɴ ʜᴇʀᴇ @Batmanlinkz</b>\n\n"
        "<b>Tᴏ Bʀᴏᴡsᴇ Sᴛᴏʀᴇᴅ Fɪʟᴇs Cʟɪᴄᴋ ᴏɴ Oᴘᴇɴ Mɪɴɪ Aᴘᴘ</b>\n\n"
        "<b>ᴛᴏ ᴋɴᴏᴡ ᴍᴏʀᴇ ᴄʟɪᴄᴋ ʜᴇʟᴘ ʙᴜᴛᴛᴏɴ.</b>",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML,
    )

    if m.chat.type != enums.ChatType.PRIVATE:
        asyncio.create_task(
            delete_after_delay(msg, DELETE_AFTER)
        )


# ------------------ Group/Private Text Search ------------------ #

@client.on_message(
    (filters.group | filters.private)
    & filters.text
    & ~filters.regex(r"^/")
)
async def search(c: Client, m: Message):
    if not m.from_user:
        return

    query = (m.text or "").strip()

    # Ignore short messages that are unlikely to be search queries.
    if len(query) < MIN_SEARCH_QUERY_LEN:
        return

    results = fetch_search_results(query)

    if not results:
        if m.chat.type == enums.ChatType.PRIVATE:
            msg = await m.reply(
                "❗️No Results found.",
                parse_mode=enums.ParseMode.HTML,
            )

            asyncio.create_task(
                delete_after_delay(msg, DELETE_DELAY)
            )

        else:
            chat_title = html.escape(m.chat.title or "Unknown")
            first_name = html.escape(
                m.from_user.first_name or "Unknown"
            )

            chat_info = (
                f"🗣 Group: <code>{chat_title}</code> "
                f"({m.chat.id})"
            )

            log_text = (
                f"🔍 <b>Missing File Request</b>\n\n"
                f"👤 User: "
                f"<a href='tg://user?id={m.from_user.id}'>"
                f"{first_name}</a>\n"
                f"🆔 User ID: <code>{m.from_user.id}</code>\n"
                f"{chat_info}\n"
                f"💬 Chat ID: <code>{m.chat.id}</code>\n"
                f"🔎 Query: <code>{html.escape(query)}</code>"
            )

            if LOG_CHANNEL:
                try:
                    await client.send_message(
                        LOG_CHANNEL,
                        log_text,
                        parse_mode=enums.ParseMode.HTML,
                    )
                except Exception as e:
                    print(
                        "[WARN] Failed to log missing-file "
                        f"request: {e}"
                    )

            msg = await m.reply(
                "<b>Nᴏ Sᴇᴀʀᴄʜ Rᴇsᴜʟᴛ Fᴏᴜɴᴅ. "
                "Pᴏssɪʙʟᴇ Sᴘᴇʟʟɪɴɢ Mɪsᴛᴀᴋᴇ ᴏʀ "
                "Uɴʀᴇʟᴇᴀsᴇᴅ/Uɴᴀᴠᴀɪʟᴀʙʟᴇ Mᴏᴠɪᴇ "
                "ᴏɴ OTT Pʟᴀᴛғᴏʀᴍ "
                "(Oɴʟʏ HD Pʀɪɴᴛs).</b>\n"
                "<b>Sᴀᴠᴇᴅ ᴀs Rᴇqᴜᴇsᴛ: "
                "Aᴅᴍɪɴ Wɪʟʟ Nᴏᴛɪғʏ ʏᴏᴜ "
                "ɪғ ғɪʟᴇs Aᴅᴅᴇᴅ.</b>",
                parse_mode=enums.ParseMode.HTML,
            )

            asyncio.create_task(
                delete_after_delay(msg, DELETE_DELAY)
            )

        return

    try:
        markup = get_file_buttons(results, query, 0)

        if not markup:
            raise ValueError("No buttons built")

        first_name = html.escape(
            m.from_user.first_name or "User"
        )

        mention = (
            f"<a href='tg://user?id={m.from_user.id}'>"
            f"{first_name}</a>"
        )

        msg = await m.reply(
            f"🔍 Found the following files for {mention}:",
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
        )

        asyncio.create_task(
            delete_after_delay(msg, DELETE_AFTER)
        )

    except Exception as e:
        msg = await m.reply(
            "⚠️ Something went wrong while building "
            "file buttons.\n\n"
            f"<b>Error:</b> "
            f"<code>{html.escape(str(e))}</code>",
            parse_mode=enums.ParseMode.HTML,
        )

        asyncio.create_task(
            delete_after_delay(msg, DELETE_DELAY)
        )


# ------------------ Auto-index Files ------------------ #

@client.on_message(
    filters.chat(INDEX_CHANNEL)
    & (filters.document | filters.video | filters.audio)
)
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
        {
            "$set": {
                "file_name": file_name,
                "file_size": file_size,
                "message_id": m.id,
            }
        },
        upsert=True,
    )
