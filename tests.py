import sqlite3

conn = sqlite3.connect('nyvaBot.db')
cursor = conn.cursor()
# cursor.execute("""CREATE TABLE music (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     genre TEXT,
#     title TEXT,
#     artist TEXT,
#     file_id TEXT
# );
# """)
# cursor.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, zodiac TEXT)""")
# conn.commit()
# NAMES_AND_ZODIAC = {
#     'ваня': 'pisces',
#     'юля': 'leo',
#     'андрей': 'virgo',
#     'надя': 'taurus'
# }
#
# # соответствие username
# USERNAMES = {
#     'ваня': '@xquisite_corpse',
#     'юля': '@YuliyaAkperova',
#     'андрей': '@AndreQA23',
#     'надя': '@nadya_teacher13'
# }
#
# # заполняем базу
# for name, zodiac in NAMES_AND_ZODIAC.items():
#     username = USERNAMES.get(name)
#     cursor.execute("REPLACE INTO users (user_id, username, zodiac) VALUES (?, ?, ?)", (None, username, zodiac))
#
# conn.commit()
#
# # проверка
# cursor.execute("SELECT * FROM users")
# for row in cursor.fetchall():
#     print(row)


# pop lose yourself eminem  CQACAgIAAxkBAAIBP2lrcw3dxp2pJbFRocJpFWW6EapQAAIbjAACtVBYS_VJjlvffdqjOAQ
cursor.execute("INSERT INTO music (genre, title, artist, file_id) VALUES (?, ?, ?, ?)", ('edm', 'Every time we touch', 'Cascada', 'CQACAgIAAxkBAAIBgWlrm6jP2v7RqpcPWUZ6crLj6fsvAAK1jwACtVBYSwW23powLJOeOAQ'))
conn.commit()
def send_all_data_from_db():
    data = cursor.execute("SELECT * FROM users").fetchall()
    return data


# cursor.execute("""
# DELETE FROM music
# WHERE artist LIKE '%Skillet%'
#    OR artist LIKE '%Disturbed%';
# """)
#
# conn.commit()