import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.types import FSInputFile
from api import get_url_meme, get_quote_of_the_day, ZODIAC_MAP, get_horoscope_of_the_day, NAMES_AND_ZODIAC
from keyboards import meme_kb, zodiac_keyboard
from help_text import greeting_text
from datetime import datetime
import sqlite3



conn = sqlite3.connect('nyvaBot.db')
cursor = conn.cursor()
date = str(datetime.today()).split(" ")[0]

bot = Bot(token='8317293211:AAEVYAjfaKyyjBWgevA9srPSIvKMdKnrunA')
dp = Dispatcher()

@dp.message(Command('start'))
async def start(message: Message):
    await message.answer('Салют! Напиши команду /help')

@dp.message(Command('help'))
async def help_text(message: Message):
    await message.answer(greeting_text)

@dp.message(Command('meme'))
async def send_random_meme(message: Message):
    url = get_url_meme()
    if url:
        await message.answer_photo(photo=url, reply_markup=meme_kb)
    else:
        await message.reply('Мема не нашлось :(')


@dp.callback_query(lambda c: c.data == 'more_meme')
async def more_meme(call):
    url = get_url_meme()
    if url:
        await call.message.answer_photo(photo=url, reply_markup=meme_kb)
    else:
        await call.answer('Мемов не нашлось :(')

@dp.callback_query(lambda c: c.data.startswith('zodiac_'))
async def answer_horoscope(call):
    data = call.data.replace('zodiac_', '')
    await call.message.answer(f"Гороскоп на {date}\n\n{get_horoscope_of_the_day(data)}")


@dp.message(Command('quote_of_the_day'))
async def send_random_quote(message: Message):
    quote = await asyncio.to_thread(get_quote_of_the_day)
    await message.answer(quote)

@dp.message(Command('horoscope'))
async def process_horoscope(message: Message):
    await message.answer('Выберите знак', reply_markup=zodiac_keyboard())


def get_zodiac(username):
    cursor.execute("SELECT zodiac FROM users WHERE username = ?", (username,))
    zodiac = cursor.fetchone()
    if zodiac:
        return zodiac[0]

@dp.message(Command('get_my_horoscope'))
async def send_user_horoscope(message: Message):
    username = f"@{message.from_user.username}"
    await message.answer(f"Гороскоп на {date}\n\n{get_horoscope_of_the_day(get_zodiac(username))}")

@dp.message()
async def detect_meme(message: Message):
    text = message.text.lower()
    if text in ('мем', 'мемы'):
        await message.answer_photo(photo=get_url_meme())
    elif text in ('цитата', 'цитаты'):
        quote = await asyncio.to_thread(get_quote_of_the_day)
        await message.answer(quote)




async def main():
    await dp.start_polling(bot)



if __name__ == '__main__':
    asyncio.run(main())