from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


meme_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Еще мем', callback_data='more_meme')]])


def zodiac_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="♈ Овен", callback_data="zodiac_aries"),
                InlineKeyboardButton(text="♉ Телец", callback_data="zodiac_taurus"),
                InlineKeyboardButton(text="♊ Близнецы", callback_data="zodiac_gemini"),
            ],
            [
                InlineKeyboardButton(text="♋ Рак", callback_data="zodiac_cancer"),
                InlineKeyboardButton(text="♌ Лев", callback_data="zodiac_leo"),
                InlineKeyboardButton(text="♍ Дева", callback_data="zodiac_virgo"),
            ],
            [
                InlineKeyboardButton(text="♎ Весы", callback_data="zodiac_libra"),
                InlineKeyboardButton(text="♏ Скорпион", callback_data="zodiac_scorpio"),
                InlineKeyboardButton(text="♐ Стрелец", callback_data="zodiac_sagittarius"),
            ],
            [
                InlineKeyboardButton(text="♑ Козерог", callback_data="zodiac_capricorn"),
                InlineKeyboardButton(text="♒ Водолей", callback_data="zodiac_aquarius"),
                InlineKeyboardButton(text="♓ Рыбы", callback_data="zodiac_pisces"),
            ],
        ]
    )