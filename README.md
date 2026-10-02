# 🐺 Blaidd Drwg - Form Filler

*Blaidd Drwg* is Welsh for "Bad Wolf". This is the first project in the **Blaidd Drwg** series.

A Telegram bot that fills out Google Forms for you, using one or more of **your own** Google accounts. You control everything with buttons inside Telegram: save your accounts, define answers once as "rules", then send a form link and press **Start**.

> ⚠️ **Read the [Disclaimer](#-disclaimer) before using this project.**

---

## ✨ Features

- 👤 **Multiple Google accounts**: sign in once per account, the session is saved
- 📝 **Reusable answer rules**: per account, or added to all accounts at once
- 🔘 Supports **text, radio, checkbox and dropdown** questions
- 📄 **Multi-page forms** (Next / Submit are handled automatically)
- 🌍 Detects "already responded" and "form closed" pages in **English and Arabic**
- 🔒 Optional **allow-list** so only your Telegram account can use the bot
- 🖱️ Fully button-driven, no commands to memorize

---

## 🚀 Quick start (Windows, no technical knowledge needed)

### 1. Get a bot token
1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the questions.
3. BotFather replies with a **token** like `123456789:ABCdef...`. Keep it secret.

### 2. Download the project
Click the green **Code** button on GitHub → **Download ZIP** → extract it anywhere (for example your Desktop).

### 3. Install
Double-click **`install.bat`**. It will:
- **install Python automatically** if it is missing (needs an internet connection)
- install everything the bot needs
- ask you to paste your bot token
- ask **who may use the bot**: *only you* (recommended, you enter your Telegram ID from **@userinfobot**) or *everyone*

> If the automatic Python install ever fails, install Python 3.10+ from python.org yourself and tick **"Add python.exe to PATH"**.
> To change the access choice later, delete `allowed_ids.txt` and run `install.bat` again.

### 4. Run
Double-click **`run.bat`**. Keep the window open while you use the bot, close it to stop.

Then open your bot in Telegram and send **/start**.

---

## 📖 How to use the bot

### Step 1: Add an account
**Accounts → ➕ Add account**, then send:
1. a short name (letters/numbers, e.g. `acc1`)
2. the Google email
3. the password (the bot deletes your message immediately and never stores it)

A Chrome window opens **on the computer running the bot** and signs in. If Google asks for 2-step verification, a captcha or "verify it's you", finish it manually in that window (you have 3 minutes).

### Step 2: Add rules
**Rules → pick an account → ➕ Add rule**, then choose:

| Step | What to pick |
|------|--------------|
| Question number | `1` = the first question in the form |
| Question type | Text / Radio / Checkbox / Dropdown |
| Value | see below |

| Type | Value you give |
|------|----------------|
| 🔤 Text | the text to type |
| 🔘 Radio | option number (`1` = first option) |
| ☑️ Checkbox | tick one or more options, then **Done** |
| 🔽 Dropdown | option number (`1` = first real option, not the "Choose" placeholder) |

Tips:
- Question numbers count **only real questions**: titles and descriptions are skipped, and numbering continues across pages.
- The rule type must match the real question type, otherwise the bot tells you which question to fix.
- **➕ Add a rule to ALL accounts** saves time when answers are the same.
- **📋 Copy rules from…** clones the rules of another account.

### Step 3: Fill a form
Paste a Google Form link (`docs.google.com/forms/...` or `forms.gle/...`) in the chat, choose which accounts should fill it, and press **▶️ Start**. You get a result line per account (✅ submitted, ⚠️ already responded / closed, ❌ with the reason).

---

## 🔐 Security notes

- **Never share or commit `token.txt`**. Anyone with it controls your bot. (It is already in `.gitignore`.)
- The **`data/` folder holds saved Google sessions**. Treat it exactly like a password. Never upload it anywhere.
- Passwords are used only to sign in and are **not stored**. Your message with the password is deleted from the chat.
- Prefer **"Only me"** access. If you allow everyone, anyone who finds your bot can use it and make your PC open browsers.
  Access is controlled by `allowed_ids.txt` next to `run.bat`: put Telegram ID(s) separated by commas (e.g. `123456789,987654321`) to restrict it, or the single word `all` to allow everyone. The installer creates this file for you.
- If your token leaks, send `/revoke` to @BotFather and put the new token in `token.txt`.

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---------|-----|
| Python could not be installed automatically | Install Python 3.10+ from python.org, tick **Add to PATH**, then rerun `install.bat` |
| Chrome fails to install | Install Google Chrome normally, or run `install.bat` as administrator |
| "session expired" | Account → **🔑 Re-login** |
| Login times out | Finish 2FA/captcha in the Chrome window within 3 minutes |
| "Q3 is a radio question but your rule says text" | Fix the rule type for that question number |
| "no questions found" | The form may need sign-in, be closed, or use an unsupported layout. A screenshot is saved in `data/` |
| Bot does not answer | Check the `run.bat` window for errors and that your ID is in `allowed_ids.txt` |

## ⚠️ Known limitations

- File upload, date/time, and grid questions are not supported. Linear scales are untested.
- Google can change its page layout at any time, which may break filling until the bot is updated.
- Google may ask for extra verification when signing in from an automated browser.
- The batch scripts are for **Windows**. On macOS/Linux you can run it manually (Python 3.10+):
  ```bash
  python3 -m venv venv && source venv/bin/activate
  pip install -r requirements.txt
  playwright install chrome
  export BOT_TOKEN="123456789:ABC..."
  export ALLOWED_IDS="your_telegram_id"
  python bot.py
  ```

## 📁 Project files

| File | Purpose |
|------|---------|
| `bot.py` | the bot |
| `install.bat` | one-time installer (Windows) |
| `run.bat` | starts the bot (Windows) |
| `requirements.txt` | Python dependencies |
| `token.txt` / `allowed_ids.txt` | created by the installer, **private** |
| `data/` | saved accounts, rules and sessions, **private** |

---

## 🛑 Disclaimer

**Blaidd Drwg - Form Filler is intended for lawful, legitimate use only**, such as saving time on your own repetitive forms, testing forms you own, or filling forms you are entitled to fill with accounts you own or are authorized to use.

It is **NOT** intended for, and must not be used for, any illegal, fraudulent, abusive or rule-violating activity, including but not limited to: submitting false or fake responses, manipulating polls, votes, surveys, giveaways or exams, bypassing one-response limits or other restrictions set by a form's owner, impersonating others, accessing accounts you are not authorized to use, spam, or violating any law, regulation, institutional/employer policy or platform terms.

By using this software you agree that:

- **You alone are responsible** for how you use it and for complying with all applicable laws and the terms of service of Google, Telegram and any form owner or organization involved. Automating sign-in or form submission may violate some of those terms, and accounts may be restricted or suspended as a result.
- You will only use accounts and credentials that belong to you or that you have explicit permission to use.
- The authors and contributors **do not condone misuse and accept no responsibility or liability** for any damage, loss, account suspension, legal consequence or other outcome arising from the use or misuse of this software.
- The software is provided **"as is"**, without warranty of any kind (see the license). It is not affiliated with, endorsed by, or sponsored by Google or Telegram.

If you do not agree, do not use this software.

---

## 📄 License

Released under the [MIT License](LICENSE).

Created by **The Viper**.
