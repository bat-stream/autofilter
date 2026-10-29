
from pyrogram import Client, filters, enums
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)
from pyrogram.errors import MessageNotModified

from config import (
    client,
    files_collection,
    INDEX_CHANNEL,
    BASE_URL,
    MINI_APP_URL,
    DELETE_AFTER,
    DELETE_AFTER_FILE,
    AUTH_CHANNELS,
    UPDATES_CHANNEL,
    MOVIES_GROUP,
    BOT_USERNAME,
    PAGE_SIZE,
)

from utils.helpers import (
    save_user,
    get_file_buttons,
    build_index_page,
    get_not_joined_channels,
    delete_after_delay,
    check_sub_and_send_file,
    send_paginated_files,
    build_search_regex,
    build_custom_caption,
    fetch_index_page,
    resolve_query_token,
)

import asyncio
import re
import math
import urllib.parse


# ------------------ Close Index ------------------

@client.on_callback_query(filters.regex(r"^close_index$"))
async def close_index_handler(_, cb: CallbackQuery):
    try:
        await cb.message.delete()
        await cb.answer()
    except Exception:
        await cb.answer(
            "❌ Couldn't close.",
            show_alert=True,
        )


# ------------------ Pagination Navigation ------------------

@client.on_callback_query(
    filters.regex(r"^nav:(\d+)\|(.+):(\d+)$")
)
async def handle_pagination_nav(
    c: Client,
    query: CallbackQuery,
):
    try:
        match = re.match(
            r"^nav:(\d+)\|(.+):(\d+)$",
            query.data,
        )

        if not match:
            return await query.answer("Invalid navigation.")

        user_id = int(match.group(1))
        filename_query = resolve_query_token(match.group(2))
        page = int(match.group(3))

        regex = build_search_regex(filename_query)

        matching_files = list(
            files_collection.find(
                {"file_name": {"$regex": regex}}
            ).sort([
                ("message_id", -1),
                ("_id", -1),
            ])
        )

        if not matching_files:
            return await query.answer(
                "❌ No results found.",
                show_alert=True,
            )

        await send_paginated_files(
            c,
            user_id,
            matching_files,
            page,
            filename_query,
            query,
        )

    except Exception as e:
        print(f"❌ Navigation error: {e}")
        await query.answer(
            "❌ Couldn't load page.",
            show_alert=True,
        )


# ------------------ Index Pagination ------------------

@client.on_callback_query(
    filters.regex(r"^indexpage_(\d+)(?:_(\w+))?$")
)
async def paginate_index(c: Client, cb: CallbackQuery):
    page = int(cb.matches[0].group(1))
    token = cb.matches[0].group(2) or "all"
    query = resolve_query_token(token)

    result = fetch_index_page(query, page)

    if not result:
        return await cb.answer(
            "❌ No indexed files.",
            show_alert=True,
        )

    text, buttons = result

    try:
        await cb.message.edit_text(
            text,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=buttons,
            disable_web_page_preview=True,
        )
        await cb.answer()

    except MessageNotModified:
        await cb.answer()

    except Exception as e:
        print(f"[ERROR] paginate_index: {e}")
        await cb.answer(
            "⚠️ Couldn't update.",
            show_alert=True,
        )


# ------------------ Retry After Joining ------------------

@client.on_callback_query(filters.regex(r"^retry_"))
async def retry_after_join(c: Client, cb: CallbackQuery):
    msg_id = int(cb.data.split("_")[1])

    not_joined = await get_not_joined_channels(
        cb.from_user.id
    )

    if not not_joined:
        await cb.message.delete()

        await check_sub_and_send_file(
            c,
            cb.message,
            msg_id,
            user_id=cb.from_user.id,
        )
        return

    join_buttons = []

    for channel_id in not_joined:
        try:
            chat = await c.get_chat(channel_id)
            chat_title = chat.title or "Channel"

            if chat.username:
                invite_link = f"https://t.me/{chat.username}"
            else:
                invite_link = await c.export_chat_invite_link(
                    channel_id
                )

        except Exception:
            chat_title = "Channel"
            invite_link = "https://t.me/yourfallbackchannel"

        join_buttons.append([
            InlineKeyboardButton(
                f"🔔 Join {chat_title}",
                url=invite_link,
            )
        ])

    join_buttons.append([
        InlineKeyboardButton(
            "✅ I Joined",
            callback_data=f"retry_{msg_id}",
        )
    ])

    try:
        await cb.message.edit_text(
            "<b>❌ You're still missing some channels!</b>\n\n"
            "<b>Please join all remaining channels below:</b>",
            reply_markup=InlineKeyboardMarkup(join_buttons),
            parse_mode=enums.ParseMode.HTML,
        )

        await cb.answer()

    except MessageNotModified:
        await cb.answer(
            "⚠️ Please join all remaining channels first!",
            show_alert=True,
        )


# ------------------ Help Callback ------------------

@client.on_callback_query(
    filters.regex(r"^help_info$")
)
async def help_callback(_, cb: CallbackQuery):
    await cb.message.edit_text(
        "<b>Hᴏᴡ ᴛᴏ Usᴇ Mᴇ?</b>\n\n"
        "<b>🔹 Jᴜsᴛ Sᴇɴᴅ ᴀɴʏ Mᴏᴠɪᴇ Nᴀᴍᴇ.</b>\n"
        "<b>🔹 I’ʟʟ Sʜᴏᴡ ʏᴏᴜ ᴛʜᴇ Aᴠᴀɪʟᴀʙʟᴇ Lɪɴᴋs ᴡɪᴛʜ Sɪᴢᴇs.</b>\n"
        "<b>🔹 Cʟɪᴄᴋ ᴛʜᴇ Oɴᴇ ʏᴏᴜ Wᴀɴᴛ, ᴀɴᴅ I’ʟʟ Sᴇɴᴅ ɪᴛ ᴛᴏ Yᴏᴜ!</b>\n\n"
        "<b>🎥 Fᴏʀ Lᴀᴛᴇsᴛ Mᴏᴠɪᴇs, Jᴏɪɴ @Batmanlinkz</b>",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="start_back",
                )
            ]
        ]),
        parse_mode=enums.ParseMode.HTML,
    )

    await cb.answer()


# ------------------ Back to Start ------------------

@client.on_callback_query(
    filters.regex(r"^start_back$")
)
async def back_to_start(_, cb: CallbackQuery):
    msg = cb.message
    chat_type = msg.chat.type

    user_name = (
        cb.from_user.first_name
        if cb.from_user
        else "User"
    )

    if chat_type == enums.ChatType.PRIVATE:
        await save_user(cb.from_user.id)

    start_text = (
        f"😎 ʜᴇʏ {user_name},\n\n"
        "ɪ ᴀᴍ Bᴀᴛᴍᴀɴ\n\n"
        "ғᴏʀ ɴᴇᴡ ᴍᴏᴠɪᴇs ᴊᴏɪɴ ʜᴇʀᴇ @Batmanlinkz\n\n"
        "Tᴏ Bʀᴏᴡsᴇ Sᴛᴏʀᴇᴅ Fɪʟᴇs Cʟɪᴄᴋ ᴏɴ Oᴘᴇɴ Mɪɴɪ Aᴘᴘ\n\n"
        "ᴛᴏ ᴋɴᴏᴡ ᴍᴏʀᴇ ᴄʟɪᴄᴋ ʜᴇʟᴘ ʙᴜᴛᴛᴏɴ."
    )

    markup = InlineKeyboardMarkup([
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

    try:
        await msg.edit_text(
            start_text,
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
        )

    except MessageNotModified:
        pass

    if chat_type != enums.ChatType.PRIVATE:
        asyncio.create_task(
            delete_after_delay(msg, DELETE_AFTER)
        )

    await cb.answer()


# ------------------ Resend File ------------------

@client.on_callback_query(
    filters.regex(r"^get_(\d+)$")
)
async def resend_file(c: Client, cb: CallbackQuery):
    msg_id = int(cb.matches[0].group(1))

    try:
        original = await c.get_messages(
            chat_id=INDEX_CHANNEL,
            message_ids=msg_id,
        )

        file_obj = None

        if original.document:
            file_obj = original.document.file_id
        elif original.video:
            file_obj = original.video.file_id
        elif original.audio:
            file_obj = original.audio.file_id

        file_name = (
            getattr(original.document, "file_name", None)
            or getattr(original.video, "file_name", None)
            or getattr(original.audio, "file_name", None)
            or original.caption
            or "File"
        )

        caption = build_custom_caption(file_name)

        if original.document:
            sent = await c.send_document(
                chat_id=cb.message.chat.id,
                document=file_obj,
                caption=caption,
                parse_mode=enums.ParseMode.HTML,
            )

        elif original.video:
            sent = await c.send_video(
                chat_id=cb.message.chat.id,
                video=file_obj,
                caption=caption,
                parse_mode=enums.ParseMode.HTML,
            )

        elif original.audio:
            sent = await c.send_audio(
                chat_id=cb.message.chat.id,
                audio=file_obj,
                caption=caption,
                parse_mode=enums.ParseMode.HTML,
            )

        else:
            sent = await c.copy_message(
                chat_id=cb.message.chat.id,
                from_chat_id=INDEX_CHANNEL,
                message_id=msg_id,
            )

        await cb.answer(
            "📥 File sent with custom caption!"
        )

        warning_text = (
            "<b><u>❗️ IMPORTANT ❗️</u></b>\n\n"
            f"This message will be deleted in "
            f"<b>{DELETE_AFTER // 60}</b> minutes 🫥.\n\n"
            "<b>📌 Forward to Saved Messages to keep it.</b>"
        )

        warning = await cb.message.reply(
            warning_text,
            parse_mode=enums.ParseMode.HTML,
        )

        asyncio.create_task(
            _expire_pair(sent, warning, DELETE_AFTER)
        )

    except Exception as e:
        print(f"[ERROR] Resend failed: {e}")

        await cb.answer(
            "❌ Failed to resend.",
            show_alert=True,
        )


async def _expire_pair(sent, warning, delay):
    try:
        await asyncio.sleep(delay)
        await sent.delete()
        await warning.delete()
    except Exception:
        pass


# ------------------ Search Results Pagination ------------------

@client.on_callback_query(
    filters.regex(r"^page_(.+)_(\d+)$")
)
async def paginate_files(c: Client, cb: CallbackQuery):
    try:
        raw_query = cb.matches[0].group(1)
        page = int(cb.matches[0].group(2))
        query = resolve_query_token(raw_query)

        regex = build_search_regex(query)

        # Use the same deterministic ordering as initial searches.
        results = list(
            files_collection.find(
                {"file_name": {"$regex": regex}}
            ).sort([
                ("message_id", -1),
                ("_id", -1),
            ])
        )

        total_files = len(results)

        if total_files == 0:
            return await cb.answer(
                "❌ No results found.",
                show_alert=True,
            )

        total_pages = max(
            1,
            math.ceil(total_files / PAGE_SIZE),
        )

        page = max(0, min(page, total_pages - 1))

        markup = get_file_buttons(
            results,
            query,
            page,
        )

        await cb.message.edit_reply_markup(
            reply_markup=markup
        )
        await cb.answer()

    except MessageNotModified:
        await cb.answer()

    except Exception as e:
        print(f"❌ Pagination error: {e}")

        await cb.answer(
            "⚠️ Couldn't load page.",
            show_alert=True,
        )


# ------------------ Send All Files ------------------

@client.on_callback_query(
    filters.regex(r"^sendall_(.+)_(\d+)$")
)
async def send_all_files_callback(
    c: Client,
    q: CallbackQuery,
):
    raw = q.matches[0].group(1)
    query = resolve_query_token(raw)
    page = int(q.matches[0].group(2))

    await save_user(q.from_user.id)

    regex = build_search_regex(query)

    files = list(
        files_collection.find(
            {"file_name": {"$regex": regex}}
        ).sort([
            ("message_id", -1),
            ("_id", -1),
        ])
    )

    total_files = len(files)

    if total_files == 0:
        await q.answer(
            "No files found for this search.",
            show_alert=True,
        )
        return

    total_pages = max(
        1,
        math.ceil(total_files / PAGE_SIZE),
    )

    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total_files)
    current_files = files[start:end]

    if not current_files:
        await q.answer(
            "No files on this page.",
            show_alert=True,
        )
        return

    await q.answer(
        f"📤 Sending {len(current_files)} files to your DM...",
        show_alert=True,
    )

    for f in current_files:
        try:
            sent = await c.copy_message(
                chat_id=q.from_user.id,
                from_chat_id=INDEX_CHANNEL,
                message_id=f["message_id"],
            )

            asyncio.create_task(
                delete_after_delay(sent, DELETE_AFTER_FILE)
            )

            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"Error sending file: {e}")

    try:
        caption_msg = await c.send_message(
            q.from_user.id,
            (
                "<b><u>❗️❗️❗️ IMPORTANT ❗️❗️❗️</u></b>\n\n"
                f"ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ "
                f"<b><u>{DELETE_AFTER_FILE // 60}</u> ᴍɪɴᴜᴛᴇs</b> 🫥 "
                "(ᴅᴜᴇ ᴛᴏ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs).\n\n"
                "<b>📌 Please forward this message to your "
                "Saved Messages or any private chat to avoid "
                "losing it.</b>"
            ),
            parse_mode=enums.ParseMode.HTML,
        )

        asyncio.create_task(
            delete_after_delay(
                caption_msg,
                DELETE_AFTER_FILE,
            )
        )

    except Exception as e:
        print(f"Error sending caption: {e}")
