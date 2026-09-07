import base64
import re

from openai import OpenAI

from app.config import settings
from app.llm.prompts import CHART_CAPTION_PROMPT, SYSTEM_PROMPT

_client = OpenAI(base_url=settings.nvidia_base_url, api_key=settings.nvidia_api_key)

# Reasoning models (e.g. nemotron, deepseek-r1) sometimes leak their chain-of-thought
# into the message content wrapped in <think> tags or prefixed with "thinking process" text.
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINKING_PREFIX_RE = re.compile(
    r"^.*?(?:here(?:'s| is)(?: a)? thinking(?: process)?|"
    r"thinking process|reasoning process|internal reasoning).*?\n",
    re.DOTALL | re.IGNORECASE,
)


def _strip_thinking(text: str) -> str:
    """Remove chain-of-thought sections that some reasoning models include in their output."""
    text = _THINK_TAG_RE.sub("", text)
    # If the response starts with an exposed thinking-process header, drop everything up to
    # the first blank line that follows (the actual answer starts after the gap).
    match = _THINKING_PREFIX_RE.match(text)
    if match:
        remainder = text[match.end():]
        # Skip any leading blank lines left after stripping the header block.
        text = remainder.lstrip("\n")
    return text.strip()


def chat_completion(user_prompt: str, temperature: float = 0.2) -> str:
    response = _client.chat.completions.create(
        model=settings.nvidia_llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )
    raw = response.choices[0].message.content or ""
    return _strip_thinking(raw)


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
