"""Generate the three original sample images used by Offline Demo Mode.

The three images required by Q.3 (education, technology, everyday objects) are
drawn programmatically with Pillow so that this project ships only *original*
image assets. No third-party photograph is copied, so there is no licence
problem and the exact contents of every picture are known and documented.

Run:
    python make_sample_images.py

Output (also the ground truth used by the evaluator):
    images/education.jpg          student studying: laptop, books, notebook, pen, mug
    images/technology.jpg         computer workspace: monitor, laptop, keyboard, mouse
    images/everyday_objects.jpg   desk objects: bottle, notebook, pen, smartphone, glasses

Style notes: flat vector-style illustrations, and **no rendered text anywhere**
inside the pictures. That is deliberate - it means any claim about "readable
text" in a generated description can honestly be flagged as unverifiable by the
evaluator instead of being an unknowable property of a stock photo.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw

W, H = 1280, 854
IMAGES_DIR = Path(__file__).parent / "images"

# ---------------------------------------------------------------- palette ----
WALL = (223, 231, 243)
WALL_2 = (238, 243, 250)
DESK = (192, 139, 92)
DESK_EDGE = (170, 120, 76)
TABLE = (214, 184, 138)
TABLE_EDGE = (188, 156, 112)
SKIN = (242, 201, 163)
HAIR = (58, 42, 34)
SWEATER = (74, 111, 212)
SLEEVE = (64, 98, 192)
DEVICE = (43, 49, 59)
DEVICE_2 = (31, 41, 55)
SCREEN = (234, 242, 255)
INK = (31, 41, 55)
METAL = (100, 116, 139)


def rounded(d: ImageDraw.ImageDraw, box, radius: int, fill=None, outline=None, width: int = 3):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def cap_line(d: ImageDraw.ImageDraw, p0, p1, colour, width: int):
    """A line with round caps (Pillow draws square caps, which looks like an arrow)."""
    d.line((p0, p1), fill=colour, width=width)
    r = width / 2
    for x, y in (p0, p1):
        d.ellipse((x - r, y - r, x + r, y + r), fill=colour)


def shadow(img: Image.Image, box, radius: int = 16, offset: int = 7, alpha: int = 40):
    """Subtle drop shadow: translucent rounded rectangle composited under an object."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = box
    d.rounded_rectangle((x0 + offset, y0 + offset, x1 + offset, y1 + offset), radius=radius,
                        fill=(25, 35, 50, alpha))
    img.alpha_composite(layer)


def stamp(img: Image.Image, layer: Image.Image, angle: float, centre) -> None:
    """Paste an RGBA layer rotated by `angle` degrees with its centre at `centre`."""
    rotated = layer.rotate(angle, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(rotated, (int(centre[0] - rotated.width / 2), int(centre[1] - rotated.height / 2)))


def pen_layer(length: int = 360, thickness: int = 15) -> Image.Image:
    """A ballpoint pen drawn horizontally on its own layer: body, grip, pocket clip, nib."""
    layer = Image.new("RGBA", (length + 60, thickness * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    mid = layer.height // 2
    rounded(d, (10, mid - thickness // 2, 10 + length, mid + thickness // 2), thickness // 2, fill=INK)
    rounded(d, (10, mid - thickness // 2, 96, mid + thickness // 2), 6, fill=(71, 85, 105))   # grip
    rounded(d, (110, mid - thickness // 2 - 9, 250, mid - thickness // 2 - 3), 3, fill=(148, 163, 184))  # clip
    d.polygon(((10 + length, mid - thickness // 2), (10 + length + 30, mid), (10 + length, mid + thickness // 2)),
              fill=INK)                                                                       # nib
    return layer


def new_canvas(wall=WALL) -> Image.Image:
    img = Image.new("RGBA", (W, H), wall + (255,))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 120), fill=WALL_2)
    return img


def save(img: Image.Image, name: str) -> Path:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    path = IMAGES_DIR / name
    img.convert("RGB").save(path, "JPEG", quality=92, optimize=True)
    return path


def desk(img: Image.Image, top: int, colour, edge) -> None:
    d = ImageDraw.Draw(img)
    d.rectangle((0, top, W, H), fill=colour)
    d.rectangle((0, top, W, top + 16), fill=(min(255, colour[0] + 14), min(255, colour[1] + 14),
                                              min(255, colour[2] + 14)))
    d.rectangle((0, H - 64, W, H), fill=edge)


# ------------------------------------------------------- scene 1: education --
def education() -> Image.Image:
    img = new_canvas()
    d = ImageDraw.Draw(img)

    # window on the wall (sky, sun, mullions)
    rounded(d, (70, 60, 360, 300), 12, fill=(188, 214, 240), outline=(255, 255, 255), width=10)
    d.ellipse((282, 92, 332, 142), fill=(250, 219, 126))
    d.line((215, 66, 215, 294), fill=(255, 255, 255), width=8)
    d.line((76, 180, 354, 180), fill=(255, 255, 255), width=8)

    # notice board (blank - ruled lines only, deliberately no rendered text)
    rounded(d, (880, 80, 1190, 320), 10, fill=(255, 255, 255), outline=(196, 160, 116), width=8)
    for i, y in enumerate((130, 175, 220, 265)):
        w = 250 if i != 3 else 150
        rounded(d, (915, y, 915 + w, y + 10), 5, fill=(206, 214, 226))

    # seated student behind the desk
    shadow(img, (612, 340, 792, 620), 52, 8, 45)
    rounded(d, (612, 352, 792, 626), 52, fill=SWEATER)                 # torso
    d.ellipse((628, 200, 776, 348), fill=HAIR)                         # hair mass
    d.ellipse((636, 244, 768, 350), fill=SKIN)                         # face over the hair
    d.ellipse((624, 216, 664, 322), fill=HAIR)                         # side hair (left)
    d.ellipse((740, 216, 780, 322), fill=HAIR)                         # side hair (right)
    rounded(d, (592, 420, 664, 604), 34, fill=SLEEVE)                  # left sleeve
    rounded(d, (740, 420, 812, 604), 34, fill=SLEEVE)                  # right sleeve

    # desk (drawn after the student so that the student sits behind it)
    desk(img, 600, DESK, DESK_EDGE)

    # laptop on the desk
    shadow(img, (300, 396, 620, 618), 12, 7, 45)
    rounded(d, (300, 396, 620, 584), 12, fill=SCREEN, outline=DEVICE, width=9)
    rounded(d, (320, 414, 600, 566), 6, fill=(214, 226, 245))
    for y, w in ((438, 236), (472, 206), (506, 150)):
        rounded(d, (338, y, 338 + w, y + 12), 5, fill=(140, 168, 210))
    rounded(d, (272, 584, 648, 606), 8, fill=DEVICE)                   # keyboard deck
    rounded(d, (250, 598, 670, 618), 8, fill=DEVICE_2)                 # laptop base

    # hands resting in front of the laptop
    d.ellipse((378, 560, 438, 612), fill=SKIN)
    d.ellipse((498, 560, 558, 612), fill=SKIN)

    # open notebook with spiral binding + pen
    shadow(img, (660, 650, 860, 740), 10, 7, 45)
    rounded(d, (660, 650, 860, 740), 8, fill=(255, 255, 255), outline=(203, 213, 225), width=4)
    d.line((760, 650, 760, 740), fill=(203, 213, 225), width=4)
    for y in (672, 696, 720):
        d.line((678, y, 748, y), fill=(190, 202, 218), width=5)
        d.line((774, y, 844, y), fill=(190, 202, 218), width=5)
    for i in range(6):
        x = 668 + i * 18
        d.ellipse((x, 638, x + 12, 652), outline=(148, 163, 184), width=3)
    cap_line(d, (632, 762), (872, 686), INK, 9)                        # pen body
    d.polygon(((872, 686), (896, 679), (876, 697)), fill=INK)          # pen nib

    # stack of books
    for y0, colour in ((616, (192, 57, 43)), (644, (39, 174, 96)), (672, (241, 196, 15))):
        rounded(d, (900, y0, 1080, y0 + 26), 6, fill=colour)
        d.rectangle((906, y0 + 20, 1074, y0 + 26), fill=(255, 255, 255, 60))
    rounded(d, (900, 698, 1080, 712), 5, fill=(120, 53, 15))           # base board of the stack

    # mug with steam
    shadow(img, (1110, 620, 1194, 710), 14, 7, 45)
    rounded(d, (1110, 620, 1194, 710), 16, fill=(246, 248, 252), outline=(203, 213, 225), width=5)
    d.arc((1178, 640, 1228, 690), 300, 60, fill=(203, 213, 225), width=10)
    for x in (1128, 1152, 1174):
        d.arc((x, 570, x + 28, 614), 0, 180, fill=(255, 255, 255), width=6)

    # desk lamp (left)
    d.ellipse((58, 742, 178, 792), fill=METAL)
    d.line((118, 752, 118, 456), fill=METAL, width=13)
    d.line((118, 456, 214, 424), fill=METAL, width=13)
    d.polygon(((206, 396), (296, 420), (292, 470), (202, 446)), fill=(241, 196, 15))
    return img


# ------------------------------------------------------ scene 2: technology --
def technology() -> Image.Image:
    img = new_canvas()
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 150), fill=(226, 233, 242))

    # wall socket
    rounded(d, (1160, 300, 1214, 358), 8, fill=(246, 248, 252), outline=(203, 213, 225), width=4)

    # desk surface
    desk(img, 600, (154, 163, 176), (124, 133, 148))
    d.rectangle((0, 600, W, 622), fill=(196, 203, 213))

    # external monitor with a bar chart and a line graph (no text)
    shadow(img, (150, 120, 800, 520), 16, 9, 45)
    rounded(d, (150, 120, 800, 500), 16, fill=DEVICE_2)
    rounded(d, (176, 146, 774, 474), 8, fill=(226, 235, 248))
    for i, (x, h) in enumerate(((216, 90), (286, 150), (356, 120), (426, 210), (496, 170), (566, 250), (636, 130))):
        rounded(d, (x, 430 - h, x + 46, 430), 6, fill=(59, 130, 246) if i % 2 == 0 else (96, 165, 250))
    d.line((210, 432, 700, 432), fill=METAL, width=6)
    d.line((216, 236, 300, 214, 380, 250, 470, 196, 560, 232, 660, 186),
           fill=(239, 68, 68), width=8, joint="curve")
    rounded(d, (430, 500, 520, 596), 8, fill=DEVICE)                   # stand
    rounded(d, (336, 586, 614, 610), 10, fill=DEVICE_2)                # base

    # laptop
    shadow(img, (820, 300, 1180, 600), 12, 8, 45)
    rounded(d, (820, 300, 1180, 536), 12, fill=SCREEN, outline=DEVICE, width=9)
    rounded(d, (842, 322, 1158, 516), 6, fill=(214, 226, 245))
    rounded(d, (862, 344, 1000, 402), 6, fill=(148, 176, 216))
    rounded(d, (862, 420, 1130, 438), 6, fill=(190, 206, 228))
    rounded(d, (862, 454, 1090, 472), 6, fill=(190, 206, 228))
    rounded(d, (790, 536, 1210, 566), 8, fill=DEVICE)
    rounded(d, (768, 558, 1232, 580), 8, fill=DEVICE_2)

    # keyboard with a key grid
    shadow(img, (240, 640, 720, 742), 12, 8, 45)
    rounded(d, (240, 640, 720, 742), 14, fill=(233, 236, 241), outline=(203, 213, 225), width=4)
    for row in range(4):
        for col in range(12):
            x = 262 + col * 37
            y = 660 + row * 20
            rounded(d, (x, y, x + 28, y + 14), 4, fill=(255, 255, 255), outline=(214, 222, 232), width=2)

    # mouse
    shadow(img, (768, 636, 900, 752), 60, 8, 45)
    d.ellipse((768, 636, 900, 752), fill=(245, 247, 250), outline=(203, 213, 225), width=5)
    d.line((834, 640, 834, 692), fill=(203, 213, 225), width=5)
    rounded(d, (824, 646, 844, 666), 6, fill=(148, 163, 184))

    # coffee mug
    shadow(img, (952, 646, 1046, 742), 16, 8, 45)
    rounded(d, (952, 646, 1046, 742), 16, fill=(255, 255, 255), outline=(203, 213, 225), width=5)
    d.arc((1030, 672, 1088, 722), 300, 60, fill=(203, 213, 225), width=11)

    # potted plant (in front, at the right edge)
    d.polygon(((1150, 700), (1266, 700), (1246, 788), (1170, 788)), fill=(196, 118, 76))
    d.ellipse((1140, 684, 1276, 716), fill=(214, 132, 86))
    for dx, dy in ((-26, -66), (6, -96), (36, -62), (0, -42)):
        d.ellipse((1208 + dx - 26, 686 + dy - 30, 1208 + dx + 26, 686 + dy + 34), fill=(34, 197, 94))

    # cables
    cap_line(d, (700, 592), (660, 648), (71, 85, 105), 8)
    d.line((1130, 592, 1160, 648), fill=(71, 85, 105), width=8)

    # smartphone at the left edge of the desk
    shadow(img, (56, 610, 186, 776), 20, 8, 45)
    rounded(d, (56, 610, 186, 776), 20, fill=DEVICE_2)
    rounded(d, (70, 628, 172, 758), 12, fill=(56, 189, 248))
    for i in range(3):
        rounded(d, (86, 652 + i * 34, 156, 676 + i * 34), 6, fill=(224, 242, 254))
    return img


# ------------------------------------------------ scene 3: everyday objects --
def everyday_objects() -> Image.Image:
    img = new_canvas()
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 470), fill=(232, 238, 246))

    # table
    d.rectangle((0, 470, W, H), fill=TABLE)
    d.rectangle((0, 470, W, 490), fill=(230, 203, 162))
    d.rectangle((0, H - 70, W, H), fill=TABLE_EDGE)

    # water bottle
    shadow(img, (186, 346, 286, 618), 30, 7, 45)
    rounded(d, (170, 340, 290, 618), 30, fill=(158, 214, 233))
    rounded(d, (206, 286, 254, 350), 12, fill=(158, 214, 233))          # neck
    rounded(d, (200, 258, 260, 296), 10, fill=(47, 111, 159))           # cap
    rounded(d, (170, 424, 290, 502), 8, fill=(255, 255, 255))           # label band
    d.line((182, 376, 278, 376), fill=(224, 245, 252), width=6)
    d.line((182, 540, 278, 540), fill=(224, 245, 252), width=6)

    # notebook (closed, elastic band, blank label)
    shadow(img, (360, 536, 700, 700), 12, 8, 45)
    rounded(d, (360, 536, 700, 700), 12, fill=(233, 79, 55))
    rounded(d, (360, 536, 396, 700), 10, fill=(196, 60, 40))            # spine
    rounded(d, (420, 576, 640, 628), 8, fill=(255, 255, 255))
    for y in (592, 610):
        rounded(d, (438, y, 622, y + 8), 4, fill=(203, 213, 225))
    d.rectangle((668, 536, 682, 700), fill=(120, 30, 20))               # elastic band

    # pen lying across the notebook (drawn as a rotated overlay so it looks like a pen)
    stamp(img, pen_layer(), -12, (516, 672))

    # smartphone
    shadow(img, (730, 458, 894, 728), 26, 8, 45)
    rounded(d, (730, 458, 894, 728), 26, fill=(17, 24, 39))
    rounded(d, (746, 476, 878, 710), 16, fill=(56, 189, 248))
    for i in range(3):
        for j in range(3):
            rounded(d, (762 + j * 38, 496 + i * 62, 794 + j * 38, 542 + i * 62), 8, fill=(224, 242, 254))
    d.ellipse((856, 692, 874, 710), fill=(148, 163, 184))

    # spectacles
    rounded(d, (930, 556, 1060, 656), 26, fill=None, outline=(71, 85, 105), width=10)
    rounded(d, (1080, 556, 1210, 656), 26, fill=None, outline=(71, 85, 105), width=10)
    d.arc((1052, 566, 1088, 606), 90, 270, fill=(71, 85, 105), width=10)
    d.line((930, 586, 886, 562), fill=(71, 85, 105), width=10)
    d.line((1210, 586, 1254, 562), fill=(71, 85, 105), width=10)
    return img


SCENES = {
    "education.jpg": education,
    "technology.jpg": technology,
    "everyday_objects.jpg": everyday_objects,
}


def main() -> None:
    for name, builder in SCENES.items():
        path = save(builder(), name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with Image.open(path) as im:
            size = f"{im.width}x{im.height}"
        print(f"{path.name:24} {size:>10}  {path.stat().st_size / 1024:6.1f} KB  sha256={digest}")


if __name__ == "__main__":
    main()
