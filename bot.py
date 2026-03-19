import asyncio
import random
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, BaseFilter
from aiogram.types import Message, InputMediaAudio, CallbackQuery, InputFile, BufferedInputFile, ReactionTypeEmoji

from anecdotes import get_random_anectode
from api import get_url_meme, get_quote_of_the_day, get_horoscope_of_the_day, get_zodiac, get_tracks_by_genre, \
    get_random_exercise, text_to_speech
from keyboards import meme_kb, zodiac_keyboard, music_keyboard, next_and_back_kb, exercise_kb, voice_kb, \
    delete_message_kb, username_kb
from help_text import greeting_text
from datetime import datetime, timedelta, time
import sqlite3
from mistral import send_message_from_mistral_bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state

conn = sqlite3.connect('nyvaBot.db', check_same_thread=False)
cursor = conn.cursor()
router = Router()

date = str(datetime.today()).split(" ")[0]
bot = Bot(token='8317293211:AAEVYAjfaKyyjBWgevA9srPSIvKMdKnrunA')
chat_id = -4909725043
dp = Dispatcher()
DRAW_TIME = time(15, 50)
name = {'@nadya_teacher13': "Надя", "@xquisite_corpse": "Ваня", "@YuliyaAkperova": "Юля", "@AndreQA23": "Андрей"}


class TrainingRecord(StatesGroup):
    exercise = State()
    weight = State()
    amount = State()


class UserFact(StatesGroup):
    user = State()
    fact = State()

music_dict = {
    'rock': 'Рок',
    'hip': 'Хип Хоп',
    'rap': 'Рэп',
    'classic': 'Классическая',
    'metal': 'Метал',
    'edm': 'EDM'
}
weekday = {
    0: {'Понедельник': 'С началом новой недели, друзья! Постарайтесь сегодня отдохнуть!'},
    1: {'Вторник': 'С добрым вторником вас, ребята! @AndreQA23, а ты сегодня дома валяешься? Отдыхай, бро!'},
    2: {"Среда": 'Привет! Ровно середина рабочей недели, друзья, всем успехов!'},
    3: {"Четверг": 'Доброе утро! Сегодня четверг, не за горами пятница и выходные, у вас всё получится!'},
    4: {'Пятница': 'Поздравляю с наступившей пятницей, фитоняшки!  Доделывайте свои дела и вперед отдыхать!'},
    5: {'Суббота': 'Всем доброе утро! Вы как, выспались? Какие планы на субботу? Обязательно сходите потренировать ноги, в частности @AndreQA23 :)'},
    6: {'Воскресенье': 'Всем привет, ребята! Воскресенье день безделья, проваляйтесь сегодня в кроватке, всех люблю!'}
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
    await bot.send_chat_action(chat_id, 'typing')
    await asyncio.sleep(3)
    await message.reply(quote)


@dp.message(Command('horoscope'))
async def process_horoscope(message: Message):
    await message.reply('Выберите знак', reply_markup=zodiac_keyboard())


@dp.message(Command('get_my_horoscope'))
async def send_user_horoscope(message: Message):
    username = f"@{message.from_user.username}"
    await bot.send_chat_action(chat_id, 'typing')
    await asyncio.sleep(3)
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
    "🛁 Вечер спа: ты натираешь меня маслом, я делаю вид, что это случайно",
    "🎁 Исполнение одного желания (даже того, о котором ты молчишь, но я догадываюсь)",
    "🍰 Десерт, который можно есть не только ложкой, но и... ну ты поняла",
    "🌹 Романтический ужин, после которого посуда подождет до утра",
    "👑 День принцессы: завтрак в постель, завтрак на мне, завтрак во мне... шутка (или нет?)",
    "💐 Букет цветов + стриптиз от партнера (цензурная версия)",
    "🎯 Право на исполнение желания. Любого. Да, даже ЭТОГО.",
    "🛍️ Шопинг-сопровождение + примерка дома (и снятие тоже)",
    "🍷 Дегустация вин с последующей дегустацией друг друга",
    "💆‍♀️ Эротический массаж от партнера (масло входит в стоимость)",
    "✨ Вечер красоты: маски, ванна, и я рядом в чем мать родила",
    "💑 Прогулка под луной с остановками в кустах",
    "🎤 Караоке в душе. Вместе. Голыми.",
    "🛋️ Вечер под пледом без одежды (плед выдержит, проверено)",
    "🍑 Один час полного повиновения твоим желаниям (фантазия приветствуется)",
    "🎰 Лотерея: снять одежду или выполнить желание (спойлер: снимешь в любом случае)",
    "🌙 Ночь без taboos: включай фантазию на полную"
]


COUPON_TYPES_MAN = [
    "🎮 Гейминг с перерывами на поцелуи (места назначения любые)",
    "🍺 Пиво с друзьями + пижамная вечеринка для двоих",
    "⚽ Футбол + игра в офсайд в спальне",
    "🍔 Бургер + я в роли соуса",
    "🎬 Кино + продолжение в стиле 18+",
    "💆‍♂️ Массаж + хэппи-энд (ты знаешь какой)",
    "🎁 Сюрприз, который мы оба оценим",
    "🏎️ Гонки + проверка твоей выносливости",
    "🎯 Настолки с друзьями + взрослые игры ночью",
    "🍖 Шашлыки + жаркий вечер",
    "🎣 Рыбалка + ночная ловля (удачи мне)",
    "🛠️ Хобби + моё хобби - удивлять тебя",
    "🚗 Музыка в машине + моя музыка в спальне",
    "🎫 Билет на ивент + личное выступление от меня",
    "🥩 Ужин + десерт (я знаю, что ты любишь сладкое)",
    "🎸 Концерт + сольный концерт для тебя",
    "📺 Футбол с пиццей + я с начинкой",
    "🎳 Боулинг + страйк в наших отношениях",
    "🎮 Новая игра + новый уровень близости",
    "🛋️ Релакс + активный отдых по желанию",
    "🔧 Ремонт + снятие усталости народными средствами",
    "🏋️‍♂️ Спортзал + кардио перед сном",
    "🛁 Ванна вдвоем + мытье посуды... друг друга",
    "💋 Полный контроль на 15 минут",
    "🍆 День твоих желаний (список утверждается на месте)",
    "🎰 Рулетка желаний: выпадет - сделаем",
    "🌙 Ночь экспериментов",
    "🔞 Одно желание без фильтров"
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
            target = now.replace(hour=21, minute=00, second=0, microsecond=0)

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
    result = cursor.fetchall()
    if result:
        await bot.send_chat_action(chat_id, 'typing')
        await asyncio.sleep(3)
        await message.reply(f"У тебя есть купон \n{result[0]}")
    else:
        await bot.send_chat_action(chat_id, 'typing')
        await asyncio.sleep(3)
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


async def send_morning_message(bot: Bot):
    while True:
        now = datetime.now()
        target = now.replace(hour=9, minute=00, second=0, microsecond=0)
        if now > target:
            target += timedelta(days=1)
        seconds_to_wait = (target - now).total_seconds()
        await asyncio.sleep(seconds_to_wait)
        day = weekday[datetime.now().weekday()]

        for _, value in day.items():
            await bot.send_message(chat_id=-4909725043,text=value, disable_notification=True)

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
        for user_id, username, zodiac, mode, extra_info in result:
            try:
                text = f"{username}, твой гороскоп на сегодня\n\n{get_horoscope_of_the_day(zodiac)}"
                await bot.send_message(chat_id=-4909725043, text=text)
            except:
                await bot.send_message(chat_id=4909725043, text='Простите, гороскоп не сработал')
@dp.message(Command('mode'))
async def change_mode(message: Message):
    text = message.text.split(maxsplit=2)
    username = f"@{message.from_user.username}"
    answer_to_name = name[username]
    mode = text[1]
    if mode in (
            'normal', 'toxic', 'simp', 'drunk', 'npc',
            'mystic', 'edgy_teen', 'gamer',
            'corporate', 'conspiracy',
            'zen', 'villain',
            'detective', 'chaos',
            'random', 'horny'
    ):
        cursor.execute("UPDATE users SET mode = ? WHERE username = ?", (mode, username))
        conn.commit()
        await message.answer(f"{answer_to_name}, твой режим - {mode}. {'Наслаждайся!' if mode != 'random' else 'Тебе пиздец'}")
    else:
        await message.answer(f"{answer_to_name}, такого режима у меня нет.")

@router.message(Command('fact'))
async def create_fact(message: Message, state: FSMContext):
    await state.set_state(UserFact.user)
    await message.reply("Запишем новый факт. О ком записываем инфу?", reply_markup=username_kb())

@router.callback_query(lambda c: c.data.startswith('user_'), UserFact.user)
async def process_user(call: CallbackQuery, state: FSMContext):
    data = call.data.replace("user_", '')
    await state.update_data(user=data)
    await state.set_state(UserFact.fact)
    await call.message.answer(f"Выбран пользователь: {data}")
    await call.message.answer("Какой факт запишем?")
    await call.answer()
    await call.message.delete()


@router.message(UserFact.fact)
async def process_fact(message: Message, state: FSMContext) -> None:
    await state.update_data(fact=message.text)
    data = await state.get_data()
    user = data['user']
    fact = data['fact'] + '.'
    await state.clear()
    cursor.execute('''
        UPDATE users 
        SET extra_info = CASE 
            WHEN extra_info IS NULL OR extra_info = '' THEN ?
            ELSE extra_info || '\n' || ?
        END
        WHERE username = ?
    ''', (fact, fact, user))
    conn.commit()
    await message.answer(f"Добавил факт - {user} {fact}")



@router.message(Command('record'))
async def create_record(message: Message, state: FSMContext):
    await state.set_state(TrainingRecord.exercise)
    await message.reply('Новый рекорд? Отлично! Напиши упражнение')


@router.message(Command("cancel", "отмена", "стоп"), ~F.state == default_state)
async def cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активного состояния для отмены")
        return

    await state.finish()  # Сброс состояния
    await message.answer("Похуй, потом запишем тогда")
@router.message(TrainingRecord.exercise)
async def process_exercise(message: Message, state: FSMContext) -> None:
    await state.update_data(exercise=message.text)
    await state.set_state(TrainingRecord.weight)
    await message.answer("Какой был вес в кг?:")
@router.message(TrainingRecord.weight)
async def process_weight(message: Message, state: FSMContext) -> None:
    await state.update_data(weight=message.text)
    await state.set_state(TrainingRecord.amount)
    await message.answer("Сколько повторений?")
@router.message(TrainingRecord.amount)
async def process_amount(message: Message, state: FSMContext) -> None:
    await state.update_data(amount=message.text)
    data = await state.get_data()
    exercise = data['exercise']
    weight = data['weight']
    amount = data['amount']
    await state.clear()
    username = f"@{message.from_user.username}"
    cursor.execute("""INSERT INTO records (username, exercise, weight, amount) VALUES (?, ?, ?, ?)""", (username, exercise, weight, amount))
    conn.commit()
    await message.answer(f"Добавил в базу твой рекорд - {exercise} {weight}x{amount}")


@dp.message(Command('get_my_records'))
async def get_my_records(message: Message):
    username = f"@{message.from_user.username}"
    cursor.execute("""SELECT exercise, weight, amount FROM records WHERE username = ?""", (username,))
    result = cursor.fetchall()
    text = "Твои рекорды:\n\n"
    for exercise, weight, amount in result:
        text += f"• {exercise}: {weight} кг × {amount}\n"
    await message.reply(text)


@dp.message(Command('voice'))
async def select_voice(message: Message):
    await message.answer("Выберите озвучку", reply_markup=voice_kb())

@dp.callback_query(lambda c: c.data.startswith('voice_'))
async def change_voice(call: CallbackQuery):
    voice = call.data.replace("voice_", '')
    cursor.execute("""UPDATE voice set current_voice = ? WHERE id = ?""", (voice, 1))
    conn.commit()
    await call.message.answer(f"Выбрана озвучка {voice}")
    await call.answer()
    await call.message.delete()

@dp.callback_query(lambda d: d.data == 'delete')
async def delete_bot_message(call: CallbackQuery):
    await call.message.edit_text('Сообщение удалено.')


@router.message(
    lambda message: (
        (message.text and message.text.lower().startswith("бот")) or
        (message.reply_to_message and message.reply_to_message.from_user.id == bot.id)
    )
)
async def handle_interactive(message: Message):
    try:
        text = message.text or message.caption
        if not text:
            return
        if text.lower().startswith(('бот', 'Бот')):
            text = text[3:].lstrip() if text[0].isupper() else text[1:].lstrip()


        username = message.from_user.username or "аноним"
        username_full = f"@{username}"
        cursor.execute(
            "INSERT INTO messages (username, role, content) VALUES (?, ?, ?)",
            (username, "user", text)
        )
        conn.commit()

        # Получаем режим из базы
        cursor.execute("""SELECT mode, extra_info FROM users WHERE username = ?;""", (username_full,))

        row = cursor.fetchone()
        mode = row[0] if row else "normal"
        extra_info = row[1]
        extra_message = ''
        if mode == 'random':
            mode = random.choice(['normal', 'toxic', 'simp', 'drunk', 'npc',
            'mystic', 'edgy_teen', 'gamer',
            'corporate', 'conspiracy',
            'zen', 'villain',
            'detective', 'chaos'])
            extra_message = f'Отправлено в режиме {mode}'
        if mode == 'toxic':
            CLOWN_CHANCE = 0.8
            should_send_clown = (
                    message.from_user.id == message.from_user.id and
                    random.random() < CLOWN_CHANCE
            )

            if should_send_clown:
                try:
                    await bot.set_message_reaction(
                        chat_id=message.chat.id,
                        message_id=message.message_id,
                        reaction=[ReactionTypeEmoji(emoji="🤡")],
                        is_big=True
                    )
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"Ошибка реакции клоуна: {e}")
        cursor.execute("""SELECT current_voice FROM voice""")
        row2 = cursor.fetchone()
        voice = row2[0]
        cursor.execute(
            """
            SELECT role, content
            FROM messages
            WHERE username = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (username,)
        )
        rows = cursor.fetchall()
        history = list(reversed(rows))

        response_text = await send_message_from_mistral_bot(
            text=text,
            username=username,
            mode=mode,
            history=history,
            extra_info=extra_info
        )
        if 'аудио' in text.lower():
            response_text = response_text.replace("*", '')
            audio = await text_to_speech(response_text, voice)
            voice_bytes = audio.getvalue()  # bytes
            voice_file = BufferedInputFile(
                file=voice_bytes,
                filename="voice.ogg"
            )
            await bot.send_chat_action(message.chat.id, 'record_voice')
            await asyncio.sleep(2 + random.uniform(0.4, 1.3))
            await message.answer_voice(voice=voice_file)
        elif 'анекдот' in text.lower():
            joke = get_random_anectode()
            audio = await text_to_speech(joke, voice)
            voice_bytes = audio.getvalue()  # bytes
            voice_file = BufferedInputFile(
                file=voice_bytes,
                filename="voice.ogg"
            )
            await bot.send_chat_action(message.chat.id, 'record_voice')
            await asyncio.sleep(2 + random.uniform(0.4, 1.3))
            await message.answer_voice(voice=voice_file)
        else:
            await bot.send_chat_action(message.chat.id, 'typing')
            await asyncio.sleep(1 + random.uniform(0.4, 1.3))

            await message.reply(f"{response_text}\n\n{extra_message}", reply_markup=delete_message_kb())

    except Exception as e:
        await message.reply("Соединение прервано, попробуй еще раз, либо пиздуй баги исправлять")
        print(f"Mistral error in handler: {e}")



    except Exception as e:
        print(f"Mistral error in handler: {e}")
        await message.reply("⚠️ Бро, я сломался 😵")






@router.message(lambda m: m.photo and m.caption and "бот оцени" in m.caption.lower())
async def handle_photo_analysis(message: Message):
    try:
        photo = message.photo[-1]  # самое большое
        file = await message.bot.get_file(photo.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        image_bytes = file_bytes.read()

        analysis = await analyze_image_simple(image_bytes)
        await message.answer("Ща, погоди")
        await asyncio.sleep(2)
        await message.reply(analysis)
    except:
        await message.reply("У меня глаза болят, попробуй позже")

async def analyze_image_simple(image_bytes: bytes) -> str:
    reactions = [
        "Неожиданно… но выглядит кайфово 🔥",
        "Окей, вот это уже достойно внимания",
        "Я не ожидал, но мне зашло",
        "Есть вайб, не буду врать",
        "Ну слушай… красиво, чё",
        "Выглядит аккуратно, респект",
        "Это явно делалось не на отъебись",
        "Сюда бы ещё свет нормальный — и вообще топ",
        "Есть стиль, есть идея",
        "Ну вот это уже не кринж, одобряем 👍",
        "Чётко. Без лишнего мусора",
        "Глаз не режет — уже успех",
        "Мне нравится, хоть я и вредный",
        "Окей, плюс в карму",
        "Редкий случай, когда фотка реально норм",
        "Ну… фотка как фотка",
        "Я посмотрел. Осмысливаю 🤔",
        "Ничего сверхъестественного, но и не жесть",
        "Окей, принято",
        "Сложно что-то сказать, если честно",
        "Без эмоций. Просто есть",
        "Я видел такое уже раз сто",
        "Средненько. Ни туда ни сюда",
        "Не зацепило, но и не выбесило",
        "Фон живёт своей жизнью, объект — своей",
        "Вроде нормально, но чего-то не хватает",
        "Не плохо. Не хорошо. Просто… да",
        "Если это идея — она пока прячется",
        "Смотрю и молчу",
        "Ну, бывает",
        "Чё-то я не понял, но выглядит стрёмно 😐",
        "Ну это уже уровень кринжа, конечно",
        "Если это шутка — то слабовато",
        "Я видел вещи и похуже, но это близко",
        "Зачем ты это вообще сфоткал?",
        "Глазам больно, если честно",
        "Тут явно нужен контекст… и психолог",
        "Это должно было остаться в галерее",
        "Я бы такое не показывал",
        "Сомнительное решение, очень",
        "Кажется, камера тут вообще ни при чём",
        "Это выглядит как ошибка, а не задумка",
        "Мне неловко, и я даже не знаю почему",
        "Фото есть — смысла нет",
        "Ну вот зачем",
    ]
    reaction = random.choice(reactions)
    return f"Так, скачал. Размер файла {len(image_bytes)} KB. {reaction}"


@dp.message(Command('lk'))
async def send_message_from_lk(message: Message):
    text = message.text
    text = text.replace('/lk', '')
    await bot.send_message(-4909725043, text)


dp.include_router(router)
async def main():
    await asyncio.gather(
        dp.start_polling(bot),
        reminder_checker(bot),
        send_draw_to_user(bot),
        send_horoscope_to_everyone(bot),
        send_morning_message(bot),
    )


if __name__ == '__main__':
    asyncio.run(main())
