#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 SAMPLE 封面（1000x1000）。字体用 Liberation Sans（SIL OFL 1.1，可商用）。"""
import os
from PIL import Image, ImageDraw, ImageFont

W = H = 1000
FONT = '/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf'
FONT_R = '/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf'


def vgrad(size, top, bottom):
    img = Image.new('RGB', size)
    d = ImageDraw.Draw(img)
    for y in range(size[1]):
        t = y / max(1, size[1] - 1)
        d.line([(0, y), (size[0], y)],
               fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img


def main(out='sample/cover.jpg'):
    img = vgrad((W, H), (18, 46, 42), (6, 14, 18))
    d = ImageDraw.Draw(img, 'RGBA')

    # 网格纹理
    for x in range(0, W, 50):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 8))
    for y in range(0, H, 50):
        d.line([(0, y), (W, y)], fill=(255, 255, 255, 8))

    f_sample = ImageFont.truetype(FONT, 190)
    f_title = ImageFont.truetype(FONT, 54)
    f_sub = ImageFont.truetype(FONT_R, 30)
    f_small = ImageFont.truetype(FONT_R, 24)

    # 中部斜向 SAMPLE 水印
    wm = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wm)
    wd.text((W / 2, H / 2), 'SAMPLE', font=f_sample, anchor='mm', fill=(255, 255, 255, 26))
    wm = wm.rotate(-18, resample=Image.BICUBIC, center=(W / 2, H / 2))
    img = Image.alpha_composite(img.convert('RGBA'), wm).convert('RGB')
    d = ImageDraw.Draw(img)

    d.rounded_rectangle([60, 60, W - 60, H - 60], radius=28, outline=(120, 220, 180, 120), width=3)

    d.text((90, 120), 'cuefs', font=ImageFont.truetype(FONT, 74), fill=(140, 235, 195))
    d.text((92, 210), 'disc image + CUE  →  WebDAV', font=ImageFont.truetype(FONT_R, 30),
           fill=(200, 230, 220))

    d.text((90, 430), 'Public Domain Sampler', font=f_title, fill=(255, 255, 255))
    d.text((90, 500), 'Monplaisir · Komiku', font=f_sub, fill=(180, 215, 205))
    d.text((90, 545), 'CC0 / Public Domain — Library of Congress, Citizen DJ (FMA)', font=f_small,
           fill=(150, 185, 175))

    d.line([(90, 620), (W - 90, 620)], fill=(120, 220, 180, 120), width=2)

    lines = ["SAMPLE ALBUM — for testing cuefs",
             "TAK + CUE + NFO + cover, 4 tracks / ~6 min",
             "Audio: citizen-dj.labs.loc.gov (public domain dedication)"]
    y = 650
    for ln in lines:
        d.text((90, y), ln, font=f_small, fill=(190, 210, 205))
        y += 40

    # 右下角 SAMPLE 角标
    d.text((W - 100, H - 110), 'SAMPLE', font=ImageFont.truetype(FONT, 72), anchor='rm',
           fill=(255, 120, 120))

    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    img.save(out, quality=92)
    print('written', out, img.size)


if __name__ == '__main__':
    main()
