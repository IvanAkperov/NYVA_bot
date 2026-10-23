"""
Работа с SQLite: одно соединение на всё приложение + миграции «на лету».
"""
import sqlite3
from datetime import datetime

from config import DB_PATH, FRIENDS

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

BOT_NAME_IN_LOG = "bot"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _add_column(table: str, column: str, ddl: str) -> None:
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, zodiac TEXT);
    CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, role TEXT, content TEXT);
    CREATE TABLE IF NOT EXISTS chatting (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        message TEXT NOT NULL,
        sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, exercise TEXT, weight TEXT, amount TEXT);
    CREATE TABLE IF NOT EXISTS voice (id INTEGER PRIMARY KEY, current_voice TEXT);
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        username TEXT,
        text TEXT NOT NULL,
        remind_time TEXT NOT NULL,
        notified INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS daily_draw (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        coupon_type TEXT NOT NULL,
        coupon_image_id TEXT,
        sent_date DATE NOT NULL,
        used BOOLEAN DEFAULT 0,
        UNIQUE(user_id, sent_date)
    );
    CREATE TABLE IF NOT EXISTS exercise (id INTEGER, user_id INTEGER, exercise_type TEXT, timestamp DATETIME NOT NULL, completed BOOLEAN DEFAULT NULL);
    CREATE TABLE IF NOT EXISTS music (id INTEGER PRIMARY KEY AUTOINCREMENT, genre TEXT, title TEXT, artist TEXT, file_id TEXT);

    -- новое
    CREATE TABLE IF NOT EXISTS polls (
        poll_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,              -- quiz | who
        chat_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        question TEXT NOT NULL,
        options TEXT NOT NULL,           -- JSON-список
        correct_option INTEGER,
        created_date TEXT NOT NULL,
        closed INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS poll_answers (
        poll_id TEXT NOT NULL,
        tg_id INTEGER NOT NULL,
        username TEXT,
        option INTEGER,
        answered_at TEXT,
        PRIMARY KEY (poll_id, tg_id)
    );
    CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER NOT NULL,
        username TEXT,
        points INTEGER NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, value TEXT);
    """)
    _add_column("users", "mode", "TEXT DEFAULT 'normal'")
    _add_column("users", "extra_info", "TEXT")
    _add_column("chatting", "chat_id", "INTEGER")
    _add_column("reminders", "reply_message_id", "INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chatting_chat ON chatting(chat_id, sent_at)")
    if conn.execute("SELECT COUNT(*) FROM voice").fetchone()[0] == 0:
        conn.execute("INSERT INTO voice (id, current_voice) VALUES (1, 'ru-RU-SvetlanaNeural')")
    conn.commit()


# ---------- key-value состояние (кулдауны, последние запуски задач) ----------
def get_state(key: str, default=None):
    row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_state(key: str, value) -> None:
    conn.execute("INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()


# ---------- лог переписки ----------
def log_message(chat_id: int, message_id: int, user_id: int, username: str, text: str) -> None:
    conn.execute(
        "INSERT INTO chatting (message_id, user_id, username, message, sent_at, chat_id) VALUES (?, ?, ?, ?, ?, ?)",
        (message_id, user_id, username or "unknown", text, _now(), chat_id),
    )
    conn.commit()


def log_bot_message(chat_id: int, message_id: int, bot_id: int, text: str) -> None:
    log_message(chat_id, message_id, bot_id, BOT_NAME_IN_LOG, text)


def recent_messages(chat_id: int, limit: int = 20, exclude_message_id: int | None = None):
    rows = conn.execute(
        """SELECT username, message, sent_at, message_id FROM chatting
           WHERE chat_id = ? ORDER BY id DESC LIMIT ?""",
        (chat_id, limit + 1),
    ).fetchall()
    rows = [r for r in rows if r[3] != exclude_message_id][:limit]
    return list(reversed(rows))


def messages_for_day(chat_id: int, day: str):
    return conn.execute(
        """SELECT username, message, sent_at FROM chatting
           WHERE chat_id = ? AND date(sent_at) = ? ORDER BY id""",
        (chat_id, day),
    ).fetchall()


def count_messages_since(chat_id: int, since: str, humans_only: bool = True) -> int:
    sql = "SELECT COUNT(*) FROM chatting WHERE chat_id = ? AND sent_at >= ?"
    if humans_only:
        sql += f" AND username != '{BOT_NAME_IN_LOG}'"
    return conn.execute(sql, (chat_id, since)).fetchone()[0]


# ---------- факты о друзьях ----------
def get_user_row(username: str):
    return conn.execute("SELECT mode, extra_info FROM users WHERE username = ?", (username,)).fetchone()


def get_all_facts() -> str:
    lines = []
    for username, extra in conn.execute("SELECT username, extra_info FROM users"):
        if extra and extra.strip():
            name = FRIENDS.get(username, {}).get("name", username)
            facts = "; ".join(f.strip().rstrip(".") for f in extra.split("\n") if f.strip())
            lines.append(f"{name}: {facts}")
    return "\n".join(lines)


def add_fact(username: str, fact: str) -> None:
    fact = fact.strip()
    if not fact.endswith("."):
        fact += "."
    exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
    if not exists:
        conn.execute("INSERT INTO users (username, extra_info) VALUES (?, ?)", (username, fact))
    else:
        conn.execute(
            """UPDATE users SET extra_info = CASE
                   WHEN extra_info IS NULL OR extra_info = '' THEN ?
                   ELSE extra_info || '\n' || ? END
               WHERE username = ?""",
            (fact, fact, username),
        )
    conn.commit()


# ---------- очки ----------
def add_points(tg_id: int, username: str | None, points: int, reason: str) -> None:
    conn.execute(
        "INSERT INTO scores (tg_id, username, points, reason, created_at) VALUES (?, ?, ?, ?, ?)",
        (tg_id, username, points, reason, _now()),
    )
    conn.commit()


def leaderboard(since: str | None = None):
    sql = "SELECT username, tg_id, SUM(points) AS p FROM scores"
    params = ()
    if since:
        sql += " WHERE created_at >= ?"
        params = (since,)
    sql += " GROUP BY tg_id ORDER BY p DESC"
    return conn.execute(sql, params).fetchall()
