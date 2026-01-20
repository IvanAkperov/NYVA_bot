import asyncio
import random
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InputMediaAudio, CallbackQuery
from api import get_url_meme, get_quote_of_the_day, get_horoscope_of_the_day, get_zodiac, get_tracks_by_genre, \
    get_random_exercise, exercises
from keyboards import meme_kb, zodiac_keyboard, music_keyboard, next_and_back_kb, exercise_kb
from help_text import greeting_text
from datetime import datetime, timedelta, time
import sqlite3

conn = sqlite3.connect('nyvaBot.db', check_same_thread=False)
cursor = conn.cursor()

date = str(datetime.today()).split(" ")[0]
bot = Bot(token='8317293211:AAEVYAjfaKyyjBWgevA9srPSIvKMdKnrunA')
dp = Dispatcher()
DRAW_TIME = time(15, 50)

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


def get_winner_of_the_day():
    cursor.execute("""SELECT username, user_id FROM users;""")
    users = cursor.fetchall()
    winner_of_the_day = random.choice(users)
    return winner_of_the_day[0], winner_of_the_day[1]

# КУПОНЫ ДЛЯ ЖЕНЩИН
COUPON_TYPES_GIRL = [
    "💆‍♀️ Сертификат на 30-минутный массаж от партнера",
    "🛁 Вечер спа-процедур с пеной и свечами",
    "🎁 Выбор подарка до 3000 рублей",
    "🍰 Домашний десерт по выбору победителя",
    "🎬 Вечер кино с выбором фильма победителем",
    "🌹 Романтический ужин при свечах",
    "🛒 Избавление от домашних дел на 1 день",
    "👑 День принцессы - завтрак в постель и повышенное внимание",
    "💐 Букет цветов от партнера",
    "🛌 Утро выходного дня без будильников",
    "🎯 Право на исполнение одного желания (в разумных пределах)",
    "🛍️ Шопинг-сопровождение без жалоб",
    "🍷 Вечер дегустации вин с закусками",
    "💆‍♀️ Профессиональный маникюр в салоне",
    "✨ Вечер красоты: маска для лица, ванна, уходовые процедуры",
    "🎮 Бесплатное право выбрать вечернее занятие",
    "📚 Час тишины и одиночества для чтения/отдыха",
    "💑 Романтическая прогулка в парке с мороженым",
    "🎤 Караоке-вечер дома",
    "🛋️ Вечер на диване под пледом с чаем и разговорами"
]

# КУПОНЫ ДЛЯ МУЖЧИН
COUPON_TYPES_MAN = [
    "🎮 Беспрепятственный гейминг на 3 часа",
    "🍺 Пивной вечер с друзьями без вопросов",
    "⚽ Просмотр любого спортивного матча на большом экране",
    "🍔 Заказ любимой еды на дом",
    "🎬 Марафон фильмов/сериалов по выбору победителя",
    "💆‍♂️ 30-минутный массаж спины от партнера",
    "🎁 Выбор подарка до 3000 рублей",
    "🏎️ Посещение картинг-центра или симулятора гонок",
    "🎯 Вечер настольных игр с друзьями",
    "🍖 Мужской пикник с мясом на гриле",
    "🎣 Выезд на рыбалку на полдня",
    "🛠️ День для хобби (гараж, моделирование и т.д.)",
    "🚗 Право выбора музыки в машине на неделю",
    "🎫 Билет на спортивное/музыкальное мероприятие",
    "🥩 Стейк-ужин в ресторане",
    "🎸 Посещение концерта любимой группы",
    "📺 Футбольный марафон с пиццей",
    "🎳 Вечер боулинга или бильярда",
    "🎮 Новейшая видеоигра по выбору",
    "🛋️ Полный релакс: диван, пульт и никаких дел"
]

import os
from datetime import datetime

# Глобальная настройка логов
LOG_FILE = "draw_log.txt"


def log_draw(message: str):
    """Запись лога в файл"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
        print(log_entry.strip())  # Также выводим в консоль
    except Exception as e:
        print(f"Ошибка записи лога: {e}")


async def send_draw_to_user(bot: Bot):
    """Функция розыгрыша с логированием в файл"""

    # Создаем файл логов если его нет
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("=== ЛОГ РОЗЫГРЫША ===\n")
        log_draw("Файл логов создан")

    log_draw("Функция розыгрыша запущена")

    while True:
        try:
            # Получаем текущее время с часовым поясом
            now = datetime.now()
            target = now.replace(hour=21, minute=30, second=0, microsecond=0)

            log_draw(f"Текущее время: {now.strftime('%H:%M:%S')}")
            log_draw(f"Целевое время: {target.strftime('%H:%M:%S')}")

            # Если уже прошло 21:00, ждем до завтра
            if now > target:
                target += timedelta(days=1)
                log_draw("21:00 уже прошло, ждем до завтра")

            seconds_to_wait = (target - now).total_seconds()
            hours, remainder = divmod(seconds_to_wait, 3600)
            minutes, seconds = divmod(remainder, 60)

            log_draw(f"До розыгрыша: {int(hours)}ч {int(minutes)}м {int(seconds)}с")

            await asyncio.sleep(seconds_to_wait)

            # === НАЧАЛО РОЗЫГРЫША ===
            log_draw("=== НАЧАЛО РОЗЫГРЫША ===")

            try:
                # Создаем новое соединение для этой итерации
                conn_local = sqlite3.connect('nyvaBot.db')
                cursor_local = conn_local.cursor()
                log_draw("Подключение к БД установлено")

                # Получаем всех пользователей
                cursor_local.execute("SELECT username, user_id FROM users")
                users = cursor_local.fetchall()

                log_draw(f"Найдено пользователей: {len(users)}")

                if not users:
                    log_draw("ОШИБКА: Нет пользователей для розыгрыша!")
                    conn_local.close()
                    continue

                # Выбираем случайного победителя
                winner_username, winner_id = random.choice(users)
                log_draw(f"Случайный выбор: {winner_username} (ID: {winner_id})")

                # Проверяем дату
                today = datetime.now().strftime('%Y-%m-%d')
                log_draw(f"Сегодняшняя дата: {today}")

                # Проверяем, был ли сегодня розыгрыш у этого пользователя
                cursor_local.execute("""
                    SELECT id, sent_date FROM daily_draw 
                    WHERE user_id = ? AND sent_date = ?
                """, (winner_id, today))

                existing_draw = cursor_local.fetchone()

                if existing_draw:
                    log_draw(f"Пользователь {winner_username} уже получал розыгрыш {existing_draw[1]}. Пропускаем.")
                    conn_local.close()
                    continue

                # Выбираем купон в зависимости от пользователя
                if winner_username in ('@xquisite_corpse', '@AndreQA23'):
                    coupon = random.choice(COUPON_TYPES_MAN)
                    log_draw(f"Выбран мужской купон: {coupon}")
                else:
                    coupon = random.choice(COUPON_TYPES_GIRL)
                    log_draw(f"Выбран женский купон: {coupon}")

                # Сохраняем в БД
                cursor_local.execute("""
                    INSERT INTO daily_draw (user_id, username, coupon_type, sent_date)
                    VALUES (?, ?, ?, ?)
                """, (winner_id, winner_username, coupon, today))
                conn_local.commit()
                log_draw(f"Данные сохранены в БД: {winner_username} -> {coupon[:50]}...")

                # Формируем сообщение
                text = f"""🎉 ЕЖЕДНЕВНЫЙ РОЗЫГРЫШ 🎉

Победитель дня: {winner_username} 🔥
Приз: {coupon}

Действует 30 дней • {datetime.now().strftime('%d.%m.%Y')}"""

                # Отправляем в группу
                try:
                    await bot.send_message(-4909725043, text)
                    log_draw(f"Сообщение успешно отправлено в группу (-4909725043)")
                    log_draw(f"ПОБЕДИТЕЛЬ: {winner_username}")
                    log_draw(f"ПРИЗ: {coupon}")
                except Exception as send_error:
                    log_draw(f"ОШИБКА отправки в группу: {send_error}")
                    # Пробуем отправить себе для диагностики
                    try:
                        await bot.send_message(
                            chat_id=1197646514,  # Замени на свой ID
                            text=f"❌ Ошибка отправки розыгрыша: {send_error}"
                        )
                    except:
                        pass

                conn_local.close()
                log_draw("Соединение с БД закрыто")

            except sqlite3.Error as db_error:
                log_draw(f"ОШИБКА БАЗЫ ДАННЫХ: {db_error}")
            except Exception as draw_error:
                log_draw(f"ОШИБКА В РОЗЫГРЫШЕ: {draw_error}")
                import traceback
                error_details = traceback.format_exc()
                log_draw(f"Трассировка:\n{error_details}")

            log_draw("=== ЗАВЕРШЕНИЕ РОЗЫГРЫША ===")

        except asyncio.CancelledError:
            log_draw("Задача розыгрыша отменена")
            raise
        except Exception as loop_error:
            log_draw(f"КРИТИЧЕСКАЯ ОШИБКА ЦИКЛА: {loop_error}")
            await asyncio.sleep(60)  # Пауза при критической ошибке


# Функция проверки напоминаний (исправленная)
async def reminder_checker(bot: Bot):
    while True:
        try:
            now = datetime.now()

            # Создаем новое соединение для этой функции
            conn_local = sqlite3.connect('nyvaBot.db')
            cursor_local = conn_local.cursor()

            cursor_local.execute("""
                SELECT id, user_id, text, remind_time
                FROM reminders
                WHERE notified = 0
            """)
            reminders = cursor_local.fetchall()

            for reminder_id, chat_id, text, remind_time_str in reminders:
                remind_time = datetime.strptime(remind_time_str, "%Y-%m-%d %H:%M:%S")
                if now >= remind_time:
                    try:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=f"⏰ Напоминание:\n{text}"
                        )

                        cursor_local.execute(
                            "UPDATE reminders SET notified = 1 WHERE id = ?",
                            (reminder_id,)
                        )
                        conn_local.commit()

                    except Exception as e:
                        print(f"❌ Не смог отправить напоминание {chat_id}: {e}")

            conn_local.close()
            await asyncio.sleep(10)

        except Exception as e:
            print(f"❌ Ошибка в reminder_checker: {e}")
            await asyncio.sleep(10)

@dp.message(Command('get_my_coupons'))
async def get_my_coupons(message: Message):
    username = f"@{message.from_user.username}"
    cursor.execute("SELECT coupon_type FROM daily_draw WHERE used = 0 AND username = ?", (username,))
    print(cursor.fetchall())
    result = cursor.fetchall()
    if result:
        await message.reply(f"У тебя есть купон \n{result[0]}")
    else:
        await message.reply(f"Купонов нет")


@dp.message(Command('getid'))
async def get_chat_id(message: Message):
    """Получить ID чата/группы"""
    chat_id = message.chat.id
    chat_type = message.chat.type
    chat_title = message.chat.title if hasattr(message.chat, 'title') else "ЛС"

    info = f"""
📊 *Информация о чате:*
├ Тип: `{chat_type}`
├ ID: `{chat_id}`
└ Название: `{chat_title}`

💡 *Как использовать:*
1. В группе: `GROUP_CHAT_ID = {chat_id}`
2. В ЛС: твой ID: `{chat_id}`
"""

    await message.reply(info, parse_mode="Markdown")


async def send_horoscope_to_everyone(bot: Bot):
    while True:
        now = datetime.now()
        target = now.replace(hour=10, minute=00, second=0, microsecond=0)

        if now > target:
            target += timedelta(days=1)

        seconds_to_wait = (target - now).total_seconds()
        print(f"До следующего гороскопа: {seconds_to_wait:.0f} сек")

        await asyncio.sleep(seconds_to_wait)
        cursor.execute("SELECT * FROM users;")
        result = cursor.fetchall()
        for user_id, username, zodiac in result:
            text = f"{username}, твой гороскоп на сегодня\n\n{get_horoscope_of_the_day(zodiac)}"
            await bot.send_message(chat_id=-4909725043, text=text)


# @dp.message(F.audio)
# async def catch_audio(message: Message):
#     print(message.audio.file_id)
async def main():
    await asyncio.gather(
        dp.start_polling(bot),
        reminder_checker(bot),
        send_draw_to_user(bot),
        send_horoscope_to_everyone(bot)
    )


if __name__ == '__main__':
    asyncio.run(main())
