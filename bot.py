import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InputMediaAudio
from aiogram.types import FSInputFile
from api import get_url_meme, get_quote_of_the_day, get_horoscope_of_the_day, get_zodiac, get_tracks_by_genre
from keyboards import meme_kb, zodiac_keyboard, music_keyboard, next_and_back_kb
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

@dp.message(Command('remind'))
async def remind_me(message: Message):
    """
    /remind YYYY-MM-DD HH:MM Текст напоминания
    """
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            raise ValueError("Недостаточно аргументов")

        remind_time_str = args[1] + " " + args[2].split()[0]  # "2026-01-17 18:30"
        remind_text = " ".join(args[2].split()[1:])
        remind_time = datetime.strptime(remind_time_str, "%Y-%m-%d %H:%M")

        user_id = message.from_user.id
        username = message.from_user.username  # для логов

        conn_local = sqlite3.connect('nyvaBot.db')
        cursor_local = conn_local.cursor()
        cursor_local.execute("""
            INSERT INTO reminders (user_id, username, text, remind_time, notified, reply_message_id)
            VALUES (?, ?, ?, ?, 0, ?)
        """, (user_id, username, remind_text, remind_time.strftime("%Y-%m-%d %H:%M:%S"), message.message_id))
        conn_local.commit()
        conn_local.close()

        await message.reply(f"✅ Напоминание добавлено на {remind_time_str}:\n{remind_text}")
    except Exception:
        await message.reply("❌ Ошибка! Используй формат:\n/remind YYYY-MM-DD HH:MM Текст задачи")


async def reminder_checker(bot: Bot):
    while True:
        now = datetime.now()

        conn_check = sqlite3.connect('nyvaBot.db')
        cursor_check = conn_check.cursor()

        cursor_check.execute("""
            SELECT id, user_id, text, remind_time, reply_message_id
            FROM reminders
            WHERE notified = 0
        """)
        reminders = cursor_check.fetchall()

        for reminder_id, user_id, text, remind_time_str, reply_message_id in reminders:
            remind_time = datetime.strptime(remind_time_str, "%Y-%m-%d %H:%M:%S")

            if now >= remind_time:
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text=f"⏰ Напоминание: {text}",
                        reply_to_message_id=reply_message_id
                    )
                    cursor_check.execute(
                        "UPDATE reminders SET notified = 1 WHERE id = ?",
                        (reminder_id,)
                    )
                    conn_check.commit()
                except Exception as e:
                    print(f"❌ Ошибка отправки {user_id}: {e}")

        conn_check.close()
        await asyncio.sleep(10)


# @dp.message(F.audio)
# async def catch_audio(message: Message):
#     print(message.audio.file_id)
async def main():
    # запускаем две задачи параллельно
    await asyncio.gather(
        dp.start_polling(bot),
        reminder_checker(bot)
    )


if __name__ == '__main__':
    asyncio.run(main())