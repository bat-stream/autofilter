"""
Reserved for chat-member update handlers (e.g. welcoming new group members,
detecting when the bot is added/removed from a chat, membership auditing).

This file previously imported ChatMemberUpdated/InlineKeyboardButton/asyncio
and UPDATES_CHANNEL without defining any handler at all — dead code that did
nothing. It's kept as an empty, import-free module so `import handlers.members`
in bot.py continues to work; add @client.on_chat_member_updated() handlers
here when you need this functionality.
"""
