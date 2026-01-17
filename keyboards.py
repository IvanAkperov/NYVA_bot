from gc import callbacks

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

def music_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='Рок', callback_data='genre_rock'),
            InlineKeyboardButton(text='Хип хоп', callback_data='genre_hip'),
        ],
        [
            InlineKeyboardButton(text='Метал', callback_data='genre_metal'),
            InlineKeyboardButton(text='EDM', callback_data='genre_edm')
        ]
    ]
    )


def next_and_back_kb(genre, index, total):
    """Создаёт клавиатуру навигации по трекам с циклической навигацией и счетчиком."""
    back_index = (index - 1) % total
    forward_index = (index + 1) % total

    buttons = [
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_{genre}_{back_index}"),
        InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="counter"),
        InlineKeyboardButton(text="➡️ Далее", callback_data=f"forward_{genre}_{forward_index}")
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def exercise_kb(exercise):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да ✅", callback_data=f"done_yes:{exercise}")],
        [InlineKeyboardButton(text="Нет ❌", callback_data=f"done_no:{exercise}")]
    ])

    return kb