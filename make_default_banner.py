"""Gera assets/default_banner.png — banner padrão do tool (usado quando o usuário
não fornece um). 384x128, redimensionado p/ 96x32 na hora de gravar no gbi.hdr."""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 384, 128
img = Image.new("RGBA", (W, H), (16, 20, 40, 255))
d = ImageDraw.Draw(img)

# faixa diagonal de destaque
for x in range(W):
    t = x / W
    d.line([(x, 0), (x, H)], fill=(16 + int(40 * t), 20 + int(60 * t),
                                   60 + int(120 * t), 255))

# moldura
d.rectangle([4, 4, W - 5, H - 5], outline=(120, 200, 255, 255), width=3)


def font(sz):
    for name in ("arialbd.ttf", "arial.ttf", "segoeuib.ttf"):
        try:
            return ImageFont.truetype(name, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def centered(text, fnt, y, fill):
    bbox = d.textbbox((0, 0), text, font=fnt)
    w = bbox[2] - bbox[0]
    d.text(((W - w) // 2, y), text, font=fnt, fill=fill)


centered("DOL → ISO", font(58), 18, (255, 255, 255, 255))
centered("GameCube Loader", font(26), 84, (150, 210, 255, 255))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets",
                   "default_banner.png")
img.save(out)
print(">> escrito", out)
