from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def generate_membership_card(
    name: str,
    user_id: int,
    status_text: str,
    expiry_ethiopian: str,
    template_path: str = "template.png",
    font_path: str = "Nyala.ttf",
) -> io.BytesIO:
    img = Image.open(template_path).convert("RGBA") if Path(template_path).exists() else Image.new("RGBA", (900, 550), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, 36) if Path(font_path).exists() else ImageFont.load_default()

    draw.text((50, 80), "Membership Card", fill="black", font=font)
    draw.text((50, 170), f"Name: {name}", fill="black", font=font)
    draw.text((50, 230), f"User ID: {user_id}", fill="black", font=font)
    draw.text((50, 290), f"Status: {status_text}", fill="black", font=font)
    draw.text((50, 350), f"Expire (ETH): {expiry_ethiopian}", fill="black", font=font)

    output = io.BytesIO()
    output.name = f"membership_{user_id}.png"
    img.save(output, format="PNG")
    output.seek(0)
    return output
