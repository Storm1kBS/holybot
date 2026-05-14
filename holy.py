import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

BOT_TOKEN = "8908809341:AAHkNUtcKsLHsuJbXSuHLekGrnyVBixt0gw"
OWNER_USERNAME = "Wromly"
DB_FILE = "users.db"

logging.basicConfig(level=logging.INFO)


# ── База данных ──────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            user_id  INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            username TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS owner (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            username TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_user(username: str, user_id: int):
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT OR REPLACE INTO users (username, user_id) VALUES (?, ?)",
        (username.lower(), user_id)
    )
    conn.commit()
    conn.close()


def get_user_id(username: str) -> int | None:
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute(
        "SELECT user_id FROM users WHERE username = ?",
        (username.lower(),)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def get_all_users() -> list:
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_owner_id() -> int | None:
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute("SELECT user_id FROM owner WHERE id = 1").fetchone()
    conn.close()
    return row[0] if row else None


def set_owner(user_id: int, username: str):
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT OR REPLACE INTO owner (id, user_id, username) VALUES (1, ?, ?)",
        (user_id, username)
    )
    conn.commit()
    conn.close()


def add_admin(user_id: int, username: str):
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT OR REPLACE INTO admins (user_id, username) VALUES (?, ?)",
        (user_id, username)
    )
    conn.commit()
    conn.close()


def remove_admin(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_admins() -> list:
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("SELECT user_id, username FROM admins").fetchall()
    conn.close()
    return rows


def is_admin(user_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute(
        "SELECT user_id FROM admins WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return row is not None


def is_owner(user_id: int) -> bool:
    return user_id == get_owner_id()


# ── Состояния ────────────────────────────────────────────────

waiting_for_broadcast = set()
waiting_for_add_admin = set()
waiting_for_remove_admin = set()


# ── Клавиатуры ───────────────────────────────────────────────

def main_keyboard(user_id: int):
    buttons = [
        [InlineKeyboardButton("🛠 Тех. поддержка", url="https://t.me/Wromly")]
    ]
    if is_owner(user_id):
        buttons.append([
            InlineKeyboardButton("➕ Добавить админа", callback_data="add_admin"),
            InlineKeyboardButton("➖ Удалить админа", callback_data="remove_admin")
        ])
        buttons.append([
            InlineKeyboardButton("📋 Список админов", callback_data="list_admins")
        ])
    if is_owner(user_id) or is_admin(user_id):
        buttons.append([
            InlineKeyboardButton("📢 Рассылка", callback_data="broadcast")
        ])
    return InlineKeyboardMarkup(buttons)


# ── Хендлеры ─────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username

    if username and username.lower() == OWNER_USERNAME.lower():
        set_owner(user.id, username)

    if username:
        save_user(username, user.id)

    kb = main_keyboard(user.id)
    text = (
        f"👋 Привет, @{username or 'пользователь'}!\n\n"
        "Ты зарегистрирован. Теперь другие могут написать тебе анонимно.\n\n"
        "📨 Чтобы написать кому-то:\n"
        "@username текст сообщения"
    )
    await update.message.reply_text(text, reply_markup=kb)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    if query.data == "broadcast":
        if is_owner(user.id) or is_admin(user.id):
            waiting_for_broadcast.add(user.id)
            await query.message.reply_text("📢 Введи текст рассылки:")

    elif query.data == "add_admin":
        if is_owner(user.id):
            waiting_for_add_admin.add(user.id)
            await query.message.reply_text("➕ Введи @username нового админа:")

    elif query.data == "remove_admin":
        if is_owner(user.id):
            admins = get_admins()
            if not admins:
                await query.message.reply_text("Админов нет.")
                return
            waiting_for_remove_admin.add(user.id)
            text = "➖ Введи @username админа для удаления:\n\n"
            text += "\n".join([f"@{a[1]}" for a in admins if a[1]])
            await query.message.reply_text(text)

    elif query.data == "list_admins":
        if is_owner(user.id):
            admins = get_admins()
            if not admins:
                await query.message.reply_text("Админов нет.")
            else:
                text = "📋 Список админов:\n" + "\n".join([f"@{a[1]}" for a in admins if a[1]])
                await query.message.reply_text(text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    if user.username:
        save_user(user.username, user.id)

    # Рассылка
    if user.id in waiting_for_broadcast:
        waiting_for_broadcast.discard(user.id)
        users = get_all_users()
        success = 0
        for uid in users:
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 Сообщение от администрации:\n\n{text}")
                success += 1
            except:
                pass
        await update.message.reply_text(f"✅ Рассылка отправлена {success} пользователям.")
        return

    # Добавление админа
    if user.id in waiting_for_add_admin:
        waiting_for_add_admin.discard(user.id)
        target = text.lstrip("@").lower()
        target_id = get_user_id(target)
        if not target_id:
            await update.message.reply_text(f"❌ @{target} не найден. Он должен был запустить бота.")
            return
        add_admin(target_id, target)
        await update.message.reply_text(f"✅ @{target} назначен админом.")
        return

    # Удаление админа
    if user.id in waiting_for_remove_admin:
        waiting_for_remove_admin.discard(user.id)
        target = text.lstrip("@").lower()
        target_id = get_user_id(target)
        if not target_id:
            await update.message.reply_text(f"❌ @{target} не найден.")
            return
        remove_admin(target_id)
        await update.message.reply_text(f"✅ @{target} удалён из админов.")
        return

    # Отправка анонимного сообщения
    if not text.startswith("@"):
        kb = main_keyboard(user.id)
        await update.message.reply_text(
            "ℹ️ Формат отправки:\n@username текст\n\nПример: @friend Как дела?",
            reply_markup=kb
        )
        return

    parts = text.split(" ", 1)
    if len(parts) < 2:
        await update.message.reply_text("❌ Укажи текст после @username.")
        return

    target_username = parts[0][1:]
    message_text = parts[1]
    target_id = get_user_id(target_username)

    if not target_id:
        await update.message.reply_text(
            f"❌ @{target_username} не найден.\nОн должен был запустить бота хотя бы раз."
        )
        return

    sender_info = f"👤 От: @{user.username}" if user.username else "👤 От: аноним"

    try:
        if is_owner(target_id) or is_admin(target_id):
            await context.bot.send_message(
                chat_id=target_id,
                text=f"📩 Анонимное сообщение:\n\n{message_text}\n\n{sender_info}"
            )
        else:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"📩 Анонимное сообщение:\n\n{message_text}"
            )
        await update.message.reply_text(f"✅ Сообщение отправлено @{target_username}!")
    except Exception as e:
        await update.message.reply_text("❌ Не удалось доставить. Возможно, пользователь заблокировал бота.")
        logging.error(f"Ошибка: {e}")


# ── Запуск ───────────────────────────────────────────────────

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
