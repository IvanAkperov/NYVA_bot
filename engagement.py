"""
Всё, что делает бота живым участником чата, а не набором команд:
- сам вклинивается в разговор и ставит реакции (редко и по делу)
- квиз дня с очками и таблицей лидеров
- опрос «Кто из нас скорее всего…»
- итоги дня с номинациями
- оживление чата, если все замолчали
- общий гороскоп одним сообщением
- розыгрыш купонов с барабаном 🎰
"""
import asyncio
import json
import logging
import random
import time as time_mod
from collections import Counter
from datetime import date, datetime, timedelta

from aiogram import Bot
from aiogram.types import Message, PollAnswer, ReactionTypeEmoji

import ai
import db
from api import get_horoscope_of_the_day
from config import (ACTIVE_HOURS, ADMIN_ID, USERNAME_ALIASES, CONTEXT_MESSAGES, DRAW_TIME, FEATURES, FRIENDS, GROUP_CHAT_ID,
                    HOROSCOPE_TIME, INTERJECT_CHANCE, INTERJECT_COOLDOWN_MIN, JOB_GRACE_MINUTES,
                    QUIZ_TIME, REACT_CHANCE, REACT_COOLDOWN_MIN, RECAP_MIN_MESSAGES, RECAP_TIME,
                    SILENCE_HOURS, WHO_POLL_TIME)
from coupons import COUPON_TYPES_GIRL, COUPON_TYPES_MAN
from keyboards import after_draw_kb
from mistral import WORLD_CONTEXT

log = logging.getLogger("engagement")

REACTIONS = ["👍", "❤", "🔥", "😁", "🤔", "🤯", "😱", "🎉", "🤩", "🤡", "🥱", "🥴", "😍", "💯", "🤣",
             "🏆", "🤨", "😐", "😈", "😴", "😭", "🤓", "👀", "🙈", "😇", "🤝", "🤗", "🫡", "🗿", "💅",
             "🤪", "😎", "🤷", "😡", "👏", "🙏", "💔", "🍌", "🌚", "❤‍🔥"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
ZODIAC_EMOJI = {"aries": "♈", "taurus": "♉", "gemini": "♊", "cancer": "♋", "leo": "♌", "virgo": "♍",
                "libra": "♎", "scorpio": "♏", "sagittarius": "♐", "capricorn": "♑", "aquarius": "♒", "pisces": "♓"}
QUIZ_TOPICS = ["кино и сериалы", "музыка", "спорт и футбол", "география и путешествия", "история",
               "наука и тело человека", "видеоигры", "книги и фэнтези", "еда и напитки", "искусство",
               "Санкт-Петербург", "интернет-культура и мемы", "английский язык", "животные"]

_engage_lock = asyncio.Lock()


# ================= helpers =================
def friend_name(username: str | None) -> str:
    if not username:
        return "кто-то"
    if username == db.BOT_NAME_IN_LOG:
        return "Бот"
    key = username if username.startswith("@") else f"@{username}"
    key = USERNAME_ALIASES.get(key.lower(), key)
    return FRIENDS.get(key, {}).get("name", username.lstrip("@"))


def knowledge() -> str:
    facts = db.get_all_facts()
    return WORLD_CONTEXT.strip() + (f"\n\nДополнительные факты:\n{facts}" if facts else "")


def transcript(chat_id: int, limit: int = CONTEXT_MESSAGES, exclude_message_id: int | None = None) -> str:
    rows = db.recent_messages(chat_id, limit, exclude_message_id)
    return "\n".join(f"[{sent_at[11:16]}] {friend_name(u)}: {text}" for u, text, sent_at, _ in rows)


def in_active_hours() -> bool:
    return ACTIVE_HOURS[0] <= datetime.now().hour < ACTIVE_HOURS[1]


def is_muted() -> bool:
    return float(db.get_state("muted_until", 0)) > time_mod.time()


def mute(hours: float) -> None:
    db.set_state("muted_until", time_mod.time() + hours * 3600)


def unmute() -> None:
    db.set_state("muted_until", 0)


async def send_logged(bot: Bot, chat_id: int, text: str, **kwargs) -> Message:
    msg = await bot.send_message(chat_id, text, **kwargs)
    db.log_bot_message(chat_id, msg.message_id, bot.id, text)
    return msg


def week_start() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


def leaderboard_text(title: str = "🏆 Квиз-лига недели") -> str:
    rows = db.leaderboard(week_start())
    if not rows:
        return ""
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"{medals[i] if i < 3 else '▫️'} {friend_name(u)} — {p}" for i, (u, _, p) in enumerate(rows)]
    return f"{title}:\n" + "\n".join(lines)


# ================= живой бот: реакции и реплики =================
async def maybe_engage(message: Message, bot: Bot) -> None:
    """Вызывается на каждое обычное сообщение в группе, которое не адресовано боту."""
    if message.chat.id != GROUP_CHAT_ID or is_muted() or _engage_lock.locked():
        return
    now = time_mod.time()
    can_reply = (FEATURES["interjections"] and in_active_hours()
                 and now - float(db.get_state("last_interject_ts", 0)) > INTERJECT_COOLDOWN_MIN * 60
                 and random.random() < INTERJECT_CHANCE)
    if can_reply:
        since = (datetime.now() - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        can_reply = db.count_messages_since(message.chat.id, since) >= 3  # вклиниваемся только в живой разговор
    can_react = (FEATURES["reactions"]
                 and now - float(db.get_state("last_react_ts", 0)) > REACT_COOLDOWN_MIN * 60
                 and random.random() < REACT_CHANCE)
    if not (can_reply or can_react):
        return

    async with _engage_lock:
        allowed = ['"skip"'] + (['"react"'] if can_react else []) + (['"reply"'] if can_reply else [])
        try:
            decision = await ai.chat_json([
                {"role": "system", "content": (
                    knowledge() +
                    "\n\nТы — бот, который сидит в чате этих друзей как ещё один участник. "
                    "Тебе показывают последние сообщения. Реши, стоит ли как-то отреагировать на ПОСЛЕДНЕЕ сообщение.\n"
                    f"Разрешённые действия: {', '.join(allowed)}.\n"
                    "- react: поставить одну эмодзи-реакцию, если сообщение смешное, эмоциональное или достойное\n"
                    "- reply: вклиниться короткой репликой (до 2 предложений) — только если реально есть что сказать "
                    "смешного или в тему; не задавай банальных вопросов, не пересказывай\n"
                    "- skip: если вмешательство будет лишним (это нормальный частый вариант)\n"
                    f"Реакции только из списка: {' '.join(REACTIONS)}\n"
                    'Верни JSON: {"action": "...", "emoji": "...", "text": "..."}'
                )},
                {"role": "user", "content": transcript(message.chat.id, 15)},
            ], temperature=0.9, max_tokens=150)
        except Exception as e:
            log.warning("engage decision failed: %r", e)
            return

        action = decision.get("action")
        if action == "react" and can_react:
            emoji = decision.get("emoji")
            if emoji not in REACTIONS:
                emoji = random.choice(["🔥", "😁", "🤣", "👀", "💯"])
            try:
                await bot.set_message_reaction(message.chat.id, message.message_id,
                                               reaction=[ReactionTypeEmoji(emoji=emoji)])
                db.set_state("last_react_ts", now)
            except Exception as e:
                log.warning("reaction failed: %r", e)
        elif action == "reply" and can_reply and decision.get("text"):
            text = ai.clean(str(decision["text"]))[:600]
            await asyncio.sleep(random.uniform(2, 6))  # как будто человек дочитал и печатает
            sent = await message.reply(text)
            db.log_bot_message(message.chat.id, sent.message_id, bot.id, text)
            db.set_state("last_interject_ts", now)


# ================= оживление тишины =================
async def silence_breaker(bot: Bot) -> None:
    if not FEATURES["silence_breaker"] or is_muted() or not in_active_hours():
        return
    last_human = float(db.get_state("last_human_ts", 0))
    if not last_human:
        db.set_state("last_human_ts", time_mod.time())
        return
    last_starter = float(db.get_state("last_starter_ts", 0))
    now = time_mod.time()
    if now - last_human < SILENCE_HOURS * 3600 or now - last_starter < 24 * 3600:
        return
    db.set_state("last_starter_ts", now)
    usernames = list(FRIENDS)
    target = random.choice(usernames)
    style = random.choice([
        f"задай {friend_name(target)} ({target}) конкретный вопрос по его/её интересам или жизни",
        "предложи всем конкретный план на ближайшие выходные (квиз, зал, бар, кино, прогулка) и спроси, кто за",
        "кинь в чат спорный, но безобидный вопрос-холивар, чтобы все захотели ответить",
        "предложи всем мини-челлендж на сегодня и пообещай очки за выполнение",
        "вспомни что-то из фактов про кого-то и подколи по-доброму, отметив его через @",
    ])
    try:
        text = await ai.chat([
            {"role": "system", "content": knowledge() + (
                "\n\nТы бот в чате этих друзей. В чате давно тишина. Напиши ОДНО короткое сообщение (1–3 предложения), "
                "на которое хочется ответить. Живой разговорный стиль, без канцелярита и без markdown. "
                "Не говори, что чат молчит, если это не смешно.")},
            {"role": "user", "content": f"Сегодня {WEEKDAYS[date.today().weekday()]}. Задача: {style}.\n"
                                        f"Последнее, о чём говорили:\n{transcript(GROUP_CHAT_ID, 8) or 'нет данных'}"},
        ], temperature=1.0, max_tokens=150)
        await send_logged(bot, GROUP_CHAT_ID, ai.clean(text))
    except Exception as e:
        log.warning("silence breaker failed: %r", e)


# ================= квиз дня =================
def _recent_questions(kind: str, limit: int = 30) -> list:
    return [r[0] for r in db.conn.execute(
        "SELECT question FROM polls WHERE kind = ? ORDER BY created_date DESC LIMIT ?", (kind, limit))]


async def send_daily_quiz(bot: Bot) -> None:
    about_us = random.random() < 0.3
    topic = "про кого-то из нашей компании (только по фактам из описания!)" if about_us else random.choice(QUIZ_TOPICS)
    data = await ai.chat_json([
        {"role": "system", "content": (
            "Ты ведущий барного квиза для компании друзей, которые обожают квизы. "
            "Придумай ОДИН интересный вопрос с 4 вариантами ответа. Факт должен быть точным и проверяемым — "
            "если не уверен, выбери другой факт. Сложность — средняя, с изюминкой, неправильные варианты правдоподобные.\n"
            "Ограничения: вопрос до 250 символов, каждый вариант до 90 символов, пояснение до 180 символов.\n"
            'Верни JSON: {"question": "...", "options": ["...", "...", "...", "..."], "correct_index": 0, "explanation": "..."}'
            + ("\n\nОписание компании:\n" + knowledge() if about_us else "")
        )},
        {"role": "user", "content": f"Тема: {topic}. Не повторяй эти вопросы: {_recent_questions('quiz')}"},
    ], temperature=0.9, max_tokens=500)

    options = [str(o).strip()[:100] for o in data["options"]][:4]
    correct_text = options[int(data["correct_index"])]
    if len(set(options)) != 4:
        raise ValueError(f"Плохие варианты: {options}")
    random.shuffle(options)  # ИИ любит ставить правильный ответ первым
    correct = options.index(correct_text)
    question = str(data["question"]).strip()

    msg = await bot.send_poll(
        GROUP_CHAT_ID,
        question=f"🧠 Квиз дня: {question}"[:300],
        options=options,
        type="quiz",
        correct_option_id=correct,
        is_anonymous=False,
        explanation=str(data.get("explanation", ""))[:200] or None,
    )
    db.conn.execute(
        "INSERT INTO polls (poll_id, kind, chat_id, message_id, question, options, correct_option, created_date) "
        "VALUES (?, 'quiz', ?, ?, ?, ?, ?, ?)",
        (msg.poll.id, GROUP_CHAT_ID, msg.message_id, question, json.dumps(options, ensure_ascii=False),
         correct, date.today().isoformat()))
    db.conn.commit()


# ================= «Кто из нас?» =================
async def send_who_poll(bot: Bot) -> None:
    data = await ai.chat_json([
        {"role": "system", "content": knowledge() + (
            "\n\nПридумай ОДИН смешной вопрос для опроса «Кто из нас скорее всего…» для этой компании. "
            "Можно опираться на их привычки и факты, но так, чтобы ответ не был очевиден и все спорили. "
            "Дерзко, но без унижений. До 120 символов. "
            'Верни JSON: {"question": "Кто из нас скорее всего ..."}')},
        {"role": "user", "content": f"Не повторяй: {_recent_questions('who')}"},
    ], temperature=1.05, max_tokens=120)
    question = str(data["question"]).strip()
    options = [f["name"] for f in FRIENDS.values()]
    msg = await bot.send_poll(GROUP_CHAT_ID, question=f"🤔 {question}"[:300], options=options, is_anonymous=False,
                               allows_multiple_answers=True)
    db.conn.execute(
        "INSERT INTO polls (poll_id, kind, chat_id, message_id, question, options, created_date) "
        "VALUES (?, 'who', ?, ?, ?, ?, ?)",
        (msg.poll.id, GROUP_CHAT_ID, msg.message_id, question, json.dumps(options, ensure_ascii=False),
         date.today().isoformat()))
    db.conn.commit()


async def handle_poll_answer(answer: PollAnswer, bot: Bot) -> None:
    row = db.conn.execute("SELECT kind, correct_option, closed FROM polls WHERE poll_id = ?",
                          (answer.poll_id,)).fetchone()
    if not row or row[2] or not answer.user or not answer.option_ids:
        return
    kind, correct, _ = row
    user = answer.user
    username = f"@{user.username}" if user.username else user.first_name
    option = answer.option_ids[0]
    cur = db.conn.execute(
        "INSERT OR IGNORE INTO poll_answers (poll_id, tg_id, username, option, answered_at) VALUES (?, ?, ?, ?, ?)",
        (answer.poll_id, user.id, username, option, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db.conn.commit()
    if kind != "quiz" or cur.rowcount == 0 or option != correct:
        return
    already_right = db.conn.execute(
        "SELECT COUNT(*) FROM poll_answers WHERE poll_id = ? AND option = ? AND tg_id != ?",
        (answer.poll_id, correct, user.id)).fetchone()[0]
    points = 2 if already_right == 0 else 1  # первый правильный — бонус
    db.add_points(user.id, username, points, "quiz")


async def close_open_polls(bot: Bot) -> list:
    lines = []
    rows = db.conn.execute(
        "SELECT poll_id, kind, chat_id, message_id, question, options, correct_option FROM polls WHERE closed = 0"
    ).fetchall()
    for poll_id, kind, chat_id, message_id, question, options_json, correct in rows:
        db.conn.execute("UPDATE polls SET closed = 1 WHERE poll_id = ?", (poll_id,))
        db.conn.commit()
        options = json.loads(options_json)
        try:
            poll = await bot.stop_poll(chat_id, message_id)
        except Exception as e:
            log.warning("stop_poll failed: %r", e)
            poll = None
        if kind == "who":
            votes = [(o.voter_count, o.text) for o in poll.options] if poll else []
            top = max((v for v, _ in votes), default=0)
            if top == 0:
                lines.append(f"🤔 «{question}» — никто не проголосовал. Позор 🙈")
            else:
                winners = " и ".join(t for v, t in votes if v == top)
                lines.append(f"🤔 «{question}»\nНарод решил: {winners} ({top} гол.) 👑")
        elif kind == "quiz":
            right = [friend_name(u) for (u,) in db.conn.execute(
                "SELECT username FROM poll_answers WHERE poll_id = ? AND option = ? ORDER BY answered_at",
                (poll_id, correct))]
            who = ", ".join(right) if right else "никто 💀"
            lines.append(f"🧠 Квиз: правильный ответ — «{options[correct]}». Угадали: {who}")
    return lines


# ================= итоги дня =================
async def send_daily_recap(bot: Bot) -> None:
    today = date.today().isoformat()
    poll_lines = await close_open_polls(bot)
    rows = db.messages_for_day(GROUP_CHAT_ID, today)
    human = [(u, m) for u, m, _ in rows if u != db.BOT_NAME_IN_LOG]

    parts = [f"🌙 Итоги дня · {date.today().strftime('%d.%m')}"]
    if len(human) >= RECAP_MIN_MESSAGES:
        chat_text = "\n".join(f"{friend_name(u)}: {m}" for u, m in human)[-12000:]
        try:
            summary = await ai.chat([
                {"role": "system", "content": knowledge() + (
                    "\n\nТы подводишь итоги дня в чате этих друзей. Формат (без markdown, только эмодзи-заголовки):\n"
                    "📌 О чём болтали — 2–4 коротких пункта\n"
                    "😂 Момент дня — одна цитата или ситуация\n"
                    "🏅 Номинации — 2–3 шуточные номинации конкретным людям по тому, что реально было в переписке\n"
                    "📅 Договорились — только если были планы, иначе пропусти блок\n"
                    "Коротко, смешно, по-дружески. Максимум 900 символов.")},
                {"role": "user", "content": chat_text},
            ], temperature=0.8, max_tokens=600)
            parts.append(ai.clean(summary))
        except Exception as e:
            log.warning("recap summary failed: %r", e)
    if human:
        counts = Counter(friend_name(u) for u, _ in human).most_common()
        parts.append("💬 Болтуны дня: " + " · ".join(f"{n} {c}" for n, c in counts))
    parts.extend(poll_lines)
    board = leaderboard_text()
    if board:
        if date.today().weekday() == 6:
            board = board.replace("Квиз-лига недели", "ФИНАЛ квиз-лиги недели") + "\n\nЧемпиону — уважение и право выбрать фильм/бар 👑"
        parts.append(board)

    if len(parts) > 1:
        await send_logged(bot, GROUP_CHAT_ID, "\n\n".join(parts), disable_notification=True)


# ================= гороскоп одним сообщением =================
ZODIAC_RU = {"aries": "Овен", "taurus": "Телец", "gemini": "Близнецы", "cancer": "Рак", "leo": "Лев",
             "virgo": "Дева", "libra": "Весы", "scorpio": "Скорпион", "sagittarius": "Стрелец",
             "capricorn": "Козерог", "aquarius": "Водолей", "pisces": "Рыбы"}


async def _fetch_horoscope(sign: str, attempts: int = 3) -> str | None:
    """Сайт гороскопов иногда отваливается — пробуем несколько раз с паузой."""
    for i in range(attempts):
        try:
            text = await asyncio.to_thread(get_horoscope_of_the_day, sign)
            if text and len(text) > 50:
                return text[:1500]
        except Exception as e:
            log.warning("horoscope %s attempt %s failed: %r", sign, i + 1, e)
        await asyncio.sleep(2 + 3 * i)
    return None


RUDE_WORDS = ("заткн", "дур", "туп", "идиот", "дебил", "сука", "бля", "хуй", "пизд", "ебан", "урод", "жирн", "отвал")


def _assemble_horoscope(text: str, people: list) -> str:
    """Берём по одной строке на каждого (дубли и болтовню модели выкидываем), недостающих дополняем."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out = []
    for name, sign, src in people:
        line = next((l for l in lines if name.lower() in l.lower() and ":" in l
                     and not any(w in l.lower() for w in RUDE_WORDS)), None)
        if line:
            msg = line.split(":", 1)[1].strip()
        elif src:
            msg = src[:220].rsplit(" ", 1)[0] + "…"
        else:
            msg = "звёзды сегодня молчат — значит, день твой, делай что хочешь 🌚"
        out.append(f"{ZODIAC_EMOJI.get(sign, '✨')} {name}: {msg}")
    return "\n\n".join(out)


async def send_group_horoscope(bot: Bot) -> None:
    rows = db.conn.execute(
        "SELECT username, zodiac FROM users WHERE zodiac IS NOT NULL AND zodiac != ''").fetchall()
    if not rows:
        return
    people = []
    for username, sign in rows:
        people.append((friend_name(username), sign, await _fetch_horoscope(sign)))
        await asyncio.sleep(1)

    names = ", ".join(p[0] for p in people)
    source = "\n\n".join(
        f"{name} — {ZODIAC_RU.get(sign, sign)}:\n{src or '(текста с сайта нет — придумай сам по знаку)'}"
        for name, sign, src in people)
    body = ""
    try:
        text = await ai.chat([
            {"role": "system", "content": knowledge() + (
                f"\n\nНапиши короткий гороскоп на сегодня для КАЖДОГО: {names}. Ровно {len(people)} строк, "
                "по строке на человека, в формате «Имя: текст», 1–2 предложения. "
                "Опирайся на исходный текст гороскопа и обыграй жизнь человека по фактам о нём.\n"
                "Тон: тёплый дружеский юмор и лёгкая ирония, как будто пишет друг. "
                "ЗАПРЕЩЕНО: грубость, оскорбления, приказы вроде «заткнись», мат, подколы про внешность. "
                "Никаких вступлений, пояснений и комментариев — только строки гороскопа. Без markdown.")},
            {"role": "user", "content": source},
        ], temperature=0.8, max_tokens=600)
        body = _assemble_horoscope(ai.clean(text), people)
    except Exception as e:
        log.warning("horoscope AI failed: %r", e)
    if not body:
        body = _assemble_horoscope("", people)
    await send_logged(bot, GROUP_CHAT_ID, f"🔮 Гороскоп на {date.today().strftime('%d.%m')}\n\n{body}",
                      disable_notification=True)


# ================= розыгрыш купонов =================
async def run_daily_draw(bot: Bot) -> None:
    users = db.conn.execute("SELECT username, user_id FROM users").fetchall()
    users = [u for u in users if u[0] in FRIENDS] or users
    if not users:
        return
    winner_username, winner_id = random.choice(users)
    is_man = FRIENDS.get(winner_username, {}).get("gender") == "m"
    coupon = random.choice(COUPON_TYPES_MAN if is_man else COUPON_TYPES_GIRL)
    today = date.today().isoformat()
    try:
        db.conn.execute("INSERT INTO daily_draw (user_id, username, coupon_type, sent_date) VALUES (?, ?, ?, ?)",
                        (winner_id, winner_username, coupon, today))
        db.conn.commit()
    except Exception as e:
        log.warning("draw insert failed: %r", e)
        return

    await bot.send_message(GROUP_CHAT_ID, "🥁 Розыгрыш купона дня! Крутим барабан…")
    await bot.send_dice(GROUP_CHAT_ID, emoji="🎰")
    await asyncio.sleep(3.5)
    text = (f"🎉 Победитель дня: {winner_username} 🔥\n"
            f"Приз: {coupon}\n\n"
            f"Действует 30 дней. Активировать — /get_my_coupons или кнопкой ниже 👇")
    await send_logged(bot, GROUP_CHAT_ID, text, reply_markup=after_draw_kb())


# ================= планировщик =================
JOBS = [
    ("horoscope", HOROSCOPE_TIME, send_group_horoscope),
    ("quiz", QUIZ_TIME, send_daily_quiz),
    ("who_poll", WHO_POLL_TIME, send_who_poll),
    ("draw", DRAW_TIME, run_daily_draw),
    ("recap", RECAP_TIME, send_daily_recap),
]


async def scheduler(bot: Bot) -> None:
    """Один цикл вместо кучи while True. Помнит в БД, что уже запускалось сегодня — рестарт не задублирует."""
    last_silence_check = 0.0
    while True:
        try:
            now = datetime.now()
            today = now.date().isoformat()
            for name, at, job in JOBS:
                if not FEATURES.get(name, True) or db.get_state(f"job_{name}") == today:
                    continue
                run_at = datetime.combine(now.date(), at)
                if run_at <= now < run_at + timedelta(minutes=JOB_GRACE_MINUTES):
                    db.set_state(f"job_{name}", today)
                    try:
                        await job(bot)
                        log.info("job %s done", name)
                    except Exception as e:
                        log.exception("job %s failed", name)
                        try:
                            await bot.send_message(ADMIN_ID, f"❌ Задача {name} упала: {e!r}"[:4000])
                        except Exception:
                            pass
            if time_mod.time() - last_silence_check > 600:
                last_silence_check = time_mod.time()
                await silence_breaker(bot)
        except Exception:
            log.exception("scheduler loop error")
        await asyncio.sleep(30)