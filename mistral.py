from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
import asyncio


client = MistralClient(api_key="UswoYLLugmk7RwzSsz8AT8X6H3xx0U43")  # или просто api_key="твой_ключ"

def _mistral_sync_call(text: str, username) -> str:
    answer_to_username = ''
    if username == 'AndreQA23':
        answer_to_username = 'Ты отвечаешь Андрею. Используй его имя в ответе, учитывая, что он - добрый учитель физкультуры.'
    elif username == 'nadya_teacher13':
        answer_to_username = 'Ты отвечаешь Наде. Используй её имя в ответе, учитывая, что она - молодая учительница английского, которая так и не сделала татуировку.'

    elif username == 'xquisite_corpse':
        answer_to_username = 'Ты отвечаешь Ване. Используй его имя в ответе, учитывая, что он - молодой и крутой айтишник который внедрил тебя в бота.'
    elif username == 'YuliyaAkperova':
        answer_to_username = 'Ты отвечаешь Юле. Используй ее имя в ответе, учитывая, что она - преподавательница английского в школе, любит bts и чтение книг.'
    response = client.chat(
        model="mistral-small-latest",
        messages=[
            ChatMessage(
                role="system",
                content=f"{answer_to_username}Ты нейтральный бот, любишь шутить остро и в тему. Отвечай на русском, кратко и по делу"
            ),
            ChatMessage(
                role="user",
                content=text  # ⚠️ СТРОКА. НЕ Message
            ),
        ],
        temperature=0.8,
        max_tokens=400,
    )

    return response.choices[0].message.content


async def send_message_from_mistral_bot(text: str, username) -> str:
    return await asyncio.to_thread(_mistral_sync_call, text, username)
