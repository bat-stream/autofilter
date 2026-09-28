"""
User-facing informational commands: /help and /report.

(/help used to be duplicated in handlers/messages.py with the exact same
filter — this is now the single copy.)
"""
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from config import client, LOG_CHANNEL


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


@client.on_message(filters.command("report") & (filters.group | filters.private))
async def report_handler(c: Client, m: Message):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        return await m.reply(
            "❗ Usage:\n<code>/report your message here</code>",
            parse_mode=enums.ParseMode.HTML
        )

    report_text = parts[1].strip()

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
