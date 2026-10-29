import asyncio
import base64
import datetime
import hashlib
import html
import math
import os
import re
import urllib.parse
import socket
from pyrogram import enums, Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery, WebAppInfo
from config import (
    client, files_collection, users_collection, queries_collection, LOG_CHANNEL, BASE_URL,
    DELETE_AFTER_FILE, DELETE_AFTER, DELETE_DELAY_REQ, INDEX_CHANNEL,
    AUTH_CHANNELS, GROUP_ID, MINI_APP_URL, MINI_APP_SHORT_NAME, BOT_USERNAME,
    PAGE_SIZE, INDEX_PAGE_SIZE,
)


REMOVE_TAGS = [
    r'\[MLM\]', r'\[MT\]', r'\[MS\]', r'\[MZM\]', r'\[CF\]', r'\[CP\]', r'\[NRX\]',
    r'\[CT™\]', r'\[PsmOfficial\]', r'\[PFM\]', r'\[FC\]', r'\[KC\]', r'\[YM\]', r'\[A2M\]',
    r'@Team_MCU', r'@MCU_Linkz', r'@BatmanLinkz', r'@smile_upload', r'@TCU_linkz', r'@Team_HDT',
    r'@UHD_Tamil', r'@MCUxLinks', r'@C\.C', r'@TamilAnimationToday', r'@Bucket_LinkZz', r'@PrimeMoviesOffl',
    r'@Nesamani_Linkz', r'@Tamil_Link_Official', r'@TeamHDT', r'@Main_Channel_Noob', r'ATK', r'@HEVCHubX',
    r'@SonyTamizh', r'@Movies_Tamizhaaas', r'@TamilCinemaToday', r'@IM_Eeswaran', r'©FC', r'@MM_Linkz',
    r'@ContenTeam', r'@WorldCinemaToday', r'@MW_Linkz', r'@FBM', r'@MM_New', r'@WMR', r'@Hdnewtamilmoviwa4k',
    r'@CC', r'@dubbedmovies', r'🄼🅂', r'@CEM', r'@AVA', r'@TR_Movies', r'@mersalananthu',
    r'@TamilNewMovie_HD', r'@MC_4U', r'@GethXan_Moviez', r'www_TamilBlasters_me', r'@trollmaa',
    r'@GSR', r'@kc_dio', r'@FBM_Dubbed', r'@Tamilmoviez', r'@mobile_mm', r'@UploaditBot', r'@CC_All',
    r'@Massmovies0', r'@GANGTAMIL_HD', r'@Team_TRR', r'@Moviezstuffofficial',
    r'@Team_5G_', r'@Tamil_Mob_LinksZz', r'@MoviesNowLinks', r'@Movies_Worldda1', r'@Smile_upload',
    r'@mtb_s', r'@Tamil_LinkzZ', r'@SPY_TALKIESS', r'@MOViEZHUNT', r'@SheikXMoviesOffl', r'@Hevc_Mob',
    r'@VideoMemesTamizh', r'@Movies_Graft', r'@THHx265', r'@MoviiWrld', r'@HEVC_Moviesz',
    r'@TamilDubFilms', r'@CelluloidCineClub', r'_@UHDPrime', r'@sokfiles', r'@Rarefilms', r'𝙼𝚁✘', r'ꜰᴏ✘'
]

REMOVE_PATTERN = re.compile(
    r'(' + '|'.join(REMOVE_TAGS) + r'|@[\w\d]+(?=[\s_\-\.]|$))',
    flags=re.IGNORECASE
)



def clean_filename(name: str) -> str:
    """Clean filename by removing tags, credits, and junk characters."""
    base, ext = os.path.splitext(name)

    base = re.sub(REMOVE_PATTERN, '', base)
    base = re.sub(
        r'[\(\[\{]?\s*(?:by|uploaded\s*by)?\s*@[\w\d_]+\s*[\)\]\}]?',
        '',
        base,
        flags=re.IGNORECASE
    )
    base = base.replace("_", " ")
    base = re.sub(r'\.(?!\w+$)', ' ', base)
    base = re.sub(r'^-\s*', '', base)
    base = re.sub(r'[\-]{2,}', ' ', base)
    base = re.sub(r'\s{2,}', ' ', base)
    base = re.sub(r'^[\s.\-\[\]]+|[\s.\-\[\]]+$', '', base).strip()

    return f"{base}{ext}"


def build_search_regex(query: str) -> re.Pattern:
    """
    Build a single compiled fuzzy-search regex from free-text keywords.
    Centralized so every caller uses identical, tested search behavior
    instead of six near-duplicate copies of the same three lines.
    """
    keywords = [k for k in re.split(r"\s+", query.strip()) if k]
    if not keywords:
        # Never compile an empty pattern (matches everything / wastes a full scan).
        return re.compile(r"(?!x)x")  # a pattern that matches nothing
    pattern = ".*".join(re.escape(k) for k in keywords)
    return re.compile(pattern, re.IGNORECASE)


# ------------------ User Utilities ------------------ #

async def save_user(user_id):
    if users_collection.find_one({"user_id": user_id}):
        return
    try:
        user = await client.get_users(user_id)
    except Exception as e:
        print(f"[WARN] save_user(): could not fetch user {user_id}: {e}")
        user = None

    users_collection.update_one(
        {"user_id": user_id}, {"$setOnInsert": {"user_id": user_id}}, upsert=True
    )

    if LOG_CHANNEL:
        name = getattr(user, "first_name", None) or "Unknown"
        msg = (
            f"#New_Bot_User\n\n"
            f"» ɴᴀᴍᴇ - <a href='tg://user?id={user_id}'>{name}</a>\n"
            f"» ɪᴅ - <code>{user_id}</code>"
        )
        try:
            await client.send_message(LOG_CHANNEL, msg, parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            print(f"[WARN] Failed to log new user: {e}")


async def delete_after_delay(msg: Message, delay: int):
    try:
        await asyncio.sleep(delay)
        await msg.delete()
    except Exception as e:
        print(f"[WARN] Failed to delete message: {e}")


# ------------------ File Parsing ------------------ #

def extract_season_episode(name: str):
    patterns = [
        r'[Ss](\d{1,2})[._\s-]*[EePp]+[._\s-]*(\d{1,3})',
        r'[Ss]eason[._\s-]*(\d{1,2})[._\s-]*[Ee]pisode[._\s-]*(\d{1,3})',
        r'[Ss](\d{1,2})[._\s-]*Ep[._\s-]*(\d{1,3})',
        r'[Ss](\d{1,2})\s*[._-]*\s*ep\s*(\d{1,3})',
    ]
    for p in patterns:
        if match := re.search(p, name, re.IGNORECASE):
            s = match.group(1).zfill(2)
            e = match.group(2).zfill(2)
            return f"S{s}EP{e}"

    ep_range_patterns = [
        r'\bep?\s*(\d{1,3})\s*[-–~to]+\s*ep?\s*(\d{1,3})\b',
        r'\be\s*(\d{1,3})\s*[-–~to]+\s*e?\s*(\d{1,3})\b',
        r'\bepisode\s*(\d{1,3})\s*[-–~to]+\s*episode\s*(\d{1,3})\b',
    ]
    for p in ep_range_patterns:
        if match := re.search(p, name, re.IGNORECASE):
            ep_start = match.group(1).zfill(2)
            ep_end = match.group(2).zfill(2)
            return f"EP{ep_start}-EP{ep_end}"

    single_ep_patterns = [
        r'\bep?\s*(\d{1,3})\b',
        r'\be\s*(\d{1,3})\b',
        r'\bepisode\s*(\d{1,3})\b',
    ]
    for p in single_ep_patterns:
        if match := re.search(p, name, re.IGNORECASE):
            return f"EP{match.group(1).zfill(2)}"

    season_patterns = [
        r'\bs(\d{1,2})\b',
        r'season\s*(\d{1,2})'
    ]
    for p in season_patterns:
        if match := re.search(p, name, re.IGNORECASE):
            return f"S{match.group(1).zfill(2)}"

    if re.search(r'\b(chapter|part|movie|vol|volume)\s*\d{1,3}\b', name, re.IGNORECASE):
        return None

    return None


def run_flask_app(flask_app):
    sock = socket.socket()
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()
    print(f"Starting Flask on port {port}")
    flask_app.run(host='0.0.0.0', port=port)


# ------------------ File Buttons & Pagination ------------------ #

def query_token(query: str) -> str:
    """
    Short, callback-safe id for a search query. Telegram rejects inline
    buttons whose callback_data exceeds 64 bytes, which long or non-English
    queries easily do — so the query is stored in MongoDB and only this
    12-char token travels in the button.
    """
    q = (query or "").strip()
    token = hashlib.sha1(q.lower().encode("utf-8")).hexdigest()[:12]
    try:
        queries_collection.update_one(
            {"_id": token},
            {"$setOnInsert": {"query": q, "created_at": datetime.datetime.utcnow()}},
            upsert=True,
        )
    except Exception as e:
        print(f"[WARN] query_token(): could not store query: {e}")
    return token


def resolve_query_token(token: str) -> str:
    """Turn a token back into the query. Falls back to the legacy
    URL-encoded format used by buttons sent before this change."""
    if token == "all":
        return ""
    try:
        doc = queries_collection.find_one({"_id": token})
        if doc and doc.get("query") is not None:
            return doc["query"]
    except Exception as e:
        print(f"[WARN] resolve_query_token(): {e}")
    return urllib.parse.unquote(token)


def file_open_link(message_id) -> str:
    """Mini App deep link for a file, or the web /redirect page if no Mini App is set up."""
    return build_miniapp_file_link(message_id) or f"{BASE_URL}/redirect?id={message_id}"


def build_index_page(files, page, total_pages, total_count, query=""):
    """Render ONE already-fetched page of the /files index (+ nav buttons that
    remember the search query)."""
    token = query_token(query) if query else "all"
    start = page * INDEX_PAGE_SIZE

    title = "📄 <b>Sᴛᴏʀᴇᴅ Fɪʟᴇs</b>"
    if query:
        title += f" — <code>{html.escape(query)}</code>"
    lines = [f"{title}\n<b>Pᴀɢᴇ:</b> {page + 1}/{total_pages} • <b>Tᴏᴛᴀʟ:</b> {total_count}\n"]

    for i, f in enumerate(files, start=start + 1):
        file_size = f.get("file_size") or 0
        size_mb = round(file_size / (1024 * 1024), 2)
        clean_name = html.escape(clean_filename(f.get("file_name") or "") or "File")
        link = file_open_link(f["message_id"])
        lines.append(f"{i}. <a href='{link}'>{clean_name}</a> ({size_mb} MB)")

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⏮️ Fɪʀsᴛ", callback_data=f"indexpage_0_{token}"))
        nav_buttons.append(InlineKeyboardButton("⬅️ Pʀᴇᴠ", callback_data=f"indexpage_{page - 1}_{token}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Nᴇxᴛ ➡️", callback_data=f"indexpage_{page + 1}_{token}"))
        nav_buttons.append(InlineKeyboardButton("⏭️ Lᴀsᴛ", callback_data=f"indexpage_{total_pages - 1}_{token}"))

    keyboard = []
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("❌ Cʟᴏsᴇ", callback_data="close_index")])
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


def fetch_index_page(query: str, page: int):
    """Query MongoDB for just the requested /files page (filtered by `query`
    when given). Returns (text, markup) or None when nothing matches."""
    flt = {"file_name": {"$regex": build_search_regex(query)}} if query else {}
    total = files_collection.count_documents(flt)
    if total == 0:
        return None
    total_pages = max(1, math.ceil(total / INDEX_PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    docs = list(
            files_collection.find(flt)
            .sort([
                ("file_name", 1),
                ("_id", 1),
            ])
            .skip(page * INDEX_PAGE_SIZE)
            .limit(INDEX_PAGE_SIZE)
        )
    return build_index_page(docs, page, total_pages, total, query)


# ------------------ Subscription ------------------ #

async def get_not_joined_channels(user_id: int):
    """Return list of channel/group IDs the user hasn't joined yet (checked in parallel)."""

    async def _check(channel_id):
        try:
            member = await client.get_chat_member(channel_id, user_id)
            if member.status not in (
                enums.ChatMemberStatus.MEMBER,
                enums.ChatMemberStatus.ADMINISTRATOR,
                enums.ChatMemberStatus.OWNER,
            ):
                return channel_id
            return None
        except Exception as e:
            err_msg = str(e).lower()
            if "user_not_participant" in err_msg or "user not found" in err_msg:
                return channel_id
            if "peer_id_invalid" in err_msg or "chat_admin_required" in err_msg:
                print(f"[INFO] Skipping inaccessible chat {channel_id} (bot not member/admin)")
                return None
            print(f"[ERROR] get_not_joined_channels(): {e}")
            return channel_id

    results = await asyncio.gather(*(_check(cid) for cid in AUTH_CHANNELS))
    return [cid for cid in results if cid is not None]


async def check_sub_and_send_file(c: Client, m: Message, msg_id: int, user_id: int = None):
    """Check all subscriptions and send file if user joined all groups/channels.

    `user_id` must be passed when `m` is one of the BOT's own messages (as in
    the "I Joined" callback) — otherwise `m.from_user` is the bot, and the
    membership check would run against the bot instead of the real user.
    """
    not_joined = await get_not_joined_channels(user_id or m.from_user.id)

    if not_joined:
        all_buttons = []
        for chat_id in not_joined:
            chat_title = f"Chat {chat_id}"
            invite_link = "https://t.me"

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

        join_buttons = [all_buttons[i:i + 2] for i in range(0, len(all_buttons), 2)]
        join_buttons.append([InlineKeyboardButton("✅ I Joined", callback_data=f"retry_{msg_id}")])

        return await m.reply_text(
            "<b>🚫 You must join all our channels/groups to access this file.</b>\n\n"
            "<b>Remaining:</b>",
            reply_markup=InlineKeyboardMarkup(join_buttons),
            parse_mode=enums.ParseMode.HTML
        )

    try:
        sent = await c.copy_message(
            chat_id=m.chat.id, from_chat_id=INDEX_CHANNEL, message_id=msg_id
        )

        warning = await m.reply(
            f"<b><u>❗️❗️❗️ IMPORTANT ❗️❗️❗️</u></b>\n\n"
            f"ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ <b><u>{DELETE_AFTER_FILE // 60}</u> ᴍɪɴᴜᴛᴇs</b> 🫥 "
            "(ᴅᴜᴇ ᴛᴏ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs).\n\n"
            "<b>📌 Please forward this message to your Saved Messages or any private chat to avoid losing it.</b>",
            parse_mode=enums.ParseMode.HTML,
        )

        asyncio.create_task(_expire_delivered_file(sent, warning, msg_id, DELETE_AFTER_FILE))

    except Exception as e:
        await m.reply(
            f"❌ Error while sending file:\n<code>{e}</code>",
            parse_mode=enums.ParseMode.HTML,
        )


async def _expire_delivered_file(sent: Message, warning: Message, msg_id: int, delay: int):
    """Background task: delete the delivered file after `delay` and update the warning message."""
    try:
        await asyncio.sleep(delay)
        await sent.delete()
        await warning.edit_text(
            "<b>ʏᴏᴜʀ ғɪʟᴇ ɪs sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ.</b>\n"
            "<b>ɪғ ʏᴏᴜ ᴡᴀɴᴛ ᴛʜɪs ғɪʟᴇ ᴀɢᴀɪɴ ᴛʜᴇɴ ᴄʟɪᴄᴋ ᴏɴ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ ↓</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 Gᴇᴛ Fɪʟᴇ Aɢᴀɪɴ", url=f"{BASE_URL}/redirect?id={msg_id}")]
            ]),
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        print(f"[WARN] _expire_delivered_file(): {e}")


# ------------------ Pagination ------------------ #

async def send_paginated_files(
    c: Client,
    user_id: int,
    files: list,
    page: int,
    filename_query: str,
    query: CallbackQuery = None
):
    """Send paginated files to user/group with cleaned filenames."""
    try:
        user = await c.get_users(user_id)
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    except Exception:
        full_name = str(user_id)

    total_pages = max(1, (len(files) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    current_files = files[start:end]

    mention = f"<a href='tg://user?id={user_id}'>{full_name}</a>"
    text = (
        f"<b>👋 Hey {mention},</b>\n\n"
        f"<b>Your requested file(s) for:</b> <code>{html.escape(filename_query)}</code>\n"
        f"<b>have been added✅</b>\n\n"
        f"<b>📄 Page:</b> {page + 1}/{total_pages}\n\n"
    )

    for file_doc in current_files:
        raw_name = file_doc.get("file_name", "")
        file_name = html.escape(clean_filename(raw_name))
        file_size = round((file_doc.get("file_size") or 0) / (1024 * 1024), 2)
        msg_id = file_doc["message_id"]

        # Same as get_file_buttons(): open the Mini App deep-linked to this
        # exact file when configured, otherwise fall back to the web page.
        get_link = file_open_link(msg_id)

        text += (
            f"➤ <b>{file_name}</b> — <code>{file_size} MB</code>\n"
            f"    <a href='{get_link}'>📥 Get File</a>\n\n"
        )

    buttons = []
    nav_buttons = []
    token = query_token(filename_query)
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("⬅️ Prev", callback_data=f"nav:{user_id}|{token}:{page - 1}")
        )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton("➡️ Next", callback_data=f"nav:{user_id}|{token}:{page + 1}")
        )
    if nav_buttons:
        buttons.append(nav_buttons)

    markup = InlineKeyboardMarkup(buttons) if buttons else None

    if query:
        await query.edit_message_text(
            text,
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )
        msg = query.message
    else:
        msg = await c.send_message(
            GROUP_ID,
            text,
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )

        pm_text = (
            f"<b>✅ Your requested files for <code>{html.escape(filename_query)}</code></b> "
            f"<b>have been successfully added and sent to the group.</b>\n\n"
            f"<b><a href='https://t.me/+Dzcz5yk-ayFjODZl'>Click Here to View</a></b>"
        )
        try:
            await c.send_message(user_id, pm_text, parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass

    asyncio.create_task(delete_after_delay(msg, DELETE_DELAY_REQ))


def get_file_buttons(files, query, page):
    total_files = len(files)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total_files)
    current_files = files[start:end]
    buttons = []

    token = query_token(query)

    for f in current_files:
        file_size = f.get("file_size", 0) or 0
        size_mb = file_size / (1024 * 1024)
        if size_mb >= 1024:
            size_str = f"{round(size_mb / 1024, 2)} GB"
        else:
            size_str = f"{round(size_mb, 2)} MB"

        name = f.get("file_name", "")
        clean_name = clean_filename(name)
        episode_info = extract_season_episode(clean_name)

        if episode_info:
            label = f"🎞 {size_str} | {episode_info} | {clean_name}"
        else:
            label = f"🎞 {size_str} | {clean_name}"

        # Every result opens the Mini App directly (deep-linked to this exact
        # file via startapp=file_<id>) instead of the plain web /redirect
        # page, whenever a Mini App short name is configured. Falls back to
        # the web redirect page automatically if it isn't.
        target_url = file_open_link(f["message_id"])

        buttons.append([
            InlineKeyboardButton(label, url=target_url)
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Pʀᴇᴠ", callback_data=f"page_{token}_{page - 1}"))
    if (page + 1) * PAGE_SIZE < total_files:
        nav.append(InlineKeyboardButton("Nᴇxᴛ ➡️", callback_data=f"page_{token}_{page + 1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


def build_miniapp_deep_link(query: str) -> str | None:
    """
    Build a t.me direct-link URL that opens the bot's Mini App with a raw
    search QUERY (not a specific file) passed through `startapp`, base64url
    encoded. Not currently called anywhere — every search result now uses
    build_miniapp_file_link() below to jump straight to a specific file
    instead. Kept as a general-purpose utility if you want a "search inside
    the app" style entry point elsewhere later.

    A regular `web_app=WebAppInfo(url=...)` button (used in the private
    /start menu) only works in private chats — Telegram silently refuses to
    render that button type inside a group's inline keyboard. A plain `url`
    button pointing at `https://t.me/<bot_username>/<short_name>?startapp=...`
    is just a normal link, so it works everywhere, including groups, and
    Telegram clients that support Mini Apps open it in-app automatically.

    Requires MINI_APP_SHORT_NAME to be configured (via @BotFather -> /newapp);
    returns None if it isn't, so callers can skip the button entirely rather
    than emit a broken link.
    """
    if not MINI_APP_SHORT_NAME or not BOT_USERNAME or not query:
        return None

    # startapp must match ^[A-Za-z0-9_-]{1,64}$ — base64url encoding the raw
    # query naturally satisfies that alphabet; truncate defensively to the
    # 64-char hard limit Telegram enforces.
    encoded = base64.urlsafe_b64encode(query.encode("utf-8")).decode("ascii").rstrip("=")
    encoded = encoded[:64]
    return f"https://t.me/{BOT_USERNAME}/{MINI_APP_SHORT_NAME}?startapp={encoded}"


def build_miniapp_file_link(message_id: int) -> str | None:
    """
    Direct t.me link that opens the bot's Mini App with a SPECIFIC file's
    message_id passed through `startapp` (as `file_<id>`), so tapping an
    individual search result opens the Mini App itself rather than the plain
    web /redirect page. Falls back to None (caller uses the web redirect
    page instead) when MINI_APP_SHORT_NAME isn't configured.
    """
    if not MINI_APP_SHORT_NAME or not BOT_USERNAME or not message_id:
        return None
    return f"https://t.me/{BOT_USERNAME}/{MINI_APP_SHORT_NAME}?startapp=file_{message_id}"


def build_custom_caption(file_name: str) -> str:
    """
    Small caption builder used when resending a file via the inline 'get_' callback.
    (Previously missing entirely — callbacks.py called this function without it being
    defined anywhere, which raised NameError and made the resend feature completely broken.)
    """
    clean_name = clean_filename(file_name or "File")
    return f"<b>{clean_name}</b>\n\nBy @BatmanLinkz"
