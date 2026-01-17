import sqlite3

conn = sqlite3.connect('nyvaBot.db')
cursor = conn.cursor()
# cursor.execute("""
# CREATE TABLE IF NOT EXISTS reminders (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     user_id INTEGER NOT NULL,        -- добавили user_id для отправки сообщений
#     username TEXT,                   -- для логов, необязательно
#     text TEXT NOT NULL,
#     remind_time TEXT NOT NULL,       -- ISO формат: "2026-01-17 18:30:00"
#     notified INTEGER DEFAULT 0       -- 0 = не отправлено, 1 = отправлено
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
# cursor.execute("INSERT INTO music (genre, title, artist, file_id) VALUES (?, ?, ?, ?)", ('edm', 'Every time we touch', 'The plot in you', 'CQACAgIAAxkBAAIBqmlrppxK80GtTxZqCF-lwpSpfVLbAAJDkAACtVBgS4JXH752OxzaOAQ'))
# conn.commit()
def send_all_data_from_db():
    data = cursor.execute("SELECT * FROM users").fetchall()
    return data

# new_file_id = "CQACAgIAAxkBAAIBqmlrppxK80GtTxZqCF-lwpSpfVLbAAJDkAACtVBgS4JXH752OxzaOAQ"
#
# # Обновляем только по title
# cursor.execute("""
#     UPDATE music
#     SET file_id = ?
#     WHERE title = ?
# """, (new_file_id, "Feel Nothing"))
#
# conn.commit()
# print(f"Обновлено {cursor.rowcount} строк")
# print(f"Обновлено {cursor.rowcount} строк")
# cursor.execute("""
# DELETE FROM music
# WHERE artist LIKE '%Skillet%'
#    OR artist LIKE '%Disturbed%';
# """)
#
# conn.commit()
# print(cursor.execute("""SELECT * FROM reminders;""").fetchall())

# cursor.execute("""ALTER TABLE reminders ADD COLUMN reply_message_id INTEGER;""")