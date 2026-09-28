# What changed vs. the original upload

## 🔴 Critical bugs fixed
1. **`resend_file()` was completely broken** (`handlers/callbacks.py`). It called an
   undefined `build_custom_caption()` and used the invalid expression
   `caption=By @BatmanLinkz` (unquoted text — Python parsed `By @ BatmanLinkz` as
   matrix-multiplying two undefined names). Both raised `NameError` at runtime.
   Fixed: added a real `build_custom_caption()` in `utils/helpers.py` and quoted
   the caption correctly.
2. **`requirements.txt` had the wrong package** (`dotenv` instead of
   `python-dotenv`). Fixed.
3. **Duplicate handler registrations** for `/status`, `/send`, `/link`,
   `/broadcast`, `/help`, and the `nav:` callback existed in two files each
   (`handlers/messages.py` + `commands/admin.py` / `commands/user.py` /
   `handlers/callbacks.py`). Pyrogram only ever ran the first-registered copy,
   silently making the other dead code — fragile if import order ever changed.
   Consolidated to exactly one definition per command/callback:
   - `commands/admin.py` — all admin-only commands
   - `commands/user.py` — `/help`, `/report`
   - `handlers/messages.py` — `/start`, `/files`, group/DM text search, channel
     file indexing
   - `handlers/callbacks.py` — every callback-query handler
4. **Config crashed with an unreadable error** if `API_ID`/`BOT_TOKEN`/etc. were
   missing (`TypeError: int() argument must be...`). `config.py` now validates
   required env vars up front and exits with a clear, actionable message.
5. **MongoDB connection failures were silent** — `client.stop()` etc. would
   later fail confusingly. `config.py` now pings MongoDB at startup and exits
   with a clear error if it can't connect.

## 🟠 Performance fixes
6. **Blocking HTTP call inside an async handler.** `/start` used to call
   `requests.get(...)` directly, freezing the entire bot's event loop (for
   *every* concurrent user) for up to 3 seconds. Now runs via
   `asyncio.to_thread(...)` as a fire-and-forget background task.
7. **Every plain-text message triggered a full, unindexed MongoDB regex scan**,
   even "hi" or "ok". Added `MIN_SEARCH_QUERY_LEN` (default 2 chars) as a cheap
   guard, plus a real MongoDB text index (see #8) so genuine searches are fast.
8. **No MongoDB indexes existed at all.** `config.py` now creates:
   - a unique index on `message_id` (used by every lookup/sort)
   - a text index on `file_name` (available for future `$text` search use)
   - a unique index on `users.user_id`
9. **Sequential channel-membership checks.** `get_not_joined_channels()` used
   to `await` each `AUTH_CHANNELS` entry one at a time. Now checked in
   parallel with `asyncio.gather`.
10. **`/broadcast` and `/status` had no FloodWait handling** and no progress
    feedback for large user bases. Both now catch `pyrogram.errors.FloodWait`
    and back off correctly, and update their status message periodically
    instead of running silently for minutes.
11. **Flask ran single-threaded** (`app.run(..., debug=False)` with no
    `threaded=True`, no production server). `run_flask_server()` now prefers
    `waitress` (a real production WSGI server, added to `requirements.txt`) and
    falls back to Flask's dev server with `threaded=True` if waitress isn't
    installed.

## 🟡 Security fixes
12. **Hardcoded default admin credentials** (`batman` / `batmanjk`) removed.
    The admin panel now refuses to log anyone in until `ADMIN_USERNAME` and
    `ADMIN_PASSWORD` are explicitly set in the environment.
13. **Insecure default Flask secret key** (`"change-this-secret"`) removed. If
    `FLASK_SECRET` isn't set, a random one is generated per-process (with a
    clear warning that sessions won't persist across restarts) instead of
    using a guessable shared default.
14. **No brute-force protection on `/admin/login`.** Added a simple in-memory
    rate limiter: 5 failed attempts locks an IP out for 5 minutes. Login
    comparisons now use `secrets.compare_digest` (constant-time) instead of
    `==`.
15. **No CSRF protection** on the state-changing admin endpoints
    (`bulk_delete`, file edit/delete, login form). Added a session-bound CSRF
    token, validated on every POST/PUT/DELETE; the dashboard's `fetch()` calls
    now send it via an `X-CSRF-Token` header.
16. **Bare `except:` clauses** (which also swallow `SystemExit`/
    `KeyboardInterrupt`) replaced with `except Exception as e:` throughout.
17. Added baseline security headers (`X-Content-Type-Options`,
    `X-Frame-Options`, `Referrer-Policy`) and safer session-cookie flags
    (`HttpOnly`, `SameSite=Lax`, `Secure` by default — configurable via
    `FORCE_HTTPS_COOKIES` for local HTTP testing).

## 🔵 Code quality / maintainability
18. **~1,200 lines of embedded HTML/CSS/JS pulled out of `bot.py`** into real
    Jinja templates under `templates/` (`home.html`, `redirect.html`,
    `files.html`, `login.html`, `dashboard.html`, `_common_head.html`), now
    rendered with `render_template()` instead of `render_template_string()`.
    `bot.py` shrank from ~1,600 lines to a normal, readable Flask app.
19. **Centralized pagination/config constants.** `PAGE_SIZE` was previously
    hardcoded inconsistently in four different files (6, 6, 6, 20). Now a
    single source of truth in `config.py`, overridable via `.env`.
20. **`handlers/members.py`** was a dead stub importing things it never used.
    Cleaned up with a clear doc-comment for future use.
21. **Duplicated fuzzy-search regex-building code** (six near-identical
    copies of the same 3 lines) consolidated into
    `utils.helpers.build_search_regex()`.
22. Added `.env.example`, `.gitignore`, and `__init__.py` markers for the
    `handlers`/`commands`/`utils` packages.

## Not changed (by design)
- Business logic/behavior (search, subscription gating, pagination, auto-delete
  timers, admin dashboard features) is functionally identical — this pass
  fixes correctness, performance, and security without changing what the bot
  does for end users.
- The bundled ad-network scripts (AdsGalaxy, highperformanceformat.com) were
  left in place since they're a monetization choice, not a bug — but they're
  worth reviewing independently if you're concerned about third-party ad
  network reliability/reputation.

## Update: Python 3.12+ / 3.13 / 3.14 compatibility
23. **`RuntimeError: There is no current event loop in thread 'MainThread'`
    at `import pyrogram`.** Pyrogram 2.0.106 calls `asyncio.get_event_loop()`
    at import time expecting it to auto-create a loop if none exists — newer
    Python versions removed that implicit behavior. `config.py` now sets an
    event loop explicitly *before* importing pyrogram, which resolves this on
    any Python version.

    This is a symptom of running an unmaintained library (last updated
    ~2023) on a very new Python release. The shim fixes this specific crash,
    but if you hit further asyncio-related errors deeper in pyrogram's
    internals, the more robust fix is to run this bot under Python 3.10–3.12
    (the project's `.python-version` already pins 3.10.13 — make sure your
    environment actually honors it, e.g. via `pyenv install 3.10.13 && pyenv
    local 3.10.13` followed by a fresh virtualenv, since Codespaces/devcontainer
    default interpreters ignore `.python-version` unless pyenv is set up).

## Before you deploy
1. Copy `.env.example` to `.env` and fill in every value — especially
   `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and `FLASK_SECRET`.
2. `pip install -r requirements.txt --break-system-packages` (or in a venv).
3. Run `python bot.py`.

## Update: /files pagination + command routing
24. **`/files <name>` → Next/Prev jumped to the whole library.** The page
    buttons only carried a page number (`indexpage_N`) and the handler loaded
    *all* files, ignoring your search. Buttons now carry a short query token
    (`indexpage_<page>_<token>`) and each page is fetched with `skip/limit`
    (no more loading every file on every click). Header shows `Page x/y • Total n`.
25. **Admin/user commands never ran.** The catch-all text-search handler was
    registered before `commands/*`, and Pyrogram runs only the first matching
    handler — so `/status /send /broadcast /link /help /report` were swallowed.
    The search handler now excludes messages starting with `/`.
26. **Buttons broke on long / non-English queries** (Telegram allows only 64
    bytes of callback_data). Search queries are now stored in MongoDB (auto-
    expire after 60 days) and buttons carry a 12-char token. Old buttons still work.
27. `/files` results (and `/link`, `/send`) now open the Mini App.
28. "✅ I Joined" checked the *bot's* membership instead of the user's — fixed.
29. HTML in file names/queries (`<`, `&`) is escaped, so it can't break messages.
30. `/status` now counts deleted accounts correctly; `/link` stores the real
    file name and size for media instead of "Unnamed".
