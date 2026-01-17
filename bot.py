import asyncio
import random
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InputMediaAudio, CallbackQuery
from api import get_url_meme, get_quote_of_the_day, get_horoscope_of_the_day, get_zodiac, get_tracks_by_genre, \
    get_random_exercise, exercises
from keyboards import meme_kb, zodiac_keyboard, music_keyboard, next_and_back_kb, exercise_kb
from help_text import greeting_text
from datetime import datetime, timedelta
import sqlite3

conn = sqlite3.connect('nyvaBot.db')
cursor = conn.cursor()
date = str(datetime.today()).split(" ")[0]
bot = Bot(token='8317293211:AAEVYAjfaKyyjBWgevA9srPSIvKMdKnrunA')
dp = Dispatcher()
music_dict = {
    'rock': 'Рок',
    'hip': 'Хип Хоп',
    'rap': 'Рэп',
    'classic': 'Классическая',
    'metal': 'Метал',
    'edm': 'EDM'
}

@dp.message(Command('start'))
async def start(message: Message):
    await message.reply('Салют! Напиши команду /help')


@dp.message(Command('help'))
async def help_text(message: Message):
    await message.reply(greeting_text)


@dp.message(Command('meme'))
async def send_random_meme(message: Message):
    url = get_url_meme()
    if url:
        await message.reply_photo(photo=url, reply_markup=meme_kb)
    else:
        await message.reply('Мема не нашлось :(')


@dp.callback_query(lambda c: c.data == 'more_meme')
async def more_meme(call):
    url = get_url_meme()
    if url:
        await call.message.reply_photo(photo=url, reply_markup=meme_kb)
    else:
        await call.reply('Мемов не нашлось :(')


@dp.callback_query(lambda c: c.data.startswith('zodiac_'))
async def reply_horoscope(call):
    data = call.data.replace('zodiac_', '')
    await call.message.reply(f"Гороскоп на {date}\n\n{get_horoscope_of_the_day(data)}")


@dp.message(Command('quote_of_the_day'))
async def send_random_quote(message: Message):
    quote = await asyncio.to_thread(get_quote_of_the_day)
    await message.reply(quote)


@dp.message(Command('horoscope'))
async def process_horoscope(message: Message):
    await message.reply('Выберите знак', reply_markup=zodiac_keyboard())


@dp.message(Command('get_my_horoscope'))
async def send_user_horoscope(message: Message):
    username = f"@{message.from_user.username}"
    await message.reply(f"Гороскоп на {date}\n\n{get_horoscope_of_the_day(get_zodiac(username, cursor))}")


@dp.message(Command('music'))
async def process_music(message: Message):
    await message.reply("Выбери жанр музыки", reply_markup=music_keyboard())


@dp.callback_query(F.data.startswith("genre_"))
async def send_audio(call):
    genre = call.data.replace("genre_", '')

    cursor.execute("""
        SELECT artist, title, file_id
        FROM music
        WHERE genre = ?
        ORDER BY id
    """, (genre,))
    tracks = cursor.fetchall()

    if not tracks:
        await call.message.answer("❌ В базе нет треков")
        await call.answer()
        return

    index = 0
    artist, title, file_id = tracks[index]

    await call.message.reply_audio(
        audio=file_id,
        caption=f"🎧 {artist} — {title}",
        reply_markup=next_and_back_kb(genre, index, len(tracks))
    )
    await call.answer()


@dp.callback_query(lambda c: c.data.startswith(("forward_", "back_")))
async def navigate_tracks(call):
    action, genre, idx = call.data.split("_")
    idx = int(idx)

    tracks = get_tracks_by_genre(genre, cursor)
    total = len(tracks)

    artist, title, file_id = tracks[idx]

    await call.message.edit_media(
        media=InputMediaAudio(media=file_id, caption=f"🎧 {artist} — {title}"),
        reply_markup=next_and_back_kb(genre, idx, total)
    )
    await call.answer()

@dp.message(Command("remind"))
async def remind_me(message: Message):
    """
    /remind YYYY-MM-DD HH:MM Текст напоминания
    Напоминание приходит в тот же чат (группа или личка)
    """
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            raise ValueError

        date_part = args[1]                      # YYYY-MM-DD
        time_part, *text_parts = args[2].split() # HH:MM + текст

        remind_time_str = f"{date_part} {time_part}"
        remind_text = " ".join(text_parts)

        remind_time = datetime.strptime(remind_time_str, "%Y-%m-%d %H:%M")

        # Сохраняем в БД
        conn_local = sqlite3.connect('nyvaBot.db')
        cursor_local = conn_local.cursor()

        cursor_local.execute("""
            INSERT INTO reminders (
                user_id,  -- оставляем для совместимости
                username,
                text,
                remind_time,
                notified
            )
            VALUES (?, ?, ?, ?, 0)
        """, (
            message.chat.id,              # ← главное изменение
            message.from_user.username,
            remind_text,
            remind_time.strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn_local.commit()
        conn_local.close()

        await message.reply(
            f"✅ Напоминание установлено на {remind_time_str}\n"
            f"📌 Жди уведомления ❤️"
        )

    except Exception:
        await message.reply(
            "❌ Ошибка!\n"
            "Формат:\n"
            "/remind YYYY-MM-DD HH:MM Текст напоминания"
        )



async def reminder_checker(bot: Bot):
    while True:
        now = datetime.now()
        conn = sqlite3.connect('nyvaBot.db')
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, user_id, text, remind_time
            FROM reminders
            WHERE notified = 0
        """)
        reminders = cursor.fetchall()

        for reminder_id, chat_id, text, remind_time_str in reminders:
            remind_time = datetime.strptime(remind_time_str, "%Y-%m-%d %H:%M:%S")
            if now >= remind_time:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"⏰ Напоминание:\n{text}"
                    )

                    cursor.execute(
                        "UPDATE reminders SET notified = 1 WHERE id = ?",
                        (reminder_id,)
                    )
                    conn.commit()

                except Exception as e:
                    print(f"❌ Не смог отправить {chat_id}: {e}")

        conn.close()
        await asyncio.sleep(10)


@dp.message(Command('exercise'))
async def send_gif(message: Message):
    exercise, gif = get_random_exercise()
    cursor.execute(
        "INSERT INTO exercise (user_id, exercise_type, timestamp) VALUES (?, ?, ?)",
        (message.chat.id, exercise, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()

    if exercise != 'Планка':
        amount = random.randint(1, 30)
        await message.reply_animation(animation=gif, caption=f"Давай ка, сделай {exercise} {amount} раз.")
    else:
        await message.reply_animation(animation=gif, caption=f"Осилишь планку 5 минут?")

    asyncio.create_task(ask_exercise_done(message.chat.id, exercise))

async def ask_exercise_done(chat_id: int, exercise: str):
    await asyncio.sleep(300)

    await bot.send_message(chat_id, f"Сделал ли ты упражнение: {exercise}?", reply_markup=exercise_kb(exercise))

# хэндлер для кнопок
@dp.callback_query(F.data.startswith("done_"))
async def handle_done(callback: CallbackQuery):
    answer, exercise = callback.data.split(":")
    if answer == "done_yes":
        await callback.message.edit_text(f"Молодец! Упражнение {exercise} выполнено 💪")
    else:
        await callback.message.edit_text(f"Жаль 😔 Упражнение {exercise} не выполнено")


# @dp.message(F.audio)
# async def catch_audio(message: Message):
#     print(message.audio.file_id)
async def main():
    await asyncio.gather(
        dp.start_polling(bot),
        reminder_checker(bot)
    )


if __name__ == '__main__':
    asyncio.run(main())