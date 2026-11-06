# -*- coding: utf-8 -*-
"""make_tak_album.py —— 把一堆 FLAC/WAV 曲目合成「一张 TAK 盘 + 一份 CUE」。

用途：给 cuefs 造测试素材（例如公有领域曲目），格式与真实 CD rip 一致：
一张整轨 TAK + 一个 CUE，轨道之间带 INDEX 00 pregap。

用法（在装了 TAK 2.3.3 与 ffmpeg 的 Windows 上）：
    python make_tak_album.py plan.json

plan.json:
{
  "album": "Demo Album",
  "performer": "Public Domain",
  "genre": "Classical",
  "date": "2026",
  "outdir": "C:/fixture/out",
  "disc": 1,
  "tracks": [
     {"file": "a.flac", "title": "Track A", "performer": "X", "pregap": 0},
     {"file": "b.flac", "title": "Track B", "pregap": 2.0}
  ]
}

pregap = 该轨 INDEX 00 → INDEX 01 之间的静音秒数（第一轨填 0）。
cuefs 默认 --pregap prev，这段静音会算进上一轨尾部，因此逐轨拼接仍与整盘逐位一致。
"""
import json
import os
import subprocess
import sys
import wave
import hashlib

FFMPEG = os.environ.get('FFMPEG', r'C:\Users\dsh\tools\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe')
TAKC = os.environ.get('TAKC', r'C:\Users\dsh\Downloads\tak233\Applications\Takc.exe')
RATE = 44100
CH = 2


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError('命令失败: %s\n%s' % (' '.join(cmd), p.stderr.decode('utf-8', 'replace')[-2000:]))
    return p


def to_wav(src, dst):
    run([FFMPEG, '-y', '-loglevel', 'error', '-i', src, '-ac', str(CH), '-ar', str(RATE),
         '-c:a', 'pcm_s16le', dst])


def wav_pcm(path):
    with wave.open(path, 'rb') as w:
        assert w.getnchannels() == CH and w.getframerate() == RATE and w.getsampwidth() == 2, \
            '需要 %d Hz / %d ch / 16 bit' % (RATE, CH)
        return w.readframes(w.getnframes())


def frames_of(samples):
    """样本数 → CUE 的 mm:ss:ff（75 帧/秒），四舍五入。"""
    total = int(round(samples * 75.0 / RATE))
    return '%02d:%02d:%02d' % (total // (75 * 60), (total // 75) % 60, total % 75)


def main():
    plan = json.load(open(sys.argv[1], encoding='utf-8-sig'))
    outdir = plan['outdir']
    os.makedirs(outdir, exist_ok=True)
    name = plan.get('filename') or 'album'
    wav_path = os.path.join(outdir, name + '.wav')
    tak_path = os.path.join(outdir, name + '.tak')
    cue_path = os.path.join(outdir, name + '.cue')

    pcm = bytearray()
    marks = []          # (start_sample, index0_sample_or_None)
    tmpdir = os.path.join(outdir, '_tmp')
    os.makedirs(tmpdir, exist_ok=True)

    for i, t in enumerate(plan['tracks'], 1):
        w = os.path.join(tmpdir, '%02d.wav' % i)
        to_wav(t['file'], w)
        data = wav_pcm(w)
        n = len(data) // (CH * 2)
        pre = float(t.get('pregap', 0) or 0)
        idx0 = None
        if i > 1 and pre > 0:
            idx0 = len(pcm) // (CH * 2)
            pcm += b'\x00' * int(round(pre * RATE)) * CH * 2
        start = len(pcm) // (CH * 2)
        pcm += data
        marks.append((start, idx0, n, t))
        print('  track %02d  %6.2fs  pregap %.2fs  start %s' % (i, n / RATE, pre, frames_of(start)))

    total = len(pcm) // (CH * 2)
    with wave.open(wav_path, 'wb') as w:
        w.setnchannels(CH); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(bytes(pcm))

    run([TAKC, '-e', '-pMax', '-md5', '-wm0', '-overwrite', '-silent', wav_path, tak_path])

    lines = []
    if plan.get('genre'):
        lines.append('REM GENRE %s' % plan['genre'])
    if plan.get('date'):
        lines.append('REM DATE %s' % plan['date'])
    lines.append('PERFORMER "%s"' % plan.get('performer', 'Various'))
    lines.append('TITLE "%s"' % plan['album'])
    lines.append('FILE "%s" WAVE' % (name + '.tak'))
    for i, (start, idx0, n, t) in enumerate(marks, 1):
        lines.append('  TRACK %02d AUDIO' % i)
        lines.append('    TITLE "%s"' % t.get('title', 'Track %d' % i))
        lines.append('    PERFORMER "%s"' % t.get('performer', plan.get('performer', 'Various')))
        if idx0 is not None:
            lines.append('    INDEX 00 %s' % frames_of(idx0))
        lines.append('    INDEX 01 %s' % frames_of(start))
    with open(cue_path, 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write('\n'.join(lines) + '\n')

    # 自检：解码整轨 TAK，与源 WAV 的 PCM 比 MD5；再按 CUE 边界切一遍确认能拼回原样
    for cand in (os.path.dirname(os.path.abspath(__file__)),
                 os.environ.get('TAKLIB_DIR', ''),
                 os.getcwd()):
        if cand and os.path.exists(os.path.join(cand, 'taklib.py')):
            sys.path.insert(0, cand)
            break
    try:
        import taklib  # noqa: E402
    except ImportError:
        sys.stderr.write('!! 找不到 taklib.py，跳过位级自检（设置 TAKLIB_DIR 指向它所在目录）\n')
        print('\n  RESULT: SKIP-VERIFY')
        return
    dll = os.environ.get('TAK_DLL')
    tf = taklib.TakFile(tak_path, dll) if dll else taklib.TakFile(tak_path)
    tf.seek(0)
    h = hashlib.md5()
    left = tf.samples
    while left > 0:
        n = min(left, 262144)
        h.update(tf.read(n))
        left -= n
    src_md5 = hashlib.md5(bytes(pcm)).hexdigest()
    print('\n  wav %d bytes / tak %d bytes (%.2f)' %
          (os.path.getsize(wav_path), os.path.getsize(tak_path),
           os.path.getsize(tak_path) / float(os.path.getsize(wav_path))))
    print('  samples %d (%.2fs)  expected %d' % (tf.samples, tf.duration, total))
    print('  md5 src/tak: %s / %s' % (src_md5, h.hexdigest()))
    ok = (src_md5 == h.hexdigest()) and tf.samples == total
    # 轨道边界连续性（cuefs 默认 --pregap prev：第 N 轨结束 = 第 N+1 轨 INDEX 01）
    bounds = [(m[0], (marks[j + 1][0] if j + 1 < len(marks) else total))
              for j, m in enumerate(marks)]
    cont = (bounds[0][0] == 0 and
            all(bounds[j][1] == bounds[j + 1][0] for j in range(len(bounds) - 1)) and
            bounds[-1][1] == total)
    print('  track boundaries contiguous:', cont)
    print('  RESULT:', 'PASS' if (ok and cont) else 'FAIL')
    print('\n  cue:', cue_path)
    for l in lines:
        print('   ', l)
    tf.close()


main()
