from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
import asyncio


client = MistralClient(api_key="UswoYLLugmk7RwzSsz8AT8X6H3xx0U43")  # или просто api_key="твой_ключ"

def _mistral_sync_call(text: str) -> str:
    response = client.chat(
        model="mistral-small-latest",
        messages=[
            ChatMessage(
                role="system",
                content="Ты дружелюбный бро-бот. Отвечай на русском, с юмором, кратко."
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


async def send_message_from_mistral_bot(text: str) -> str:
    return await asyncio.to_thread(_mistral_sync_call, text)