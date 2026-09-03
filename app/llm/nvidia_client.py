import base64

from openai import OpenAI

from app.config import settings
from app.llm.prompts import CHART_CAPTION_PROMPT, SYSTEM_PROMPT

_client = OpenAI(base_url=settings.nvidia_base_url, api_key=settings.nvidia_api_key)


def chat_completion(user_prompt: str, temperature: float = 0.2) -> str:
    response = _client.chat.completions.create(
        model=settings.nvidia_llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


def caption_image(image_bytes: bytes, mime_type: str = "image/png") -> str:
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime_type};base64,{b64}"
    response = _client.chat.completions.create(
        model=settings.nvidia_vision_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": CHART_CAPTION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content or ""
