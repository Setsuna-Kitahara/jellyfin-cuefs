#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""takdec.py — 在 Windows Python（容器里由 wine 运行）中把整张 TAK 解码成 WAV。

用法（容器内）：
    wine /winepy/python.exe /app/takdec.py --tak /src/a.tak --dll /app/tak_deco_lib.dll --wav /cache/a.wav

只依赖标准库 + taklib.py（ctypes 调官方 x64 解码库）。
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import taklib  # noqa: E402


def write_wav_header(f, n_samples, rate, channels, bits):
    block = channels * (bits // 8)
    data_size = n_samples * block
    f.write(b'RIFF')
    f.write(struct.pack('<I', 36 + data_size))
    f.write(b'WAVEfmt ')
    f.write(struct.pack('<IHHIIHH', 16, 1, channels, rate, rate * block, block, bits))
    f.write(b'data')
    f.write(struct.pack('<I', data_size))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tak', required=True)
    ap.add_argument('--dll', required=True)
    ap.add_argument('--wav', required=True)
    ap.add_argument('--chunk', type=int, default=262144)
    ap.add_argument('--start-sec', type=float, default=0.0,
                    help='从这一秒开始解码（随机访问，不必整盘落地）')
    ap.add_argument('--dur-sec', type=float, default=0.0,
                    help='只解码这么长（0=到结尾）')
    ap.add_argument('--stdout-wav', action='store_true',
                    help='把 WAV 写到 stdout（配合 ffmpeg -i pipe:0）')
    args = ap.parse_args()

    dec = taklib.TakFile(args.tak, args.dll)
    start = int(round(args.start_sec * dec.sample_rate)) if args.start_sec > 0 else 0
    start = max(0, min(start, dec.samples))
    count = dec.samples - start if args.dur_sec <= 0 else min(
        dec.samples - start, int(round(args.dur_sec * dec.sample_rate)))
    tmp = args.wav + '.part'
    done = 0
    try:
        if args.stdout_wav:
            f = getattr(sys.stdout, 'buffer', sys.stdout)
            write_wav_header(f, count, dec.sample_rate, dec.channels, dec.bits)
        else:
            f = open(tmp, 'wb')
            write_wav_header(f, count, dec.sample_rate, dec.channels, dec.bits)
        try:
            dec.seek(start)
            left = count
            while left > 0:
                n = min(left, args.chunk)
                data = dec.read(n)
                if not data:
                    break
                f.write(data)
                left -= n
                done += n
                if done % (args.chunk * 40) < args.chunk:
                    sys.stderr.write('decoded %d/%d samples\n' % (done, count))
                    sys.stderr.flush()
        finally:
            if not args.stdout_wav:
                f.close()
        if args.stdout_wav:
            try:
                sys.stdout.buffer.flush()
            except Exception:
                pass
        else:
            os.replace(tmp, args.wav)
    finally:
        dec.close()
    if args.stdout_wav:
        return
    print('WAV OK %s samples=%d rate=%d ch=%d bits=%d bytes=%d'
          % (args.wav, dec.samples, dec.sample_rate, dec.channels, dec.bits,
             os.path.getsize(args.wav)))


if __name__ == '__main__':
    main()
