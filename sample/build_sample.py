#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建「Public Domain Sampler」测试盘：WAV 整盘 → TAK → CUE / NFO / meta.json。

用法
----
    python3 sample/build_sample.py --ffmpeg ffmpeg --outdir sample/out
    # 然后在 Windows 上（takc 只有 32 位）：
    takc -e -pMax -md5 -wm0 -overwrite -silent sample_disc.wav sample-disc.tak

时间轴按实际采样数算，CUE 的 INDEX 与切片严格对齐。
"""
import argparse
import json
import os
import subprocess
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'src')

TRACKS = [
    ('fma-182157.mp3', 'A Good Start', 'Monplaisir',
     'https://citizen-dj.labs.loc.gov/items/loc-fma/fma-182157/'),
    ('fma-178536.mp3', 'Beach', 'Komiku',
     'https://citizen-dj.labs.loc.gov/items/loc-fma/fma-178536/'),
    ('fma-178534.mp3', 'Home', 'Komiku',
     'https://citizen-dj.labs.loc.gov/items/loc-fma/fma-178534/'),
    ('fma-152618.mp3', 'Free To Use 9', 'Monplaisir',
     'https://citizen-dj.labs.loc.gov/items/loc-fma/fma-152618/'),
]
ALBUM = 'Public Domain Sampler'
ALBUM_ARTIST = 'Monplaisir / Komiku'
DATE = '2026-11-06'
GENRE = 'Test'
CATALOG = 'PD-SAMPLE-001'


def cue_time(seconds):
    f = int(round(seconds * 75))
    return '%02d:%02d:%02d' % (f // (75 * 60), (f // 75) % 60, f % 75)


def wav_frames(path):
    with wave.open(path, 'rb') as w:
        return w.getnframes(), w.getframerate()


def to_wav(ffmpeg, src, dst):
    subprocess.check_call([ffmpeg, '-v', 'error', '-y', '-i', src, '-vn',
                           '-ac', '2', '-ar', '44100', '-c:a', 'pcm_s16le', dst])
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ffmpeg', default='ffmpeg')
    ap.add_argument('--wav', help='已有的整盘 WAV（跳过合成）')
    ap.add_argument('--outdir', default=os.path.join(HERE, 'out'))
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    # 1) 每轨转 WAV，记下精确采样数
    parts, frames = [], []
    for i, (fn, *_r) in enumerate(TRACKS):
        src = os.path.join(SRC, fn)
        if not os.path.exists(src):
            sys.exit('missing %s' % src)
        p = os.path.join(a.outdir, 'part%02d.wav' % (i + 1))
        to_wav(a.ffmpeg, src, p)
        n, rate = wav_frames(p)
        parts.append(p)
        frames.append(n)

    # 2) 拼整盘（若没给现成的 WAV）
    wav = a.wav
    if not wav:
        wav = os.path.join(a.outdir, 'sample_disc.wav')
        listing = os.path.join(a.outdir, 'concat.txt')
        with open(listing, 'w', encoding='utf-8') as f:
            for p in parts:
                f.write("file '%s'\n" % p.replace("'", "'\\''"))
        subprocess.check_call([a.ffmpeg, '-v', 'error', '-y', '-f', 'concat', '-safe', '0',
                               '-i', listing, '-c:a', 'pcm_s16le', '-ar', '44100', '-ac', '2', wav])
        os.remove(listing)

    total_frames, rate = wav_frames(wav)
    if sum(frames) != total_frames:
        # 以整盘实际帧数为准，按比例校正每轨
        k = total_frames / float(sum(frames))
        frames = [f * k for f in frames]

    starts, acc = [], 0.0
    for f in frames:
        starts.append(acc / rate)
        acc += f

    # 3) CUE
    head = ['REM GENRE "%s"' % GENRE, 'REM DATE %s' % DATE,
            'REM COMMENT "cuefs sample album — public domain audio, see CREDITS.md"']
    head += ['REM SOURCE "%s"' % t[3] for t in TRACKS]
    head += ['PERFORMER "%s"' % ALBUM_ARTIST, 'TITLE "%s"' % ALBUM,
             'FILE "sample-disc.tak" WAVE', '']
    for i, (fn, title, artist, _url) in enumerate(TRACKS):
        head += ['  TRACK %02d AUDIO' % (i + 1),
                 '    TITLE "%s"' % title,
                 '    PERFORMER "%s"' % artist,
                 '    INDEX 01 %s' % cue_time(starts[i]), '']
    cue = os.path.join(a.outdir, 'sample-disc.cue')
    with open(cue, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write('\n'.join(head))

    # 4) album.nfo
    nfo = '''<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<album>
  <title>%s</title>
  <artist>%s</artist>
  <albumartist>%s</albumartist>
  <year>2026</year>
  <premiered>%s</premiered>
  <releasedate>%s</releasedate>
  <genre>%s</genre>
  <label>Library of Congress — Citizen DJ / Free Music Archive</label>
  <catalognumber>%s</catalognumber>
  <type>Album</type>
  <review>SAMPLE ALBUM for cuefs testing. Public-domain audio (CC0 dedication) from the Library of Congress Citizen DJ / Free Music Archive subset: "A Good Start" by Monplaisir, "Beach" and "Home" by Komiku, "Free To Use 9" by Monplaisir. Sources: %s</review>
  <outline>Not a real release — SAMPLE ONLY.</outline>
  <lockdata>false</lockdata>
</album>
''' % (ALBUM, ALBUM_ARTIST, ALBUM_ARTIST, DATE, DATE, GENRE, CATALOG,
       ' | '.join(t[3] for t in TRACKS))
    open(os.path.join(a.outdir, 'album.nfo'), 'w', encoding='utf-8').write(nfo)

    # 5) meta.json（演示 CUE 表达不了的字段）
    meta = {'album': {'label': 'Library of Congress — Citizen DJ / Free Music Archive',
                      'catalognumber': CATALOG,
                      'comment': 'SAMPLE — public domain (CC0) audio; see CREDITS.md',
                      'copyright': 'Public Domain (CC0 dedication)',
                      'genre': GENRE},
            'tracks': {str(i + 1): {'composer': t[2], 'comment': t[3]}
                       for i, t in enumerate(TRACKS)}}
    open(os.path.join(a.outdir, 'meta.json'), 'w', encoding='utf-8').write(
        json.dumps(meta, ensure_ascii=False, indent=2))

    for p in parts:
        if os.path.exists(p):
            os.remove(p)
    print('wav   : %s (%.3fs)' % (wav, total_frames / float(rate)))
    for i, t in enumerate(TRACKS):
        print('  %02d %-16s %-12s INDEX 01 %s' % (i + 1, t[1], t[2], cue_time(starts[i])))
    print('cue   : %s' % cue)
    print('\nTAK 编码（Windows，takc 是 32 位）：')
    print('  takc -e -pMax -md5 -wm0 -overwrite -silent sample_disc.wav sample-disc.tak')


if __name__ == '__main__':
    main()
