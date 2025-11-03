import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery,WebAppInfo
from config import client, files_collection, GROUP_ID, BASE_URL, BOT_USERNAME,INDEX_CHANNEL,MINI_APP_URL, UPDATES_CHANNEL, MOVIES_GROUP,ADMIN_ID, LOG_CHANNEL,DELETE_DELAY,DELETE_AFTER
from utils.helpers import save_user, delete_after_delay,users_collection,files_collection, check_sub_and_send_file,build_index_page,get_file_buttons,send_paginated_files

PAGE_SIZE = 6  # Default delay for messages in seconds

# ------------------ Group /start ------------------ #
@client.on_message(filters.private & filters.command("help"))
async def help_cmd(c, m: Message):
    await m.reply_text(
         "<b>Hᴏᴡ ᴛᴏ Usᴇ Mᴇ?</b>\n\n"
        "<b>🔹 Jᴜsᴛ Sᴇɴᴅ ᴀɴʏ Mᴏᴠɪᴇ Nᴀᴍᴇ.</b>\n"
        "<b>🔹 I’ʟʟ Sʜᴏᴡ ʏᴏᴜ ᴛʜᴇ Aᴠᴀɪʟᴀʙʟᴇ Lɪɴᴋs ᴡɪᴛʜ Sɪᴢᴇs.</b>\n"
        "<b>🔹 Cʟɪᴄᴋ ᴛʜᴇ Oɴᴇ ʏᴏᴜ Wᴀɴᴛ, ᴀɴᴅ I’ʟʟ Sᴇɴᴅ ɪᴛ ᴛᴏ Yᴏᴜ!</b>\n\n"
        "<b>🎥 Fᴏʀ Lᴀᴛᴇsᴛ Mᴏᴠɪᴇs, Jᴏɪɴ @Batmanlinkz</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Join Here", url="https://t.me/batmanlinkz")]
        ])
    )


# ------------------ /report Command ------------------ #
@client.on_message(filters.command("report") & (filters.group | filters.private))
async def report_handler(c: Client, m: Message):
    # Extract report text
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        return await m.reply(
            "❗ Usage:\n<code>/report your message here</code>",
            parse_mode=enums.ParseMode.HTML
        )

    report_text = parts[1].strip()

    # Build user info safely
    if m.from_user:
        user_mention = f"<a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>"
        user_id = m.from_user.id
    else:
        user_mention = "Unknown User"
        user_id = "N/A"

    chat_info = (
        f"🗣 Group: <code>{m.chat.title}</code> ({m.chat.id})"
        if m.chat.type != enums.ChatType.PRIVATE else "👤 Private Chat"
    )

    log_text = (
        f"🚨 <b>New Report</b>\n\n"
        f"👤 From: {user_mention}\n"
        f"🆔 User ID: <code>{user_id}</code>\n"
        f"{chat_info}\n\n"
        f"📝 Report:\n<code>{report_text}</code>"
    )

    try:
        if LOG_CHANNEL:
            await client.send_message(LOG_CHANNEL, log_text, parse_mode=enums.ParseMode.HTML)
            await m.reply("✅ Your report has been submitted. Thanks!", quote=True)
        else:
            await m.reply("❌ Log channel is not set.", quote=True)
    except Exception as e:
        await m.reply(f"❌ Failed to send report:\n<code>{e}</code>", parse_mode=enums.ParseMode.HTML)


@client.on_message(filters.command("status") & filters.user(ADMIN_ID))
async def status(_, m: Message):
    total = users_collection.count_documents({})
    deleted = 0
    blocked = 0

    msg = await m.reply("⏳ Checking user status...")

    for user in users_collection.find():
        try:
            await client.get_users(user["user_id"])
        except Exception as e:
            if "deleted account" in str(e).lower():
                deleted += 1
            elif "USER_IS_BLOCKED" in str(e):
                blocked += 1
        await asyncio.sleep(0.05)

    active = total - deleted - blocked

    await msg.edit_text(
        f"📊 <b>Bot Status:</b>\n\n"
        f"👥 Total Users: <code>{total}</code>\n"
        f"✅ Active Users: <code>{active}</code>\n"
        f"🚫 Blocked Users: <code>{blocked}</code>\n"
        f"🗑 Deleted Accounts: <code>{deleted}</code>",
        parse_mode=enums.ParseMode.HTML
    )

# ------------------ /send ------------------ #
@client.on_message(filters.command("send") & filters.user(ADMIN_ID))
async def send_file_paginated_handler(c: Client, m: Message):
    try:
        parts = m.text.split(maxsplit=2)
        if len(parts) < 3:
            return await m.reply(
                "❗ Usage: `/send <user_id> <filename>`",
                parse_mode=enums.ParseMode.MARKDOWN
            )

        user_id = int(parts[1])
        filename_query = parts[2].strip()

        try:
            user = await c.get_users(user_id)
        except Exception:
            user = None

        # Fuzzy search using regex
        keywords = re.split(r"\s+", filename_query)
        regex_pattern = ".*".join(map(re.escape, keywords))
        regex = re.compile(regex_pattern, re.IGNORECASE)
        matching_files = list(files_collection.find({"file_name": {"$regex": regex}}))

        if not matching_files:
            return await m.reply("❌ No files found matching your query.")

        # Send paginated files (first page)
        await send_paginated_files(c, user_id, matching_files, 0, filename_query)

        # Confirmation
        if user:
            name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            await m.reply(f"✅ Sent to <a href='tg://user?id={user_id}'>{name}</a>", parse_mode=enums.ParseMode.HTML)
        else:
            await m.reply(f"✅ Files sent to user ID: <code>{user_id}</code>", parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        await m.reply(f"❌ Error:\n<code>{e}</code>", parse_mode=enums.ParseMode.HTML)

# ------------------ /link ------------------ #
@client.on_message(filters.command("link") & filters.user(ADMIN_ID))
async def link_handler(c: Client, m: Message):
    if not m.reply_to_message:
        return await m.reply("❌ Please reply to a message with `/link`.", quote=True)

    reply = m.reply_to_message
    try:
        fwd_msg = await reply.copy(chat_id=INDEX_CHANNEL)
    except Exception as e:
        return await m.reply(f"❌ Failed to copy message: {e}")

    file_name = reply.text or getattr(reply, "caption", None) or "Unnamed"
    files_collection.insert_one({
        "file_name": file_name,
        "message_id": fwd_msg.id,
        "type": "generic"
    })

    redirect_link = f"{BASE_URL}/redirect?id={fwd_msg.id}"
    await m.reply(f"✅ File indexed!\n\n<code>{redirect_link}</code>", parse_mode=enums.ParseMode.HTML)

# ------------------ Broadcast ------------------ #
@client.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast(_, m: Message):
    if not m.reply_to_message:
        return await m.reply("❗ Reply to a message to broadcast.")

    sent, failed = 0, 0
    for user in users_collection.find():
        try:
            await m.reply_to_message.copy(user["user_id"])
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.1)

    await m.reply(f"✅ Broadcast done.\n✔️ Sent: {sent}\n❌ Failed: {failed}")

# ------------------ Pagination Callback ------------------ #
@client.on_callback_query(filters.regex(r"^nav:(\d+)\|(.+):(\d+)$"))
async def handle_pagination_nav(c: Client, query: CallbackQuery):
    try:
        match = re.match(r"^nav:(\d+)\|(.+):(\d+)$", query.data)
        if not match:
            return await query.answer("Invalid navigation.")

        user_id = int(match.group(1))
        filename_query = match.group(2)
        page = int(match.group(3))

        # Fuzzy search again
        keywords = re.split(r"\s+", filename_query)
        regex_pattern = ".*".join(map(re.escape, keywords))
        regex = re.compile(regex_pattern, re.IGNORECASE)
        matching_files = list(files_collection.find({"file_name": {"$regex": regex}}))

        await send_paginated_files(c, user_id, matching_files, page, filename_query, query)

    except Exception as e:
        await query.answer(f"❌ Error: {e}", show_alert=True)


# ------------------ /files command ------------------ #
@client.on_message(filters.command("files"))
async def index_list(c: Client, m: Message):
    command_parts = m.text.split(maxsplit=1)
    query = command_parts[1].strip() if len(command_parts) > 1 else ""

    if query:
        keywords = re.split(r"\s+", query)
        regex_pattern = ".*".join(map(re.escape, keywords))
        regex = re.compile(regex_pattern, re.IGNORECASE)
        files = list(files_collection.find({"file_name": {"$regex": regex}}).sort("file_name", 1))
    else:
        files = list(files_collection.find().sort("file_name", 1))

    if not files:
        return await m.reply("📂 No matching files found.")

    text, buttons = build_index_page(files, 0)
    await m.reply(text, parse_mode=enums.ParseMode.HTML, reply_markup=buttons, disable_web_page_preview=True)



# ------------------ Private /start ------------------ #
@client.on_message(filters.command("start") & (filters.private | filters.group))
async def start(c: Client, m: Message):
    if m.chat.type == enums.ChatType.PRIVATE:
        await save_user(m.from_user.id)

    args = m.text.split(maxsplit=1)

    # Deep link with file
    if len(args) > 1 and args[1].startswith("file_") and m.chat.type == enums.ChatType.PRIVATE:
        try:
            msg_id = int(args[1].split("_")[1])
            await check_sub_and_send_file(c, m, msg_id)
        except Exception as e:
            msg = await m.reply(
                f"❌ Error:\n<code>{e}</code>",
                parse_mode=enums.ParseMode.HTML
            )
            asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))
        return

    # Deep link with search
    if len(args) > 1 and args[1].startswith("search_") and m.chat.type == enums.ChatType.PRIVATE:
        query = args[1].replace("search_", "").replace("_", " ").strip()

        keywords = re.split(r"\s+", query)
        regex_pattern = ".*".join(map(re.escape, keywords))
        regex = re.compile(regex_pattern, re.IGNORECASE)

        results = list(files_collection.find({"file_name": {"$regex": regex}}))

        if not results:
            msg = await m.reply(
                f"❗️No results found for <b>{query}</b>",
                parse_mode=enums.ParseMode.HTML
            )
            asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))
            return

        markup = get_file_buttons(results, query, 0)
        msg = await m.reply(
            f"🔍 Search results for <b>{query}</b>:",
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML
        )
        asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))
        return

    # Default welcome
    name = m.from_user.first_name if m.from_user else "User"

    # Private: show WebApp button (opens inside Telegram)
    if m.chat.type == enums.ChatType.PRIVATE:
        keyboard = InlineKeyboardMarkup([
            [ InlineKeyboardButton("🚀 Oᴘᴇɴ Mɪɴɪ Aᴘᴘ", web_app=WebAppInfo(url=MINI_APP_URL)) ],
            [ InlineKeyboardButton("📢 Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ", url=UPDATES_CHANNEL),
              InlineKeyboardButton("Hᴇʟᴘ❓", callback_data="help_info") ],
            [ InlineKeyboardButton("🎬 Mᴏᴠɪᴇ Sᴇᴀʀᴄʜ Gʀᴏᴜᴘ", url=MOVIES_GROUP) ]
        ])
    else:
        # Group: don't show web_app button (it may not behave well in groups),
        # show link to bot or channel instead
        keyboard = InlineKeyboardMarkup([
            [ InlineKeyboardButton("🚀 Oᴘᴇɴ Mɪɴɪ Aᴘᴘ", web_app=WebAppInfo(url=MINI_APP_URL)) ],
            [ InlineKeyboardButton("📢 Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ", url=UPDATES_CHANNEL),
              InlineKeyboardButton("Hᴇʟᴘ❓", callback_data="help_info") ],
            [ InlineKeyboardButton("🎬 Mᴏᴠɪᴇ Sᴇᴀʀᴄʜ Gʀᴏᴜᴘ", url=MOVIES_GROUP) ],
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

    # Auto-delete welcome in groups only
    if m.chat.type != enums.ChatType.PRIVATE:
        asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))




# ------------------ Group Text Search ------------------ #
@client.on_message((filters.group | filters.private) & filters.text)
async def search(c: Client, m: Message):
    if m.text.startswith("/"):
        return  # 🚫 Ignore commands

    # 🚫 Skip anonymous admin or channel posts
    if not m.from_user:  
        return  

    query = m.text.strip()
    if not query:
        return  

    # 🔎 Build regex for keyword search
    keywords = re.split(r"\s+", query)
    regex_pattern = ".*".join(map(re.escape, keywords))
    regex = re.compile(regex_pattern, re.IGNORECASE)

    # 📂 Search in DB
    results = list(files_collection.find({"file_name": {"$regex": regex}}))

    # ✅ No results
    if not results:
        if m.chat.type == enums.ChatType.PRIVATE:
            msg = await m.reply(
                "❗️No Results found.",
                parse_mode=enums.ParseMode.HTML
            )
            asyncio.create_task(delete_after_delay(msg, DELETE_DELAY))

        else:
            chat_info = f"🗣 Group: <code>{m.chat.title}</code> ({m.chat.id})"
            log_text = (
                f"🔍 <b>Missing File Request</b>\n\n"
                f"👤 User: <a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>\n"
                f"🆔 User ID: <code>{m.from_user.id}</code>\n"
                f"{chat_info}\n"
                f"💬 Chat ID: <code>{m.chat.id}</code>\n"
                f"🔎 Query: <code>{query}</code>"
            )

            if LOG_CHANNEL:
                try:
                    await client.send_message(LOG_CHANNEL, log_text, parse_mode=enums.ParseMode.HTML)
                except Exception:
                    pass

            msg = await m.reply(
                "<b>Nᴏ Sᴇᴀʀᴄʜ Rᴇsᴜʟᴛ Fᴏᴜɴᴅ. Pᴏssɪʙʟᴇ Sᴘᴇʟʟɪɴɢ Mɪsᴛᴀᴋᴇ ᴏʀ Uɴʀᴇʟᴇᴀsᴇᴅ/Uɴᴀᴠᴀɪʟᴀʙʟᴇ Mᴏᴠɪᴇ ᴏɴ OTT Pʟᴀᴛғᴏʀᴍ (Oɴʟʏ HD Pʀɪɴᴛs).</b>\n"
                "<b>Sᴀᴠᴇᴅ ᴀs Rᴇqᴜᴇsᴛ:Aᴅᴍɪɴ Wɪʟʟ Nᴏᴛɪғʏ ʏᴏᴜ ɪғ ғɪʟᴇs Aᴅᴅᴇᴅ.</b>",
                parse_mode=enums.ParseMode.HTML
            )
            asyncio.create_task(delete_after_delay(msg, DELETE_DELAY))
        return

    # ✅ Results found
    try:
        markup = get_file_buttons(results, query, 0)
        if not markup:  # safeguard against "No files" error
            raise ValueError("No buttons built")

        mention = f"<a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>"
        msg = await m.reply(
            f"🔍 Found the following files for {mention}:",
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML
        )

        # 🔥 Always auto-delete results after DELETE_AFTER seconds
        asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))

    except Exception as e:
        # fallback message to prevent "No files found" bug
        msg = await m.reply(
            f"⚠️ Something went wrong while building file buttons.\n\n<b>Error:</b> <code>{e}</code>",
            parse_mode=enums.ParseMode.HTML
        )
        asyncio.create_task(delete_after_delay(msg, DELETE_DELAY))




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

    # fallback if still None
    if not file_name:
        file_name = m.caption or f"File-{m.message_id}"

    files_collection.update_one(
        {"message_id": m.id},
        {"$set": {
            "file_name": file_name,
            "file_size": file_size,
            "message_id": m.id
        }},
        upsert=True
    )
  
