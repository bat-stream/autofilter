from pyrogram import Client, filters, enums
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import client, files_collection, INDEX_CHANNEL, BASE_URL, DELETE_AFTER, DELETE_AFTER_FILE, AUTH_CHANNELS,UPDATES_CHANNEL, MOVIES_GROUP,BOT_USERNAME
from utils.helpers import save_user,get_file_buttons,build_index_page,get_not_joined_channels,delete_after_delay,check_sub_and_send_file,build_custom_caption,send_paginated_files,send_file_with_caption
import asyncio, re
from pyrogram.errors import MessageNotModified
import urllib.parse
import math

# Close index
@client.on_callback_query(filters.regex("close_index"))
async def close_index_handler(_, cb: CallbackQuery):
    try:
        await cb.message.delete()
        await cb.answer()
    except Exception:
        await cb.answer("❌ Couldn't close.", show_alert=True)

@client.on_callback_query(filters.regex(r"^nav:(\d+)\|(.+):(\d+)$"))
async def handle_pagination_nav(c: Client, query: CallbackQuery):
    try:
        match = re.match(r"^nav:(\d+)\|(.+):(\d+)$", query.data)
        if not match:
            return await query.answer("Invalid navigation.")

        user_id = int(match.group(1))
        filename_query = match.group(2)
        page = int(match.group(3))

        keywords = re.split(r"\s+", filename_query)
        regex_pattern = ".*".join(map(re.escape, keywords))
        regex = re.compile(regex_pattern, re.IGNORECASE)
        matching_files = list(files_collection.find({"file_name": {"$regex": regex}}))

        await send_paginated_files(c, user_id, matching_files, page, filename_query, query)

    except Exception as e:
        await query.answer(f"❌ Error: {e}", show_alert=True)

@client.on_callback_query(filters.regex(r"^indexpage_(\d+)$"))
async def paginate_index(c: Client, cb: CallbackQuery):
    page = int(cb.matches[0].group(1))
    files = list(files_collection.find().sort("file_name", 1))

    if not files:
        return await cb.answer("❌ No indexed files.", show_alert=True)

    # Clean file names before passing to build_index_page
    for f in files:
        file_name = f.get('file_name') or ''
        f['clean_name'] = re.sub(r'^@[^_\s-]+[_\s-]*', '', file_name).strip()

    text, buttons = build_index_page(files, page)

    try:
        await cb.message.edit_text(
            text,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=buttons,
            disable_web_page_preview=True
        )
        await cb.answer()
    except Exception as e:
        await cb.answer("⚠️ Couldn't update.", show_alert=True)



@client.on_callback_query(filters.regex(r"^retry_"))
async def retry_after_join(c: Client, cb: CallbackQuery):
    msg_id = int(cb.data.split("_")[1])

    not_joined = await get_not_joined_channels(cb.from_user.id)

    if not not_joined:
        # ✅ Joined all channels — send file
        await cb.message.delete()
        await check_sub_and_send_file(c, cb.message, msg_id)
        return

    # ❌ Still missing some channels
    join_buttons = []
    for channel_id in not_joined:
        try:
            chat = await c.get_chat(channel_id)
            chat_title = chat.title
            if chat.username:
                invite_link = f"https://t.me/{chat.username}"
            else:
                invite_link = await c.export_chat_invite_link(channel_id)
        except Exception:
            chat_title = "Channel"
            invite_link = "https://t.me/yourfallbackchannel"

        join_buttons.append([InlineKeyboardButton(f"🔔 Join {chat_title}", url=invite_link)])

    join_buttons.append([InlineKeyboardButton("✅ I Joined", callback_data=f"retry_{msg_id}")])

    try:
        await cb.message.edit_text(
            "<b>❌ You're still missing some channels!</b>\n\n"
            "<b>Please join all remaining channels below:</b>",
            reply_markup=InlineKeyboardMarkup(join_buttons),
            parse_mode=enums.ParseMode.HTML
        )
    except MessageNotModified:
        # Ignore harmless "message not modified" errors
        await cb.answer("⚠️ Please join all remaining channels first!", show_alert=True)

# ---------------- Help callback ----------------
@client.on_callback_query(filters.regex("help_info"))
async def help_callback(_, cb: CallbackQuery):
    await cb.message.edit_text(
        "<b>How to use me?</b>\n\n"
        "🔹 Just type any movie or file name.\n"
        "🔹 I’ll show you the available links.\n"
        "🔹 Click the one you want, and I’ll send it to you!\n\n"
        "🎥 For latest movies, join @Batmanlinkz",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="start_back")]
        ]),
        parse_mode=enums.ParseMode.HTML
    )
    await cb.answer()

# ---------------- Back to start ----------------
@client.on_callback_query(filters.regex("start_back"))
async def back_to_start(_, cb: CallbackQuery):
    # Call the shared start logic
    msg = cb.message
    chat_type = msg.chat.type
    user_name = cb.from_user.first_name if cb.from_user else "User"

    # Save user if private
    if chat_type == enums.ChatType.PRIVATE:
        await save_user(cb.from_user.id)

    start_text = (
        f"😎 ʜᴇʏ {user_name},\n\n"
        "ɪ ᴀᴍ ᴀ ғɪʟᴛᴇʀ ʙᴏᴛ...\n\n"
        "ғᴏʀ ɴᴇᴡ ᴍᴏᴠɪᴇs ᴊᴏɪɴ ʜᴇʀᴇ @Batmanlinkz\n\n"
        "ᴛᴏ ᴋɴᴏᴡ ᴍᴏʀᴇ ᴄʟɪᴄᴋ ʜᴇʟᴘ ʙᴜᴛᴛᴏɴ."
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Me To Group", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")],
        [InlineKeyboardButton("📢 Updates Channel", url=UPDATES_CHANNEL),
         InlineKeyboardButton("Help❓", callback_data="help_info")],
        [InlineKeyboardButton("🎬 Movie Group", url=MOVIES_GROUP)]
    ])

    await msg.edit_text(
        start_text,
        reply_markup=markup,
        parse_mode=enums.ParseMode.HTML
    )

    # Auto-delete in groups
    if chat_type != enums.ChatType.PRIVATE:
        asyncio.create_task(delete_after_delay(msg, DELETE_AFTER))

    await cb.answer()

@client.on_callback_query(filters.regex(r"^get_(\d+)$"))
async def resend_file(c: Client, cb: CallbackQuery):
    msg_id = int(cb.matches[0].group(1))
    try:
        original = await c.get_messages(chat_id=INDEX_CHANNEL, message_ids=msg_id)

        # Extract file or caption
        file_obj = None
        if original.document:
            file_obj = original.document.file_id
        elif original.video:
            file_obj = original.video.file_id
        elif original.audio:
            file_obj = original.audio.file_id

        # Get file name or fallback to caption
        file_name = (
            getattr(original.document, "file_name", None)
            or getattr(original.video, "file_name", None)
            or getattr(original.audio, "file_name", None)
            or original.caption
            or "File"
        )

        # Build custom caption
        caption = build_custom_caption(file_name)

        # Send file with custom caption
        if original.document:
            sent = await c.send_document(
                chat_id=cb.message.chat.id,
                document=file_obj,
                caption=By @BatmanLinkz,
                parse_mode=enums.ParseMode.HTML
            )
        elif original.video:
            sent = await c.send_video(
                chat_id=cb.message.chat.id,
                video=file_obj,
                caption=caption,
                parse_mode=enums.ParseMode.HTML
            )
        elif original.audio:
            sent = await c.send_audio(
                chat_id=cb.message.chat.id,
                audio=file_obj,
                caption=By @BatmanLinkz,
                parse_mode=enums.ParseMode.HTML
            )
        else:
            # fallback: copy message
            sent = await c.copy_message(
                chat_id=cb.message.chat.id,
                from_chat_id=INDEX_CHANNEL,
                message_id=msg_id
            )

        await cb.answer("📥 File sent with custom caption!")

        # Optional auto-delete warning
        warning_text = (
            "<b><u>❗️ IMPORTANT ❗️</u></b>\n\n"
            f"This message will be deleted in <b>{DELETE_AFTER // 60}</b> minutes 🫥.\n\n"
            "<b>📌 Forward to Saved Messages to keep it.</b>"
        )
        warning = await cb.message.reply(warning_text, parse_mode=enums.ParseMode.HTML)

        await asyncio.sleep(DELETE_AFTER)
        await sent.delete()
        await warning.delete()

    except Exception as e:
        print(f"[ERROR] Resend failed: {e}")
        await cb.answer("❌ Failed to resend.", show_alert=True)



@client.on_callback_query(filters.regex(r"^page_(.+)_(\d+)$"))
async def paginate_files(c: Client, cb: CallbackQuery):
    raw_query, page = cb.matches[0].group(1), int(cb.matches[0].group(2))

    # ✅ Properly decode the query
    query = urllib.parse.unquote(raw_query)

    # Build regex search
    keywords = re.split(r"\s+", query.strip())
    regex_pattern = ".*".join(map(re.escape, keywords))
    regex = re.compile(regex_pattern, re.IGNORECASE)

    # Fetch results
    results = list(files_collection.find({"file_name": {"$regex": regex}}))
    total_files = len(results)
    if total_files == 0:
        return await cb.answer("❌ No results found.", show_alert=True)

    # ✅ Clamp page within valid range
    total_pages = math.ceil(total_files / PAGE_SIZE)
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    # Build new markup
    markup = get_file_buttons(results, query, page)

    try:
        await cb.message.edit_reply_markup(markup)
        await cb.answer()
    except Exception as e:
        print(f"❌ Pagination error: {e}")
        await cb.answer("⚠️ Couldn't load page.", show_alert=True)

PAGE_SIZE=6

@client.on_callback_query(filters.regex(r"^sendall_(.+)_(\d+)$"))
async def send_all_files_callback(c: Client, q: CallbackQuery):
    import urllib.parse

    raw = q.matches[0].group(1)
    query = urllib.parse.unquote(raw)
    page = int(q.matches[0].group(2))

    await save_user(q.from_user.id)

    # 🔎 Build regex like in search
    keywords = re.split(r"\s+", query.strip())
    pattern = ".*".join([re.escape(k) for k in keywords if k])
    mongo_filter = {"file_name": {"$regex": pattern, "$options": "i"}}

    files = list(files_collection.find(mongo_filter).sort("file_name", 1))
    total_files = len(files)
    if total_files == 0:
        await q.answer("No files found for this search.", show_alert=True)
        return

    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total_files)
    current_files = files[start:end]

    if not current_files:
        await q.answer("No files on this page.", show_alert=True)
        return

    # 🔔 POPUP immediately when button clicked
    await q.answer(
        f"📤 Sending {len(current_files)} files to your DM...",
        show_alert=True
    )

    # ✅ Send each file
    for f in current_files:
        try:
            sent = await c.copy_message(
                chat_id=q.from_user.id,
                from_chat_id=INDEX_CHANNEL,
                message_id=f["message_id"]
            )
            asyncio.create_task(delete_after_delay(sent, DELETE_AFTER_FILE))
            await asyncio.sleep(0.5)  # avoid FloodWait
        except Exception as e:
            print(f"Error sending file: {e}")

    # ⚠️ Send ONE final important notice
    try:
        caption_msg = await c.send_message(
            q.from_user.id,
            (
                f"<b><u>❗️❗️❗️ IMPORTANT ❗️❗️❗️</u></b>\n\n"
                f"ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ <b><u>{DELETE_AFTER_FILE//60}</u> ᴍɪɴᴜᴛᴇs</b> 🫥 "
                "(ᴅᴜᴇ ᴛᴏ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs).\n\n"
                "<b>📌 Please forward this message to your Saved Messages or any private chat to avoid losing it.</b>"
            ),
            parse_mode=enums.ParseMode.HTML
        )
        asyncio.create_task(delete_after_delay(caption_msg, DELETE_AFTER_FILE))
    except Exception as e:
        print(f"Error sending caption: {e}")





# TODO: Other callbacks (pagination, retry, resend_file, etc.) should be added here based on original bot.py
