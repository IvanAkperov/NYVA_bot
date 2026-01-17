import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InputMediaAudio
from aiogram.types import FSInputFile
from api import get_url_meme, get_quote_of_the_day, get_horoscope_of_the_day, get_zodiac, get_tracks_by_genre
from keyboards import meme_kb, zodiac_keyboard, music_keyboard, next_and_back_kb
from help_text import greeting_text
from datetime import datetime
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

# @dp.message(F.audio)
# async def catch_audio(message: Message):
#     print(message.audio.file_id)
async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())