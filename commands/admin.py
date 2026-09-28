"""
Admin-only commands.

NOTE: These used to be defined in BOTH commands/admin.py and handlers/messages.py
with identical names/filters. Pyrogram only ever invoked the first-registered
copy (silently making the other a dead duplicate) — this file is now the single
source of truth for every admin command, and messages.py no longer redefines them.
"""
import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import client, ADMIN_ID, users_collection, files_collection, INDEX_CHANNEL, BASE_URL
from utils.helpers import send_paginated_files, build_search_regex, file_open_link


# ------------------ /status ------------------ #
@client.on_message(filters.command("status") & filters.user(ADMIN_ID))
async def status(_, m: Message):
    total = users_collection.count_documents({})
    deleted = 0
    unreachable = 0
    checked = 0

    msg = await m.reply("⏳ Checking user status...")

    for user in users_collection.find({}, {"user_id": 1}):
        checked += 1
        try:
            u = await client.get_users(user["user_id"])
            # Telegram returns deleted accounts normally (flagged), it does not raise.
            if getattr(u, "is_deleted", False):
                deleted += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            unreachable += 1
        await asyncio.sleep(0.05)

        if checked % 200 == 0:
            try:
                await msg.edit_text(f"⏳ Checking user status... ({checked}/{total})")
            except Exception:
                pass

    active = total - deleted - unreachable

    await msg.edit_text(
        f"📊 <b>Bot Status:</b>\n\n"
        f"👥 Total Users: <code>{total}</code>\n"
        f"✅ Active Users: <code>{active}</code>\n"
        f"🗑 Deleted Accounts: <code>{deleted}</code>\n"
        f"❓ Unreachable: <code>{unreachable}</code>\n"
        f"📁 Indexed Files: <code>{files_collection.count_documents({})}</code>",
        parse_mode=enums.ParseMode.HTML
    )


# ------------------ /send ------------------ #
@client.on_message(filters.command("send") & filters.user(ADMIN_ID))
async def send_file_paginated(c: Client, m: Message):
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

        regex = build_search_regex(filename_query)
        matching_files = list(files_collection.find({"file_name": {"$regex": regex}}))

        if not matching_files:
            return await m.reply("❌ No files found matching your query.")

        await send_paginated_files(c, user_id, matching_files, 0, filename_query)

        if user:
            name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            await m.reply(f"✅ Sent to <a href='tg://user?id={user_id}'>{name}</a>", parse_mode=enums.ParseMode.HTML)
        else:
            await m.reply(f"✅ Files sent to user ID: <code>{user_id}</code>", parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        await m.reply(f"❌ Error:\n<code>{e}</code>", parse_mode=enums.ParseMode.HTML)


# ------------------ /broadcast ------------------ #
@client.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast(_, m: Message):
    if not m.reply_to_message:
        return await m.reply("❗ Reply to a message to broadcast.")

    sent, failed = 0, 0
    status_msg = await m.reply("📣 Starting broadcast...")

    total = users_collection.count_documents({})
    for i, user in enumerate(users_collection.find({}, {"user_id": 1}), start=1):
        try:
            sent_msg = await m.reply_to_message.copy(user["user_id"])
            sent += 1
            asyncio.create_task(_auto_delete(sent_msg, delay=172800))
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            failed += 1
        await asyncio.sleep(0.1)

        if i % 100 == 0:
            try:
                await status_msg.edit_text(f"📣 Broadcasting... {i}/{total} (sent {sent}, failed {failed})")
            except Exception:
                pass

    await status_msg.edit_text(f"✅ Broadcast done.\n✔️ Sent: {sent}\n❌ Failed: {failed}")


async def _auto_delete(message: Message, delay: int = 10):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


# ------------------ /link ------------------ #
@client.on_message(filters.command("link") & filters.user(ADMIN_ID))
async def link_handler(c: Client, m: Message):
    if not m.reply_to_message:
        return await m.reply("❌ Please reply to any message (text/media) with `/link`.", quote=True)

    reply = m.reply_to_message
    try:
        fwd_msg = await reply.copy(chat_id=INDEX_CHANNEL)
    except Exception as e:
        return await m.reply(f"❌ Failed to copy message: {e}")

    media = reply.document or reply.video or reply.audio
    file_name = (
        getattr(media, "file_name", None)
        or reply.caption
        or reply.text
        or "Unnamed"
    )
    file_size = getattr(media, "file_size", None)
    files_collection.update_one(
        {"message_id": fwd_msg.id},
        {"$set": {
            "file_name": str(file_name),
            "file_size": file_size,
            "message_id": fwd_msg.id,
            "type": "generic",
        }},
        upsert=True,
    )

    redirect_link = file_open_link(fwd_msg.id)
    await m.reply(f"✅ File indexed!\n\n<code>{redirect_link}</code>", parse_mode=enums.ParseMode.HTML)


# ------------------ /uploadsession & /showsession ------------------ #
@client.on_message(filters.command("uploadsession") & filters.user(ADMIN_ID))
async def upload_session_handler(c, m):
    from config import save_session_to_db
    await m.reply("🔄 Exporting session and saving to DB... Please wait.", quote=True)
    ok = await save_session_to_db()
    if ok:
        await m.reply("✅ Session saved to MongoDB.", quote=True)
    else:
        await m.reply("❌ Failed to save session. Check logs.", quote=True)


@client.on_message(filters.command("showsession") & filters.user(ADMIN_ID))
async def showsession(c, m):
    from config import load_session_from_db
    s = load_session_from_db()
    if s:
        await m.reply("✅ Session exists in DB.", quote=True)
    else:
        await m.reply("❌ No session stored in DB yet.", quote=True)
