"""
Telegram Google-Form auto-filler: multi-account, fully button-driven.

Setup:
    pip install "python-telegram-bot==21.*" playwright
    playwright install chrome
    set BOT_TOKEN=123:ABC...
    (optional) set ALLOWED_IDS=111111111,222222222     <- only these Telegram IDs can use the bot
    python bot.py

Usage: send /start, then use the buttons. Send any Google Form link to fill it.
"""
import asyncio
import json
import logging
import os
import re
from pathlib import Path

from playwright.async_api import async_playwright
from telegram import (
    InlineKeyboardButton as Btn, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update,
)
from telegram.error import BadRequest
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters,
)

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ["BOT_TOKEN"]
# ALLOWED_IDS: comma-separated Telegram IDs. Leave empty, or use "*" / "all", to allow everyone.
_raw_allowed = os.getenv("ALLOWED_IDS", "").strip().lower()
ALLOWED = set() if _raw_allowed in ("", "*", "all") else {
    int(x) for x in _raw_allowed.split(",") if x.strip().isdigit()}

DATA = Path("data")
(DATA / "sessions").mkdir(parents=True, exist_ok=True)
STORE_FILE = DATA / "store.json"

FORM_URL_RE = re.compile(r"https?://(?:forms\.gle|docs\.google\.com/forms)\S+")
LABEL_RE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
TYPE_NAMES = {"text": "🔤 Text", "radio": "🔘 Radio", "checkbox": "☑️ Checkbox", "dropdown": "🔽 Dropdown"}

# ================================================================ storage
# store = { "<telegram_id>": { "<label>": {"email": "...", "rules": [{"q":1,"type":"text","value":"x"}]} } }
def load_store() -> dict:
    if not STORE_FILE.exists():
        return {}
    try:
        return json.loads(STORE_FILE.read_text(encoding="utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Damaged file: keep a copy for inspection and start clean instead of crashing.
        bad = STORE_FILE.with_name("store.corrupt.json")
        try:
            os.replace(STORE_FILE, bad)
        except OSError:
            pass
        logging.error("store.json was damaged; moved to %s and started a fresh store", bad)
        return {}

def save_store(s: dict) -> None:
    # utf-8 + write to a temp file, then swap: a crash can never leave a half-written store.json
    tmp = STORE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STORE_FILE)

def session_path(uid, label: str) -> Path:
    return DATA / "sessions" / f"{uid}_{label}.json"

def accounts_of(uid) -> dict:
    return load_store().get(str(uid), {})

# ================================================================ Google login / fill
async def google_login(uid: int, label: str, email: str, password: str) -> bool:
    """Opens a visible Chrome window, pre-fills email/password (best effort), then
    waits up to 3 minutes for Google session cookies. If Google asks for 2FA,
    a captcha or "verify it's you", finish it manually in that window."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome", headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        ctx = await browser.new_context(no_viewport=True)
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await ctx.new_page()
        try:
            await page.goto("https://accounts.google.com/signin")
            # Best-effort auto-fill. Any failure here is fine: finish by hand in the window.
            try:
                await page.fill('input[type="email"]', email, timeout=15000)
                await page.click("#identifierNext")
                await page.wait_for_selector('input[type="password"]', state="visible", timeout=20000)
                await page.fill('input[type="password"]', password)
                await page.click("#passwordNext")
            except Exception as e:
                logging.info("auto-fill step skipped (%s): %s", label, e)

            # Success = Google session cookies exist (does not depend on the redirect URL)
            for _ in range(180):
                cookies = await ctx.cookies("https://accounts.google.com")
                names = {c["name"] for c in cookies}
                if names & {"SAPISID", "__Secure-1PSID", "SID"}:
                    await page.wait_for_timeout(2500)  # let all cookies settle
                    await ctx.storage_state(path=str(session_path(uid, label)))
                    return True
                if page.is_closed():
                    break
                await asyncio.sleep(1)
            logging.warning("login timed out/closed (%s). Last URL: %s", label,
                            page.url if not page.is_closed() else "window closed")
            return False
        except Exception as e:
            logging.warning("login failed (%s): %s", label, e)
            return False
        finally:
            await browser.close()

_AR_MARKS = re.compile("[\u064b-\u065f\u0670\u0640]")  # tashkeel + tatweel

def norm_text(t: str) -> str:
    """Lowercase, drop Arabic diacritics, unify alef/yeh/teh-marbuta, collapse spaces."""
    t = _AR_MARKS.sub("", t.lower())
    for src, dst in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه"), ("’", "'")):
        t = t.replace(src, dst)
    return " ".join(t.split())

# Patterns run on norm_text() output (so write Arabic without diacritics, ة as ه, ى as ي).
ALREADY_RE = re.compile(
    r"already responded|only accepts? one response|can.t submit another|only once|"
    r"fill out this form once|"
    r"(اجبت|استجبت|رددت|ارسلت ردا|ارسلت اجابه|سجلت ردا|سجلت اجابه)\s*(علي هذا النموذج\s*)?بالفعل|"
    r"(ملء|تعبئه|املا|ارسال)\s*هذا النموذج\s*(لمره واحده|مره واحده)|مره واحده فقط|"
    r"لا يمكنك (ارسال|تقديم) (ردا|اجابه|رد) اخر|تم الرد علي هذا النموذج")
CLOSED_RE = re.compile(
    r"no longer accepting responses|not accepting responses|is closed for new responses|"
    r"(لم يعد|لا)\s*(هذا النموذج\s*)?يقبل\s*(ال)?(ردود|اجابات|استجابات)|"
    r"تم اغلاق (هذا )?النموذج|النموذج مغلق")
DONE_RE = re.compile(r"recorded|submit another response|تم تسجيل|ارسال رد اخر|ارسال اجابه اخري", re.I)

async def page_text(page) -> str:
    try:
        return norm_text(await page.inner_text("body", timeout=3000))
    except Exception:
        return ""

async def special_page(page) -> str | None:
    """Detects one-response-per-account and closed forms (English + Arabic); None if normal."""
    txt = await page_text(page)
    if ALREADY_RE.search(txt):
        return "⚠️ already responded (form allows one response per account), skipped"
    if CLOSED_RE.search(txt):
        return "⚠️ form is closed (not accepting responses)"
    return None

async def fill_one(browser, uid, label: str, url: str, rules: list[dict]) -> str:
    sp = session_path(uid, label)
    if not sp.exists():
        return "❌ no saved session (log in again)"
    by_q = {r["q"]: r for r in rules}
    ctx = await browser.new_context(storage_state=str(sp))
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        if "accounts.google.com" in page.url:
            return "❌ session expired (log in again)"
        try:
            await page.wait_for_selector('div[role="listitem"]', timeout=20000)
        except Exception:
            special = await special_page(page)
            if special:
                return special
            # Unknown page: save a screenshot and show what the page says, so it can be diagnosed
            try:
                shot = DATA / f"debug_{label}.png"
                await page.screenshot(path=str(shot))
                seen = " ".join((await page.inner_text("body")).split())[:200]
            except Exception:
                seen, shot = "", None
            return (f"❌ no questions found on the page. Page says: \"{seen}\"" +
                    (f" (screenshot: {shot})" if shot else ""))

        counter = 0
        for _ in range(20):
            # Real questions only: visible, top-level, and containing an answer widget
            # (skips title/description blocks, hidden earlier pages, nested list items).
            items = page.locator(
                'div[role="listitem"]:visible:not(div[role="listitem"] *)'
            ).filter(has=page.locator(
                'input:not([type="hidden"]), textarea, [role="radio"], [role="checkbox"], [role="listbox"]'))
            n = await items.count()
            for i in range(n):
                counter += 1
                rule = by_q.get(counter)
                if not rule:
                    continue
                item = items.nth(i)
                t, v = rule["type"], str(rule["value"])
                kind = await item.evaluate(
                    """el => el.querySelector('[role=radio]') ? 'radio'
                        : el.querySelector('[role=checkbox]') ? 'checkbox'
                        : el.querySelector('[role=listbox]') ? 'dropdown' : 'text'""")
                if kind != t:
                    return (f"❌ Q{counter} is a {kind} question but your rule says {t}. "
                            f"Fix the rule type for Q{counter}.")
                try:
                    if t == "text":
                        await item.locator(
                            'textarea, input:not([type="hidden"]):not([role])'
                        ).first.fill(v, timeout=8000)
                    elif t == "radio":
                        await item.locator('div[role="radio"]').nth(int(v) - 1).click(timeout=8000)
                    elif t == "checkbox":
                        for num in v.split(","):
                            await item.locator('div[role="checkbox"]').nth(int(num) - 1).click(timeout=8000)
                    elif t == "dropdown":
                        await item.locator('div[role="listbox"]').click(timeout=8000)
                        await page.wait_for_timeout(400)
                        await item.locator('div[role="option"]').nth(int(v)).click(timeout=8000)
                except Exception as e:
                    return f"❌ Q{counter} ({t}) failed: {str(e).splitlines()[0][:100]}"

            nxt = page.get_by_role("button", name=re.compile(r"^(Next|التالي)$"))
            if await nxt.count():
                await nxt.first.click()
                await page.wait_for_timeout(800)
                continue
            submit = page.get_by_role("button", name=re.compile(r"^(Submit|إرسال)$"))
            if await submit.count():
                await submit.first.click()
                invalid = page.locator('[role="alert"]:visible')
                for _ in range(20):  # wait up to ~10 s for the result
                    await page.wait_for_timeout(500)
                    if "formResponse" in page.url or DONE_RE.search(await page_text(page)):
                        return "✅ submitted"
                    special = await special_page(page)
                    if special:
                        return special
                    if await invalid.count():
                        txt = (await invalid.first.inner_text()).strip().replace("\n", " ")[:80]
                        return f"❌ not submitted: {txt or 'a required/invalid answer'}"
                    if not await submit.count():
                        return "✅ submitted (Submit button gone)"
                return "⚠️ clicked submit, no confirmation after 10s (check this account manually)"
            break
        return "❌ no Submit button found"
    except Exception as e:
        logging.exception("fill failed for %s", label)
        return f"❌ error: {str(e)[:120]}"
    finally:
        await ctx.close()

# ================================================================ UI helpers
def grid(buttons, per_row):
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]

def home_btn():
    return Btn("🏠 Menu", callback_data="m")

def authorized(update: Update) -> bool:
    return not ALLOWED or update.effective_user.id in ALLOWED

async def show(update: Update, text: str, rows):
    """Edit the current message if triggered by a button, otherwise send a new one."""
    markup = InlineKeyboardMarkup(rows)
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=markup)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)

# ================================================================ screens
async def show_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    accs = accounts_of(update.effective_user.id)
    n_rules = sum(len(a["rules"]) for a in accs.values())
    text = (f"📋 Main menu\n\n👤 Accounts: {len(accs)}\n📝 Rules: {n_rules}\n\n"
            "Send a Google Form link anytime to fill it.")
    await show(update, text, [
        [Btn("👤 Accounts", callback_data="acc"), Btn("📝 Rules", callback_data="rules")],
        [Btn("❓ How to use", callback_data="help")],
    ])

async def show_help(update, ctx):
    await show(update,
        "1️⃣ Accounts → Add account (name, email, password). A Chrome window opens to sign in.\n"
        "2️⃣ Rules → pick an account → Add rule (question number, type, value).\n"
        "3️⃣ Paste a Google Form link in the chat, choose the accounts, press Start.\n\n"
        "The form is filled once per selected account.",
        [[home_btn()]])

async def show_accounts(update, ctx):
    accs = accounts_of(update.effective_user.id)
    rows = [[Btn(f"👤 {l} ({a['email']})", callback_data=f"a:{l}")] for l, a in accs.items()]
    rows.append([Btn("➕ Add account", callback_data="adda")])
    rows.append([home_btn()])
    await show(update, "👤 Your accounts:" if accs else "No accounts yet. Add one 👇", rows)

async def show_account(update, ctx, label):
    a = accounts_of(update.effective_user.id).get(label)
    if not a:
        return await show_accounts(update, ctx)
    await show(update, f"👤 {label}\n📧 {a['email']}\n📝 {len(a['rules'])} rules", [
        [Btn("📝 Rules", callback_data=f"rl:{label}"), Btn("🔑 Re-login", callback_data=f"relog:{label}")],
        [Btn("📋 Copy rules from…", callback_data=f"cp:{label}")],
        [Btn("🗑 Remove account", callback_data=f"del:{label}")],
        [Btn("🔙 Back", callback_data="acc")],
    ])

async def show_rules_pick(update, ctx):
    accs = accounts_of(update.effective_user.id)
    if not accs:
        return await show(update, "Add an account first.", [[Btn("➕ Add account", callback_data="adda")], [home_btn()]])
    rows = [[Btn(f"📝 {l} ({len(a['rules'])})", callback_data=f"rl:{l}")] for l, a in accs.items()]
    rows.append([Btn("➕ Add a rule to ALL accounts", callback_data="ar:*")])
    rows.append([home_btn()])
    await show(update, "📝 Whose rules?", rows)

async def show_rule_list(update, ctx, label):
    a = accounts_of(update.effective_user.id).get(label)
    if not a:
        return await show_rules_pick(update, ctx)
    lines = [f"Q{r['q']}: {r['type']} → {r['value']}" for r in a["rules"]]
    text = f"📝 Rules for {label}\n\n" + ("\n".join(lines) if lines else "(no rules yet)")
    rows = grid([Btn(f"🗑 Q{r['q']}", callback_data=f"dr:{label}:{r['q']}") for r in a["rules"]], 4)
    rows.append([Btn("➕ Add rule", callback_data=f"ar:{label}")])
    if a["rules"]:
        rows.append([Btn("🧹 Clear all", callback_data=f"cl:{label}")])
    rows.append([Btn("🔙 Back", callback_data="rules"), home_btn()])
    await show(update, text, rows)

# ----- add-rule wizard
async def ask_q(update, ctx):
    rule = ctx.user_data["rule"]
    who = "ALL accounts" if rule["acc"] == "*" else rule["acc"]
    btns = [Btn(str(i), callback_data=f"q:{i}") for i in range(1, 13)]
    rows = grid(btns, 4) + [[Btn("✏️ Other number", callback_data="qo")], [Btn("❌ Cancel", callback_data="m")]]
    await show(update, f"➕ New rule for {who}\n\nWhich question number?\n(1 = first question in the form)", rows)

async def ask_type(update, ctx):
    rule = ctx.user_data["rule"]
    rows = [[Btn(TYPE_NAMES["text"], callback_data="t:text"), Btn(TYPE_NAMES["radio"], callback_data="t:radio")],
            [Btn(TYPE_NAMES["checkbox"], callback_data="t:checkbox"), Btn(TYPE_NAMES["dropdown"], callback_data="t:dropdown")],
            [Btn("🔙 Back", callback_data=f"ar:{rule['acc']}"), Btn("❌ Cancel", callback_data="m")]]
    await show(update, f"Question {rule['q']}: what type of question is it?", rows)

async def ask_value(update, ctx):
    rule = ctx.user_data["rule"]
    t = rule["type"]
    if t == "text":
        ctx.user_data["await"] = "textval"
        return await show(update, f"Q{rule['q']} (text)\n\nSend the text to fill 👇", [[Btn("❌ Cancel", callback_data="m")]])
    if t in ("radio", "dropdown"):
        btns = [Btn(str(i), callback_data=f"v:{i}") for i in range(1, 11)]
        rows = grid(btns, 5) + [[Btn("✏️ Other number", callback_data="vo")], [Btn("❌ Cancel", callback_data="m")]]
        return await show(update, f"Q{rule['q']} ({t})\n\nWhich option number? (1 = first option)", rows)
    # checkbox: toggle buttons
    sel = rule.setdefault("sel", set())
    btns = [Btn(("✅ " if i in sel else "") + str(i), callback_data=f"c:{i}") for i in range(1, 11)]
    rows = grid(btns, 5) + [[Btn("✔️ Done", callback_data="cd")], [Btn("❌ Cancel", callback_data="m")]]
    chosen = ", ".join(map(str, sorted(sel))) or "none"
    await show(update, f"Q{rule['q']} (checkbox)\n\nTap the options to tick, then Done.\nSelected: {chosen}", rows)

def save_rule(uid, rule: dict, value: str) -> list[str]:
    store = load_store()
    accs = store.get(str(uid), {})
    labels = list(accs) if rule["acc"] == "*" else [rule["acc"]]
    for l in labels:
        if l not in accs:
            continue
        rules = [r for r in accs[l]["rules"] if r["q"] != rule["q"]]
        rules.append({"q": rule["q"], "type": rule["type"], "value": value})
        accs[l]["rules"] = sorted(rules, key=lambda r: r["q"])
    save_store(store)
    return labels

async def after_save(update, ctx, value: str):
    rule = ctx.user_data["rule"]
    labels = save_rule(update.effective_user.id, rule, value)
    q = rule["q"]
    view = "rules" if rule["acc"] == "*" else f"rl:{rule['acc']}"
    rule.pop("sel", None); rule.pop("type", None)
    ctx.user_data.pop("await", None)
    await show(update, f"✅ Saved Q{q} → {value}\nFor: {', '.join(labels)}", [
        [Btn(f"➕ Next question (Q{q + 1})", callback_data=f"q:{q + 1}")],
        [Btn("📋 View rules", callback_data=view), home_btn()],
    ])

# ----- fill selection
async def show_fill_select(update, ctx):
    uid = update.effective_user.id
    accs = {l: a for l, a in accounts_of(uid).items() if a["rules"]}
    sel = ctx.user_data.setdefault("fsel", set(accs))
    rows = [[Btn(("✅ " if l in sel else "⬜ ") + f"{l} ({a['email']})", callback_data=f"go:{l}")]
            for l, a in accs.items()]
    rows.append([Btn(f"▶️ Start ({len(sel & set(accs))})", callback_data="run")])
    rows.append([Btn("❌ Cancel", callback_data="m")])
    await show(update, "📄 Form detected.\nWhich accounts should fill it? (once per account)", rows)

async def run_fill(update, ctx):
    q = update.callback_query
    uid = update.effective_user.id
    url, sel = ctx.user_data.get("link"), ctx.user_data.get("fsel", set())
    accs = {l: a for l, a in accounts_of(uid).items() if l in sel and a["rules"]}
    if not url or not accs:
        return await show_menu(update, ctx)
    ctx.user_data.pop("link", None); ctx.user_data.pop("fsel", None)

    home = InlineKeyboardMarkup([[home_btn()]])
    await q.edit_message_text(f"⏳ Filling with {len(accs)} account(s)…", reply_markup=home)
    results = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome", headless=True)
            try:
                for i, (label, a) in enumerate(accs.items(), 1):
                    try:
                        res = await fill_one(browser, uid, label, url, a["rules"])
                    except Exception as e:
                        res = f"❌ error: {str(e).splitlines()[0][:100]}"
                    results.append(f"{label} ({a['email']}): {res}")
                    await q.edit_message_text(
                        f"⏳ Progress {i}/{len(accs)}\n\n" + "\n".join(results), reply_markup=home)
            finally:
                await browser.close()
        text = "🏁 Done\n\n" + "\n".join(results)
    except Exception as e:
        logging.exception("run_fill crashed")
        text = ("❌ Could not run the browser: " + str(e).splitlines()[0][:150]
                + ("\n\n" + "\n".join(results) if results else ""))
    await q.edit_message_text(text[:4000], reply_markup=home)

# ================================================================ handlers
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await update.message.reply_text("⛔ Not authorized.")
    await update.message.reply_text(
        "👋 Welcome! Use the buttons below.",
        reply_markup=ReplyKeyboardMarkup([["📋 Menu"]], resize_keyboard=True))
    await show_menu(update, ctx)

async def menu_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if authorized(update):
        await show_menu(update, ctx)

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not authorized(update):
        return
    uid = update.effective_user.id
    parts = q.data.split(":")
    cmd, args = parts[0], parts[1:]
    ud = ctx.user_data

    if cmd == "m":
        return await show_menu(update, ctx)
    if cmd == "help":
        return await show_help(update, ctx)
    if cmd == "acc":
        ud.clear(); return await show_accounts(update, ctx)
    if cmd == "a":
        return await show_account(update, ctx, args[0])
    if cmd == "rules":
        ud.clear(); return await show_rules_pick(update, ctx)
    if cmd == "rl":
        ud.clear(); return await show_rule_list(update, ctx, args[0])

    # ---- add / re-login account
    if cmd == "adda":
        ud.clear(); ud["await"] = "label"; ud["draft"] = {}
        return await show(update, "➕ New account\n\nSend a short name for it (letters/numbers, e.g. acc1) 👇",
                          [[Btn("❌ Cancel", callback_data="m")]])
    if cmd == "relog":
        label = args[0]
        ud.clear(); ud["await"] = "password"
        ud["draft"] = {"label": label, "email": accounts_of(uid)[label]["email"]}
        return await show(update, f"🔑 Re-login '{label}'\n\nSend the password. I delete your message right away and don't store it.",
                          [[Btn("❌ Cancel", callback_data="m")]])

    # ---- remove account
    if cmd == "del":
        return await show(update, f"Remove '{args[0]}' and all its rules?", [
            [Btn("✅ Yes, remove", callback_data=f"delok:{args[0]}"), Btn("❌ No", callback_data=f"a:{args[0]}")]])
    if cmd == "delok":
        store = load_store()
        store.get(str(uid), {}).pop(args[0], None)
        save_store(store)
        session_path(uid, args[0]).unlink(missing_ok=True)
        return await show_accounts(update, ctx)

    # ---- copy rules
    if cmd == "cp":
        dst = args[0]
        others = [l for l in accounts_of(uid) if l != dst]
        rows = [[Btn(f"📋 from {l}", callback_data=f"cpto:{l}:{dst}")] for l in others]
        rows.append([Btn("🔙 Back", callback_data=f"a:{dst}")])
        return await show(update, f"Copy rules into '{dst}' (replaces its current rules). From which account?"
                          if others else "You need a second account first.", rows)
    if cmd == "cpto":
        src, dst = args
        store = load_store(); accs = store.get(str(uid), {})
        if src in accs and dst in accs:
            accs[dst]["rules"] = json.loads(json.dumps(accs[src]["rules"]))
            save_store(store)
        return await show_rule_list(update, ctx, dst)

    # ---- delete rule / clear
    if cmd == "dr":
        label, num = args[0], int(args[1])
        store = load_store(); accs = store.get(str(uid), {})
        if label in accs:
            accs[label]["rules"] = [r for r in accs[label]["rules"] if r["q"] != num]
            save_store(store)
        return await show_rule_list(update, ctx, label)
    if cmd == "cl":
        return await show(update, f"Delete ALL rules of '{args[0]}'?", [
            [Btn("✅ Yes", callback_data=f"clok:{args[0]}"), Btn("❌ No", callback_data=f"rl:{args[0]}")]])
    if cmd == "clok":
        store = load_store(); accs = store.get(str(uid), {})
        if args[0] in accs:
            accs[args[0]]["rules"] = []
            save_store(store)
        return await show_rule_list(update, ctx, args[0])

    # ---- add-rule wizard
    if cmd == "ar":
        ud.clear(); ud["rule"] = {"acc": args[0]}
        return await ask_q(update, ctx)
    if cmd in ("q", "qo", "t", "v", "vo", "c", "cd"):
        rule = ud.get("rule")
        if not rule:
            return await show_menu(update, ctx)
        if cmd == "q":
            rule["q"] = int(args[0]); rule.pop("type", None); rule.pop("sel", None)
            return await ask_type(update, ctx)
        if cmd == "qo":
            ud["await"] = "qnum"
            return await show(update, "Send the question number 👇", [[Btn("❌ Cancel", callback_data="m")]])
        if cmd == "t":
            rule["type"] = args[0]
            return await ask_value(update, ctx)
        if cmd == "v":
            return await after_save(update, ctx, args[0])
        if cmd == "vo":
            ud["await"] = "valnum"
            return await show(update, "Send the option number 👇", [[Btn("❌ Cancel", callback_data="m")]])
        if cmd == "c":
            sel = rule.setdefault("sel", set())
            sel.symmetric_difference_update({int(args[0])})
            return await ask_value(update, ctx)
        if cmd == "cd":
            if not rule.get("sel"):
                return await q.answer("Tick at least one option", show_alert=True)
            return await after_save(update, ctx, ",".join(map(str, sorted(rule["sel"]))))

    # ---- fill flow
    if cmd == "go":
        sel = ud.setdefault("fsel", set())
        sel.symmetric_difference_update({args[0]})
        return await show_fill_select(update, ctx)
    if cmd == "run":
        return await run_fill(update, ctx)

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await update.message.reply_text("⛔ Not authorized.")
    text = update.message.text.strip()
    ud = ctx.user_data
    uid = update.effective_user.id

    if text == "📋 Menu":
        return await show_menu(update, ctx)

    aw = ud.get("await")
    cancel = [[Btn("❌ Cancel", callback_data="m")]]

    if aw == "label":
        if not LABEL_RE.match(text):
            return await update.message.reply_text("Use letters/numbers/_/- only (max 20). Try again:")
        ud["draft"] = {"label": text}; ud["await"] = "email"
        return await show(update, f"📧 Send the Google email for '{text}' 👇", cancel)

    if aw == "email":
        if "@" not in text:
            return await update.message.reply_text("That doesn't look like an email. Try again:")
        ud["draft"]["email"] = text; ud["await"] = "password"
        return await show(update, "🔒 Send the password.\nI delete your message right away and don't store it.", cancel)

    if aw == "password":
        try:
            await update.message.delete()
        except Exception:
            pass
        d = ud.pop("draft"); ud.pop("await", None)
        status = await ctx.bot.send_message(
            update.effective_chat.id,
            f"⏳ Signing in '{d['label']}'… A Chrome window will open. If Google asks for 2FA/captcha, finish it in that window (3 min).")
        ok = await google_login(uid, d["label"], d["email"], text)
        if ok:
            store = load_store()
            acc = store.setdefault(str(uid), {}).setdefault(d["label"], {"rules": []})
            acc["email"] = d["email"]
            save_store(store)
            msg = f"✅ '{d['label']}' ({d['email']}) is logged in."
            rows = [[Btn("📝 Add rules", callback_data=f"rl:{d['label']}")], [home_btn()]]
        else:
            msg = "❌ Login failed or timed out. Check the run.bat window for the reason, then try again."
            rows = [[Btn("🔁 Try again", callback_data="adda")], [home_btn()]]
        return await status.edit_text(msg, reply_markup=InlineKeyboardMarkup(rows))

    if aw == "qnum":
        if not text.isdigit() or int(text) < 1:
            return await update.message.reply_text("Send a number (1 or more):")
        ud["rule"]["q"] = int(text); ud.pop("await", None)
        return await ask_type(update, ctx)

    if aw == "textval":
        return await after_save(update, ctx, text)

    if aw == "valnum":
        if not text.isdigit() or int(text) < 1:
            return await update.message.reply_text("Send a number (1 or more):")
        return await after_save(update, ctx, text)

    # no pending input: is it a form link?
    m = FORM_URL_RE.search(text)
    if m:
        accs = {l: a for l, a in accounts_of(uid).items() if a["rules"]}
        if not accs:
            return await show(update, "No account has rules yet.", [[Btn("📝 Add rules", callback_data="rules")], [home_btn()]])
        ud["link"] = m.group(0); ud.pop("fsel", None)
        return await show_fill_select(update, ctx)

    await update.message.reply_text("Use the buttons 👇", reply_markup=InlineKeyboardMarkup([[home_btn()]]))

async def on_error(update, ctx: ContextTypes.DEFAULT_TYPE):
    """Never leave the user with a dead screen: log the error and show the menu button."""
    logging.error("Unhandled error", exc_info=ctx.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await ctx.bot.send_message(
                update.effective_chat.id,
                f"⚠️ Something went wrong: {str(ctx.error)[:150]}",
                reply_markup=InlineKeyboardMarkup([[home_btn()]]))
        except Exception:
            pass

def main():
    app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    app.run_polling()

if __name__ == "__main__":
    main()
