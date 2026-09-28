import threading
import secrets
import time
from math import ceil
import asyncio
import signal
import os
import re
import sys
import config
from pyrogram import idle
from flask import (
    Flask, request, render_template, redirect, url_for, session, flash, jsonify
)
from pymongo import DESCENDING
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from config import client, files_collection, BOT_USERNAME

# Import handlers so they register their @client.on_message / @client.on_callback_query decorators
import handlers.callbacks
import handlers.messages
import handlers.members
import commands.admin
import commands.user
from utils.helpers import clean_filename

STOP_TIMEOUT = 6
FLASK_JOIN_TIMEOUT = 2

users_collection = getattr(config, "users_collection", None)

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET

# Reasonably safe session-cookie defaults for an admin panel.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FORCE_HTTPS_COOKIES", "1") == "1",
)


@app.after_request
def _security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp


# ---------------- CSRF protection for the admin panel ----------------
# Lightweight session-bound token (no extra dependency). Every admin page
# render issues a fresh-if-missing token; every state-changing admin request
# (form POST or JSON fetch from the dashboard) must echo it back.
def _get_csrf_token():
    tok = session.get("csrf_token")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["csrf_token"] = tok
    return tok


def _csrf_protect(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            expected = session.get("csrf_token")
            if not expected or not sent or not secrets.compare_digest(sent, expected):
                return jsonify({"ok": False, "error": "Invalid or missing CSRF token"}), 400
        return f(*args, **kwargs)
    return wrapped


# ---------------- Simple login rate limiting ----------------
# In-memory is fine for a single-process deployment; swap for Redis if you
# scale to multiple Flask workers/processes.
_login_attempts = {}
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 300


def _client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()


def _is_locked_out(ip):
    entry = _login_attempts.get(ip)
    if not entry:
        return False
    count, first_attempt = entry
    if count < LOGIN_MAX_ATTEMPTS:
        return False
    if time.time() - first_attempt > LOGIN_LOCKOUT_SECONDS:
        _login_attempts.pop(ip, None)
        return False
    return True


def _record_failed_login(ip):
    count, first_attempt = _login_attempts.get(ip, (0, time.time()))
    _login_attempts[ip] = (count + 1, first_attempt)


def _clear_login_attempts(ip):
    _login_attempts.pop(ip, None)


# ---------------- Auth decorator ----------------
def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if session.get("admin_logged_in"):
            return f(*args, **kwargs)
        return redirect(url_for("admin_login", next=request.path))
    return wrapped


# ---------------- Public routes ----------------
@app.route('/')
def home():
    return render_template("home.html", bot_username=BOT_USERNAME)


@app.route('/redirect')
def redirect_page():
    msg_id = request.args.get('id', default=None)
    if not msg_id:
        return redirect(f"https://t.me/{BOT_USERNAME}")

    try:
        msg_int = int(msg_id)
    except (TypeError, ValueError):
        return redirect(f"https://t.me/{BOT_USERNAME}")

    file_entry = files_collection.find_one({"message_id": msg_int}) or {}
    raw_name = file_entry.get('file_name') or "Requested File"
    file_name = clean_filename(raw_name)

    return render_template(
        "redirect.html",
        msg_id=msg_int,
        bot_username=BOT_USERNAME,
        file_name=file_name
    )


@app.route('/files')
def files_list():
    """Server-side search + pagination over the files collection."""
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    per_page = config.WEB_FILES_PER_PAGE

    search_q = request.args.get('search', '').strip()
    mongo_filter = {}
    if search_q:
        safe_q = re.escape(search_q)
        mongo_filter = {"file_name": {"$regex": safe_q, "$options": "i"}}

    total_count = files_collection.count_documents(mongo_filter)
    total_pages = max(1, ceil(total_count / per_page))
    if page > total_pages:
        page = total_pages

    skip = (page - 1) * per_page
    cursor = files_collection.find(mongo_filter).sort("message_id", DESCENDING).skip(skip).limit(per_page)
    files = list(cursor)

    return render_template(
        "files.html",
        files=files, page=page, per_page=per_page, total_pages=total_pages,
        query=search_q, bot_username=BOT_USERNAME
    )


# ---------------- Admin auth routes ----------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if not config.ADMIN_USERNAME or not config.ADMIN_PASSWORD:
        return "Admin login is not configured. Set ADMIN_USERNAME and ADMIN_PASSWORD in your environment.", 503

    ip = _client_ip()

    if request.method == "POST":
        if _is_locked_out(ip):
            flash("Too many failed login attempts. Try again later.")
            return render_template("login.html", csrf_token=_get_csrf_token())

        sent_token = request.form.get("csrf_token")
        expected_token = session.get("csrf_token")
        if not expected_token or not sent_token or not secrets.compare_digest(sent_token, expected_token):
            flash("Session expired, please try again.")
            return render_template("login.html", csrf_token=_get_csrf_token())

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        # constant-time comparisons to avoid leaking timing information
        valid_user = secrets.compare_digest(username, config.ADMIN_USERNAME)
        valid_pass = secrets.compare_digest(password, config.ADMIN_PASSWORD)

        if valid_user and valid_pass:
            _clear_login_attempts(ip)
            session.clear()
            session["admin_logged_in"] = True
            session["admin_username"] = username
            next_url = request.args.get("next") or url_for("admin_dashboard")
            return redirect(next_url)
        else:
            _record_failed_login(ip)
            flash("Invalid username or password")

    return render_template("login.html", csrf_token=_get_csrf_token())


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    session.pop("admin_username", None)
    return redirect(url_for("admin_login"))


def human_readable_size(sz):
    """Return human-readable size. Accepts int/float/numeric string."""
    try:
        s = int(sz)
    except (TypeError, ValueError):
        try:
            s = float(sz)
        except (TypeError, ValueError):
            return str(sz)

    if s < 1024:
        return f"{s} B"
    if s < 1048576:
        return f"{s/1024:.1f} KB"
    if s < 1073741824:
        return f"{s/1048576:.1f} MB"
    return f"{s/1073741824:.2f} GB"


@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    per_page = config.WEB_DASHBOARD_PER_PAGE

    q = request.args.get("q", "").strip()
    mongo_filter = {}

    if q:
        sub_filters = []
        if q.isdigit():
            sub_filters.append({"message_id": int(q)})
        if q.startswith('/') and q.endswith('/') and len(q) > 2:
            pattern = q[1:-1]
        else:
            pattern = re.escape(q)
        try:
            re.compile(pattern)
            sub_filters.append({"file_name": {"$regex": pattern, "$options": "i"}})
        except re.error:
            sub_filters.append({"file_name": {"$regex": re.escape(q), "$options": "i"}})

        mongo_filter["$or"] = sub_filters

    total_count = files_collection.count_documents(mongo_filter)
    total_pages = max(1, ceil(total_count / per_page))
    if page > total_pages:
        page = total_pages
    skip = (page - 1) * per_page

    cursor = files_collection.find(mongo_filter).sort("message_id", DESCENDING).skip(skip).limit(per_page)
    files = list(cursor)

    return render_template(
        "dashboard.html",
        files=files, page=page, per_page=per_page, total_pages=total_pages,
        request=request, human_readable_size=human_readable_size,
        csrf_token=_get_csrf_token(),
    )


@app.route("/admin/api/files/bulk_delete", methods=["POST"])
@login_required
@_csrf_protect
def admin_bulk_delete():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"ok": False, "error": "No ids provided"}), 400

    queries = []
    for i in ids:
        try:
            queries.append(ObjectId(i))
        except Exception:
            queries.append(i)

    res = files_collection.delete_many({"_id": {"$in": queries}})
    return jsonify({"ok": True, "deleted_count": res.deleted_count})


@app.route("/admin/api/file/<id>", methods=["GET", "PUT", "DELETE"])
@login_required
@_csrf_protect
def admin_file_api(id):
    try:
        oid = ObjectId(id)
        query = {"_id": oid}
    except Exception:
        query = {"_id": id}

    if request.method == "GET":
        doc = files_collection.find_one(query)
        if not doc:
            return jsonify({"ok": False, "error": "Not found"}), 404
        doc["_id"] = {"$oid": str(doc["_id"])} if isinstance(doc.get("_id"), ObjectId) else doc["_id"]
        return jsonify({"ok": True, "file": doc})

    if request.method == "PUT":
        data = request.get_json(silent=True) or {}
        update = {}
        if "file_name" in data:
            update["file_name"] = data["file_name"]
        if "message_id" in data:
            try:
                update["message_id"] = int(data["message_id"])
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "message_id must be an integer"}), 400
        if not update:
            return jsonify({"ok": False, "error": "Nothing to update"}), 400
        res = files_collection.update_one(query, {"$set": update})
        if res.modified_count:
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "No changes made or not found"}), 404

    if request.method == "DELETE":
        res = files_collection.delete_one(query)
        if res.deleted_count:
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "Not found"}), 404


# ---- helper to create admin user (kept for API-based provisioning) ----
def create_admin(username, password):
    if users_collection is None:
        raise RuntimeError("users_collection not configured in config.py")
    if not username or not password:
        raise ValueError("username & password required")
    users_collection.update_one(
        {"username": username},
        {"$set": {"username": username, "password_hash": generate_password_hash(password)}},
        upsert=True,
    )
    print("Admin user created/updated")


@app.route("/setup", methods=["POST"])
def setup_route():
    if os.environ.get("ALLOW_SETUP") != "1":
        return "setup disabled", 403
    if users_collection is None:
        return jsonify({"ok": False, "error": "users_collection missing"}), 500
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"ok": False, "error": "username & password required"}), 400
    create_admin(username, password)
    return jsonify({"ok": True})


# ---------------- Run (Flask + Pyrogram) ----------------
def run_flask_server():
    """
    Serve the Flask app. Prefers Waitress (a real production WSGI server) if
    installed; falls back to Flask's dev server (now with threaded=True so
    concurrent redirect/file requests don't queue behind each other) if
    Waitress isn't available.
    """
    port = int(os.environ.get("PORT", 5000))
    try:
        from waitress import serve
        print(f"[FLASK] Serving via waitress on 0.0.0.0:{port}")
        serve(app, host="0.0.0.0", port=port, threads=8)
    except ImportError:
        print("[FLASK] waitress not installed — falling back to Flask's dev server "
              "(fine for testing, install `waitress` for production).")
        try:
            app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
        except Exception as e:
            print(f"[FLASK] Exception in Flask thread: {e}")


flask_thread = threading.Thread(target=run_flask_server, daemon=True, name="flask-thread")
flask_thread.start()

try:
    config.client.start()
except Exception as e:
    print("[ERROR] Failed to start Pyrogram client:", e)
    try:
        flask_thread.join(timeout=1)
    except Exception:
        pass
    raise SystemExit(1)

loop = asyncio.get_event_loop()


async def _post_start_tasks():
    if hasattr(config, "save_session_to_db"):
        try:
            await config.save_session_to_db()
        except Exception as e:
            print("[SESSION] save_session_to_db() failed (non-fatal):", e)

    if hasattr(config, "save_session_string_to_file"):
        try:
            res = await config.save_session_string_to_file()
            if res:
                print(f"[SESSION] session string file saved: {res}")
        except Exception as e:
            print("[SESSION] save_session_string_to_file() failed (non-fatal):", e)

    if hasattr(config, "write_short_session_marker"):
        try:
            marker = config.write_short_session_marker()
            if marker:
                print(f"[SESSION] wrote marker: {marker}")
        except Exception as e:
            print("[SESSION] write_short_session_marker() failed (non-fatal):", e)

    if hasattr(config, "start_preloader"):
        try:
            await config.start_preloader()
        except Exception as e:
            print("[WARN] start_preloader() failed (non-fatal):", e)

    # Back up the session file (with its cached channel peers) to MongoDB now,
    # then keep it refreshed, so it survives wiped folders / ephemeral disks.
    try:
        await asyncio.to_thread(config.persist_session_file_to_db)
        asyncio.create_task(config.session_persist_loop())
    except Exception as e:
        print("[SESSION] session backup setup failed (non-fatal):", e)


try:
    loop.run_until_complete(_post_start_tasks())
except Exception as e:
    print("[WARN] Post-start tasks encountered an error:", e)

print("[READY] ✅ Bot started. Waiting for events... (Ctrl+C to stop)")

SHUTDOWN_WAIT = 6.0


def _shutdown_and_exit(signame):
    print(f"\n[SHUTDOWN] Received {signame}. Stopping client...")
    try:
        config.client.stop()
        print("[SHUTDOWN] client.stop() returned.")
    except Exception as e:
        print("[SHUTDOWN] client.stop() raised:", e)

    try:
        config.persist_session_file_to_db()
    except Exception as e:
        print("[SHUTDOWN] session backup failed:", e)

    try:
        flask_thread.join(timeout=1.0)
    except Exception:
        pass

    print("[SHUTDOWN] Exiting now.")
    sys.exit(0)


def _signal_handler(sig, frame):
    name = signal.Signals(sig).name if hasattr(signal, "Signals") else str(sig)
    _shutdown_and_exit(name)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

try:
    idle()
except KeyboardInterrupt:
    print("[SHUTDOWN] KeyboardInterrupt received.")
    _shutdown_and_exit("KeyboardInterrupt")
finally:
    try:
        config.client.stop()
    except Exception:
        pass
    try:
        flask_thread.join(timeout=1.0)
    except Exception:
        pass
    sys.exit(0)
