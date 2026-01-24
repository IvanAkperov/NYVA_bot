import requests
import random
from translate import Translator
from bs4 import BeautifulSoup


headers = {'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 YaBrowser/25.12.0.0 Safari/537.36'}

exercises = {
    'Отжимания': 'https://media1.tenor.com/m/wr_9-cLvSkYAAAAC/отжимания.gif',
    'Приседания': 'https://i.pinimg.com/originals/f9/db/a3/f9dba36451cab8b0b5be6d5ec9fd438a.gif',
    'Планка': 'https://i.pinimg.com/originals/d9/af/0e/d9af0e82465af0aa3c41e15cd8ed6d7b.gif',
    'Выпады': 'https://media1.tenor.com/m/PF7Q7Qu1wJEAAAAC/lunges.gif'
}

def get_random_exercise():
    exercise_type = random.choice(list(exercises.keys()))
    return exercise_type, exercises[exercise_type]

def get_url_meme():
    try:

        memes = requests.get('https://api.imgflip.com/get_memes', headers=headers).json()['data']['memes']
        return random.choice([i['url'] for i in memes])
    except:
        return None

def translate_from_english(text, from_lang='en', to_lang='ru'):
    translator = Translator(from_lang=from_lang, to_lang=to_lang)
    try:
        text = translator.translate(text)
        return text
    except:
        return 'Не удалось перевести язык'


def get_quote_of_the_day():
    resp = requests.get("https://zenquotes.io/api/random").json()
    for i in resp:
        ru = translate_from_english(i['q'])
        author = i['a']
        text = f"{ru}\n *{author}*"
        return text

def get_zodiac(username, cursor):
    cursor.execute("SELECT zodiac FROM users WHERE username = ?", (username,))
    zodiac = cursor.fetchone()
    if zodiac:
        return zodiac[0]

def get_horoscope_of_the_day(sign):
    url = requests.get(
        f'https://goroskop365.ru/{sign}/',
        headers=headers,
        timeout=10
    )
    soup = BeautifulSoup(url.text, 'html.parser')

    wrapper = (
        soup
        .find(id='main_content')
        .find(id='main_content_main')
        .find(id='content_wrapper')
    )
    text = " ".join(
        s.strip()
        for s in wrapper
        if len(s.strip()) > 50
    )

    return text


def get_tracks_by_genre(genre, cursor):
    cursor.execute("""
        SELECT artist, title, file_id
        FROM music
        WHERE genre = ?
        ORDER BY id
    """, (genre,))
    return cursor.fetchall()
