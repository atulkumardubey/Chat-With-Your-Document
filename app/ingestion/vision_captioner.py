from app.llm.nvidia_client import caption_image


def caption_chart_image(image_bytes: bytes, mime_type: str = "image/png") -> str:
    return caption_image(image_bytes, mime_type)
