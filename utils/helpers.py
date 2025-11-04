import asyncio
import re
import urllib.parse
import socket
from pyrogram import enums, Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery,WebAppInfo
from config import (
    client, files_collection, users_collection, LOG_CHANNEL, BASE_URL, 
    DELETE_AFTER_FILE, DELETE_AFTER, DELETE_DELAY_REQ, INDEX_CHANNEL, 
    AUTH_CHANNELS, GROUP_ID,MINI_APP_URL
)



# ------------------ User Utilities ------------------ #

async def save_user(user_id):
    if not users_collection.find_one({"user_id": user_id}):
        user = await client.get_users(user_id)
        users_collection.insert_one({"user_id": user_id})
        msg = (
            f"#New_Bot_User\n\n"
            f"» ɴᴀᴍᴇ - <a href='tg://user?id={user_id}'>{user.first_name}</a>\n"
            f"» ɪᴅ - <code>{user_id}</code>"
        )
        try:
            await client.send_message(LOG_CHANNEL, msg, parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            print(f"Failed to log new user: {e}")


async def delete_after_delay(msg: Message, delay: int):
    try:
        await asyncio.sleep(delay)
        await msg.delete()
    except Exception as e:
        print(f"Failed to delete message: {e}")


# ------------------ File Parsing ------------------ #


def extract_season_episode(filename: str):
    name = filename.replace(".", " ").replace("_", " ").lower().strip()

    # 1️⃣ Season + Episode Range (all hybrids)
    range_patterns = [
        # Season 4 Episode (01-08)
        r'season\s*(\d{1,2})\s*episode\s*[\(\[\{]?\s*(\d{1,3})\s*[-–~to]+\s*(\d{1,3})[\)\]\}]?',
        # S04 (01-08)
        r's(\d{1,2})\s*[\(\[\{]?\s*(\d{1,3})\s*[-–~to]+\s*(\d{1,3})[\)\]\}]?',
        # S04 (ep01-ep08) or S04(ep1–ep8)
        r's(\d{1,2})\s*[\(\[\{]?\s*ep?\s*(\d{1,3})\s*[-–~to]+\s*ep?\s*(\d{1,3})[\)\]\}]?',
        # S04 (e01-e08)
        r's(\d{1,2})\s*[\(\[\{]?\s*e\s*(\d{1,3})\s*[-–~to]+\s*e?\s*(\d{1,3})[\)\]\}]?',
        # S03E01 - E08 / S03EP01 - EP08 / S03E01 - 08
        r's(\d{1,2})e?p?(\d{1,3})\s*[-–~to]+\s*e?p?(\d{1,3})',
        # S04 01-08 (no explicit E)
        r's(\d{1,2})\s*(\d{1,3})\s*[-–~to]+\s*(\d{1,3})',
    ]
    for p in range_patterns:
        if match := re.search(p, name, re.IGNORECASE):
            season = match.group(1).zfill(2)
            ep_start = match.group(2).zfill(2)
            ep_end = match.group(3).zfill(2)
            return f"S{season}EP{ep_start}-EP{ep_end}"

    # 2️⃣ Season + Episode single
    single_patterns = [
        r'season\s*(\d{1,2})\s*episode\s*(\d{1,3})',
        r'season\s*(\d{1,2})\s*ep?\s*(\d{1,3})',
        r's(\d{1,2})\s*ep?\s*(\d{1,3})',
        r's(\d{1,2})\s*e(\d{1,3})',
        r's(\d{1,2})\s*(\d{1,3})',  # e.g. S04 08
    ]
    for p in single_patterns:
        if match := re.search(p, name, re.IGNORECASE):
            season = match.group(1).zfill(2)
            episode = match.group(2).zfill(2)
            return f"S{season}EP{episode}"

    # 3️⃣ Episode-only range (no season)
    ep_range_patterns = [
        r'\bep?\s*(\d{1,3})\s*[-–~to]+\s*ep?\s*(\d{1,3})\b',
        r'\be\s*(\d{1,3})\s*[-–~to]+\s*e?\s*(\d{1,3})\b',
        r'\b(\d{1,3})\s*[-–~to]+\s*(\d{1,3})\b',
    ]
    for p in ep_range_patterns:
        if match := re.search(p, name, re.IGNORECASE):
            ep_start = match.group(1).zfill(2)
            ep_end = match.group(2).zfill(2)
            return f"EP{ep_start}-EP{ep_end}"

    # 4️⃣ Episode-only single
    single_ep_patterns = [
        r'\bep?\s*(\d{1,3})\b',
        r'\be\s*(\d{1,3})\b',
        r'\bepisode\s*(\d{1,3})\b',
    ]
    for p in single_ep_patterns:
        if match := re.search(p, name, re.IGNORECASE):
            return f"EP{match.group(1).zfill(2)}"

    # 5️⃣ Season-only
    season_patterns = [
        r'\bs(\d{1,2})\b',
        r'season\s*(\d{1,2})'
    ]
    for p in season_patterns:
        if match := re.search(p, name, re.IGNORECASE):
            return f"S{match.group(1).zfill(2)}"

    # 6️⃣ Fallback: numeric episode detection (01, 1, etc.)
    if fallback := re.search(r'\b(\d{1,3})\b', name):
        num = int(fallback.group(1))
        if 0 < num < 300:
            return f"EP{str(num).zfill(2)}"

    return None



def run_flask_app(flask_app):
    sock = socket.socket()
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()
    print(f"Starting Flask on port {port}")
    flask_app.run(host='0.0.0.0', port=port)

PAGE_SIZE=6



# ------------------ File Buttons & Pagination ------------------ #


def build_index_page(files, page):
    PAGE_SIZE = 20
    total_pages = (len(files) + PAGE_SIZE - 1) // PAGE_SIZE
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    current = files[start:end]

    lines = ["📄 <b>Sᴛᴏʀᴇᴅ Fɪʟᴇs:</b>\n"]
    for i, f in enumerate(current, start=start + 1):
        file_size = f.get("file_size") or 0
        size_mb = round(file_size / (1024 * 1024), 2)
        file_name = f.get('file_name') or ''
        clean_name = re.sub(r'^@[^_\s-]+[_\s-]*', '', file_name).strip()
        link = f"{BASE_URL}/redirect?id={f['message_id']}"
        lines.append(f"{i}. <a href='{link}'>{clean_name}</a> ({size_mb} MB)")

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⏮️ Fɪʀsᴛ", callback_data="indexpage_0"))
        nav_buttons.append(InlineKeyboardButton("⬅️ Pʀᴇᴠ", callback_data=f"indexpage_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Nᴇxᴛ ➡️", callback_data=f"indexpage_{page + 1}"))
        nav_buttons.append(InlineKeyboardButton("⏭️ Lᴀsᴛ", callback_data=f"indexpage_{total_pages - 1}"))

    close_button = [InlineKeyboardButton("❌ Cʟᴏsᴇ", callback_data="close_index")]

    keyboard = []
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append(close_button)

    markup = InlineKeyboardMarkup(keyboard)
    return "\n".join(lines), markup


# ------------------ Subscription ------------------ #


async def get_not_joined_channels(user_id: int):
    """Return list of channel/group IDs the user hasn't joined yet."""
    not_joined = []
    for channel_id in AUTH_CHANNELS:
        try:
            member = await client.get_chat_member(channel_id, user_id)
            if member.status not in (
                enums.ChatMemberStatus.MEMBER,
                enums.ChatMemberStatus.ADMINISTRATOR,
                enums.ChatMemberStatus.OWNER,
            ):
                not_joined.append(channel_id)
        except Exception as e:
            # Only add to not_joined, no warning printed for normal "not a member" cases
            err_msg = str(e).lower()
            if "user_not_participant" in err_msg or "user not found" in err_msg:
                # normal, user just not joined
                not_joined.append(channel_id)
            elif "peer id invalid" in err_msg:
                # Bot not in that chat
                print(f"[INFO] Skipping inaccessible chat {channel_id} (bot not member)")
            else:
                # unexpected errors only
                print(f"[ERROR] get_not_joined_channels(): {e}")
                not_joined.append(channel_id)
    return not_joined

async def check_sub_and_send_file(c: Client, m: Message, msg_id: int):
    """Check all subscriptions and send file if user joined all groups/channels."""
    not_joined = await get_not_joined_channels(m.from_user.id)

    if not_joined:
        join_buttons = []

        # Build all join buttons first
        all_buttons = []
        for chat_id in not_joined:
            chat_title = f"Chat {chat_id}"  # default title
            invite_link = "https://t.me"    # default fallback

            try:
                chat = await c.get_chat(chat_id)
                chat_title = chat.title or "Group/Channel"

                if chat.username:
                    invite_link = f"https://t.me/{chat.username}"
                else:
                    try:
                        invite_link = await c.export_chat_invite_link(chat_id)
                    except Exception as e:
                        print(f"[WARN] Cannot export invite link for {chat_id}: {e}")
            except Exception as e:
                print(f"[ERROR] Failed to process {chat_id}: {e}")

            all_buttons.append(InlineKeyboardButton(f"Join: {chat_title}", url=invite_link))

        # Group buttons 2 per row
        for i in range(0, len(all_buttons), 2):
            join_buttons.append(all_buttons[i:i+2])

        # Add "I Joined" button at the end
        join_buttons.append([
            InlineKeyboardButton("✅ I Joined", callback_data=f"retry_{msg_id}")
        ])

        return await m.reply_text(
            "<b>🚫 You must join all our channels/groups to access this file.</b>\n\n"
            "<b>Remaining:</b>",
            reply_markup=InlineKeyboardMarkup(join_buttons),
            parse_mode=enums.ParseMode.HTML
        )

    # ✅ User joined all channels/groups
    try:
        sent = await c.copy_message(
            chat_id=m.chat.id, from_chat_id=INDEX_CHANNEL, message_id=msg_id
        )

        warning = await m.reply(
            f"<b><u>❗️❗️❗️ IMPORTANT ❗️❗️❗️</u></b>\n\n"
            f"ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ <b><u>{DELETE_AFTER_FILE//60}</u> ᴍɪɴᴜᴛᴇs</b> 🫥 "
            "(ᴅᴜᴇ ᴛᴏ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs).\n\n"
            "<b>📌 Please forward this message to your Saved Messages or any private chat to avoid losing it.</b>",
            parse_mode=enums.ParseMode.HTML,
        )

        await asyncio.sleep(DELETE_AFTER_FILE)
        await sent.delete()

        await warning.edit_text(
            "<b>Yᴏᴜʀ Fɪʟᴇ ɪs Sᴜᴄᴄᴇssғᴜʟʟʏ Dᴇʟᴇᴛᴇᴅ.</b>\n"
            "<b>Iғ ʏᴏᴜ Wᴀɴᴛ ᴛʜɪs Fɪʟᴇ Aɢᴀɪɴ ᴛʜᴇɴ Cʟɪᴄᴋ ᴏɴ Bᴇʟᴏᴡ Bᴜᴛᴛᴏɴ</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 Gᴇᴛ Fɪʟᴇ Aɢᴀɪɴ", url=f"{BASE_URL}/redirect?id={msg_id}")]
            ]),
            parse_mode=enums.ParseMode.HTML
        )

    except Exception as e:
        await m.reply(
            f"❌ Error while sending file:\n<code>{e}</code>",
            parse_mode=enums.ParseMode.HTML,
        )





# ------------------ Pagination ------------------ #

ITEMS_PER_PAGE = 6

async def send_paginated_files(
    c: Client,
    user_id: int,
    files: list,
    page: int,
    filename_query: str,
    query: CallbackQuery = None
):
    """Send paginated files to user/group with improved messages and dynamic filename display."""
    user = await c.get_users(user_id)
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

    # Pagination logic
    total_pages = (len(files) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    page = max(0, min(page, total_pages - 1))
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    current_files = files[start:end]

    mention = f"<a href='tg://user?id={user_id}'>{full_name}</a>"
    text = (
        f"<b>👋 Hey {mention},</b>\n\n"
        f"<b>Your requested file(s) for:</b> <code>{filename_query}</code>\n"
        f"<b>have been added and sent to the group ✅</b>\n\n"
        f"<b>📄 Page:</b> {page + 1}/{total_pages}\n\n"
    )

    for i, file_doc in enumerate(current_files, start=1):
        file_name = file_doc["file_name"]
        file_size = round(file_doc.get("file_size", 0) / (1024 * 1024), 2)
        msg_id = file_doc["message_id"]

        text += (
            f"➤ <b>{file_name}</b> — <code>{file_size} MB</code>\n"
            f"    <a href='{BASE_URL}/redirect?id={msg_id}'>📥 Get File</a>\n\n"
        )

    # Navigation buttons
    buttons = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("⬅️ Prev", callback_data=f"nav:{user_id}|{filename_query}:{page - 1}")
        )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton("➡️ Next", callback_data=f"nav:{user_id}|{filename_query}:{page + 1}")
        )
    if nav_buttons:
        buttons.append(nav_buttons)

    markup = InlineKeyboardMarkup(buttons) if buttons else None

    # Edit or send message
    if query:
        # When using inline callback for navigation
        await query.edit_message_text(
            text,
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )
        msg = query.message
    else:
        # Initial message — send to group
        msg = await c.send_message(
            GROUP_ID,
            text,
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )

        # Notify the user privately (optional)
        pm_text = (
            f"<b>✅ Yᴏᴜʀ ʀᴇᴏ̨ᴜᴇsᴛᴇᴅ ғɪʟᴇs ғᴏʀ <code>{filename_query}</code></b> "
            f"<b>ʜᴀᴠᴇ ʙᴇᴇɴ sᴜᴄᴄᴇssғᴜʟʟʏ ᴀᴅᴅᴇᴅ ᴀɴᴅ sᴇɴᴛ ᴛᴏ ᴛʜᴇ ɢʀᴏᴜᴘ.</b>\n\n"
            f"<b><a href='https://t.me/+Dzcz5yk-ayFjODZl'>Cʟɪᴄᴋ Hᴇʀᴇ ᴛᴏ Vɪᴇᴡ</a></b>"
        )

        try:
            await c.send_message(user_id, pm_text, parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass

    # Schedule message deletion
    asyncio.create_task(delete_after_delay(msg, DELETE_DELAY_REQ))




def get_file_buttons(files, query, page):
    total_files = len(files)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total_files)
    current_files = files[start:end]
    buttons = []

    encoded_query = urllib.parse.quote(query)

    for f in current_files:
        size_mb = round(f.get("file_size", 0) / (1024 * 1024), 2)
        name = f['file_name']

        # ✅ Remove known uploader/channel names and any @tags or [MM]
        clean_name = re.sub(
            r'(\[MM\])|@(?:[\w\d_]+|Team_MCU|MCU_Linkz|BatmanLinkz|smile_upload|TCU_linkz|Team_HDT)',
            '',
            name,
            flags=re.IGNORECASE
        )

        # ✅ Remove leftover credits or patterns like "- by @...", "(by ...)", "[by ...]"
        clean_name = re.sub(r'[\(\[\{]?\s*(by|uploaded\s*by)?\s*@[\w\d_]+\s*[\)\]\}]?', '', clean_name, flags=re.IGNORECASE)

        # ✅ Clean extra underscores, hyphens, dots, and multiple spaces
        clean_name = re.sub(r'[_\.\-]{2,}', ' ', clean_name)
        clean_name = re.sub(r'\s{2,}', ' ', clean_name)
        clean_name = re.sub(r'^[\s._\-\[\]]+|[\s._\-\[\]]+$', '', clean_name).strip()

        # ✅ Extract episode pattern like SxxEyy / Eyy / EPyy / SxxEyy-Ezz etc.
        match = re.search(
            r'(S?\d{1,2})[\s._-]*[Vv]?[Oo]?[Ll]?[\s._-]*(E[Pp]?\d{1,3})',
            clean_name,
            re.IGNORECASE
        )

        if match:
            season = match.group(1).upper().replace("S", "").zfill(2)
            episode = re.sub(r"[^\d]", "", match.group(2)).zfill(2)
            episode_info = f"S{season}EP{episode}"
            label = f"🎞 {size_mb}MB | {episode_info} | {clean_name}"
        else:
            label = f"🎞 {size_mb}MB | {clean_name}"

        buttons.append([
            InlineKeyboardButton(label, url=f"{BASE_URL}/redirect?id={f['message_id']}")
        ])

    # ✅ Pagination
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Pʀᴇᴠ", callback_data=f"page_{encoded_query}_{page - 1}"))

    if (page + 1) * PAGE_SIZE < total_files:
        nav.append(InlineKeyboardButton("Nᴇxᴛ ➡️", callback_data=f"page_{encoded_query}_{page + 1}"))

    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


