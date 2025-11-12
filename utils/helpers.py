import asyncio
import os
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

REMOVE_TAGS = [
    r'\[MM\]', r'\[MLM\]', r'\[MT\]', r'\[MS\]', r'\[MZM\]', r'\[CF\]', r'\[CP\]', r'\[NRX\]',
    r'\[CT™\]', r'\[PsmOfficial\]', r'\[PFM\]', r'\[FC\]', r'\[KC\]', r'\[YM\]', r'\[A2M\]', r'\[CL\]',
    r'@Team_MCU', r'@MCU_Linkz', r'@BatmanLinkz', r'@smile_upload', r'@TCU_linkz', r'@Team_HDT',
    r'@UHD_Tamil', r'@MCUxLinks', r'@C\.C', r'@TamilAnimationToday', r'@Bucket_LinkZz', r'@PrimeMoviesOffl',
    r'@Nesamani_Linkz', r'@Tamil_Link_Official', r'@TeamHDT', r'@Main_Channel_Noob', r'ATK', r'@HEVCHubX',
    r'@SonyTamizh', r'@Movies_Tamizhaaas', r'@TamilCinemaToday', r'@IM_Eeswaran', r'©FC', r'@MM_Linkz',
    r'@ContenTeam', r'@WorldCinemaToday', r'@MW_Linkz', r'@FBM', r'@MM_New', r'@WMR', r'@Hdnewtamilmoviwa4k',
    r'@CC', r'@dubbedmovies', r'🄼🅂', r'@CEM', r'@AVA', r'@TR_Movies', r'@mersalananthu',
    r'@TamilNewMovie_HD', r'@MC_4U', r'@GethXan_Moviez', r'www_TamilBlasters_me', r'mm', r'@trollmaa',
    r'@GSR', r'@kc_dio', r'@FBM_Dubbed', r'@Tamilmoviez', r'@mobile_mm', r'@UploaditBot', r'@CC_All',
    r'@Massmovies0', r'@GANGTAMIL_HD', r'@Team_TRR', r'@Moviezstuffofficial',
    r'@Team_5G_', r'@Tamil_Mob_LinksZz', r'@MoviesNowLinks', r'@Movies_Worldda1', r'@Smile_upload',
    r'@mtb_s', r'@Tamil_LinkzZ', r'@SPY_TALKIESS', r'@MOViEZHUNT', r'@SheikXMoviesOffl', r'@Hevc_Mob',
    r'@VideoMemesTamizh', r'@Movies_Graft', r'@THHx265', r'@MoviiWrld', r'@HEVC_Moviesz',
    r'@TamilDubFilms', r'@CelluloidCineClub',r'_@UHDPrime', r'@sokfiles', r'@Rarefilms', r'𝙼𝚁✘', r'ꜰᴏ✘'
]
REMOVE_PATTERN = re.compile(
    r'(' + '|'.join(REMOVE_TAGS) + r'|@[\w\d]+(?=[\s_\-\.]|$))',
    flags=re.IGNORECASE
)

def clean_filename(name: str) -> str:
    """Clean filename by removing tags, credits, and junk characters."""

    # Separate base name and extension (so we don't modify the extension)
    base, ext = os.path.splitext(name)

    # Remove known uploader/channel tags
    base = re.sub(REMOVE_PATTERN, '', base)

    # Remove leftover "by @..." or "(by ...)"
    base = re.sub(
        r'[\(\[\{]?\s*(?:by|uploaded\s*by)?\s*@[\w\d_]+\s*[\)\]\}]?',
        '',
        base,
        flags=re.IGNORECASE
    )

    # Replace underscores with spaces
    base = base.replace("_", " ")

    # Replace dots with spaces (but not the one before the extension)
    base = re.sub(r'\.(?!\w+$)', ' ', base)

    # Remove a leading dash "-" (only if at the start)
    base = re.sub(r'^-\s*', '', base)

    # Clean redundant dashes, extra spaces
    base = re.sub(r'[\-]{2,}', ' ', base)
    base = re.sub(r'\s{2,}', ' ', base)

    # Trim unwanted characters from start and end
    base = re.sub(r'^[\s.\-\[\]]+|[\s.\-\[\]]+$', '', base).strip()

    # Reattach extension
    return f"{base}{ext}"

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


def extract_season_episode(name: str):
    # 1️⃣ Season + Episode range
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

    # 2️⃣ Episode range only
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

    # 3️⃣ Single episode only
    single_ep_patterns = [
        r'\bep?\s*(\d{1,3})\b',
        r'\be\s*(\d{1,3})\b',
        r'\bepisode\s*(\d{1,3})\b',
    ]
    for p in single_ep_patterns:
        if match := re.search(p, name, re.IGNORECASE):
            return f"EP{match.group(1).zfill(2)}"

    # 4️⃣ Season-only
    season_patterns = [
        r'\bs(\d{1,2})\b',
        r'season\s*(\d{1,2})'
    ]
    for p in season_patterns:
        if match := re.search(p, name, re.IGNORECASE):
            return f"S{match.group(1).zfill(2)}"

    # 5️⃣ Ignore “chapter 1”, “part 1”, “volume 1”, etc.
    if re.search(r'\b(chapter|part|movie|vol|volume)\s*\d{1,3}\b', name, re.IGNORECASE):
        return None

    # ✅ No fallback numeric detection
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
        clean_name = clean_filename(file_name)  # ✅ use your existing cleaner
        link = f"{BASE_URL}/redirect?id={f['message_id']}"
        lines.append(f"{i}. <a href='{link}'>{clean_name}</a> ({size_mb} MB)")

    # Pagination buttons
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
            "<b>ʏᴏᴜʀ ғɪʟᴇ ɪs sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ.</b>\n"
            "<b>ɪғ ʏᴏᴜ ᴡᴀɴᴛ ᴛʜɪs ғɪʟᴇ ᴀɢᴀɪɴ ᴛʜᴇɴ ᴄʟɪᴄᴋ ᴏɴ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ ↓</b>",
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
    """Send paginated files to user/group with cleaned filenames."""
    user = await c.get_users(user_id)
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

    total_pages = (len(files) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    page = max(0, min(page, total_pages - 1))
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    current_files = files[start:end]

    mention = f"<a href='tg://user?id={user_id}'>{full_name}</a>"
    text = (
        f"<b>👋 Hey {mention},</b>\n\n"
        f"<b>Your requested file(s) for:</b> <code>{filename_query}</code>\n"
        f"<b>have been added✅</b>\n\n"
        f"<b>📄 Page:</b> {page + 1}/{total_pages}\n\n"
    )

    # ✅ Apply cleaning before display
    for i, file_doc in enumerate(current_files, start=1):
        raw_name = file_doc["file_name"]
        file_name = clean_filename(raw_name)
        file_size = round(file_doc.get("file_size", 0) / (1024 * 1024), 2)
        msg_id = file_doc["message_id"]

        text += (
            f"➤ <b>{file_name}</b> — <code>{file_size} MB</code>\n"
            f"    <a href='{BASE_URL}/redirect?id={msg_id}'>📥 Get File</a>\n\n"
        )

    # Pagination buttons
    buttons = []
    nav_buttons = []
    encoded_query = urllib.parse.quote(filename_query)
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("⬅️ Prev", callback_data=f"nav:{user_id}|{encoded_query}:{page - 1}")
        )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton("➡️ Next", callback_data=f"nav:{user_id}|{encoded_query}:{page + 1}")
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

        # Notify user in PM
        pm_text = (
            f"<b>✅ Your requested files for <code>{filename_query}</code></b> "
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

    encoded_query = urllib.parse.quote(query)

    for f in current_files:
        file_size = f.get("file_size", 0)
        # ✅ Auto-format size: show in GB if >= 1024 MB
        size_mb = file_size / (1024 * 1024)
        if size_mb >= 1024:
            size_str = f"{round(size_mb / 1024, 2)} GB"
        else:
            size_str = f"{round(size_mb, 2)} MB"

        name = f["file_name"]
        clean_name = clean_filename(name)
        episode_info = extract_season_episode(clean_name)

        # ✅ Build label
        if episode_info:
            label = f"🎞 {size_str} | {episode_info} | {clean_name}"
        else:
            label = f"🎞 {size_str} | {clean_name}"

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






