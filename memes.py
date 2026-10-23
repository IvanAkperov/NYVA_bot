"""
ИИ-мемы про вашу переписку: берём классический шаблон с imgflip,
нейросеть придумывает подпись по последним сообщениям чата, Pillow рисует текст.
Если Pillow не установлен — функция вернёт None и бот пришлёт обычный мем.
"""
import asyncio
import io
import logging
import os
import random
import textwrap

import requests

import ai

log = logging.getLogger("memes")

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_OK = True
except ImportError:  # pip install pillow
    PIL_OK = False

HEADERS = {"user-agent": "Mozilla/5.0"}
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\impact.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]
# классика с подписью «сверху/снизу»
CLASSIC = {
    "One Does Not Simply", "Futurama Fry", "Ancient Aliens", "Success Kid", "Roll Safe Think About It",
    "Leonardo Dicaprio Cheers", "Grumpy Cat", "Bad Luck Brian", "Disaster Girl", "Hide the Pain Harold",
    "Matrix Morpheus", "Third World Skeptical Kid", "Evil Toddler", "Am I The Only One Around Here",
    "Mugatu So Hot Right Now", "Y U No", "Sad Pablo Escobar", "Waiting Skeleton", "Surprised Pikachu",
    "Monkey Puppet", "Doge", "Philosoraptor", "Unsettled Tom", "Grandma Finds The Internet",
    "Laughing Leo", "The Rock Driving", "Picard Wtf", "X, X Everywhere", "Captain Picard Facepalm",
}

_templates_cache: list | None = None


def _font_path() -> str | None:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _get_templates() -> list:
    global _templates_cache
    if _templates_cache is None:
        memes = requests.get("https://api.imgflip.com/get_memes", headers=HEADERS, timeout=10).json()["data"]["memes"]
        classic = [m for m in memes if m["name"] in CLASSIC]
        two_box = [m for m in memes if m.get("box_count") == 2]
        _templates_cache = classic if len(classic) >= 5 else two_box
    return _templates_cache


def _download(url: str) -> bytes:
    return requests.get(url, headers=HEADERS, timeout=15).content


def _fit_text(draw, text, font_path, img_w, max_h):
    size = max(18, img_w // 9)
    while size >= 14:
        font = ImageFont.truetype(font_path, size)
        avg_char = max(1, draw.textlength("Ж", font=font))
        width_chars = max(8, int(img_w * 0.94 / avg_char))
        lines = textwrap.wrap(text, width=width_chars) or [""]
        line_h = font.getbbox("Жy")[3] + 4
        if len(lines) * line_h <= max_h and all(draw.textlength(l, font=font) <= img_w * 0.96 for l in lines):
            return font, lines, line_h
        size -= 2
    font = ImageFont.truetype(font_path, 14)
    return font, textwrap.wrap(text, width=40), font.getbbox("Жy")[3] + 4


def render_meme(image_bytes: bytes, top: str, bottom: str) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if img.width < 500:
        ratio = 500 / img.width
        img = img.resize((500, int(img.height * ratio)))
    draw = ImageDraw.Draw(img)
    font_path = _font_path()
    if not font_path:
        raise RuntimeError("Не найден шрифт с кириллицей")

    def put(text, from_top: bool):
        if not text:
            return
        font, lines, line_h = _fit_text(draw, text.upper(), font_path, img.width, int(img.height * 0.3))
        stroke = max(2, font.size // 12)
        y = 8 if from_top else img.height - len(lines) * line_h - 12
        for line in lines:
            w = draw.textlength(line, font=font)
            draw.text(((img.width - w) / 2, y), line, font=font, fill="white", stroke_width=stroke, stroke_fill="black")
            y += line_h

    put(top, True)
    put(bottom, False)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


async def make_chat_meme(transcript: str, knowledge: str) -> bytes | None:
    """Возвращает JPEG мема про чат или None, если что-то не получилось."""
    if not PIL_OK or not _font_path():
        return None
    try:
        templates = await asyncio.to_thread(_get_templates)
        candidates = random.sample(templates, min(8, len(templates)))
        names = [t["name"] for t in candidates]
        about = transcript or "Переписки за сегодня нет — сделай мем про кого-то из компании по фактам о нём."
        data = await ai.chat_json([
            {"role": "system", "content": (
                "Ты делаешь смешные мемы для чата друзей. Вот кто они:\n" + knowledge +
                "\n\nПиши подписи по-русски, коротко (до 60 символов каждая), в стиле интернет-мемов. "
                "Шути по-доброму, про конкретную ситуацию из чата. "
                'Верни JSON: {"template": "<точное имя шаблона из списка>", "top": "...", "bottom": "..."}'
            )},
            {"role": "user", "content": f"Шаблоны: {names}\n\nПоследние сообщения чата:\n{about}"},
        ], temperature=1.0, max_tokens=200)
        tpl = next((t for t in candidates if t["name"] == data.get("template")), random.choice(candidates))
        image = await asyncio.to_thread(_download, tpl["url"])
        return await asyncio.to_thread(render_meme, image, str(data.get("top", ""))[:90], str(data.get("bottom", ""))[:90])
    except Exception as e:
        log.warning("meme failed: %r", e)
        return None
