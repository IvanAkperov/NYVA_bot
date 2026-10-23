"""
Все настройки бота в одном месте.
Секреты (токены) берутся из файла .env рядом с bot.py — в код и в git они больше не попадают.
"""
import os
from datetime import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_env(path: Path) -> None:
    """Мини-загрузчик .env без внешних зависимостей."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(BASE_DIR / ".env")


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Не задан {name}. Добавь его в файл .env рядом с bot.py")
    return value


# ---------- секреты ----------
BOT_TOKEN = _require("BOT_TOKEN")
MISTRAL_API_KEY = _require("MISTRAL_API_KEY")

# ---------- чат ----------
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "-4909725043"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "1197646514"))
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "nyvaBot.db"))  # на сервере база лежит вне git

# ---------- компания ----------
FRIENDS = {
    "@xquisite_corpse": {"name": "Ваня", "gender": "m", "partner": "@YuliyaAkperova",
                         "forms": ["ваня", "вани", "ване", "ваню", "ваней", "ванёк", "ванек", "ванечка"]},
    "@YuliyaAkperova": {"name": "Юля", "gender": "f", "partner": "@xquisite_corpse",
                        "forms": ["юля", "юли", "юле", "юлю", "юлей", "юлечка", "юлька"]},
    "@AIAND23": {"name": "Андрей", "gender": "m", "partner": "@nadya_teacher13",
                 "forms": ["андрей", "андрея", "андрею", "андреем", "андрее", "андрюха", "андрюша"]},
    "@nadya_teacher13": {"name": "Надя", "gender": "f", "partner": "@AIAND23",
                         "forms": ["надя", "нади", "наде", "надю", "надей", "надюша", "надька"]},
}

# ---------- расписание (время сервера) ----------
HOROSCOPE_TIME = time(10, 0)    # один общий гороскоп вместо 4 сообщений
QUIZ_TIME = time(12, 30)        # квиз дня с очками
WHO_POLL_TIME = time(18, 0)     # опрос «Кто из нас скорее всего…»
DRAW_TIME = time(21, 0)         # розыгрыш купонов
RECAP_TIME = time(22, 30)       # итоги дня + результаты опросов
JOB_GRACE_MINUTES = 60          # если бот был выключен дольше — задачу за день пропускаем

# ---------- «живой» бот ----------
FEATURES = {
    "horoscope": True,
    "quiz": True,
    "who_poll": True,
    "draw": True,
    "recap": True,
    "interjections": True,      # бот иногда сам вклинивается в разговор
    "reactions": True,          # бот иногда ставит реакции на сообщения
    "silence_breaker": True,    # бот оживляет чат, если все молчат
}
INTERJECT_CHANCE = 0.12         # шанс, что бот задумается вклиниться в живой разговор
INTERJECT_COOLDOWN_MIN = 90     # не чаще раза в N минут
REACT_CHANCE = 0.15             # шанс поставить реакцию на сообщение
REACT_COOLDOWN_MIN = 20
SILENCE_HOURS = 30              # сколько часов тишины считается «чат умер»
ACTIVE_HOURS = (11, 22)         # когда боту можно самому писать (с, по)
RECAP_MIN_MESSAGES = 8          # меньше сообщений за день — без пересказа, только опросы
CONTEXT_MESSAGES = 20           # сколько последних сообщений чата бот видит при ответе
