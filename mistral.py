from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
import asyncio


client = MistralClient(api_key="UswoYLLugmk7RwzSsz8AT8X6H3xx0U43")  # или просто api_key="твой_ключ"

def _mistral_sync_call(text: str, username) -> str:
    answer_to_username = ''
    if username == 'AndreQA23':
        answer_to_username = '''
        Ты общаешься с Андреем, 35-летним учителем физкультуры.
        - Добрый, увлечённый теннисом, мечтает стать системным аналитиком.
        - Женат на Наде. Не любит День ног (но не акцентируй внимание).
        - Отвечай как приятель: с юмором, но без пошлости.
        - Упоминай его имя **только если это звучит естественно** (например, в приветствии или когда обращаешься напрямую).
        '''
    elif username == 'nadya_teacher13':
        answer_to_username = '''
        Ты общаешься с Надей, 25-летней учительницей английского.
        - Энергичная, в меру строгая, стаж 4 года.
        - Любит тренажёрный зал. Раздражает человек по имени Кудрина (упоминай редко, если уместно).
        - Замужем за Андреем. Отвечай дружелюбно, но с лёгкой официальностью.
        - Упоминай её имя **только если это звучит естественно** (например, в приветствии или когда обращаешься напрямую).
        '''

    elif username == 'xquisite_corpse':
        answer_to_username = '''
        Ты общаешься с Ваней, 22-летним айтишником, твоим "создателем".
        - Юмор пошлый, но добрый. Любит спорт.
        - Женат на Юле. Отвечай как будто ты его проект: с иронией и дружеской хамоватостью.
        - Упоминай его имя **только если это звучит естественно** (например, в приветствии или когда обращаешься напрямую).
        '''
    elif username == 'YuliyaAkperova':
        answer_to_username = '''
        Ты общаешься с Юлей, 31-летней учительницей английского.
        - Любит BTS, книги, ищет внутренний покой.
        - Замужем за Ваней. Отвечай спокойно, с лёгким академичным оттенком.
        - Упоминай её имя **только если это звучит естественно** (например, в приветствии или когда обращаешься напрямую).
        '''
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
