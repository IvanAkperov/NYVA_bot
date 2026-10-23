import asyncio
import base64
import logging
import random
import re
import time
import traceback
from datetime import date, datetime

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (BotCommand, BufferedInputFile, CallbackQuery, InputMediaAudio, Message, PollAnswer,
                           ReactionTypeEmoji)
from aiogram.utils.chat_action import ChatActionSender

import ai
import db
import engagement
from anecdotes import get_random_anectode
from api import (get_horoscope_of_the_day, get_quote_of_the_day, get_random_exercise, get_tracks_by_genre,
                 get_url_meme, get_zodiac, text_to_speech)
from config import BOT_TOKEN, CONTEXT_MESSAGES, FRIENDS, GROUP_CHAT_ID
from help_text import greeting_text
from keyboards import (MODES_LIST, coupons_kb, exercise_kb, meme_kb, meme_kb_ai, mode_kb, music_keyboard,
                       next_and_back_kb, username_kb, voice_kb, zodiac_keyboard)
from memes import make_chat_meme
from mistral import build_system_prompt, send_message_from_mistral_bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")

db.init_db()
conn, cursor = db.conn, db.cursor

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
BOT_USERNAME = ""

RANDOM_POOL = ['normal', 'toxic', 'simp', 'drunk', 'npc', 'mystic', 'edgy_teen', 'gamer',
               'corporate', 'conspiracy', 'zen', 'villain', 'detective', 'chaos']
BOT_CALL_RE = re.compile(r"^\s*бот(?![а-яёa-z])[\s,.:;!?-]*", re.IGNORECASE)


class TrainingRecord(StatesGroup):
    exercise = State()
    weight = State()
    amount = State()


class UserFact(StatesGroup):
    user = State()
    fact = State()


music_dict = {'rock': 'Рок', 'hip': 'Хип Хоп', 'rap': 'Рэп', 'classic': 'Классическая', 'metal': 'Метал', 'edm': 'EDM'}


# ===================== вспомогательное =====================
def call_name(user) -> str:
    """Как обращаться к человеку."""
    if user.username and f"@{user.username}" in FRIENDS:
        return FRIENDS[f"@{user.username}"]["name"]
    return user.first_name or "бро"


def describe(message: Message) -> str | None:
    """Текстовое представление сообщения для лога/контекста."""
    if message.text:
        return message.text
    caption = f" {message.caption}" if message.caption else ""
    if message.photo:
        return f"[фото]{caption}"
    if message.sticker:
        return f"[стикер {message.sticker.emoji or ''}]"
    if message.voice:
        return "[голосовое]"
    if message.video_note:
        return "[кружок]"
    if message.animation:
        return f"[гифка]{caption}"
    if message.video:
        return f"[видео]{caption}"
    if message.audio:
        return f"[трек]{caption}"
    if message.poll:
        return f"[опрос] {message.poll.question}"
    if message.document:
        return f"[файл]{caption}"
    return None


def strip_call(text: str) -> str:
    text = BOT_CALL_RE.sub("", text, count=1)
    if BOT_USERNAME:
        text = re.sub(rf"@{re.escape(BOT_USERNAME)}", "", text, flags=re.IGNORECASE)
    return text.strip()


def is_reply_to_bot(message: Message) -> bool:
    r = message.reply_to_message
    return bool(r and r.from_user and r.from_user.id == bot.id)


def is_addressed(message: Message) -> bool:
    text = message.text or ""
    if text.startswith("/"):
        return False
    if message.chat.type == "private":
        return True
    if BOT_CALL_RE.match(text) or is_reply_to_bot(message):
        return True
    return bool(BOT_USERNAME) and f"@{BOT_USERNAME}".lower() in text.lower()


def photo_addressed(message: Message) -> bool:
    return bool(message.photo) and (
        bool(message.caption and BOT_CALL_RE.match(message.caption)) or is_reply_to_bot(message)
        or message.chat.type == "private")


async def reply_logged(message: Message, text: str, **kwargs) -> Message:
    sent = await message.reply(text, **kwargs)
    db.log_bot_message(message.chat.id, sent.message_id, bot.id, text)
    return sent


def resolve_mode(username_full: str) -> tuple[str, str]:
    row = db.get_user_row(username_full)
    mode = (row[0] if row and row[0] else "normal")
    extra_message = ""
    if mode == "random":
        mode = random.choice(RANDOM_POOL)
        extra_message = f"\n\nОтправлено в режиме {mode}"
    return mode, extra_message


def current_voice() -> str:
    row = cursor.execute("SELECT current_voice FROM voice").fetchone()
    voice = row[0] if row and row[0] else "ru-RU-SvetlanaNeural"
    return voice.replace("voice_", "")


async def send_tts(message: Message, text: str) -> None:
    audio = await text_to_speech(text.replace("*", ""), current_voice())
    voice_file = BufferedInputFile(file=audio.getvalue(), filename="voice.ogg")
    async with ChatActionSender.record_voice(bot=bot, chat_id=message.chat.id):
        await asyncio.sleep(1 + random.uniform(0.4, 1.3))
    await message.answer_voice(voice=voice_file)


def log_error(where: str) -> None:
    with open("errors.txt", "a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] {where}\n{traceback.format_exc()}")


# ===================== лог всей переписки =====================
class ChatLogMiddleware(BaseMiddleware):
    """Пишет в БД все сообщения — так бот понимает контекст, делает итоги дня и мемы про вас."""

    async def __call__(self, handler, event: Message, data):
        try:
            text = describe(event)
            if text and event.from_user and not event.from_user.is_bot:
                db.log_message(event.chat.id, event.message_id, event.from_user.id,
                               event.from_user.username or event.from_user.first_name, text)
                if event.chat.id == GROUP_CHAT_ID:
                    db.set_state("last_human_ts", time.time())
        except Exception:
            log.exception("chat log failed")
        return await handler(event, data)


dp.message.outer_middleware(ChatLogMiddleware())


# ===================== базовые команды =====================
@dp.message(Command('start'))
async def start(message: Message):
    await message.reply('Салют! Напиши команду /help')


@dp.message(Command('help'))
async def help_text(message: Message):
    await message.reply(greeting_text, parse_mode="HTML")


@dp.message(Command('meme'))
async def send_random_meme(message: Message):
    await send_meme(message)


@dp.callback_query(F.data == 'more_meme')
async def more_meme(call: CallbackQuery):
    await call.answer("Ща нарисую…")
    await send_meme(call.message)


async def send_meme(message: Message):
    async with ChatActionSender.upload_photo(bot=bot, chat_id=message.chat.id):
        meme = await make_chat_meme(engagement.transcript(message.chat.id, 25), engagement.knowledge())
    if meme:
        await message.answer_photo(BufferedInputFile(meme, filename="meme.jpg"), reply_markup=meme_kb_ai())
        return
    url = await asyncio.to_thread(get_url_meme)
    if url:
        await message.answer_photo(photo=url, reply_markup=meme_kb)
    else:
        await message.answer('Мема не нашлось :(')


@dp.callback_query(F.data.startswith('zodiac_'))
async def reply_horoscope(call: CallbackQuery):
    await call.answer()
    sign = call.data.replace('zodiac_', '')
    try:
        text = await asyncio.to_thread(get_horoscope_of_the_day, sign)
    except Exception:
        text = "Звёзды сегодня молчат 🌚"
    await call.message.reply(f"Гороскоп на {date.today():%d.%m.%Y}\n\n{text}")


@dp.message(Command('quote_of_the_day'))
async def send_random_quote(message: Message):
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        quote = await asyncio.to_thread(get_quote_of_the_day)
    await message.reply(quote)


@dp.message(Command('horoscope'))
async def process_horoscope(message: Message):
    await message.reply('Выберите знак', reply_markup=zodiac_keyboard())


@dp.message(Command('get_my_horoscope'))
async def send_user_horoscope(message: Message):
    username = f"@{message.from_user.username}"
    sign = get_zodiac(username, cursor)
    if not sign:
        await message.reply("Не знаю твой знак зодиака 🤷 Выбери вручную: /horoscope")
        return
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        text = await asyncio.to_thread(get_horoscope_of_the_day, sign)
    await message.reply(f"Гороскоп на {date.today():%d.%m.%Y}\n\n{text}")


# ===================== музыка =====================
@dp.message(Command('music'))
async def process_music(message: Message):
    await message.reply("Выбери жанр музыки", reply_markup=music_keyboard())


@dp.callback_query(F.data.startswith("genre_"))
async def send_audio(call: CallbackQuery):
    genre = call.data.replace("genre_", '')
    tracks = get_tracks_by_genre(genre, cursor)
    if not tracks:
        await call.message.answer("❌ В базе нет треков")
        await call.answer()
        return
    artist, title, file_id = tracks[0]
    await call.message.reply_audio(audio=file_id, caption=f"🎧 {artist} — {title}",
                                   reply_markup=next_and_back_kb(genre, 0, len(tracks)))
    await call.answer()


@dp.callback_query(F.data.startswith(("forward_", "back_")))
async def navigate_tracks(call: CallbackQuery):
    _, genre, idx = call.data.split("_")
    idx = int(idx)
    tracks = get_tracks_by_genre(genre, cursor)
    if not tracks:
        await call.answer("Треков нет")
        return
    idx %= len(tracks)
    artist, title, file_id = tracks[idx]
    await call.message.edit_media(media=InputMediaAudio(media=file_id, caption=f"🎧 {artist} — {title}"),
                                  reply_markup=next_and_back_kb(genre, idx, len(tracks)))
    await call.answer()


@dp.callback_query(F.data == "counter")
async def counter_click(call: CallbackQuery):
    await call.answer()


# ===================== напоминания =====================
def save_reminder(chat_id: int, username: str | None, text: str, when: datetime) -> None:
    cursor.execute(
        "INSERT INTO reminders (user_id, username, text, remind_time, notified) VALUES (?, ?, ?, ?, 0)",
        (chat_id, username, text, when.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()


@dp.message(Command("remind"))
async def remind_me(message: Message):
    """/remind YYYY-MM-DD HH:MM Текст напоминания"""
    try:
        _, date_part, time_part, remind_text = message.text.split(maxsplit=3)
        remind_time = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M")
        save_reminder(message.chat.id, message.from_user.username, remind_text, remind_time)
        await message.reply(f"✅ Напоминание установлено на {remind_time:%d.%m %H:%M}\n📌 Жди уведомления ❤️\n\n"
                            f"Кстати, можно проще: «бот напомни завтра в 9 позвонить маме»")
    except Exception:
        await message.reply("❌ Ошибка!\nФормат:\n/remind YYYY-MM-DD HH:MM Текст напоминания\n\n"
                            "Или просто: «бот напомни в пятницу в 19 купить билеты»")


async def reminder_checker(bot: Bot):
    while True:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = conn.execute(
                "SELECT id, user_id, username, text FROM reminders WHERE notified = 0 AND remind_time <= ?",
                (now,)).fetchall()
            for reminder_id, chat_id, username, text in rows:
                who = f"@{username}, " if username else ""
                try:
                    await bot.send_message(chat_id=chat_id, text=f"⏰ {who}напоминаю:\n{text}")
                except Exception as e:
                    log.warning("reminder %s failed: %r", reminder_id, e)
                conn.execute("UPDATE reminders SET notified = 1 WHERE id = ?", (reminder_id,))
                conn.commit()
        except Exception:
            log.exception("reminder_checker")
        await asyncio.sleep(10)


# ===================== упражнения =====================
@dp.message(Command('exercise'))
async def send_gif(message: Message):
    exercise, gif = get_random_exercise()
    cursor.execute("INSERT INTO exercise (user_id, exercise_type, timestamp) VALUES (?, ?, ?)",
                   (message.chat.id, exercise, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    if exercise != 'Планка':
        await message.reply_animation(animation=gif, caption=f"Давай ка, сделай {exercise} {random.randint(1, 30)} раз.")
    else:
        await message.reply_animation(animation=gif, caption="Осилишь планку 5 минут?")
    asyncio.create_task(ask_exercise_done(message.chat.id, exercise))


async def ask_exercise_done(chat_id: int, exercise: str):
    await asyncio.sleep(300)
    await bot.send_message(chat_id, f"Сделал ли ты упражнение: {exercise}?", reply_markup=exercise_kb(exercise))


@dp.callback_query(F.data.startswith("done_"))
async def handle_done(callback: CallbackQuery):
    answer, exercise = callback.data.split(":")
    if answer == "done_yes":
        await callback.message.edit_text(f"Молодец! Упражнение {exercise} выполнено 💪")
    else:
        await callback.message.edit_text(f"Жаль 😔 Упражнение {exercise} не выполнено")
    await callback.answer()


# ===================== купоны =====================
def active_coupons(username: str):
    return cursor.execute(
        """SELECT id, coupon_type FROM daily_draw
           WHERE used = 0 AND username = ? AND sent_date >= date('now', 'localtime', '-30 day')
           ORDER BY sent_date""", (username,)).fetchall()


async def show_coupons(target: Message, user) -> None:
    username = f"@{user.username}"
    coupons = active_coupons(username)
    if not coupons:
        await target.answer(f"{call_name(user)}, купонов нет 🥲 Жди розыгрыш в 21:00")
        return
    lines = "\n".join(f"{i}. {c}" for i, (_, c) in enumerate(coupons, 1))
    await target.answer(f"🎟 {call_name(user)}, твои купоны:\n\n{lines}", reply_markup=coupons_kb(coupons))


@dp.message(Command('get_my_coupons'))
async def get_my_coupons(message: Message):
    await show_coupons(message, message.from_user)


@dp.callback_query(F.data == "my_coupons")
async def my_coupons_button(call: CallbackQuery):
    await call.answer()
    await show_coupons(call.message, call.from_user)


@dp.callback_query(F.data.startswith("coupon_use:"))
async def use_coupon(call: CallbackQuery):
    coupon_id = int(call.data.split(":")[1])
    row = cursor.execute("SELECT username, coupon_type, used FROM daily_draw WHERE id = ?", (coupon_id,)).fetchone()
    if not row:
        await call.answer("Купон не найден", show_alert=True)
        return
    owner, coupon, used = row
    if owner != f"@{call.from_user.username}":
        await call.answer("Это не твой купон 😏", show_alert=True)
        return
    if used:
        await call.answer("Уже использован")
        return
    cursor.execute("UPDATE daily_draw SET used = 1 WHERE id = ?", (coupon_id,))
    conn.commit()
    await call.answer("Купон активирован! 🎉")
    partner = FRIENDS.get(owner, {}).get("partner", "")
    text = f"🎟 {call_name(call.from_user)} активирует купон!\n\n{coupon}\n\n{partner + ', ' if partner else ''}это тебе. Отмазки не принимаются 😏"
    await engagement.send_logged(bot, GROUP_CHAT_ID, text)
    try:
        await call.message.delete()
    except Exception:
        pass


# ===================== служебное =====================
@dp.message(Command('getid'))
async def get_chat_id(message: Message):
    chat = message.chat
    await message.reply(f"📊 Тип: {chat.type}\nID: {chat.id}\nНазвание: {chat.title or 'ЛС'}")


@dp.message(Command('lk'))
async def send_message_from_lk(message: Message):
    text = message.text.replace('/lk', '', 1).strip()
    if text:
        await engagement.send_logged(bot, GROUP_CHAT_ID, text)


@dp.message(Command('mode'))
async def change_mode(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Выбери, каким мне быть с тобой:", reply_markup=mode_kb())
        return
    await apply_mode(message, message.from_user, parts[1].strip().lower())


@dp.callback_query(F.data.startswith("setmode_"))
async def mode_button(call: CallbackQuery):
    await call.answer()
    await apply_mode(call.message, call.from_user, call.data.replace("setmode_", ""))


async def apply_mode(target: Message, user, mode: str):
    if mode not in MODES_LIST:
        await target.answer(f"{call_name(user)}, такого режима у меня нет. Жми /mode")
        return
    username = f"@{user.username}"
    if not cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        cursor.execute("INSERT INTO users (username, mode) VALUES (?, ?)", (username, mode))
    else:
        cursor.execute("UPDATE users SET mode = ? WHERE username = ?", (mode, username))
    conn.commit()
    await target.answer(f"{call_name(user)}, твой режим — {mode}. {'Наслаждайся!' if mode != 'random' else 'Тебе пиздец'}")


@dp.message(Command('voice'))
async def select_voice(message: Message):
    await message.answer("Выберите озвучку", reply_markup=voice_kb())


@dp.callback_query(F.data.startswith('voice_'))
async def change_voice(call: CallbackQuery):
    voice = call.data.replace("voice_", '')
    cursor.execute("UPDATE voice SET current_voice = ? WHERE id = ?", (voice, 1))
    conn.commit()
    await call.message.answer(f"Выбрана озвучка {voice}")
    await call.answer()
    await call.message.delete()


@dp.callback_query(F.data == 'delete')
async def delete_bot_message(call: CallbackQuery):
    await call.message.edit_text('Сообщение удалено.')
    await call.answer()


# ===================== новое: игры, итоги, тишина =====================
@dp.message(Command("top"))
async def top(message: Message):
    week = engagement.leaderboard_text()
    total = db.leaderboard()
    all_time = "\n".join(f"{engagement.friend_name(u)} — {p}" for u, _, p in total)
    text = (week or "На этой неделе очков пока нет — квиз дня в 12:30 🧠")
    if all_time:
        text += f"\n\n📜 За всё время:\n{all_time}"
    await message.reply(text)


@dp.message(Command("quiz"))
async def quiz_now(message: Message):
    try:
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            await engagement.send_daily_quiz(bot)
    except Exception:
        log_error("quiz")
        await message.reply("Ведущий квиза подавился вопросом, попробуй ещё раз")


@dp.message(Command("who"))
async def who_now(message: Message):
    try:
        await engagement.send_who_poll(bot)
    except Exception:
        log_error("who")
        await message.reply("Не придумал вопрос, попробуй ещё раз")


@dp.message(Command("recap"))
async def recap_now(message: Message):
    await engagement.send_daily_recap(bot)


@dp.message(Command("mute"))
async def mute_cmd(message: Message):
    engagement.mute(3)
    await message.reply("Ок, 3 часа сам не влезаю в разговор 🤐 На «бот …» всё равно отвечу. /unmute — вернуть")


@dp.message(Command("unmute"))
async def unmute_cmd(message: Message):
    engagement.unmute()
    await message.reply("Я вернулся 😈")


@dp.message(Command("summary"))
async def summary(message: Message):
    rows = db.messages_for_day(message.chat.id, date.today().isoformat())
    history = "\n".join(f"{engagement.friend_name(u)}: {m}" for u, m, _ in rows if u != db.BOT_NAME_IN_LOG)
    if not history:
        await message.reply("Сегодня тут было тихо, пересказывать нечего 🦗")
        return
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        answer = await ai.chat([
            {"role": "system", "content": "Сделай краткую сводку переписки друзей за день: основные темы, важные события, "
                                          "смешные моменты, планы и договорённости. Коротко, по-дружески, без markdown."},
            {"role": "user", "content": history[-12000:]},
        ], max_tokens=700, temperature=0.6)
    await reply_logged(message, ai.clean(answer))


@router.poll_answer()
async def on_poll_answer(poll_answer: PollAnswer):
    try:
        await engagement.handle_poll_answer(poll_answer, bot)
    except Exception:
        log.exception("poll answer")


# ===================== FSM: факты и рекорды =====================
@router.message(Command("cancel", "отмена", "стоп"), StateFilter("*"))
async def cancel_handler(message: Message, state: FSMContext):
    if await state.get_state() is None:
        await message.answer("Нет активного состояния для отмены")
        return
    await state.clear()
    await message.answer("Похуй, потом запишем тогда")


@router.message(Command('fact'))
async def create_fact(message: Message, state: FSMContext):
    await state.set_state(UserFact.user)
    await message.reply("Запишем новый факт. О ком записываем инфу?", reply_markup=username_kb())


@router.callback_query(F.data.startswith('user_'), UserFact.user)
async def process_user(call: CallbackQuery, state: FSMContext):
    data = call.data.replace("user_", '')
    await state.update_data(user=data)
    await state.set_state(UserFact.fact)
    await call.message.answer(f"Выбран пользователь: {engagement.friend_name(data)}\nКакой факт запишем?")
    await call.answer()
    await call.message.delete()


@router.message(UserFact.fact)
async def process_fact(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    db.add_fact(data['user'], message.text or "")
    await message.answer(f"Добавил факт — {engagement.friend_name(data['user'])}: {message.text}")


@router.message(Command('record'))
async def create_record(message: Message, state: FSMContext):
    await state.set_state(TrainingRecord.exercise)
    await message.reply('Новый рекорд? Отлично! Напиши упражнение (или /cancel)')


@router.message(TrainingRecord.exercise)
async def process_exercise(message: Message, state: FSMContext) -> None:
    await state.update_data(exercise=message.text)
    await state.set_state(TrainingRecord.weight)
    await message.answer("Какой был вес в кг?")


@router.message(TrainingRecord.weight)
async def process_weight(message: Message, state: FSMContext) -> None:
    await state.update_data(weight=message.text)
    await state.set_state(TrainingRecord.amount)
    await message.answer("Сколько повторений?")


@router.message(TrainingRecord.amount)
async def process_amount(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    username = f"@{message.from_user.username}"
    cursor.execute("INSERT INTO records (username, exercise, weight, amount) VALUES (?, ?, ?, ?)",
                   (username, data['exercise'], data['weight'], message.text))
    conn.commit()
    await message.answer(f"Добавил в базу твой рекорд — {data['exercise']} {data['weight']}x{message.text} 💪")
    if message.chat.id != GROUP_CHAT_ID:
        await engagement.send_logged(
            bot, GROUP_CHAT_ID, f"🏋️ {call_name(message.from_user)} поставил(а) рекорд: {data['exercise']} {data['weight']}×{message.text}")


@dp.message(Command('get_my_records'))
async def get_my_records(message: Message):
    username = f"@{message.from_user.username}"
    rows = cursor.execute("SELECT exercise, weight, amount FROM records WHERE username = ?", (username,)).fetchall()
    if not rows:
        await message.reply("Рекордов пока нет. Записать: /record")
        return
    await message.reply("Твои рекорды:\n\n" + "\n".join(f"• {e}: {w} кг × {a}" for e, w, a in rows))


# ===================== фото: реальный разбор нейросетью =====================
FALLBACK_PHOTO_REACTIONS = [
    "Неожиданно… но выглядит кайфово 🔥", "Есть вайб, не буду врать", "Ну слушай… красиво, чё",
    "Я посмотрел. Осмысливаю 🤔", "Средненько. Ни туда ни сюда", "Это должно было остаться в галерее",
    "Чё-то я не понял, но выглядит стрёмно 😐", "Ну вот зачем",
]


@router.message(F.photo, F.func(photo_addressed))
async def handle_photo_analysis(message: Message):
    username = message.from_user.username or ""
    question = strip_call(message.caption or "") or "оцени фото"
    try:
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            file = await bot.get_file(message.photo[-1].file_id)
            data = await bot.download_file(file.file_path)
            b64 = base64.b64encode(data.read()).decode()
            mode, extra = resolve_mode(f"@{username}")
            system = build_system_prompt(username, mode, db.get_all_facts(),
                                         engagement.transcript(message.chat.id, 10, message.message_id))
            system += ("\n\nК сообщению приложено фото — внимательно посмотри на него и ответь именно про то, что на нём. "
                       "Если просят оценить — дай честную смешную оценку и поставь балл X/10. 2–4 предложения.")
            answer = await ai.vision(system, question, b64)
        await reply_logged(message, ai.clean(answer) + extra)
    except Exception:
        log_error("photo")
        await message.reply(random.choice(FALLBACK_PHOTO_REACTIONS))


# ===================== разговор с ботом =====================
MUTE_RE = re.compile(r"^(заткнись|помолчи|молчи|отстань|не влезай|тихо)", re.IGNORECASE)


def fact_subject(fact: str, author_username: str) -> str:
    words = re.findall(r"[а-яёa-z]+", fact.lower())
    for word in words:
        for username, info in FRIENDS.items():
            if word in info["forms"]:
                return username
    return author_username


async def parse_reminder(text: str) -> tuple[datetime, str] | None:
    now = datetime.now()
    data = await ai.chat_json([
        {"role": "system", "content": (
            f"Сейчас {now:%Y-%m-%d %H:%M}, {engagement.WEEKDAYS[now.weekday()]}. Извлеки из просьбы напоминание. "
            "Если время не указано: утром=09:00, днём=13:00, вечером=19:00, иначе 10:00. "
            'Верни JSON {"datetime": "YYYY-MM-DD HH:MM", "text": "что напомнить, коротко"}; '
            'если понять нельзя — {"datetime": null}')},
        {"role": "user", "content": text},
    ], temperature=0, max_tokens=120)
    if not data.get("datetime"):
        return None
    when = datetime.strptime(data["datetime"], "%Y-%m-%d %H:%M")
    return (when, data.get("text") or text) if when > now else None


@router.message(F.text, F.func(is_addressed))
async def handle_interactive(message: Message):
    try:
        text = strip_call(message.text)
        user = message.from_user
        username = user.username or ""
        username_full = f"@{username}"
        low = text.lower()

        if not text:
            await reply_logged(message, random.choice(["чё?", "ну?", "я тут", "слушаю 👀"]))
            return

        if MUTE_RE.match(low):
            engagement.mute(3)
            await message.reply("Ладно-ладно, 3 часа сам не влезаю 🤐 (/unmute — вернуть)")
            return

        if low.startswith("запомни"):
            fact = re.sub(r"^запомни[\s,:]*(что\s+)?", "", text, flags=re.IGNORECASE).strip()
            if not fact:
                await message.reply("Что запомнить-то?")
                return
            subject = fact_subject(fact, username_full)
            db.add_fact(subject, fact)
            await message.reply(f"🧠 Запомнил ({engagement.friend_name(subject)}): {fact}")
            return

        if low.startswith("напомни"):
            parsed = await parse_reminder(text)
            if not parsed:
                await message.reply("Не понял, когда напомнить 🤔 Скажи, например: «бот напомни завтра в 9 позвонить маме»")
                return
            when, what = parsed
            save_reminder(message.chat.id, username or None, what, when)
            await message.reply(f"✅ Напомню {when:%d.%m в %H:%M}: {what}")
            return

        mode, extra_message = resolve_mode(username_full)
        if mode == 'toxic' and random.random() < 0.8:
            try:
                await bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id,
                                               reaction=[ReactionTypeEmoji(emoji="🤡")], is_big=True)
            except Exception as e:
                log.warning("clown reaction: %r", e)

        if 'анекдот' in low:
            await send_tts(message, get_random_anectode())
            return

        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            response_text = await send_message_from_mistral_bot(
                text=text,
                username=username,
                mode=mode,
                extra_info=db.get_all_facts(),
                chat_context=engagement.transcript(message.chat.id, CONTEXT_MESSAGES, message.message_id),
            )

        if 'аудио' in low or 'голосом' in low or 'голосовое' in low:
            db.log_bot_message(message.chat.id, 0, bot.id, response_text)
            await send_tts(message, response_text)
        else:
            await reply_logged(message, f"{response_text}{extra_message}")

    except Exception:
        log_error("interactive")
        await message.reply("Соединение прервано, попробуй еще раз, либо пиздуй баги исправлять")


# ===================== всё остальное в группе: бот «слушает» =====================
@router.message(F.chat.id == GROUP_CHAT_ID)
async def group_listener(message: Message):
    if message.text and message.text.startswith("/"):
        return
    try:
        await engagement.maybe_engage(message, bot)
    except Exception:
        log.exception("maybe_engage")


dp.include_router(router)


async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="help", description="что я умею"),
        BotCommand(command="top", description="таблица квиз-лиги"),
        BotCommand(command="quiz", description="внеочередной квиз"),
        BotCommand(command="who", description="опрос «Кто из нас…»"),
        BotCommand(command="meme", description="мем про нашу переписку"),
        BotCommand(command="summary", description="пересказ чата за сегодня"),
        BotCommand(command="get_my_coupons", description="мои купоны"),
        BotCommand(command="mode", description="мой характер"),
        BotCommand(command="get_my_horoscope", description="мой гороскоп"),
        BotCommand(command="exercise", description="упражнение на честность"),
        BotCommand(command="record", description="записать рекорд"),
        BotCommand(command="music", description="музыка"),
        BotCommand(command="mute", description="не влезать в разговор 3 часа"),
        BotCommand(command="unmute", description="снова болтать"),
    ])


async def main():
    global BOT_USERNAME
    me = await bot.me()
    BOT_USERNAME = me.username or ""
    if not db.get_state("last_human_ts"):
        db.set_state("last_human_ts", time.time())
    try:
        await set_commands()
    except Exception:
        log.exception("set_commands")

    background = [asyncio.create_task(reminder_checker(bot)), asyncio.create_task(engagement.scheduler(bot))]
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        for task in background:
            task.cancel()
        await ai.close()


if __name__ == '__main__':
    asyncio.run(main())
