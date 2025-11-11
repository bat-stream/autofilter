import threading
from math import ceil
import asyncio
import signal
import os
import time
import traceback
import sys
import config
from pyrogram import idle
from flask import Flask, request, render_template_string, redirect, url_for, session, flash, jsonify
from pymongo import DESCENDING
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from bson.objectid import ObjectId
from config import client, files_collection, BOT_USERNAME,start_preloader

# Import handlers so they register (if needed by your bot)
import handlers.callbacks
import handlers.messages
import handlers.members
import commands.admin
import commands.user
from utils.helpers import clean_filename

STOP_TIMEOUT = 6  # seconds to wait for client.stop() before force-exit
FLASK_JOIN_TIMEOUT = 2 



# Use users_collection from config (you already set this in config.py)
users_collection = getattr(config, "users_collection", None)
if users_collection is None:
    print("[WARN] config.users_collection not found — create it in config.py to enable admin users.")


app = Flask(__name__)

# Ensure Flask has a secret key (set FLASK_SECRET in env)
app.secret_key = os.environ.get("FLASK_SECRET", "change-this-secret")
# ---------- Common CSS / header fragments ----------
# Keep theme consistent across pages
COMMON_HEAD = """
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
:root{
  --bg:#0d1117; --card:#0f1620; --text:#e6f7fb;
  --primary:#00bcd4; --accent:#1e90ff;
  --muted:rgba(230,247,251,0.12);
}
*{box-sizing:border-box}
html,body{height:100%; margin:0; background:var(--bg); color:var(--text); font-family:Poppins,Inter,Segoe UI,Arial; -webkit-font-smoothing:antialiased}
a{color:inherit; text-decoration:none}
.container{width:100%; max-width:1100px; margin:0 auto; padding:24px}
.center-full { min-height:calc(100vh - 48px); display:flex; align-items:center; justify-content:center; flex-direction:column; text-align:center; padding:32px }
.glow-btn{background:linear-gradient(90deg,var(--accent),var(--primary)); color:#032; border:none; padding:12px 22px; border-radius:999px; cursor:pointer; box-shadow:0 6px 28px rgba(0,180,255,0.12); transition:transform .18s ease}
.glow-btn:hover{transform:translateY(-3px); box-shadow:0 12px 45px rgba(0,180,255,0.18)}
.card{background:linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); border:1px solid var(--muted); padding:18px; border-radius:12px}
.small{font-size:0.92rem; color:rgba(230,247,251,0.78)}
.grid{display:grid; gap:16px}
@media(min-width:900px){ .grid-cols-2{grid-template-columns:repeat(2,1fr)} }
@media(max-width:899px){ .grid-cols-2{grid-template-columns:1fr} }

/* subtle background gradients */
.page-bg {
  position:fixed; inset:0; z-index:-1;
  background:
    radial-gradient(circle at 10% 20%, rgba(0,188,212,0.06), transparent 12%),
    radial-gradient(circle at 90% 80%, rgba(33,150,243,0.06), transparent 12%);
  filter:blur(6px);
  transform:scale(1.05);
}
</style>
"""

# ---------- HOME TEMPLATE ----------
HOME_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <title>Iᴀᴍ Bᴀᴛᴍᴀɴ</title>
  <link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png">
  <link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png">
  <link rel="icon" type="image/png" href="/static/favicon.png">
  """ + COMMON_HEAD + """
  <style>
    /* PUBG-like cinematic fade for the logo */
    .logo { width:200px; height:auto; opacity:0; transform:scale(1.18);
           filter: drop-shadow(0 0 14px rgba(0,188,212,0.55)) drop-shadow(0 0 30px rgba(30,144,255,0.45));
           animation: pubgFade 3.6s cubic-bezier(.2,.9,.2,1) forwards; }
    @keyframes pubgFade {
      0%   { opacity:0; transform:scale(1.4); filter:blur(10px); }
      55%  { opacity:1; transform:scale(1.03); filter:blur(2px); }
      100% { opacity:1; transform:scale(1); filter:blur(0); }
    }
    .title { font-size:1.6rem; margin-top:20px; color:var(--primary); opacity:0; transform:translateY(8px);
            animation: fadeUp .9s 3.8s forwards; }
    .subtitle { margin-top:10px; color:rgba(230,247,251,0.82); max-width:720px; opacity:0; transform:translateY(8px);
               animation: fadeUp .9s 4.0s forwards; }
    .home-actions{display:flex; gap:12px; margin-top:26px; opacity:0; transform:translateY(8px); animation:fadeUp .9s 4.2s forwards}
    @keyframes fadeUp{ to {opacity:1; transform:none} }
    .link-outline { padding:10px 18px; border-radius:10px; border:1px solid rgba(255,255,255,0.06); background:transparent; color:var(--text) }
  </style>
</head>
<body>
  <div class="page-bg"></div>
  <div class="center-full container" role="main" aria-labelledby="home-title">
    <img src="/static/logo.png" alt="Logo" class="logo" />
    <div id="home-title" class="title">Wᴇʟᴄᴏᴍᴇ ᴛᴏ Bᴀᴛᴍᴀɴ's Fɪʟᴇs Sᴛᴏʀᴀɢᴇ</div>
    <div class="subtitle small">Aᴄᴄᴇss sᴛᴏʀᴇᴅ ғɪʟᴇs ɪɴsᴛᴀɴᴛʟʏ ᴠɪᴀ Tᴇʟᴇɢʀᴀᴍ. Bʀᴏᴡsᴇ, sᴇᴀʀᴄʜ, ᴀɴᴅ ᴅᴏᴡɴʟᴏᴀᴅ ғɪʟᴇs ᴇғғᴏʀᴛʟᴇssʟʏ.</div>

    <div class="home-actions">
      <button class="glow-btn" onclick="location.href='{{ url_for('files_list') }}'">📁 Vɪᴇᴡ Sᴛᴏʀᴇᴅ Fɪʟᴇs</button>
      <a class="glow-btn"
   href="https://bat-stream.blogspot.com"
   onclick="window.open('https://bat-stream.blogspot.com', '_system'); return false;">
  🎬 Sᴛʀᴇᴀᴍɪɴɢ Wᴇʙsɪᴛᴇ
</a>
  </div>

  <!-- Footer -->
<footer class="site-footer">
  <div class="footer-content">
    © 2025 IAmBatman. All Rights Reserved.
  </div>
</footer>

<style>
.site-footer {
  width: 100%;
  padding: 14px 0;
  background: rgba(0, 0, 0, 0.25);
  text-align: center;
  color: rgba(230, 247, 251, 0.7);
  font-size: 0.88rem;
  position: relative;
  bottom: 0;
  margin-top: 220px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(4px);
}
.site-footer .footer-content {
  max-width: 1100px;
  margin: 0 auto;
}
.site-footer a {
  color: var(--primary);
  text-decoration: none;
}
.site-footer a:hover {
  text-decoration: underline;
}
@media(max-width:600px){
  .site-footer { font-size: 0.82rem; padding: 12px 8px; margin-top: 350px; }
}
</style>

</body>
</html>
"""




# ---------- REDIRECT TEMPLATE (faster loading bar + top menu + tight ads + popup on click) ----------
REDIRECT_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <title>Iᴀᴍ Bᴀᴛᴍᴀɴ : {{ file_name }}</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" integrity="sha512-Qf6gkbhURu0bXFlXN0JjF5U9epVJt5XJkTR3R3aJv1j/lX0XfN6nxCPLQ+7oK93kN6mH/Vp4rX6xgMWTlrLgAQ==" crossorigin="anonymous" referrerpolicy="no-referrer" />
  <link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png">
  <link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png">
  <link rel="icon" type="image/png" href="/static/favicon.ico">

  """ + COMMON_HEAD + """
  <style>
    /* Navigation Bar */
    .top-nav {
      display:flex; justify-content:space-between; align-items:center;
      padding:10px 18px; position:fixed; top:0; left:0; width:100%;
      background:rgba(0,0,0,0.35); backdrop-filter:blur(10px);
      border-bottom:1px solid rgba(255,255,255,0.05);
      z-index:1000;
    }
    .top-nav a {
      color:var(--text); text-decoration:none; margin:0 8px;
      font-weight:500; font-size:0.95rem; transition:0.25s;
    }
    .top-nav a:hover { color:var(--primary); text-shadow:0 0 10px var(--primary); }

    .logo {
      width:150px; height:auto; margin:20px auto 10px auto;
      filter:drop-shadow(0 0 12px rgba(0,188,212,0.6)) drop-shadow(0 0 25px rgba(30,144,255,0.45));
      opacity:0; transform:scale(1.18);
      animation: pubgFade 3.6s cubic-bezier(.2,.9,.2,1) forwards;
    }

    @keyframes pubgFade {
      0% { opacity:0; transform:scale(1.4); filter:blur(10px); }
      55%{ opacity:1; transform:scale(1.03); filter:blur(2px); }
      100%{ opacity:1; transform:scale(1); filter:blur(0); }
    }

    .card-centered {
      width:94%; max-width:760px; margin:0 auto; text-align:center;
      padding:20px 22px; border-radius:14px; border:1px solid rgba(255,255,255,0.04);
    }

    h1 { 
        margin:6px 0 10px 0; 
        color:var(--primary); 
        word-break: break-all;      /* ✅ break long words anywhere */
        overflow-wrap: anywhere;    /* ✅ for modern browsers */
        hyphens: auto;              /* optional: insert hyphens if needed */
      }

    .small {
        font-size:0.95rem;
        color:rgba(230,247,251,0.84);
        word-break: break-word;
        overflow-wrap: anywhere;
      }


    .loading-bar {
      width:90%; max-width:620px; height:10px;
      background:rgba(255,255,255,0.06); border-radius:999px;
      margin:14px auto; overflow:hidden; border:1px solid rgba(255,255,255,0.03);
    }

    .loading-fill {
      height:100%; width:0%;
      background:linear-gradient(90deg,var(--accent),var(--primary));
      box-shadow:0 6px 26px rgba(30,144,255,0.16);
      border-radius:inherit;
      animation: fillAnim 3s linear forwards;
    }

    @keyframes fillAnim { from{width:0%} to{width:100%} }

    #getButton {
      display:none; margin-top:16px; padding:12px 22px; border-radius:999px; border:none;
      background:linear-gradient(90deg,var(--accent),var(--primary));
      color:#021; cursor:pointer; font-weight:600;
      box-shadow:0 10px 40px rgba(0,188,212,0.12);
    }

  

    /* Ad containers (tight spacing near card) */
    .ad-container {
      display:flex; justify-content:center; align-items:center;
      margin:6px 0;
    }

    /* Popup Ad */
    #popupAd {
      display:none; position:fixed; top:0; left:0; width:100%; height:100%;
      background:rgba(0,0,0,0.7); z-index:9999; justify-content:center; align-items:center;
      animation: fadeIn 0.3s ease forwards;
    }
    #popupAd .ad-box {
      position:relative; background:#fff; padding:10px; border-radius:12px;
      box-shadow:0 0 15px rgba(0,0,0,0.3);
      transform:scale(0.8); opacity:0;
      animation: zoomIn 0.4s ease forwards;
    }
    @keyframes fadeIn { from{opacity:0;} to{opacity:1;} }
    @keyframes zoomIn { to{transform:scale(1); opacity:1;} }

    #closeAd {
      position:absolute; top:-25px; right:8px; background:#fff; color:#000;
      border:none; border-radius:3px; cursor:pointer; padding:2px 6px; font-weight:bold;
    }

    @media (max-width:600px) {
      .logo { width:120px; margin-top:60px; }
      .top-nav { padding:8px 12px; }
      .top-nav a { font-size:0.9rem; }
      .ad-container { margin:4px 0; }
    }
  </style>
</head>
<body>
  <div class="page-bg"></div>

  <!-- Top Navigation -->
  <div class="top-nav">
    <div>
      <a href="{{ url_for('home') }}">🏠 Home</a>
      <a href="{{ url_for('files_list') }}">📁 Files List</a>
      <a href="https://bat-stream.blogspot.com" target="_blank">
  🎬 Sᴛʀᴇᴀᴍɪɴɢ Wᴇʙsɪᴛᴇ
</a>
      <a id="backBtn" href="#" style="display:none;">← Bᴀᴄᴋ</a>
    </div>
  </div>

  <!-- Top Ad (tight above card) -->
  <div class="ad-container" style="margin-top:58px;">
    <script type="text/javascript">
      atOptions = {
        'key' : 'bf07742ac8514ce05bb75cd85a9bcd6e',
        'format' : 'iframe',
        'height' : 50,
        'width' : 320,
        'params' : {}
      };
    </script>
    <script type="text/javascript" src="//www.highperformanceformat.com/bf07742ac8514ce05bb75cd85a9bcd6e/invoke.js"></script>
  </div>

  <!-- Main Card -->
  <div class="center-full container" aria-live="polite" style="margin-top:0;">
    <div class="card-centered card">
      <img src="/static/logo.png" class="logo" alt="Logo" />
      <h1>{{ file_name }}</h1>
      <div class="small">Pʀᴇᴘᴀʀɪɴɢ ʏᴏᴜʀ ғɪʟᴇ : ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ</div>

      <div class="loading-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
        <div class="loading-fill" id="loadingFill"></div>
      </div>

     <a id="fileLink" href="https://t.me/{{ bot_username }}?start=file_{{ msg_id }}">
        <button id="getButton" aria-hidden="true">
          <img src="https://cdn-icons-png.flaticon.com/512/724/724933.png" alt="Download" style="width:16px; height:16px; vertical-align:middle; margin-right:6px;">
          Gᴇᴛ Fɪʟᴇ
        </button>
      </a>


      <div class="small" style="margin-top:12px; color:rgba(230,247,251,0.6)">
        Iғ ᴛʜᴇ ʙᴜᴛᴛᴏɴ ᴅᴏᴇsɴ'ᴛ ᴀᴘᴘᴇᴀʀ ᴀғᴛᴇʀ ᴀ ғᴇᴡ sᴇᴄᴏɴᴅs, ᴛʀʏ ʀᴇғʀᴇsʜɪɴɢ.
      </div>

      
    </div>
  </div>

  <!-- Bottom Ad (tight below card) -->
  <div class="ad-container" style="margin-bottom:12px;">
    <script type="text/javascript">
      atOptions = {
        'key' : 'bf07742ac8514ce05bb75cd85a9bcd6e',
        'format' : 'iframe',
        'height' : 50,
        'width' : 320,
        'params' : {}
      };
    </script>
    <script type="text/javascript" src="//www.highperformanceformat.com/bf07742ac8514ce05bb75cd85a9bcd6e/invoke.js"></script>
  </div>

  <!-- Popup Ad -->
  <div id="popupAd">
    <div class="ad-box">
      <button id="closeAd">X</button>
      <script type="text/javascript">
        atOptions = {
          'key' : '798f099ab777961c4eee87794ca29801',
          'format' : 'iframe',
          'height' : 600,
          'width' : 160,
          'params' : {}
        };
      </script>
      <script type="text/javascript" src="//www.highperformanceformat.com/798f099ab777961c4eee87794ca29801/invoke.js"></script>
    </div>
  </div>

<script>
  const loadingFill = document.getElementById('loadingFill');
  const getBtn = document.getElementById('getButton');
  const popupAd = document.getElementById('popupAd');
  const closeAd = document.getElementById('closeAd');
  const fileLink = document.getElementById('fileLink');

  loadingFill.addEventListener('animationend', () => {
    getBtn.style.display = 'inline-block';
    getBtn.style.opacity = 0;
    getBtn.style.transform = 'translateY(6px)';
    setTimeout(()=> {
      getBtn.style.transition = 'opacity .25s ease, transform .25s ease';
      getBtn.style.opacity = 1;
      getBtn.style.transform = 'translateY(0)';
      getBtn.removeAttribute('aria-hidden');
    }, 60);
  });

  // --- Popup on click ---
  getBtn.addEventListener('click', (e) => {
    e.preventDefault();
    popupAd.style.display = 'flex';
    setTimeout(() => {
      popupAd.style.display = 'none';
      window.location.href = fileLink.href;
    }, 1000);
  });

  closeAd.addEventListener('click', () => {
    popupAd.style.display = 'none';
  });

  // Disable context menu & inspect
  document.addEventListener('contextmenu', e => e.preventDefault());
  document.addEventListener('keydown', e => {
    if (e.key === 'F12' || (e.ctrlKey || e.metaKey) &&
      (['U','S','P'].includes(e.key.toUpperCase()) ||
      (e.shiftKey && ['I','J','C','K'].includes(e.key.toUpperCase()))))
      e.preventDefault();
  });

  // --- Show Back button only if came from files list ---
  const backBtn = document.getElementById('backBtn');
  if (document.referrer.includes('/files')) {
    backBtn.style.display = 'inline-block';
    backBtn.addEventListener('click', (e) => {
      e.preventDefault();
      window.history.back();
    });
  }
</script>

<!-- Footer -->
<footer class="site-footer">
  <div class="footer-content">
    © 2025 IAmBatman. All Rights Reserved.
  </div>
</footer>

<style>
.site-footer {
  width: 100%;
  padding: 14px 0;
  background: rgba(0, 0, 0, 0.25);
  text-align: center;
  color: rgba(230, 247, 251, 0.7);
  font-size: 0.88rem;
  position: relative;
  bottom: 0;
  margin-top: 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(4px);
}
.site-footer .footer-content {
  max-width: 1100px;
  margin: 0 auto;
}
.site-footer a {
  color: var(--primary);
  text-decoration: none;
}
.site-footer a:hover {
  text-decoration: underline;
}
@media(max-width:600px){
  .site-footer { font-size: 0.82rem; padding: 12px 8px; }
}
</style>

</body>
</html>
"""




# ---------- FILES LIST TEMPLATE (search + server-side pagination + centered ads + readable file size + popup ad on search) ----------
FILES_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <title>Sᴛᴏʀᴇᴅ Fɪʟᴇs : page {{ page }}{% if query %} (search: {{ query }}){% endif %}</title>
  <link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png">
  <link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png">
  <link rel="icon" type="image/png" href="/static/favicon.png">
  """ + COMMON_HEAD + """
  <style>
    .top-row { display:flex; gap:12px; align-items:center; justify-content:space-between; margin-bottom:18px; flex-wrap:wrap }
    .search-box { display:flex; gap:8px; align-items:center; flex:1 }
    .search-field { flex:1; padding:10px 12px; border-radius:10px; border:1px solid rgba(255,255,255,0.06);
                    background:rgba(255,255,255,0.02); color:var(--text); min-width:180px }
    .perpage { color:rgba(230,247,251,0.8); font-size:0.92rem; white-space:nowrap }
    .card-file {
      display:flex; flex-direction:row; gap:12px; align-items:center; justify-content:space-between;
      padding:16px; border-radius:12px; border:1px solid rgba(255,255,255,0.04);
      background:rgba(255,255,255,0.02); transition:transform .2s ease, box-shadow .2s ease;
    }
    .card-file:hover {
      transform:translateY(-4px);
      box-shadow:0 6px 20px rgba(0,188,212,0.12);
    }
    .meta { flex:1; text-align:left }
    .file-name { font-weight:600; color:var(--text); word-break:break-word; font-size:1rem }
    .file-size { font-size:0.9rem; color:rgba(230,247,251,0.7); margin-left:8px; white-space:nowrap }
    .actions { display:flex; gap:8px; align-items:center; flex-shrink:0 }
    .page-btn { padding:10px 16px; border-radius:10px; border:1px solid rgba(255,255,255,0.08);
                background:linear-gradient(90deg,var(--accent),var(--primary)); color:#032; font-weight:600;
                box-shadow:0 4px 18px rgba(0,188,212,0.15); transition:transform .18s ease; }
    .page-btn:hover { transform:translateY(-2px) }
    .page-btn[disabled]{ opacity:0.35; cursor:not-allowed }
    .pagination { display:flex; gap:8px; justify-content:center; margin-top:22px; align-items:center; flex-wrap:wrap }
    .grid { display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)) }
    .ad-container { display:flex; justify-content:center; align-items:center; margin:25px 0; text-align:center; }

    /* Popup Ad Styles */
    #popupAd {
      display:none; position:fixed; top:0; left:0; width:100%; height:100%;
      background:rgba(0,0,0,0.7); z-index:9999; justify-content:center; align-items:center;
      animation: fadeIn 0.3s ease forwards;
    }
    #popupAd .ad-box {
      position:relative; background:#fff; padding:10px; border-radius:12px;
      box-shadow:0 0 15px rgba(0,0,0,0.3);
      transform:scale(0.8); opacity:0;
      animation: zoomIn 0.4s ease forwards;
    }
    @keyframes fadeIn { from{opacity:0;} to{opacity:1;} }
    @keyframes zoomIn { to{transform:scale(1); opacity:1;} }
    #closeAd {
      position:absolute; top:-23px;font-size:20px; right:8px; background:#fff; color:black;
      border:none; border-radius:3px; cursor:pointer; padding:2px 6px;
    }

    /* Responsive tweaks */
    @media(max-width:600px){
      .card-file { flex-direction:column; align-items:flex-start; }
      .file-size { margin-left:0; display:block; margin-top:4px; }
      .actions { width:100%; justify-content:flex-end; }
      .page-btn { width:100%; text-align:center; }
      .search-box { width:100%; }
      .search-field { width:100%; }
      .ad-container { margin:16px 0; }
    }
  </style>

</head>
<body>
  <div class="page-bg"></div>
  <div class="container" role="main">
    <div style="display:flex;align-items:center;gap:18px; margin-bottom:18px; flex-wrap:wrap">
      <a href="{{ url_for('home') }}">
        <img src="/static/logo.png" alt="logo" style="width:64px; cursor:pointer; filter:drop-shadow(0 0 10px rgba(0,188,212,0.55))">
      </a>

      <div>
        <div style="font-size:1.1rem; color:var(--primary); font-weight:600">Sᴛᴏʀᴇᴅ Fɪʟᴇs</div>
        <div class="small">Bʀᴏᴡsᴇ sᴛᴏʀᴇᴅ ғɪʟᴇs (Pᴀɢᴇ {{ page }} ᴏғ {{ total_pages }})</div>
      </div>
      <div style="margin-left:auto">
        {% if page > 1 %}
          <a class="glow-btn" href="{{ url_for('files_list') }}?page={{ page-1 }}{% if query %}&search={{ query | urlencode }}{% endif %}">← Bᴀᴄᴋ</a>
        {% else %}
          <a class="glow-btn" href="{{ url_for('home') }}">← Bᴀᴄᴋ</a>
        {% endif %}
      </div>

    </div>

    <!-- Top Ad -->
    <div class="ad-container">
      <script type="text/javascript">
        atOptions = {
          'key' : 'bf07742ac8514ce05bb75cd85a9bcd6e',
          'format' : 'iframe',
          'height' : 50,
          'width' : 320,
          'params' : {}
        };
      </script>
      <script type="text/javascript" src="//www.highperformanceformat.com/bf07742ac8514ce05bb75cd85a9bcd6e/invoke.js"></script>
    </div>

    <div class="card">
      <div class="top-row">
        <form id="searchForm" method="get" action="{{ url_for('files_list') }}" style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; width:100%">
          <div class="search-box">
            <input class="search-field" name="search" placeholder="Sᴇᴀʀᴄʜ ғɪʟᴇ ɴᴀᴍᴇs..." value="{{ query | e }}">
            <button class="page-btn" type="submit">Sᴇᴀʀᴄʜ</button>
          </div>
          <div class="perpage">Sʜᴏᴡɪɴɢ {{ per_page }} ᴘᴇʀ ᴘᴀɢᴇ</div>
        </form>
      </div>

      <div class="grid">
        {% if files %}
          {% for f in files %}
            <div class="card-file">
              <div class="meta">
                <div class="file-name">
                  {{ f.get('file_name', 'Unnamed File') }}
                  {% if f.get('file_size') %}
                    {% set size = f.get('file_size')|int %}
                    {% if size < 1024 %}
                      <span class="file-size">({{ size }} B)</span>
                    {% elif size < 1048576 %}
                      <span class="file-size">({{ '%.1f' % (size / 1024) }} KB)</span>
                    {% elif size < 1073741824 %}
                      <span class="file-size">({{ '%.1f' % (size / 1048576) }} MB)</span>
                    {% else %}
                      <span class="file-size">({{ '%.2f' % (size / 1073741824) }} GB)</span>
                    {% endif %}
                  {% endif %}
                </div>
              </div>
              <div class="actions">
                <a class="page-btn" href="{{ url_for('redirect_page') }}?id={{ f.get('message_id') }}">Gᴇᴛ</a>
              </div>
            </div>
          {% endfor %}
        {% else %}
          <div class="small" style="padding:20px">No files found.</div>
        {% endif %}
      </div>

      <div class="pagination">
        {% if page > 1 %}
          <a class="page-btn" href="{{ url_for('files_list') }}?page={{ page-1 }}{% if query %}&search={{ query | urlencode }}{% endif %}">Pʀᴇᴠɪᴏᴜs</a>
        {% else %}
          <button class="page-btn" disabled>Pʀᴇᴠɪᴏᴜs</button>
        {% endif %}

        <div class="small">Pᴀɢᴇ {{ page }} / {{ total_pages }}</div>

        {% if page < total_pages %}
          <a class="page-btn" id="nextBtn" href="{{ url_for('files_list') }}?page={{ page+1 }}{% if query %}&search={{ query | urlencode }}{% endif %}">Nᴇxᴛ</a>
        {% else %}
          <button class="page-btn" disabled>Nᴇxᴛ</button>
        {% endif %}
      </div>
    </div>

    <!-- Bottom Ad -->
    <div class="ad-container">
      <script type="text/javascript">
        atOptions = {
          'key' : 'bf07742ac8514ce05bb75cd85a9bcd6e',
          'format' : 'iframe',
          'height' : 50,
          'width' : 320,
          'params' : {}
        };
      </script>
      <script type="text/javascript" src="//www.highperformanceformat.com/bf07742ac8514ce05bb75cd85a9bcd6e/invoke.js"></script>
    </div>

    <!-- Popup Ad -->
    <div id="popupAd">
      <div class="ad-box">
        <button id="closeAd">Close</button>
        <script type="text/javascript">
          atOptions = {
            'key' : 'fdf3bc4ff7c8fb37b011cb27d58ecc67',
            'format' : 'iframe',
            'height' : 250,
            'width' : 300,
            'params' : {}
          };
        </script>
        <script type="text/javascript" src="//www.highperformanceformat.com/fdf3bc4ff7c8fb37b011cb27d58ecc67/invoke.js"></script>
      </div>
    </div>

    <script>
    const nextBtn = document.getElementById('nextBtn');
    const popupAd = document.getElementById('popupAd');
    const closeAd = document.getElementById('closeAd');
    const searchForm = document.getElementById('searchForm');

    // Show popup every 3 pages
    if (nextBtn) {
      nextBtn.addEventListener('click', function(event) {
        event.preventDefault();
        let adCount = parseInt(localStorage.getItem('adCount') || '0');
        adCount++;
        if (adCount >= 3) {
          popupAd.style.display = 'flex';
          localStorage.setItem('adCount', 0);
          closeAd.onclick = () => {
            popupAd.style.display = 'none';
            window.location.href = nextBtn.href;
          };
        } else {
          localStorage.setItem('adCount', adCount);
          window.location.href = nextBtn.href;
        }
      });
    }

    // Show popup after search submit
    if (searchForm) {
      searchForm.addEventListener('submit', function(e) {
        e.preventDefault();
        popupAd.style.display = 'flex';
        closeAd.onclick = () => {
          popupAd.style.display = 'none';
          searchForm.submit();
        };
      });
    }
    </script>
  
  </div>

  <!-- Footer -->
<footer class="site-footer">
  <div class="footer-content">
    © 2025 IAmBatman. All Rights Reserved.
  </div>
</footer>

<style>
.site-footer {
  width: 100%;
  padding: 14px 0;
  background: rgba(0, 0, 0, 0.25);
  text-align: center;
  color: rgba(230, 247, 251, 0.7);
  font-size: 0.88rem;
  position: relative;
  bottom: 0;
  margin-top: 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(4px);
}
.site-footer .footer-content {
  max-width: 1100px;
  margin: 0 auto;
}
.site-footer a {
  color: var(--primary);
  text-decoration: none;
}
.site-footer a:hover {
  text-decoration: underline;
}
@media(max-width:600px){
  .site-footer { font-size: 0.82rem; padding: 12px 8px; }
}
</style>

</body>
</html>
"""



# ---- Login template ----
LOGIN_TEMPLATE = r"""
<!doctype html><html><head><meta charset="utf-8"><title>Admin Login</title>""" + COMMON_HEAD + r"""
<style>
.login-box{max-width:420px;margin:80px auto;padding:18px;border-radius:12px}
input{width:100%;padding:10px;margin:6px 0;border-radius:8px;border:1px solid rgba(255,255,255,0.06);background:transparent;color:var(--text)}
button{padding:10px 14px;border-radius:10px;border:none;background:linear-gradient(90deg,var(--accent),var(--primary));color:#032;font-weight:600}
</style>
</head><body><div class="container"><div class="login-box card">
  <h2 style="margin-top:0">Admin Login</h2>
  {% with msgs = get_flashed_messages() %}
    {% if msgs %}
      <div style="color:#ffb3b3;padding:8px;border-radius:8px;background:rgba(255,120,120,0.03)">{{ msgs[0] }}</div>
    {% endif %}
  {% endwith %}
  <form method="post">
    <label>Username</label><br><input name="username" autofocus required><br>
    <label>Password</label><br><input name="password" type="password" required><br><br>
    <button type="submit">Login</button>
  </form>
  <p class="small" style="margin-top:10px">Create admin with <code>create_admin(username,password)</code> helper.</p>
</div></div></body></html>
"""

# ---- Dashboard template (search only, human-readable size) ----
DASHBOARD_TEMPLATE = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Admin Dashboard - Files</title>
  """ + COMMON_HEAD + r"""
  <style>
    
    .actions{display:flex;gap:8px}
    .danger{background:linear-gradient(90deg,#ff7a7a,#ffb3b3);color:#2b0000}
    .small{color:rgba(230,247,251,0.78)}
    .btn { padding:10px 14px; border-radius:10px; border:none; cursor:pointer; font-weight:600; }
    .btn-primary { background:linear-gradient(90deg,var(--accent),var(--primary)); color:#032; box-shadow:0 8px 30px rgba(0,188,212,0.08); }
    .btn-ghost { background:transparent; border:1px solid rgba(255,255,255,0.06); color:var(--text); }
    .btn-danger { background:linear-gradient(90deg,#ff7a7a,#ffb3b3); color:#2b0000; }
    .btn-sm { padding:8px 10px; font-size:0.95rem; border-radius:8px; }
   /* ===== Reliable row layout: flex + pinned right-side actions ===== */
/* ===== Forced layout: pin actions to the far right ===== */
.card-file {
  position: relative !important;
  display: flex !important;
  align-items: center !important;
  gap: 12px !important;
  padding: 14px 18px 14px 18px !important;  /* keep left padding, we'll reserve space with meta */
  border-radius: 10px !important;
  border: 1px solid rgba(255,255,255,0.04) !important;
  background: rgba(255,255,255,0.02) !important;
  box-sizing: border-box !important;
  overflow: visible !important;
}

/* Reserve space for the actions on the right so content never reaches them */
.card-file .meta {
  flex: 1 1 auto !important;
  min-width: 0 !important;        /* allow ellipsis */
  margin-right: 260px !important; /* <-- increase this to push actions further right */
  text-align: left !important;
}

/* File name: prefer single-line with ellipsis on desktop */
.card-file .meta .file-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  color: var(--text);
  font-size: 1rem;
  margin: 0;
}

/* Pin the action buttons absolutely to the far right of the card */
.card-file .actions {
  position: absolute !important;
  right: 4px !important;        /* try 4px (near flush). change to 0 or 8px if you prefer */
  top: 50% !important;
  transform: translateY(-50%) !important;
  display: flex !important;
  gap: 8px !important;
  align-items: center !important;
  z-index: 999 !important;
  white-space: nowrap !important;
}

/* Buttons sizing so they fit within reserved width */
.card-file .actions .btn {
  min-width: 72px !important;
  padding: 8px 12px !important;
  justify-content: center !important;
}

    /* --- Stylish Search Bar Redesign --- */
.search-field {
  flex: 1;
  padding: 12px 16px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text);
  font-size: 1rem;
  letter-spacing: 0.2px;
  transition: all 0.25s ease;
  outline: none;
  backdrop-filter: blur(8px);
  box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.05);
}

.search-field::placeholder {
  color: rgba(230, 247, 251, 0.5);
  font-style: italic;
}

.search-field:focus {
  border-color: rgba(0, 188, 212, 0.4);
  background: rgba(255, 255, 255, 0.07);
  box-shadow: 0 0 10px rgba(0, 188, 212, 0.2), inset 0 0 4px rgba(0, 188, 212, 0.1);
  transform: translateY(-1px);
}

/* Container card refinement */
.card {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.01));
  border: 1px solid rgba(255, 255, 255, 0.04);
  border-radius: 14px;
  padding: 18px;
  box-shadow: 0 8px 24px rgba(2, 12, 20, 0.3);
  backdrop-filter: blur(8px);
}

/* Button enhancements */
.btn {
  cursor: pointer;
  font-weight: 600;
  border: none;
  padding: 11px 18px;
  border-radius: 12px;
  font-size: 0.95rem;
  transition: all 0.22s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn-primary {
  background: linear-gradient(90deg, var(--accent), var(--primary));
  color: #032;
  box-shadow: 0 4px 16px rgba(0, 188, 212, 0.25);
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 28px rgba(0, 188, 212, 0.35);
}

.btn-ghost {
  background: rgba(255, 255, 255, 0.05);
  color: var(--text);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.btn-ghost:hover {
  background: rgba(255, 255, 255, 0.08);
  transform: translateY(-2px);
  border-color: rgba(0, 188, 212, 0.3);
}

/* Form alignment for desktop & mobile */
#searchForm {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  justify-content: space-between;
}
    /* Mobile-only styles (drop-in) */
@media (max-width: 900px) {
  :root{
    --mobile-font-base: 13px;
    --mobile-font-small: 11px;
    --mobile-btn-padding-vertical: 8px;
    --mobile-btn-padding-horizontal: 10px;
    --mobile-btn-radius: 9px;
    --mobile-card-padding: 10px;
    --mobile-gap: 8px;
  }

  /* Card becomes a vertical stack for touch-friendly layout */
  .card-file {
    display: flex !important;
    flex-direction: column !important;
    align-items: stretch !important;
    padding: var(--mobile-card-padding) !important;
    gap: var(--mobile-gap) !important;
  }

  /* Remove desktop reserved right margin so meta can use full width */
  .card-file .meta {
    margin-right: 0 !important;
    width: 100% !important;
    min-width: 0 !important;
    text-align: left !important;
  }

  /* File name: allow up to 2 lines, smaller text */
  .card-file .meta .file-name,
  .card-file .meta > div > .file-name,
  .card-file .meta > div > div:first-child {
    font-size: var(--mobile-font-base) !important;
    line-height: 1.2 !important;
    white-space: normal !important;
    overflow: hidden !important;
    display: -webkit-box !important;
    -webkit-line-clamp: 2 !important; /* max 2 lines */
    -webkit-box-orient: vertical !important;
    word-break: break-word !important;
  }

  /* Smaller secondary text */
  .card-file .small {
    font-size: var(--mobile-font-small) !important;
    margin-top: 6px;
  }

  /* Keep checkbox + first-line meta compact */
  .card-file > div[style*="flex: 0 0 auto;"],
  .card-file > input[type="checkbox"],
  .card-file .meta {
    display: flex !important;
    align-items: center !important;
    gap: 10px !important;
  }

  /* Improve checkbox hit area */
  .card-file input[type="checkbox"] {
    width: 18px !important;
    height: 18px !important;
    margin: 0 !important;
  }

  /* Actions flow below meta, full-width touch targets */
  .card-file .actions {
    position: static !important;
    transform: none !important;
    margin-top: 8px !important;
    width: 100% !important;
    display: flex !important;
    gap: 8px !important;
    justify-content: space-between !important;
    padding-top: 8px !important;
    border-top: 1px solid rgba(255,255,255,0.03) !important;
  }

  /* Buttons: reduced size, fill space evenly */
  .card-file .actions .btn {
    flex: 1 1 auto !important;
    min-width: 0 !important;
    padding: var(--mobile-btn-padding-vertical) var(--mobile-btn-padding-horizontal) !important;
    font-size: var(--mobile-font-small) !important;
    border-radius: var(--mobile-btn-radius) !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
  }

  /* Slight visual tweak for danger button to remain prominent */
  .card-file .actions .btn-danger {
    padding-top: calc(var(--mobile-btn-padding-vertical) - 1px) !important;
    padding-bottom: calc(var(--mobile-btn-padding-vertical) - 1px) !important;
  }

  /* Optional: stack buttons vertically on very small screens */
  @media (max-width: 420px) {
    .card-file .actions {
      flex-direction: column !important;
    }
    .card-file .actions .btn {
      width: 100% !important;
    }
  }
}

    
  </style>
</head>
<body>
<div class="container">
  <div style="display:flex;align-items:center;gap:18px;margin-bottom:18px">
    <a href="{{ url_for('home') }}"><img src="/static/logo.png" style="width:64px"></a>
    <div>
      <div style="font-size:1.1rem;color:var(--primary);font-weight:600">Admin Dashboard</div>
      <div class="small">Manage stored files — Page {{ page }} of {{ total_pages }}</div>
    </div>
    <div style="margin-left:auto; display:flex; gap:8px;">
      <a class="btn btn-ghost" href="{{ url_for('files_list') }}">View public files</a>
      <a class="btn btn-ghost" href="{{ url_for('admin_logout') }}">Logout</a>
    </div>
  </div>

  <div class="card" style="margin-bottom:12px">
    <div id="alertContainer"></div>

    <!-- Simple Search (only q) -->
    <form id="searchForm" method="get" action="{{ url_for('admin_dashboard') }}" style="display:flex;gap:8px;align-items:center;">
      <input name="q" placeholder="Search filename or message_id (regex supported)" class="search-field" value="{{ request.args.get('q','')|e }}" style="flex:1">
      <button class="btn btn-primary" type="submit">Search</button>
      <button class="btn btn-ghost" type="button" id="clearFilters">Clear</button>
    </form>
  </div>

  <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px">
    <label style="display:flex;gap:8px;align-items:center">
      <input type="checkbox" id="selectAll"> <span class="small">Select all on page</span>
    </label>
    <button id="bulkDeleteBtn" class="btn btn-danger btn-sm" disabled>Delete selected</button>
    <div id="selectedCount" class="small" style="margin-left:8px">0 selected</div>
    <div style="margin-left:auto" class="small">Showing {{ files|length }} items (page size {{ per_page }})</div>
  </div>

 <div class="grid" style="display:flex;flex-direction:column;gap:12px">
  {% if files %}
    {% for f in files %}
      <div class="card-file" data-id="{{ f.get('_id') }}">
        <!-- Left: checkbox -->
        <div style="flex: 0 0 auto; margin-right:10px;">
          <input type="checkbox" class="rowCheckbox" data-id="{{ f.get('_id') }}">
        </div>

        <!-- Middle: meta (flexes to fill available space) -->
        <div class="meta">
          <div style="min-width:0">
            <div style="font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
              {{ f.get('file_name','Unnamed File') }}
            </div>
            <div class="small" style="margin-top:6px">
              Message ID: <strong>{{ f.get('message_id') }}</strong>
              {% if f.get('file_size') %}
                • Size: <strong>{{ human_readable_size(f.get('file_size')) }}</strong>
              {% endif %}
            </div>
          </div>
        </div>

        <!-- Right: actions (absolutely pinned by your CSS) -->
        <div class="actions" style="position:absolute; right:8px; top:50%; transform:translateY(-50%);">
          <a class="btn btn-ghost btn-sm" href="{{ url_for('redirect_page') }}?id={{ f.get('message_id') }}" target="_blank">Get</a>
          <button class="btn btn-sm" onclick="openEdit('{{ f.get('_id') }}')">Edit</button>
          <button class="btn btn-danger btn-sm" onclick="doDelete('{{ f.get('_id') }}')">Delete</button>
        </div>
      </div>
    {% endfor %}
  {% else %}
    <div class="small" style="padding:18px">No files found for this query.</div>
  {% endif %}
</div>


  <div style="display:flex;gap:8px;justify-content:center;align-items:center;margin-top:18px">
    {% if page > 1 %}
      <a class="btn btn-ghost" href="{{ url_for('admin_dashboard') }}?page={{ page-1 }}{% if request.query_string %}&{{ request.query_string.decode('utf-8') }}{% endif %}">Previous</a>
    {% else %}
      <button class="btn btn-ghost" disabled>Previous</button>
    {% endif %}
    <div class="small">Page {{ page }} / {{ total_pages }}</div>
    {% if page < total_pages %}
      <a class="btn btn-ghost" href="{{ url_for('admin_dashboard') }}?page={{ page+1 }}{% if request.query_string %}&{{ request.query_string.decode('utf-8') }}{% endif %}">Next</a>
    {% else %}
      <button class="btn btn-ghost" disabled>Next</button>
    {% endif %}
  </div>

</div>

<!-- Edit modal (unchanged) -->
<div id="editModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);align-items:center;justify-content:center">
  <div style="background:var(--card);padding:16px;border-radius:10px;width:min(720px,95%)">
    <h3>Edit file</h3>
    <form id="editForm">
      <input type="hidden" id="edit_id" name="_id">
      <label>File name</label><br><input id="edit_name" name="file_name" style="width:100%;padding:8px;border-radius:6px"><br>
      <label>Message ID</label><br><input id="edit_msgid" name="message_id" style="width:100%;padding:8px;border-radius:6px"><br><br>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button type="button" class="btn btn-ghost" onclick="closeEdit()">Cancel</button>
        <button type="submit" class="btn btn-primary">Save</button>
      </div>
    </form>
  </div>
</div>

<script>
/* (JS same as earlier — selection, bulk delete, edit, alerts, clear) */
const selectAll = document.getElementById('selectAll');
const bulkDeleteBtn = document.getElementById('bulkDeleteBtn');
const selectedCount = document.getElementById('selectedCount');
const alertContainer = document.getElementById('alertContainer');

function getRowCheckboxes(){ return Array.from(document.querySelectorAll('.rowCheckbox')); }
function getSelectedIds(){ return getRowCheckboxes().filter(cb=>cb.checked).map(cb=>cb.getAttribute('data-id')); }
function updateSelectionUI(){ const count = getSelectedIds().length; selectedCount.textContent = `${count} selected`; bulkDeleteBtn.disabled = (count === 0); }

selectAll?.addEventListener('change', (e)=>{ const checked = e.target.checked; getRowCheckboxes().forEach(cb => cb.checked = checked); updateSelectionUI(); });
document.addEventListener('change', (e)=>{ if(e.target && e.target.classList && e.target.classList.contains('rowCheckbox')) updateSelectionUI(); });

bulkDeleteBtn?.addEventListener('click', async ()=>{ const ids = getSelectedIds(); if(!ids.length) return; if(!confirm(`Delete ${ids.length} selected items? This cannot be undone.`)) return; try{ const res = await fetch('/admin/api/files/bulk_delete', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ ids }) }); const j = await res.json(); if(j.ok){ showAlert('Deleted '+ (j.deleted_count || ids.length) +' items', 'success'); setTimeout(()=> location.reload(), 800); } else { showAlert(j.error || 'Bulk delete failed', 'error'); } } catch(err){ showAlert(err.message || 'Request failed', 'error'); } });

function openEdit(id){ fetch('/admin/api/file/' + id).then(r=>r.json()).then(j=>{ if(!j.ok){ showAlert(j.error||'Failed','error'); return; } const f = j.file; document.getElementById('edit_id').value = f._id.$oid || f._id; document.getElementById('edit_name').value = f.file_name || ''; document.getElementById('edit_msgid').value = f.message_id || ''; document.getElementById('editModal').style.display = 'flex'; }).catch(e=> showAlert(e.message,'error')); }
function closeEdit(){ document.getElementById('editModal').style.display = 'none'; }
document.getElementById('editForm').addEventListener('submit', function(e){ e.preventDefault(); const id = document.getElementById('edit_id').value; const payload = { file_name: document.getElementById('edit_name').value, message_id: document.getElementById('edit_msgid').value }; fetch('/admin/api/file/' + id, { method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) }).then(r=>r.json()).then(j=>{ if(j.ok) location.reload(); else showAlert(j.error||'Save failed','error'); }).catch(e=>showAlert(e.message,'error')); });

function doDelete(id){ if(!confirm('Delete this file? This cannot be undone.')) return; fetch('/admin/api/file/' + id, { method:'DELETE' }).then(r=>r.json()).then(j=>{ if(j.ok) location.reload(); else showAlert(j.error||'Delete failed','error'); }); }

function showAlert(msg, kind='success'){ alertContainer.innerHTML = `<div class="alert ${kind==='success'?'alert-success':'alert-error'}">${msg}</div>`; setTimeout(()=>{ if(alertContainer.firstChild) alertContainer.removeChild(alertContainer.firstChild); }, 4000); }

document.getElementById('clearFilters').addEventListener('click', (e)=>{ const f = document.getElementById('searchForm'); Array.from(f.querySelectorAll('input')).forEach(i => { if(i.name!=='q') i.value=''; }); f.querySelector('[name=q]').value=''; f.submit(); });
</script>

</body>
</html>
"""



# ---------- Routes ----------

@app.route('/')
def home():
    return render_template_string(HOME_TEMPLATE)

@app.route('/redirect')
def redirect_page():
    # 'id' query param -> message_id
    msg_id = request.args.get('id', default=None)
    if not msg_id:
        # fallback to bot homepage if no id
        return redirect(f"https://t.me/{BOT_USERNAME}")

    # safely convert message_id
    try:
        msg_int = int(msg_id)
    except Exception:
        return redirect(f"https://t.me/{BOT_USERNAME}")

    # find the file entry
    file_entry = files_collection.find_one({"message_id": msg_int}) or {}
    raw_name = file_entry.get('file_name') or "Requested File"

    # ✅ Clean the filename before using it
    file_name = clean_filename(raw_name)

    # render the redirect page
    return render_template_string(
        REDIRECT_TEMPLATE,
        msg_id=msg_int,
        bot_username=BOT_USERNAME,
        file_name=file_name
    )
@app.route('/files')
def files_list():
    """
    Server-side search + pagination.
    Query params:
      - page (int, 1-based)
      - search (string)
    """
    # pagination settings
    try:
        page = max(1, int(request.args.get('page', 1)))
    except Exception:
        page = 1
    per_page = 10

    search_q = request.args.get('search', '').strip()
    mongo_filter = {}
    if search_q:
        # perform case-insensitive substring search on file_name
        # use regex anchored anywhere (escape special chars)
        import re
        safe_q = re.escape(search_q)
        mongo_filter = {"file_name": {"$regex": safe_q, "$options": "i"}}

    total_count = files_collection.count_documents(mongo_filter)
    total_pages = max(1, ceil(total_count / per_page))
    if page > total_pages:
        page = total_pages

    skip = (page - 1) * per_page

    # fetch results sorted by newest (if message_id correlates with time); adjust sort if you have timestamp
    cursor = files_collection.find(mongo_filter).sort("message_id", DESCENDING).skip(skip).limit(per_page)
    files = list(cursor)

    return render_template_string(FILES_TEMPLATE,
                                  files=files,
                                  page=page,
                                  per_page=per_page,
                                  total_pages=total_pages,
                                  query=search_q,
                                  bot_username=BOT_USERNAME)



# ---- auth decorator ----
def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if session.get("admin_logged_in"):
            return f(*args, **kwargs)
        return redirect(url_for("admin_login", next=request.path))
    return wrapped

# ---- routes ----
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    from config import ADMIN_USERNAME, ADMIN_PASSWORD  # ✅ import from config

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            session["admin_username"] = username
            next_url = request.args.get("next") or url_for("admin_dashboard")
            return redirect(next_url)
        else:
            flash("Invalid username or password")

    return render_template_string(LOGIN_TEMPLATE)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    session.pop("admin_username", None)
    return redirect(url_for("admin_login"))

def human_readable_size(sz):
    """Return human-readable size. Accepts int or numeric string. Examples: '1.2 MB', '3.45 GB'."""
    try:
        s = int(sz)
    except Exception:
        try:
            s = float(sz)
        except Exception:
            return str(sz)  # fallback

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
    # page param
    try:
        page = max(1, int(request.args.get("page", 1)))
    except Exception:
        page = 1
    per_page = 12

    # Only 'q' is supported now
    q = request.args.get("q", "").strip()

    mongo_filter = {}

    if q:
        sub_filters = []
        if q.isdigit():
            sub_filters.append({"message_id": int(q)})
        try:
            import re
            if q.startswith('/') and q.endswith('/') and len(q) > 2:
                pattern = q[1:-1]
            else:
                pattern = re.escape(q)
            sub_filters.append({"file_name": {"$regex": pattern, "$options": "i"}})
        except Exception:
            # fallback substring
            sub_filters.append({"file_name": {"$regex": q, "$options": "i"}})

        mongo_filter["$or"] = sub_filters

    # Count + pagination
    total_count = files_collection.count_documents(mongo_filter)
    total_pages = max(1, ceil(total_count / per_page))
    if page > total_pages:
        page = total_pages
    skip = (page - 1) * per_page

    cursor = files_collection.find(mongo_filter).sort("message_id", DESCENDING).skip(skip).limit(per_page)
    files = list(cursor)

    # pass human_readable_size into template
    return render_template_string(DASHBOARD_TEMPLATE, files=files, page=page, per_page=per_page, total_pages=total_pages, request=request, human_readable_size=human_readable_size)
@app.route("/admin/api/files/bulk_delete", methods=["POST"])
@login_required
def admin_bulk_delete():
    data = request.get_json() or {}
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"ok": False, "error": "No ids provided"}), 400

    # Build deletion query that accepts ObjectId or string _id
    queries = []
    for i in ids:
        try:
            queries.append(ObjectId(i))
        except Exception:
            queries.append(i)

    # Delete by matching _id in list
    res = files_collection.delete_many({"_id": {"$in": queries}})
    return jsonify({"ok": True, "deleted_count": res.deleted_count})


@app.route("/admin/api/file/<id>", methods=["GET", "PUT", "DELETE"])
@login_required
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
        data = request.get_json() or {}
        update = {}
        if "file_name" in data: update["file_name"] = data["file_name"]
        if "message_id" in data: update["message_id"] = data["message_id"]
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

# ---- helper to create admin user ----
def create_admin(username, password):
    if users_collection is None:
        raise RuntimeError("users_collection not configured in config.py")
    if not username or not password:
        raise ValueError("username & password required")
    users_collection.update_one({"username": username}, {"$set": {"username": username, "password_hash": generate_password_hash(password)}}, upsert=True)
    print("Admin user created/updated")

@app.route("/setup", methods=["POST"])
def setup_route():
    if os.environ.get("ALLOW_SETUP") != "1":
        return "setup disabled", 403
    if users_collection is None:
        return jsonify({"ok": False, "error": "users_collection missing"}), 500
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"ok": False, "error": "username & password required"}), 400
    create_admin(username, password)
    return jsonify({"ok": True})
# -------------------------------------------------------------------------------



# ---------- Run (flask + your telegram client) ----------
def run_flask():
    app.run(host="0.0.0.0", port=5000, debug=False)

def run_flask_server():
    """Run Flask without reloader so it doesn't spawn extra threads."""
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    except Exception as e:
        print(f"[FLASK] Exception in Flask thread: {e}")

# Start Flask in background (daemon)
flask_thread = threading.Thread(target=run_flask_server, daemon=True, name="flask-thread")
flask_thread.start()

# Start Pyrogram client
try:
    config.client.start()
except Exception as e:
    print("[ERROR] Failed to start Pyrogram client:", e)
    # If client failed to start, stop flask thread and exit
    try:
        flask_thread.join(timeout=1)
    except Exception:
        pass
    raise SystemExit(1)

# Use the running event loop for async helpers
loop = asyncio.get_event_loop()

# Run async post-start tasks: save session, write marker, preload chats
async def _post_start_tasks():
    # 1) Try to save session to DB (non-fatal)
    if hasattr(config, "save_session_to_db"):
        try:
            await config.save_session_to_db()
        except Exception as e:
            print("[SESSION] save_session_to_db() failed (non-fatal):", e)

    # 2) Write session string to a short file (non-fatal)
    if hasattr(config, "save_session_string_to_file"):
        try:
            res = await config.save_session_string_to_file()
            if res:
                print(f"[SESSION] session string file saved: {res}")
        except Exception as e:
            print("[SESSION] save_session_string_to_file() failed (non-fatal):", e)

    # 3) Write a short session marker so /tmp/pyro_sessions shows a friendly name
    if hasattr(config, "write_short_session_marker"):
        try:
            marker = config.write_short_session_marker()
            if marker:
                print(f"[SESSION] wrote marker: {marker}")
        except Exception as e:
            print("[SESSION] write_short_session_marker() failed (non-fatal):", e)

    # 4) start_preloader: optional, non-fatal
    if hasattr(config, "start_preloader"):
        try:
            await config.start_preloader()
        except Exception as e:
            print("[WARN] start_preloader() failed (non-fatal):", e)

# Run the async post-start tasks synchronously here
try:
    loop.run_until_complete(_post_start_tasks())
except Exception as e:
    print("[WARN] Post-start tasks encountered an error:", e)

print("[READY] ✅ Bot started. Waiting for events... (Ctrl+C to stop)")

# -------- Graceful shutdown --------
SHUTDOWN_WAIT = 6.0  # seconds to wait for graceful stop

def _shutdown_and_exit(signame):
    """Stop client and exit (called on signal)."""
    print(f"\n[SHUTDOWN] Received {signame}. Stopping client...")
    try:
        # call stop() synchronously — Pyrogram's sync wrapper will run it on loop
        config.client.stop()
        print("[SHUTDOWN] client.stop() returned.")
    except Exception as e:
        print("[SHUTDOWN] client.stop() raised:", e)

    # join Flask thread briefly (daemon thread won't block if still running)
    try:
        flask_thread.join(timeout=1.0)
    except Exception:
        pass

    print("[SHUTDOWN] Exiting now.")
    sys.exit(0)

def _signal_handler(sig, frame):
    # Map signal numbers to names nicely
    name = signal.Signals(sig).name if hasattr(signal, "Signals") else str(sig)
    # Call shutdown helper
    _shutdown_and_exit(name)

# Register handlers
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# Keep process alive until killed
try:
    idle()
except KeyboardInterrupt:
    print("[SHUTDOWN] KeyboardInterrupt received.")
    _shutdown_and_exit("KeyboardInterrupt")
finally:
    # Safety: ensure client stopped if we somehow reach here
    try:
        config.client.stop()
    except Exception:
        pass
    try:
        flask_thread.join(timeout=1.0)
    except Exception:
        pass
    sys.exit(0)
