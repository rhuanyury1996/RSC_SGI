"""Avatar helpers — guarda foto redimensionada no banco (data URI) para sobreviver no Render."""

from __future__ import annotations

import base64
import io
from typing import BinaryIO

from PIL import Image, ImageOps


def encode_avatar(uploaded_file: BinaryIO, max_size: int = 320) -> str:
    """Converte upload em data URI JPEG pequeno o bastante para TextField."""
    uploaded_file.seek(0)
    with Image.open(uploaded_file) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"
