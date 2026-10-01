# -*- coding: utf-8 -*-
"""
generate_branding_assets.py
---------------------------
مولد الهوية البصرية الرسمية لتطبيق 'رتّب' (Rateb):
- assets/branding/logo_mark.png (1024x1024)
- assets/branding/logo_horizontal.png (1600x500)
- assets/icon.png (512x512)
- assets/logo.png (1024x1024)
- assets/presplash.png (768x1376)
"""

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ASSETS_DIR = Path("assets")
BRANDING_DIR = ASSETS_DIR / "branding"
BRANDING_DIR.mkdir(parents=True, exist_ok=True)

# ألوان الهوية البصرية الحديثة
COLOR_DEEP_NAVY = (15, 23, 42, 255)       # #0F172A
COLOR_DARK_INDIGO = (30, 27, 75, 255)     # #1E1B4B
COLOR_VIOLET = (109, 40, 217, 255)        # #6D28D9
COLOR_CYAN = (6, 182, 212, 255)           # #06B6D4
COLOR_SKY = (56, 189, 248, 255)           # #38BDF8
COLOR_EMERALD = (16, 185, 129, 255)       # #10B981
COLOR_WHITE = (255, 255, 255, 255)
COLOR_TEXT_DIM = (148, 163, 184, 255)


def draw_linear_gradient(draw: ImageDraw.ImageDraw, bbox: tuple[int, int, int, int], col_a: tuple, col_b: tuple, angle: float = 45):
    x0, y0, x1, y1 = bbox
    w = max(1, x1 - x0)
    h = max(1, y1 - y0)
    rad = math.radians(angle)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    max_len = math.sqrt(w*w + h*h)
    
    # رسم خطوط ناعمة
    for y in range(y0, y1, 2):
        for x in range(x0, x1, 2):
            proj = ((x - x0) * cos_a + (y - y0) * sin_a) / max_len
            proj = max(0.0, min(1.0, proj))
            r = int(col_a[0] + proj * (col_b[0] - col_a[0]))
            g = int(col_a[1] + proj * (col_b[1] - col_a[1]))
            b = int(col_a[2] + proj * (col_b[2] - col_a[2]))
            draw.rectangle([x, y, x+1, y+1], fill=(r, g, b, 255))


def draw_modern_logo_mark(size: int = 1024) -> Image.Image:
    """رسم رمز اللوجو المودرن مع بطاقات الوسائط المصنفة وورقة الاختبار"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    scale = size / 1024.0
    cx = size // 2
    cy = size // 2

    # 1. إشعاع ضوئي خلفي ناعم
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_radius = int(320 * scale)
    glow_draw.ellipse(
        [cx - glow_radius, cy - glow_radius, cx + glow_radius, cy + glow_radius],
        fill=(109, 40, 217, 70),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(int(50 * scale)))
    img.paste(glow, (0, 0), glow)

    # 2. بطاقة 1: وسائط الفيديو (خلفية مائلة لليسار بلون نيلي/بنفسجي)
    card1_w = int(420 * scale)
    card1_h = int(520 * scale)
    c1_img = Image.new("RGBA", (card1_w, card1_h), (0, 0, 0, 0))
    c1_draw = ImageDraw.Draw(c1_img)
    c1_draw.rounded_rectangle(
        [0, 0, card1_w, card1_h],
        radius=int(60 * scale),
        fill=(49, 46, 129, 230),
        outline=(99, 102, 241, 180),
        width=int(4 * scale),
    )
    # رمز تشغيل فيديو صغير
    tri_c = (card1_w // 2, int(150 * scale))
    ts = int(40 * scale)
    c1_draw.polygon([
        (tri_c[0] - ts // 2, tri_c[1] - ts),
        (tri_c[0] - ts // 2, tri_c[1] + ts),
        (tri_c[0] + ts, tri_c[1]),
    ], fill=(165, 180, 252, 220))
    
    c1_rot = c1_img.rotate(16, expand=True, resample=Image.Resampling.BICUBIC)
    img.paste(c1_rot, (cx - int(340 * scale), cy - int(320 * scale)), c1_rot)

    # 3. بطاقة 2: ورقة الاختبار والامتحان (مائلة لليمين بلون فاتح عاجي مع أسطر كتابة ورمز A+)
    card2_w = int(440 * scale)
    card2_h = int(540 * scale)
    c2_img = Image.new("RGBA", (card2_w, card2_h), (0, 0, 0, 0))
    c2_draw = ImageDraw.Draw(c2_img)
    c2_draw.rounded_rectangle(
        [0, 0, card2_w, card2_h],
        radius=int(60 * scale),
        fill=(248, 250, 252, 245),
        outline=(203, 213, 225, 200),
        width=int(4 * scale),
    )
    # أسطر نص الامتحان
    for i in range(5):
        ly = int((140 + i * 55) * scale)
        lw = max(int(40 * scale), int(card2_w - int(140 * scale) - (i % 2) * int(40 * scale)))
        c2_draw.rounded_rectangle(
            [int(50 * scale), ly, int(50 * scale) + lw, ly + max(2, int(14 * scale))],
            radius=max(2, int(7 * scale)),
            fill=(203, 213, 225, 220),
        )
    # ترويسة الامتحان ودرجة A+
    c2_draw.ellipse(
        [card2_w - int(130 * scale), int(60 * scale), card2_w - int(60 * scale), int(130 * scale)],
        fill=(16, 185, 129, 230),
    )
    c2_rot = c2_img.rotate(-14, expand=True, resample=Image.Resampling.BICUBIC)
    img.paste(c2_rot, (cx - int(120 * scale), cy - int(340 * scale)), c2_rot)

    # 4. بطاقة 3: البطاقة الأمامية الرئيسية (صور وفرز ذكي بتدرج سماوي متألق)
    card3_w = int(480 * scale)
    card3_h = int(580 * scale)
    c3_img = Image.new("RGBA", (card3_w, card3_h), (0, 0, 0, 0))
    c3_draw = ImageDraw.Draw(c3_img)
    
    # تدرج متدرج أنيق للبطاقة الأمامية
    c3_draw.rounded_rectangle(
        [0, 0, card3_w, card3_h],
        radius=int(75 * scale),
        fill=(14, 165, 233, 250),
        outline=(255, 255, 255, 220),
        width=int(6 * scale),
    )
    # أيقونة فرز الطبقات الماسية في الوسط
    mid_x = card3_w // 2
    mid_y = int(240 * scale)
    dia_s = int(80 * scale)
    # طبقة 1
    c3_draw.polygon([
        (mid_x, mid_y - dia_s),
        (mid_x + dia_s + int(30 * scale), mid_y),
        (mid_x, mid_y + dia_s),
        (mid_x - dia_s - int(30 * scale), mid_y),
    ], fill=(255, 255, 255, 240))
    # طبقة 2 سفلى
    mid_y2 = mid_y + int(90 * scale)
    c3_draw.polygon([
        (mid_x, mid_y2 - int(50 * scale)),
        (mid_x + dia_s + int(30 * scale), mid_y2),
        (mid_x, mid_y2 + int(50 * scale)),
        (mid_x - dia_s - int(30 * scale), mid_y2),
    ], fill=(224, 242, 254, 180))

    # نجوم الذكاء الاصطناعي (Sparkles)
    for sx, sy, sr in [(int(100*scale), int(120*scale), int(22*scale)), (card3_w - int(110*scale), int(140*scale), int(28*scale))]:
        c3_draw.ellipse([sx-sr, sy-sr, sx+sr, sy+sr], fill=(255, 255, 255, 230))

    img.paste(c3_img, (cx - card3_w // 2, cy - card3_h // 2 + int(40 * scale)), c3_img)

    return img


def create_app_icon():
    """أيقونة التطبيق الرسمية 512x512 مع هوامش أمان"""
    size = 512
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)

    # خلفية ناعمة داكنة فاخرة (Squircle)
    margin = 16
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=110,
        fill=(15, 23, 42, 255),
        outline=(56, 189, 248, 120),
        width=4,
    )

    # شعار الشعار الداخلي
    mark = draw_modern_logo_mark(380)
    offset = (size - 380) // 2
    icon.paste(mark, (offset, offset - 4), mark)

    icon.save(ASSETS_DIR / "icon.png", format="PNG", optimize=True)
    print("✓ تم حفظ assets/icon.png بنجاح.")


def create_standalone_logo():
    """الشعار الرسمي 1024x1024 شفاف"""
    mark = draw_modern_logo_mark(1024)
    mark.save(ASSETS_DIR / "logo.png", format="PNG", optimize=True)
    mark.save(BRANDING_DIR / "logo_mark.png", format="PNG", optimize=True)
    print("✓ تم حفظ assets/logo.png و branding/logo_mark.png بنجاح.")


def create_presplash_screen():
    """شاشة البداية 768x1376 مستقلة كلياً عن الشعار"""
    w, h = 768, 1376
    splash = Image.new("RGBA", (w, h), COLOR_DEEP_NAVY)
    draw = ImageDraw.Draw(splash)

    # تدرج خلفي أنيق من الأزرق العميق إلى النيلي
    for y in range(0, h, 4):
        ratio = y / h
        r = int(15 + ratio * 20)
        g = int(23 + ratio * 15)
        b = int(42 + ratio * 45)
        draw.rectangle([0, y, w, y + 4], fill=(r, g, b, 255))

    # شعاع ضوئي ناعم في المركز
    cx, cy = w // 2, int(h * 0.44)
    glow_r = 300
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow)
    g_draw.ellipse([cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r], fill=(56, 189, 248, 35))
    glow = glow.filter(ImageFilter.GaussianBlur(60))
    splash.paste(glow, (0, 0), glow)

    # رسم الشعار في المركز بحجم متناسق
    mark = draw_modern_logo_mark(420)
    splash.paste(mark, (cx - 210, cy - 240), mark)

    # عنوان شاشة البداية النصي بتصميم نظيف
    # خط افتراضي أنيق إذا لم تتوفر خطوط إضافية
    title_y = cy + 220
    draw.text((cx, title_y), "Rateb • رتّب", fill=COLOR_WHITE, anchor="mm", font_size=42)
    draw.text((cx, title_y + 50), "AI Media & Exam Sorter", fill=COLOR_SKY, anchor="mm", font_size=24)
    draw.text((cx, h - 80), "v2.0 • Offline First", fill=COLOR_TEXT_DIM, anchor="mm", font_size=18)

    splash.save(ASSETS_DIR / "presplash.png", format="PNG", optimize=True)
    print("✓ تم حفظ assets/presplash.png (شاشة بداية مستقلة ومميزة).")


def create_horizontal_logo():
    """شعار أفقي عريض 1600x500 للترويسة والموقع"""
    w, h = 1600, 500
    logo_h = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(logo_h)

    # الرمز على اليسار
    mark = draw_modern_logo_mark(400)
    logo_h.paste(mark, (60, 50), mark)

    # النصوص على اليمين
    draw.text((500, 180), "رتّب", fill=COLOR_WHITE, anchor="lm", font_size=110)
    draw.text((750, 190), "Rateb", fill=COLOR_SKY, anchor="lm", font_size=75)
    draw.text((505, 300), "الفرز والتنظيم الذكي للوسائط وأوراق الاختبارات", fill=COLOR_TEXT_DIM, anchor="lm", font_size=32)

    logo_h.save(BRANDING_DIR / "logo_horizontal.png", format="PNG", optimize=True)
    print("✓ تم حفظ branding/logo_horizontal.png بنجاح.")


if __name__ == "__main__":
    create_standalone_logo()
    create_app_icon()
    create_presplash_screen()
    create_horizontal_logo()
    print("اكتمل إنشاء كافة الأصول البصرية الرسمية بنجاح!")
