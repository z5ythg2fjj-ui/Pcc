"""
M3SB Proxy Bot — Secure Edition
Owner  : 8555397763 
Token  : 8992791788:AAGfVOgwy7GLpuNd_EhaRRduDzVyUpQsSfE
Install: pip install python-telegram-bot==20.7
Run    : python3 m3sb_bot.py
"""

import sqlite3, re, logging, random, string
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode

# ══════════════════════════════════════════════════════════════
TOKEN    = "8992791788:AAGfVOgwy7GLpuNd_EhaRRduDzVyUpQsSfE"
OWNER_ID = 8286090730
DB_PATH  = "m3sb.db"
SEP      = "━━━━━━━━━━━━━━━━━━━━"

# ══════════════════════════════════════════════════════════════
#  DB
# ══════════════════════════════════════════════════════════════
def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS keys (
            key         TEXT PRIMARY KEY,
            duration    TEXT DEFAULT '1 Day',
            used_by     INTEGER DEFAULT NULL,
            used_at     TEXT DEFAULT NULL,
            ip          TEXT DEFAULT NULL,
            reset_count INTEGER DEFAULT 0,
            last_reset  TEXT DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            uid          INTEGER PRIMARY KEY,
            name         TEXT,
            username     TEXT,
            key          TEXT DEFAULT NULL,
            ip           TEXT DEFAULT NULL,
            activated_at TEXT DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS admins (
            uid   INTEGER PRIMARY KEY,
            perms TEXT DEFAULT 'reset,check'
        );
        CREATE TABLE IF NOT EXISTS settings (
            k TEXT PRIMARY KEY,
            v TEXT
        );
    """)
    defaults = {
        "proxy_ip":        "2.24.121.175",
        "proxy_port":      "9999",
        "proxy_port2":     "9998",
        "proxy_name":      "FREE FIRE NORMAL",
        "dns_link":        "https://example.com/dns",
        "reset_cooldown":  "3",             # hours
        "welcome_extra":   "",
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings(k,v) VALUES(?,?)", (k, v))
    c.commit(); c.close()

def cfg(k, default=""):
    c = db()
    r = c.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
    c.close()
    return r["v"] if r else default

def set_cfg(k, v):
    c = db()
    c.execute("INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)", (k, v))
    c.commit(); c.close()

# ══════════════════════════════════════════════════════════════
#  PERMISSIONS
# ══════════════════════════════════════════════════════════════
def is_admin(uid):
    if uid == OWNER_ID: return True
    c = db()
    r = c.execute("SELECT 1 FROM admins WHERE uid=?", (uid,)).fetchone()
    c.close()
    return bool(r)

def get_perms(uid):
    if uid == OWNER_ID:
        return {"reset","check","buy","add_admin","del_admin",
                "broadcast","settings","view_users","del_key"}
    c = db()
    r = c.execute("SELECT perms FROM admins WHERE uid=?", (uid,)).fetchone()
    c.close()
    if not r: return set()
    return {p.strip() for p in r["perms"].split(",")}

def has_perm(uid, perm): return perm in get_perms(uid)

# ══════════════════════════════════════════════════════════════
#  VALIDATION  (strict)
# ══════════════════════════════════════════════════════════════
KEY_PATTERN = re.compile(r"^NITRO-[A-Za-z0-9]{5}-[A-Za-z0-9]{5}-[A-Za-z0-9]{5}$")
IP_PATTERN  = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")

def valid_key(k: str) -> bool:
    return bool(KEY_PATTERN.match(k.strip()))

def valid_ip(ip: str) -> bool:
    m = IP_PATTERN.match(ip.strip())
    if not m: return False
    return all(0 <= int(m.group(i)) <= 255 for i in range(1, 5))

def gen_key() -> str:
    chars = string.ascii_uppercase + string.digits
    seg = lambda: "".join(random.choices(chars, k=5))
    return f"NITRO-{seg()}-{seg()}-{seg()}"

def mask_key(key: str) -> str:
    p = key.split("-")
    return f"{p[0]}-{p[1]}-░░░░░-░░░░░"

# ══════════════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════════════
def user_kb(uid=None):
    rows = [
        ["🔑 Check Key",  "📥 Download DNS"],
        ["📡 My Config",  "ℹ️ About"],
    ]
    if uid and is_admin(uid):
        rows.append(["⚙️ Admin Panel"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def admin_kb(uid):
    p, rows = get_perms(uid), []
    r1 = []
    if "buy"     in p: r1.append(InlineKeyboardButton("➕ Add Key",   callback_data="adm_add_key"))
    if "del_key" in p: r1.append(InlineKeyboardButton("🗑 Del Key",   callback_data="adm_del_key"))
    if r1: rows.append(r1)
    r2 = []
    if "reset"   in p: r2.append(InlineKeyboardButton("🔄 Reset Key", callback_data="adm_reset_key"))
    if "check"   in p: r2.append(InlineKeyboardButton("🔍 Check Key", callback_data="adm_check_key"))
    if r2: rows.append(r2)
    if "view_users" in p:
        rows.append([InlineKeyboardButton("👥 Users",     callback_data="adm_users"),
                     InlineKeyboardButton("📊 Stats",     callback_data="adm_stats")])
    if "broadcast" in p:
        rows.append([InlineKeyboardButton("📣 Broadcast", callback_data="adm_broadcast")])
    if uid == OWNER_ID:
        rows.append([InlineKeyboardButton("👮 Admins",    callback_data="adm_admins"),
                     InlineKeyboardButton("⚙️ Settings",  callback_data="adm_settings")])
    rows.append([InlineKeyboardButton("✖️ Close",         callback_data="close")])
    return InlineKeyboardMarkup(rows)

def back_kb(cb):
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data=cb)]])

# ══════════════════════════════════════════════════════════════
#  PROXY CONFIG MESSAGE
# ══════════════════════════════════════════════════════════════
def proxy_msg(name: str) -> str:
    ip    = cfg("proxy_ip")
    port  = cfg("proxy_port")
    port2 = cfg("proxy_port2")
    pname = cfg("proxy_name")
    extra = cfg("welcome_extra")
    msg = (
        f"Hi 👋 *{name}*\n\n"
        f"• *{pname} \\[AIM NECK\\]*\n\n"
        f"• PORT : `{ip}`\n"
        f"• SERVIDOR : `{port}`\n\n"
        f"• *{pname} \\[AIM PEITO\\]*\n\n"
        f"• PORT : `{ip}`\n"
        f"• SERVIDOR : `{port2}`"
    )
    if extra and extra.strip() and extra.strip() != "-":
        msg += f"\n\n{extra.strip()}"
    return msg

# ══════════════════════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    fname = update.effective_user.first_name or "User"
    uname = update.effective_user.username
    # register user
    c = db()
    c.execute("INSERT OR IGNORE INTO users(uid,name,username) VALUES(?,?,?)",
              (uid, fname, uname))
    c.commit(); c.close()
    # clear any pending state
    ctx.user_data.clear()
    await update.message.reply_text(
        f"👋 *Welcome to NITRO ToP Proxy*\n"
        f"{SEP}\n"
        f"Send your key to activate access.\n"
        f"Example: `NITRO-XXXXX-XXXXX-XXXXX`",
        reply_markup=user_kb(uid),
        parse_mode=ParseMode.MARKDOWN
    )

# ══════════════════════════════════════════════════════════════
#  MESSAGE HANDLER
# ══════════════════════════════════════════════════════════════
async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg   = update.message
    uid   = msg.from_user.id
    fname = msg.from_user.first_name or "User"
    text  = msg.text.strip() if msg.text else ""
    action = ctx.user_data.get("action", "")

    # ── Static buttons ──────────────────────────────────────
    if text == "⚙️ Admin Panel":
        if not is_admin(uid): return
        ctx.user_data.clear()
        await msg.reply_text(
            f"🛠 *Admin Panel*\n{SEP}",
            reply_markup=admin_kb(uid),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if text == "🔑 Check Key":
        ctx.user_data.clear()
        ctx.user_data["action"] = "user_check"
        await msg.reply_text(
            f"🔍 *Check Key*\n{SEP}\n📝 Send the key:",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if text == "📥 Download DNS":
        ctx.user_data.clear()
        link = cfg("dns_link")
        await msg.reply_text(
            f"📥 *Download DNS*\n{SEP}\n\n🔗 [Click to Download]({link})",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False
        )
        return

    if text == "📡 My Config":
        ctx.user_data.clear()
        c = db()
        u = c.execute("SELECT key FROM users WHERE uid=?", (uid,)).fetchone()
        c.close()
        if not u or not u["key"]:
            await msg.reply_text("❌ You have no active key yet.")
        else:
            await msg.reply_text(proxy_msg(fname), reply_markup=user_kb(uid), parse_mode=ParseMode.MARKDOWN)
        return

    if text == "ℹ️ About":
        ctx.user_data.clear()
        await msg.reply_text(
            f"*M3SB Proxy Bot*\n{SEP}\n"
            "🔐 Key-based secure access\n"
            "📡 Auto proxy config delivery\n"
            "🌐 IP-locked sessions\n"
            "🛡 Protected with password",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ── Admin input ─────────────────────────────────────────
    if action and is_admin(uid):
        await _admin_input(update, ctx, uid, fname, action, text)
        return

    # ── User: check key ─────────────────────────────────────
    if action == "user_check":
        ctx.user_data.clear()
        key = text.strip()
        if not valid_key(key):
            await msg.reply_text(
                "❌ *Invalid key format.*\nExample: `NITRO-XXXXX-XXXXX-XXXXX`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        c = db()
        k = c.execute("SELECT * FROM keys WHERE key=?", (key,)).fetchone()
        c.close()
        if not k:
            await msg.reply_text("❌ Key not found.")
        else:
            st = "✅ Active" if k["used_by"] else "🟢 Available"
            await msg.reply_text(
                f"🔑 *Key Info*\n{SEP}\n"
                f"Key      : `{k['key']}`\n"
                f"Duration : {k['duration']}\n"
                f"Status   : {st}\n"
                f"IP       : `{k['ip'] or 'N/A'}`",
                parse_mode=ParseMode.MARKDOWN
            )
        return

    # ── Step 2: waiting for IP ───────────────────────────────
    if action == "wait_ip":
        pending_key = ctx.user_data.get("pending_key", "")
        if not pending_key:
            ctx.user_data.clear()
            await msg.reply_text("⚠️ Session expired. Please send your key again.")
            return
        if not valid_ip(text):
            await msg.reply_text(
                "⚠️ *Invalid IP address.*\nExample: `105.74.64.140`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        pending_ip = text.strip()
        # ✅ All good — activate
        ctx.user_data.clear()
        c = db()
        c.execute(
            "UPDATE keys SET used_by=?,used_at=?,ip=? WHERE key=?",
            (uid, datetime.now().isoformat(), pending_ip, pending_key)
        )
        c.execute(
            "UPDATE users SET key=?,ip=?,activated_at=? WHERE uid=?",
            (pending_key, pending_ip, datetime.now().isoformat(), uid)
        )
        c.commit(); c.close()
        # notify owner
        try:
            await ctx.bot.send_message(
                OWNER_ID,
                f"🔔 *New Activation*\n{SEP}\n"
                f"👤 [{fname}](tg://user?id={uid})\n"
                f"🔑 `{pending_key}`\n"
                f"🌐 `{pending_ip}`",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass
        await msg.reply_text(proxy_msg(fname), reply_markup=user_kb(uid), parse_mode=ParseMode.MARKDOWN)
        return

    # ── Step 1: key input ────────────────────────────────────
    key = text.strip()
    if valid_key(key):
        c = db()
        k = c.execute("SELECT * FROM keys WHERE key=?", (key,)).fetchone()
        c.close()
        # key doesn't exist
        if not k:
            await msg.reply_text(
                "📩 *Send your key to get started.*\n"
                "Example: `NITRO-XXXXX-XXXXX-XXXXX`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        # key used by someone else
        if k["used_by"] and k["used_by"] != uid:
            await msg.reply_text(
                "🚫 *This key is already in use.*\nContact support.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        # ✅ key valid — ask for password first
        ctx.user_data["action"]      = "wait_ip"
        ctx.user_data["pending_key"] = key
        await msg.reply_text(
            f"✅ *Key Verified!*\n{SEP}\n"
            f"🔑  Key      : `{key}`\n"
            f"⏱  Duration : {k['duration']}\n\n"
            f"📡 Now send your IP address to activate:",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ── Anything else: invalid key ───────────────────────────
    await msg.reply_text(
        "📩 *Send your key to get started.*\n"
        "Example: `NITRO-XXXXX-XXXXX-XXXXX`",
        parse_mode=ParseMode.MARKDOWN
    )

# ══════════════════════════════════════════════════════════════
#  ADMIN INPUT
# ══════════════════════════════════════════════════════════════
async def _admin_input(update, ctx, uid, fname, action, text):
    msg = update.message

    if action == "adm_add_key":
        parts = text.strip().split(maxsplit=1)
        key = parts[0].strip()
        dur = parts[1].strip() if len(parts) > 1 else "1 Day"
        if not valid_key(key):
            await msg.reply_text(
                "❌ *Invalid key format.*\nExample:\n`NITRO-AAAAA-BBBBB-CCCCC 7 Days`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        c = db()
        existing = c.execute("SELECT 1 FROM keys WHERE key=?", (key,)).fetchone()
        if existing:
            c.close()
            await msg.reply_text("⚠️ This key already exists.")
            return
        c.execute("INSERT INTO keys(key,duration) VALUES(?,?)", (key, dur))
        c.commit(); c.close()
        ctx.user_data.clear()
        await msg.reply_text(
            f"✅ *Key Added!*\n{SEP}\n🔑 `{key}`\n⏱ {dur}",
            parse_mode=ParseMode.MARKDOWN
        )

    elif action == "adm_del_key":
        key = text.strip()
        if not valid_key(key):
            await msg.reply_text(
                "❌ *Invalid key format.*\nExample: `NITRO-AAAAA-BBBBB-CCCCC`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        c = db()
        k = c.execute("SELECT 1 FROM keys WHERE key=?", (key,)).fetchone()
        if not k:
            c.close()
            await msg.reply_text("❌ Key not found.")
            return
        c.execute("UPDATE users SET key=NULL,ip=NULL WHERE key=?", (key,))
        c.execute("DELETE FROM keys WHERE key=?", (key,))
        c.commit(); c.close()
        ctx.user_data.clear()
        await msg.reply_text(f"🗑 Deleted: `{key}`", parse_mode=ParseMode.MARKDOWN)

    elif action == "adm_reset_key":
        key = text.strip()
        if not valid_key(key):
            await msg.reply_text(
                "❌ *Invalid key format.*\nExample: `NITRO-AAAAA-BBBBB-CCCCC`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        c = db()
        k = c.execute("SELECT * FROM keys WHERE key=?", (key,)).fetchone()
        if not k:
            c.close()
            await msg.reply_text("❌ Key not found.")
            return
        cooldown_h = int(cfg("reset_cooldown", "3"))
        now = datetime.now()
        within = False
        if k["last_reset"]:
            diff_h = (now - datetime.fromisoformat(k["last_reset"])).total_seconds() / 3600
            within = diff_h < cooldown_h
        if within and k["reset_count"] >= 3:
            left = round(cooldown_h - diff_h, 1)
            c.close()
            ctx.user_data.clear()
            await msg.reply_text(
                f"⏳ *Max resets reached.*\nWait {left}h before resetting this key again.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        new_count = (k["reset_count"] + 1) if within else 1
        c.execute(
            "UPDATE keys SET used_by=NULL,used_at=NULL,ip=NULL,reset_count=?,last_reset=? WHERE key=?",
            (new_count, now.isoformat(), key)
        )
        c.execute("UPDATE users SET key=NULL,ip=NULL WHERE key=?", (key,))
        c.commit(); c.close()
        ctx.user_data.clear()
        await msg.reply_text(
            f"🔄 *Key Reset!*\n{SEP}\n🔑 `{key}`\n🔢 Resets used: {new_count}/3",
            parse_mode=ParseMode.MARKDOWN
        )

    elif action == "adm_check_key":
        key = text.strip()
        if not valid_key(key):
            await msg.reply_text(
                "❌ *Invalid key format.*\nExample: `NITRO-AAAAA-BBBBB-CCCCC`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        c = db()
        k = c.execute("SELECT * FROM keys WHERE key=?", (key,)).fetchone()
        c.close()
        ctx.user_data.clear()
        if not k:
            await msg.reply_text("❌ Key not found.")
            return
        st = "✅ Active" if k["used_by"] else "🟢 Available"
        await msg.reply_text(
            f"🔍 *Key Details*\n{SEP}\n"
            f"🔑 Key      : `{k['key']}`\n"
            f"⏱ Duration : {k['duration']}\n"
            f"📌 Status   : {st}\n"
            f"🌐 IP       : `{k['ip'] or 'N/A'}`\n"
            f"🔢 Resets   : {k['reset_count']}/3\n"
            f"📅 Used at  : {str(k['used_at'])[:16] if k['used_at'] else 'Never'}",
            parse_mode=ParseMode.MARKDOWN
        )

    elif action == "adm_broadcast":
        c = db()
        users = c.execute("SELECT uid FROM users").fetchall()
        c.close()
        sent = 0
        for u in users:
            try:
                await ctx.bot.send_message(u["uid"], text, parse_mode=ParseMode.MARKDOWN)
                sent += 1
            except Exception:
                pass
        ctx.user_data.clear()
        await msg.reply_text(f"📣 Sent to {sent}/{len(users)} users.")

    elif action == "adm_add_admin":
        try:
            target = int(text.strip())
        except ValueError:
            await msg.reply_text("❌ Send a valid numeric user ID.")
            return
        if target == OWNER_ID:
            await msg.reply_text("⚠️ That's the owner account.")
            return
        ctx.user_data["action"] = f"adm_perm_choice"
        ctx.user_data["adm_target"] = target
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Reset Only",   callback_data=f"perm_set_{target}_reset"),
             InlineKeyboardButton("🔍 Check+Reset",  callback_data=f"perm_set_{target}_check,reset")],
            [InlineKeyboardButton("🛒 +Buy",         callback_data=f"perm_set_{target}_reset,check,buy"),
             InlineKeyboardButton("🔥 Full Access",  callback_data=f"perm_set_{target}_reset,check,buy,broadcast,view_users,del_key")],
            [InlineKeyboardButton("◀️ Cancel",       callback_data="adm_menu")],
        ])
        await msg.reply_text(
            f"👮 *Add Admin* `{target}`\n{SEP}\nChoose permissions:",
            reply_markup=kb, parse_mode=ParseMode.MARKDOWN
        )

    elif action == "adm_del_admin":
        try:
            target = int(text.strip())
        except ValueError:
            await msg.reply_text("❌ Send a valid numeric user ID.")
            return
        if target == OWNER_ID:
            await msg.reply_text("⚠️ Cannot remove the owner.")
            return
        c = db()
        c.execute("DELETE FROM admins WHERE uid=?", (target,))
        c.commit(); c.close()
        ctx.user_data.clear()
        await msg.reply_text(f"✅ Admin `{target}` removed.", parse_mode=ParseMode.MARKDOWN)

    elif action.startswith("adm_setting_"):
        key = action[12:]
        val = text.strip()
        if val == "-":
            val = ""
        set_cfg(key, val)
        ctx.user_data.clear()
        await msg.reply_text(
            f"✅ `{key}` updated to:\n`{val or '(cleared)'}`",
            parse_mode=ParseMode.MARKDOWN
        )

# ══════════════════════════════════════════════════════════════
#  CALLBACK HANDLER
# ══════════════════════════════════════════════════════════════
async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    uid  = q.from_user.id
    data = q.data
    await q.answer()

    if data == "close":
        try: await q.delete_message()
        except Exception: pass
        return

    if not is_admin(uid):
        await q.answer("❌ Access denied.", show_alert=True)
        return

    # ── back to admin menu ──────────────────────────────────
    if data == "adm_menu":
        ctx.user_data.clear()
        await q.edit_message_text(
            f"🛠 *Admin Panel*\n{SEP}",
            reply_markup=admin_kb(uid), parse_mode=ParseMode.MARKDOWN
        )
        return

    # ── add key ─────────────────────────────────────────────
    if data == "adm_add_key":
        if not has_perm(uid, "buy"):
            await q.answer("❌ No permission", show_alert=True); return
        ctx.user_data.clear()
        await q.edit_message_text(
            f"➕ *Add Key*\n{SEP}\nاختار المدة:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎲 1 Day",   callback_data="gen_key_1 Day"),
                 InlineKeyboardButton("🎲 7 Days",  callback_data="gen_key_7 Days")],
                [InlineKeyboardButton("🎲 15 Days", callback_data="gen_key_15 Days"),
                 InlineKeyboardButton("🎲 30 Days", callback_data="gen_key_30 Days")],
                [InlineKeyboardButton("◀️ Back", callback_data="adm_menu")],
            ]),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data.startswith("gen_key_"):
        if not has_perm(uid, "buy"):
            await q.answer("❌ No permission", show_alert=True); return
        dur = data[8:]
        key = gen_key()
        c = db()
        while c.execute("SELECT 1 FROM keys WHERE key=?", (key,)).fetchone():
            key = gen_key()
        c.execute("INSERT INTO keys(key,duration) VALUES(?,?)", (key, dur))
        c.commit(); c.close()
        masked = mask_key(key)
        # رسالة المشتري — مخربشة
        await q.edit_message_text(
            f"🛍️ *PROXY NITRO Top*\n{SEP}\n\n"
            f"• `{masked}`\n\n"
            f"• ⏱ {dur}\n"
            f"• 👤 صالح لشخص واحد فقط",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎲 كود جديد", callback_data="adm_add_key"),
                 InlineKeyboardButton("◀️ Back",     callback_data="adm_menu")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
        # رسالة منفصلة للادمين بالكود الكامل
        await ctx.bot.send_message(
            uid,
            f"🔑 *الكود الكامل:*\n`{key}`\n⏱ {dur}",
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "adm_del_key":
        if not has_perm(uid, "del_key"):
            await q.answer("❌", show_alert=True); return
        ctx.user_data.clear()
        ctx.user_data["action"] = "adm_del_key"
        await q.edit_message_text(
            f"🗑 *Delete Key*\n{SEP}\n📝 Send the key to delete:",
            reply_markup=back_kb("adm_menu"), parse_mode=ParseMode.MARKDOWN
        )

    elif data == "adm_reset_key":
        if not has_perm(uid, "reset"):
            await q.answer("❌", show_alert=True); return
        ctx.user_data.clear()
        ctx.user_data["action"] = "adm_reset_key"
        cd = cfg("reset_cooldown", "3")
        await q.edit_message_text(
            f"🔄 *Reset Key*\n{SEP}\n"
            f"📝 Send the key to reset:\n_Max 3 resets per {cd}h cooldown_",
            reply_markup=back_kb("adm_menu"), parse_mode=ParseMode.MARKDOWN
        )

    elif data == "adm_check_key":
        if not has_perm(uid, "check"):
            await q.answer("❌", show_alert=True); return
        ctx.user_data.clear()
        ctx.user_data["action"] = "adm_check_key"
        await q.edit_message_text(
            f"🔍 *Check Key*\n{SEP}\n📝 Send the key:",
            reply_markup=back_kb("adm_menu"), parse_mode=ParseMode.MARKDOWN
        )

    elif data == "adm_broadcast":
        if not has_perm(uid, "broadcast"):
            await q.answer("❌", show_alert=True); return
        ctx.user_data.clear()
        ctx.user_data["action"] = "adm_broadcast"
        await q.edit_message_text(
            f"📣 *Broadcast*\n{SEP}\n📝 Send your message (Markdown supported):",
            reply_markup=back_kb("adm_menu"), parse_mode=ParseMode.MARKDOWN
        )

    elif data == "adm_stats":
        c = db()
        tk = c.execute("SELECT COUNT(*) FROM keys").fetchone()[0]
        uk = c.execute("SELECT COUNT(*) FROM keys WHERE used_by IS NOT NULL").fetchone()[0]
        tu = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        au = c.execute("SELECT COUNT(*) FROM users WHERE key IS NOT NULL").fetchone()[0]
        ta = c.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
        c.close()
        await q.edit_message_text(
            f"📊 *Statistics*\n{SEP}\n"
            f"👥 Total Users   : {tu}\n"
            f"✅ Active Users  : {au}\n"
            f"🔑 Total Keys    : {tk}\n"
            f"🟢 Free Keys     : {tk - uk}\n"
            f"🔴 Used Keys     : {uk}\n"
            f"👮 Admins        : {ta}",
            reply_markup=back_kb("adm_menu"), parse_mode=ParseMode.MARKDOWN
        )

    elif data == "adm_users":
        if not has_perm(uid, "view_users"):
            await q.answer("❌", show_alert=True); return
        c = db()
        rows = c.execute(
            "SELECT uid,name,username,key,ip FROM users ORDER BY rowid DESC LIMIT 25"
        ).fetchall(); c.close()
        lines = [f"👥 *Users (last 25)*\n{SEP}"]
        for r in rows:
            un = f"@{r['username']}" if r["username"] else str(r["uid"])
            st = "✅" if r["key"] else "⭕"
            lines.append(f"{st} {un}  `{r['ip'] or 'N/A'}`")
        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 Buyers", callback_data="adm_buyers"),
                 InlineKeyboardButton("◀️ Back",   callback_data="adm_menu")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "adm_buyers":
        c = db()
        rows = c.execute(
            "SELECT uid,name,username,key,ip,activated_at FROM users "
            "WHERE key IS NOT NULL ORDER BY activated_at DESC LIMIT 20"
        ).fetchall(); c.close()
        lines = [f"🛒 *Active Buyers*\n{SEP}"]
        for r in rows:
            un = f"@{r['username']}" if r["username"] else str(r["uid"])
            dt = str(r["activated_at"])[:10] if r["activated_at"] else "?"
            lines.append(
                f"• {un}\n  🔑 `{r['key']}`\n  🌐 `{r['ip'] or '?'}`  📅 {dt}"
            )
        await q.edit_message_text(
            "\n".join(lines) if len(lines) > 1 else f"No buyers yet.\n{SEP}",
            reply_markup=back_kb("adm_users"), parse_mode=ParseMode.MARKDOWN
        )

    elif data == "adm_admins":
        if uid != OWNER_ID:
            await q.answer("❌ Owner only", show_alert=True); return
        c = db()
        ads = c.execute("SELECT uid,perms FROM admins").fetchall(); c.close()
        lines = [f"👮 *Admin Management*\n{SEP}\n🔑 Owner: `{OWNER_ID}`\n"]
        rows_kb = []
        for a in ads:
            lines.append(f"• `{a['uid']}` — `{a['perms']}`")
            rows_kb.append([
                InlineKeyboardButton(f"✏️ {a['uid']}", callback_data=f"adm_edit_{a['uid']}"),
                InlineKeyboardButton("🗑 Remove",       callback_data=f"adm_rm_{a['uid']}")
            ])
        rows_kb.append([InlineKeyboardButton("➕ Add Admin",    callback_data="adm_add_admin_start")])
        rows_kb.append([InlineKeyboardButton("◀️ Back",         callback_data="adm_menu")])
        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(rows_kb),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "adm_add_admin_start":
        ctx.user_data.clear()
        ctx.user_data["action"] = "adm_add_admin"
        await q.edit_message_text(
            f"➕ *Add Admin*\n{SEP}\n📝 Send the user ID:",
            reply_markup=back_kb("adm_admins"), parse_mode=ParseMode.MARKDOWN
        )

    elif data.startswith("adm_rm_"):
        target = int(data[7:])
        c = db()
        c.execute("DELETE FROM admins WHERE uid=?", (target,))
        c.commit(); c.close()
        await q.answer(f"✅ Removed {target}")
        # reload list
        c = db(); ads = c.execute("SELECT uid,perms FROM admins").fetchall(); c.close()
        lines = [f"👮 *Admin Management*\n{SEP}\n🔑 Owner: `{OWNER_ID}`\n"]
        rows_kb = []
        for a in ads:
            lines.append(f"• `{a['uid']}` — `{a['perms']}`")
            rows_kb.append([
                InlineKeyboardButton(f"✏️ {a['uid']}", callback_data=f"adm_edit_{a['uid']}"),
                InlineKeyboardButton("🗑 Remove",       callback_data=f"adm_rm_{a['uid']}")
            ])
        rows_kb.append([InlineKeyboardButton("➕ Add Admin", callback_data="adm_add_admin_start")])
        rows_kb.append([InlineKeyboardButton("◀️ Back",      callback_data="adm_menu")])
        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(rows_kb),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data.startswith("adm_edit_"):
        target = int(data[9:])
        c = db()
        r = c.execute("SELECT perms FROM admins WHERE uid=?", (target,)).fetchone(); c.close()
        cur = r["perms"] if r else "none"
        await q.edit_message_text(
            f"✏️ *Edit Admin* `{target}`\n{SEP}\nCurrent: `{cur}`\n\nChoose permissions:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Reset Only",   callback_data=f"perm_set_{target}_reset"),
                 InlineKeyboardButton("🔍 Check+Reset",  callback_data=f"perm_set_{target}_check,reset")],
                [InlineKeyboardButton("🛒 +Buy",         callback_data=f"perm_set_{target}_reset,check,buy"),
                 InlineKeyboardButton("🔥 Full Access",  callback_data=f"perm_set_{target}_reset,check,buy,broadcast,view_users,del_key")],
                [InlineKeyboardButton("◀️ Back",         callback_data="adm_admins")],
            ]),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data.startswith("perm_set_"):
        rest   = data[9:]
        idx    = rest.index("_")
        target = int(rest[:idx])
        perms  = rest[idx + 1:]
        c = db()
        c.execute("INSERT OR REPLACE INTO admins(uid,perms) VALUES(?,?)", (target, perms))
        c.commit(); c.close()
        ctx.user_data.clear()
        await q.answer(f"✅ Set: {perms}")
        c = db(); ads = c.execute("SELECT uid,perms FROM admins").fetchall(); c.close()
        lines = [f"👮 *Admin Management*\n{SEP}\n🔑 Owner: `{OWNER_ID}`\n"]
        rows_kb = []
        for a in ads:
            lines.append(f"• `{a['uid']}` — `{a['perms']}`")
            rows_kb.append([
                InlineKeyboardButton(f"✏️ {a['uid']}", callback_data=f"adm_edit_{a['uid']}"),
                InlineKeyboardButton("🗑 Remove",       callback_data=f"adm_rm_{a['uid']}")
            ])
        rows_kb.append([InlineKeyboardButton("➕ Add Admin", callback_data="adm_add_admin_start")])
        rows_kb.append([InlineKeyboardButton("◀️ Back",      callback_data="adm_menu")])
        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(rows_kb),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "adm_settings":
        if uid != OWNER_ID:
            await q.answer("❌ Owner only", show_alert=True); return
        ip    = cfg("proxy_ip")
        port  = cfg("proxy_port")
        port2 = cfg("proxy_port2")
        pname = cfg("proxy_name")
        dns   = cfg("dns_link")
        cd    = cfg("reset_cooldown", "3")
        await q.edit_message_text(
            f"⚙️ *Settings*\n{SEP}\n"
            f"🌐 Proxy IP    : `{ip}`\n"
            f"🔌 Port 1      : `{port}`\n"
            f"🔌 Port 2      : `{port2}`\n"
            f"🎮 Name        : `{pname}`\n"
            f"📥 DNS Link    : `{dns}`\n"
            f"⏱ Reset CD    : `{cd}h`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🌐 Proxy IP (Owner)",  callback_data="set_proxy_ip"),
                 InlineKeyboardButton(f"🔌 Port 1",        callback_data="set_proxy_port")],
                [InlineKeyboardButton(f"🔌 Port 2",        callback_data="set_proxy_port2"),
                 InlineKeyboardButton(f"🎮 Name",          callback_data="set_proxy_name")],
                [InlineKeyboardButton(f"📥 DNS Link",      callback_data="set_dns_link"),
                 InlineKeyboardButton(f"⏱ Reset CD",      callback_data="set_reset_cooldown")],
                [InlineKeyboardButton("📝 Extra Msg",      callback_data="set_welcome_extra")],
                [InlineKeyboardButton("◀️ Back",           callback_data="adm_menu")],
            ]),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data.startswith("set_"):
        key = data[4:]
        if key == "proxy_ip" and uid != OWNER_ID:
            await q.answer("❌ المالك فقط يقدر يبدل الـ IP", show_alert=True)
            return
        key = data[4:]
        ctx.user_data.clear()
        ctx.user_data["action"] = f"adm_setting_{key}"
        LABELS = {
            "proxy_ip":       "🌐 Enter new Proxy IP",
            "proxy_port":     "🔌 Enter new Port 1",
            "proxy_port2":    "🔌 Enter new Port 2",
            "proxy_name":     "🎮 Enter new Proxy Name",
            "dns_link":       "📥 Enter new DNS download link",
            "reset_cooldown": "⏱ Enter reset cooldown in hours",
            "welcome_extra":  "📝 Enter extra message\n_(send `-` to clear)_",
        }
        lbl = LABELS.get(key, key)
        await q.edit_message_text(
            f"✏️ *Edit Setting*\n{SEP}\n{lbl}:",
            reply_markup=back_kb("adm_settings"),
            parse_mode=ParseMode.MARKDOWN
        )

# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    print("✅ M3SB Proxy Bot running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
