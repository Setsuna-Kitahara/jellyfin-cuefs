#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cuefs — 把「整轨 TAK/APE/FLAC/WAV + CUE」虚拟化成「一轨一文件」的 WebDAV 服务。

容器版设计
----------
* 只读输入 A（--src）：CUE + TAK 原盘，永远不改动、不拆分；
* 可写覆盖层 B（--overlay）：Jellyfin 通过 WebDAV 写入的 album.nfo / poster.jpg /
  folder.jpg / *.lrc 等全部落在这里；虚拟轨道本身仍然是只读的；
* WebDAV 对外只暴露一层目录，读时 B 优先、其次虚拟轨道；
* 解码后端（--backend）：
    wine   —— Linux 容器里用 Wine 跑官方 x64 解码库（Windows 版 Python + taklib.py），
              整盘解成 WAV 后按 CUE 切片；验证过与官方 takc 位级一致；
    dll    —— Windows 原生跑 taklib.py，按样本随机访问，不落地整盘 WAV；
    ffmpeg —— 非 TAK 源（flac/wav/ape 里 ffmpeg 认得的）直接切片；
    auto   —— 有 wine 用 wine，有 DLL 用 dll，否则 ffmpeg。

挂载方式见 README.md。
"""
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import xml.sax.saxutils as sx
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote, quote

VERSION = '1.5.0'

AUDIO_EXTS = ('.tak', '.ape', '.flac', '.wav', '.tta', '.wv')


# ---------------------------------------------------------------- 工具函数
def cue_time(t):
    """mm:ss:ff (75 frames/s) -> 秒"""
    m = re.match(r'^(\d+):(\d+):(\d+)$', (t or '').strip())
    if not m:
        return 0.0
    return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 75.0


def safe_name(s, fallback='untitled'):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', '_', s or '')
    s = s.strip().strip('.')
    return s or fallback


def human(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return '%.1f %s' % (n, unit) if unit != 'B' else '%d B' % n
        n /= 1024.0


def log(*a):
    print(time.strftime('[%H:%M:%S]'), *a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- CUE 解析
class Track(object):
    def __init__(self, no):
        self.no = no
        self.title = ''
        self.performer = ''
        self.idx00 = None
        self.idx01 = None
        self.start = 0.0
        self.end = 0.0


class Album(object):
    def __init__(self, cue_path, pregap='prev'):
        self.cue_path = cue_path
        self.dir = os.path.dirname(cue_path)
        self.title = ''
        self.performer = ''
        self.date = ''
        self.genre = ''
        self.audio_file = ''
        self.pregap_mode = pregap
        self.tracks = []
        self._parse()
        self._boundaries()

    def _read_text(self):
        with open(self.cue_path, 'rb') as f:
            raw = f.read()
        for enc in ('utf-8-sig', 'utf-8', 'gbk', 'shift_jis', 'cp1252'):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode('utf-8', 'replace')

    def _parse(self):
        cur = None
        for line in self._read_text().splitlines():
            s = line.strip()
            if not s:
                continue
            if s.upper().startswith('REM '):
                m = re.match(r'REM\s+(GENRE|DATE)\s+"?([^"]*)"?', s, re.I)
                if m:
                    if m.group(1).upper() == 'GENRE':
                        self.genre = m.group(2).strip()
                    else:
                        self.date = m.group(2).strip()
                continue
            kw, _, rest = s.partition(' ')
            kw = kw.upper()
            val = rest.strip()
            if len(val) >= 2 and val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            if kw == 'FILE':
                m = re.match(r'^"?(.+?)"?\s+\w+$', rest.strip())
                # 兼容不带类型（WAVE/BINARY）的 FILE 行，也兼容只有引号包住的情况
                self.audio_file = (m.group(1) if m else val).strip().strip('"')
            elif kw == 'TRACK':
                m = re.match(r'^(\d+)\s+(\w+)', rest)
                if m:
                    cur = Track(int(m.group(1)))
                    self.tracks.append(cur)
            elif kw == 'TITLE':
                if cur:
                    cur.title = val
                else:
                    self.title = val
            elif kw == 'PERFORMER':
                if cur:
                    cur.performer = val
                else:
                    self.performer = val
            elif kw == 'INDEX':
                m = re.match(r'^(\d+)\s+(\d+:\d+:\d+)', rest)
                if m and cur:
                    if m.group(1) == '00':
                        cur.idx00 = cue_time(m.group(2))
                    elif m.group(1) == '01':
                        cur.idx01 = cue_time(m.group(2))
        if not self.audio_file:
            base = os.path.splitext(os.path.basename(self.cue_path))[0]
            for ext in AUDIO_EXTS:
                if os.path.exists(os.path.join(self.dir, base + ext)):
                    self.audio_file = base + ext
                    break

    def _boundaries(self):
        self.tracks.sort(key=lambda t: t.idx01 if t.idx01 is not None else 0)
        for i, t in enumerate(self.tracks):
            t.start = t.idx01 if t.idx01 is not None else 0.0
            if i + 1 < len(self.tracks):
                nxt = self.tracks[i + 1]
                if self.pregap_mode == 'next':
                    t.end = nxt.idx00 if nxt.idx00 is not None else (nxt.idx01 or t.start)
                else:
                    # 默认：下一轨 INDEX 00 起的 pregap 归到本轨尾部，
                    # 全专辑逐轨拼接 = 整盘 PCM，一个采样都不丢。
                    t.end = nxt.idx01 if nxt.idx01 is not None else (
                        nxt.idx00 if nxt.idx00 is not None else t.start)
            else:
                t.end = 0.0

    def audio_path(self):
        return os.path.join(self.dir, self.audio_file)


# ---------------------------------------------------------------- 媒体层
def ffprobe_duration(ffprobe, path):
    try:
        out = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration',
                              '-of', 'default=nk=1:nw=1', path],
                             capture_output=True, text=True, timeout=300).stdout.strip()
        return float(out)
    except Exception:
        return 0.0


def exact_duration(ffprobe, path):
    """精确到样本的时长（duration_ts x time_base）。

    ffprobe 的 format=duration 只有百分之一秒，末轨按它切会少 100 多个样本，
    导致「逐轨拼接 != 整盘 PCM」。任何 ffmpeg 能解的整盘（flac/wv/ape/tta/wav...）
    都能从 stream 的 duration_ts 拿到精确样本数。
    """
    try:
        out = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'a:0',
                              '-show_entries', 'stream=duration_ts,time_base',
                              '-of', 'json', path],
                             capture_output=True, text=True, timeout=300).stdout
        st = (json.loads(out).get('streams') or [{}])[0]
        ts = st.get('duration_ts')
        tb = st.get('time_base') or ''
        if ts and '/' in tb:
            num, den = tb.split('/', 1)
            v = float(ts) * float(num) / float(den)
            if v > 0:
                return v
    except Exception:
        pass
    return 0.0


def wav_duration(path):
    """直接从 WAV 头算时长：Wine 后端解出的整盘 WAV 是精确样本数，
    ffprobe/ffmpeg 的百分之一秒精度会让末轨少 100 多个样本。"""
    try:
        with open(path, 'rb') as f:
            if f.read(4) != b'RIFF':
                return 0.0
            f.read(4)
            if f.read(4) != b'WAVE':
                return 0.0
            ch = rate = bits = 0
            data = 0
            while True:
                cid = f.read(4)
                if len(cid) < 4:
                    break
                size = int.from_bytes(f.read(4), 'little')
                if cid == b'fmt ':
                    body = f.read(size)
                    ch = int.from_bytes(body[2:4], 'little')
                    rate = int.from_bytes(body[4:8], 'little')
                    bits = int.from_bytes(body[14:16], 'little') if len(body) >= 16 else 16
                elif cid == b'data':
                    data = size
                    break
                else:
                    f.seek(size + (size & 1), 1)
            if ch and rate and bits and data:
                return data / float(ch * rate * bits // 8)
    except Exception:
        pass
    return 0.0


def ffmpeg_duration(ffmpeg, path):
    """没有 ffprobe 时（比如只装了静态 ffmpeg 的精简镜像）从 `ffmpeg -i` 的 stderr 里取时长。"""
    try:
        r = subprocess.run([ffmpeg, '-hide_banner', '-i', path],
                           capture_output=True, text=True, timeout=300)
        for line in (r.stderr or '').splitlines():
            line = line.strip()
            if line.startswith('Duration:'):
                stamp = line.split('Duration:')[1].split(',')[0].strip()
                h, m, sec = stamp.split(':')
                return int(h) * 3600 + int(m) * 60 + float(sec)
    except Exception:
        pass
    return 0.0


class Media(object):
    def __init__(self, src, overlay, cache, ffmpeg='ffmpeg', ffprobe='ffprobe',
                 backend='auto', tak_dll='', wine='wine', wine_python='/winepy/python.exe',
                 takdec='/app/takdec.py', keep_wav=False, cache_max_gb=0.0,
                 cache_ttl_h=0.0, tak_mode='range', sidecar='both',
                 pregap='prev', workers=3):
        self.src = src
        self.overlay = overlay
        self.cache = cache
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.wine = self._resolve_wine(wine)
        self.backend = self._pick_backend(backend, tak_dll, self.wine, wine_python)
        self.tak_dll = tak_dll or self.default_tak_dll()
        self.wine_python = wine_python
        self.takdec = takdec
        self.keep_wav = keep_wav
        self.cache_max_gb = cache_max_gb
        self.cache_ttl_h = float(cache_ttl_h or 0.0)
        self.tak_mode = (tak_mode or 'range').lower()
        self.sidecar = (sidecar or 'both').lower()
        self._cue_count = {}
        self.pregap = pregap
        self.workers = max(1, workers)
        self.albums = {}
        self._locks = {}
        self._lock_guard = threading.Lock()
        self._durs = {}
        self._metajson = {}
        os.makedirs(self.overlay, exist_ok=True)
        os.makedirs(self.cache, exist_ok=True)
        self.reload()

    # -- 后端选择 --------------------------------------------------
    @staticmethod
    def _resolve_wine(wine):
        """Debian 的 wine64 包只提供 /usr/lib/wine/wine64，没有 /usr/bin/wine。"""
        for c in (wine, '/usr/lib/wine/wine64', '/usr/bin/wine64', '/usr/bin/wine'):
            if not c:
                continue
            if os.path.isabs(c):
                if os.path.exists(c):
                    return c
            elif shutil.which(c):
                return shutil.which(c)
        return wine

    @staticmethod
    def default_tak_dll():
        """TAK 解码库不在镜像里，安装时用 import_tak.py 导入到 /opt/tak。"""
        for p in (os.environ.get('CUEFS_TAK_DLL', ''),
                  '/opt/tak/Deco_Lib/tak_deco_lib.dll',
                  '/opt/tak/tak_deco_lib.dll',
                  '/app/tak_deco_lib.dll'):
            if p and os.path.exists(p):
                return p
        return ''

    def _pick_backend(self, backend, tak_dll, wine, wine_python):
        if backend != 'auto':
            return backend
        if sys.platform == 'win32' and tak_dll and os.path.exists(tak_dll):
            return 'dll'
        if wine and (os.path.exists(wine) or shutil.which(wine)) and wine_python and os.path.exists(wine_python):
            return 'wine'
        return 'ffmpeg'

    def has_tak(self):
        return any(a.audio_path().lower().endswith('.tak') for a in self.albums.values())

    # -- 索引 ------------------------------------------------------
    def reload(self):
        found = {}
        for dp, _dn, fn in os.walk(self.src):
            for f in sorted(fn):
                if not f.lower().endswith('.cue'):
                    continue
                try:
                    a = Album(os.path.join(dp, f), self.pregap)
                    if not a.tracks or not os.path.exists(a.audio_path()):
                        log('skip cue (no audio):', f)
                        continue
                    key = self.album_key(a)
                    if key in found:
                        key = key + '_' + hashlib.sha1(a.cue_path.encode()).hexdigest()[:4]
                    found[key] = a
                except Exception as e:
                    log('cue parse fail', f, e)
        self.albums = found
        log('albums:', len(found), 'backend:', self.backend,
            'tracks:', sum(len(a.tracks) for a in found.values()))

    @staticmethod
    def album_key(a):
        return safe_name(a.title or os.path.splitext(os.path.basename(a.cue_path))[0], 'album')

    @staticmethod
    def track_name(t):
        return '%02d - %s.flac' % (t.no, safe_name(t.title or ('track%02d' % t.no), 'track%02d' % t.no))

    # -- 缓存 ------------------------------------------------------
    def cache_dir(self, a):
        return os.path.join(self.cache, hashlib.sha1(a.cue_path.encode('utf-8')).hexdigest()[:12])

    def cache_path(self, a, t):
        return os.path.join(self.cache_dir(a), '%02d.flac' % t.no)

    # -- 侧车文件（封面/歌词/nfo）----------------------------------
    ALBUM_SIDECARS = ('cover.jpg', 'cover.png', 'folder.jpg', 'folder.png',
                      'poster.jpg', 'backdrop.jpg', 'album.nfo')

    def _cue_count_in(self, d):
        if d not in self._cue_count:
            try:
                self._cue_count[d] = len([f for f in os.listdir(d)
                                          if f.lower().endswith('.cue')])
            except OSError:
                self._cue_count[d] = 0
        return self._cue_count[d]

    def sidecar_dirs(self, a):
        """按优先级返回可放侧车文件的目录列表 [(path, kind)]。

        kind: 'overlay' 表示 B 里以专辑虚拟名建目录；'album' 表示 A 里以 CUE 文件名为名的子目录；
              'flat' 表示与 CUE 同级（只有该目录下仅一张 CUE 时才用，避免串味）。
        """
        out = []
        bdir = os.path.join(self.overlay, self.album_key(a))
        stem = os.path.splitext(os.path.basename(a.cue_path))[0]
        adir = os.path.join(a.dir, stem)
        a_dirs = [(adir, 'album')]
        if self._cue_count_in(a.dir) <= 1:
            a_dirs.append((a.dir, 'flat'))
        if self.sidecar == 'overlay':
            return [(bdir, 'overlay')]
        if self.sidecar == 'src':
            # 源目录优先；源里没有的再回落到 B（B 仍是唯一可写位置）
            return a_dirs + [(bdir, 'overlay')]
        return [(bdir, 'overlay')] + a_dirs

    def _sidecar_names(self, a, name):
        """同一个逻辑文件在 A 里的可能写法（含 <cue stem>.jpg / <cue stem>.nfo 前缀式）。"""
        names = [name]
        stem = os.path.splitext(os.path.basename(a.cue_path))[0]
        low = name.lower()
        if low in ('cover.jpg', 'cover.png', 'folder.jpg', 'folder.png'):
            names.append(stem + os.path.splitext(low)[1])
        if low == 'album.nfo':
            names.append(stem + '.nfo')
        return names

    def sidecar_lookup(self, a, name):
        for d, kind in self.sidecar_dirs(a):
            for cand in (self._sidecar_names(a, name) if kind != 'overlay' else [name]):
                p = os.path.join(d, cand)
                if os.path.isfile(p):
                    return p
        return None

    def sidecar_list(self, a):
        """专辑目录下可以列出来的侧车文件：{虚拟文件名: 实际路径}。"""
        got = {}
        for d, kind in self.sidecar_dirs(a):
            if not os.path.isdir(d):
                continue
            try:
                names = sorted(os.listdir(d))
            except OSError:
                continue
            for f in names:
                p = os.path.join(d, f)
                if not os.path.isfile(p):
                    continue
                low = f.lower()
                if not (low.endswith(('.jpg', '.jpeg', '.png', '.nfo', '.lrc', '.txt'))):
                    continue
                if kind == 'flat' and low.endswith('.nfo') and low != 'album.nfo':
                    continue
                if low.endswith('.cue') or low.endswith('.tak'):
                    continue
                virt = f
                stem = os.path.splitext(os.path.basename(a.cue_path))[0]
                if kind != 'overlay' and f.startswith(stem + '.') and f != 'album.nfo':
                    virt = 'cover' + f[len(stem):] if f[len(stem):].lower() in ('.jpg', '.png') else f
                got.setdefault(virt, p)
        return got

    def wav_path(self, a):
        return os.path.join(self.cache_dir(a), '_album.wav')

    def cached(self, a, t):
        p = self.cache_path(a, t)
        try:
            if os.path.getsize(p) > 1024:
                if self.cache_ttl_h:
                    now = time.time()
                    # 命中即续命；刷新粒度取 TTL 的 1/4（上限 60s），短 TTL 也能真正续期
                    thr = min(60.0, max(1.0, self.cache_ttl_h * 900.0))
                    if now - os.path.getmtime(p) > thr:
                        os.utime(p, (now, now))
                return p
        except OSError:
            return None
        return None

    def _album_lock(self, key):
        with self._lock_guard:
            lk = self._locks.get(key)
            if lk is None:
                lk = self._locks[key] = threading.Lock()
            return lk

    META_KEYS = ('title', 'artist', 'album', 'album_artist', 'track', 'disc', 'date',
                 'genre', 'composer', 'lyricist', 'label', 'catalognumber', 'isrc',
                 'comment', 'copyright', 'grouping', 'media', 'bpm', 'discsubtitle')

    def _meta_json(self, a):
        """可选的 meta.json：放在 A 或 B 的专辑目录里，用来补 CUE 表达不了的字段。

        结构：{"album": {...}, "tracks": {"7": {...}}}
        键名限 META_KEYS（ffmpeg 的 metadata 键），值一律当字符串写真进 FLAC。
        """
        if a.cue_path in self._metajson:
            return self._metajson[a.cue_path]
        data = {}
        cands = [d for d, _kind in self.sidecar_dirs(a)] + [os.path.dirname(a.cue_path)]
        for d in cands:
            p = os.path.join(d, 'meta.json')
            if os.path.isfile(p):
                try:
                    with open(p, 'r', encoding='utf-8-sig') as f:
                        data = json.load(f)
                    log('meta.json:', p)
                    break
                except Exception as e:
                    log('meta.json parse fail', p, e)
        self._metajson[a.cue_path] = data if isinstance(data, dict) else {}
        return self._metajson[a.cue_path]

    def _meta(self, a, t):
        m = {
            'title': t.title or ('Track %02d' % t.no),
            'artist': t.performer or a.performer,
            'album': a.title,
            'album_artist': a.performer,
            'track': str(t.no),
            'date': a.date,
            'genre': a.genre,
        }
        extra = self._meta_json(a)
        for src in (extra.get('album') or {}, (extra.get('tracks') or {}).get(str(t.no)) or {}):
            if not isinstance(src, dict):
                continue
            for k, v in src.items():
                if k in self.META_KEYS and v not in (None, ''):
                    m[k] = str(v)
        return m

    # -- 时长 ------------------------------------------------------
    def total_duration(self, a):
        d = self._durs.get(a.cue_path)
        if d:
            return d
        wav = self.wav_path(a)
        if os.path.exists(wav) and os.path.getsize(wav) > 1024:
            d = wav_duration(wav) or ffprobe_duration(self.ffprobe, wav)
        if not d:
            d = exact_duration(self.ffprobe, a.audio_path())
        if not d:
            d = ffprobe_duration(self.ffprobe, a.audio_path())
        if not d and a.audio_path().lower().endswith('.tak'):
            # taklib 给出精确到样本的时长（ffmpeg/ffprobe 只有百分一秒），末轨切点靠它才不差样本
            try:
                import taklib
                d = taklib.TakFile(a.audio_path(), self.tak_dll).duration
            except Exception:
                d = 0.0
        if not d:
            d = ffmpeg_duration(self.ffmpeg, a.audio_path())
        if not d:
            d = max([t.start for t in a.tracks] or [0])
        self._durs[a.cue_path] = d
        return d

    def track_duration(self, a, t):
        if t.end > t.start:
            return t.end - t.start
        total = self.total_duration(a)
        return max(0.0, total - t.start) if total else 0.0

    # -- 整盘 WAV（wine 后端） --------------------------------------
    def ensure_wav(self, a):
        wav = self.wav_path(a)
        if os.path.exists(wav) and os.path.getsize(wav) > 1024:
            if self.cache_ttl_h:
                try:
                    now = time.time()
                    os.utime(wav, (now, now))
                except OSError:
                    pass
            return wav
        os.makedirs(os.path.dirname(wav), exist_ok=True)
        env = dict(os.environ)
        env.setdefault('WINEPREFIX', os.environ.get('WINEPREFIX', '/wine'))
        env.setdefault('WINEDEBUG', '-all')
        env.setdefault('WINEDLLOVERRIDES', 'mscoree,mshtml=')
        cmd = [self.wine, self.wine_python, self.takdec,
               '--tak', a.audio_path(), '--dll', self.tak_dll, '--wav', wav]
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=7200, env=env)
        if r.returncode != 0 or not os.path.exists(wav):
            raise RuntimeError('wine takdec 失败: rc=%d %s %s'
                               % (r.returncode, (r.stderr or '')[-400:], (r.stdout or '')[-200:]))
        log('decoded wav %s (%.1fs) %s' % (os.path.basename(wav), time.time() - t0,
                                           human(os.path.getsize(wav))))
        self._durs.pop(a.cue_path, None)
        return wav

    # -- 单轨生成 --------------------------------------------------
    def build(self, a, t):
        hit = self.cached(a, t)
        if hit:
            return hit
        out = self.cache_path(a, t)
        with self._album_lock(a.cue_path):
            hit = self.cached(a, t)
            if hit:
                return hit
            os.makedirs(os.path.dirname(out), exist_ok=True)
            dur = self.track_duration(a, t)
            if dur <= 0.0005:
                raise RuntimeError('zero duration: %s track %d' % (a.cue_path, t.no))
            tmp = out + '.part'
            meta = self._meta(a, t)
            src = a.audio_path()
            is_tak = src.lower().endswith('.tak')
            if is_tak and self.backend in ('dll', 'wine') and not self.tak_dll:
                raise RuntimeError(
                    'TAK 解码器未导入：请按 docs/02-TAK-LICENSE.md 下载 TAK 2.3.3 SDK，'
                    '再执行 docker exec -i <容器> python3 /app/import_tak.py --accept-license - < tak233.zip')
            if is_tak and self.backend == 'dll':
                self._build_tak_dll(a, t, dur, tmp, meta)
            elif is_tak and self.backend == 'wine' and self.tak_mode == 'range':
                try:
                    self._build_tak_wine_range(a, t, dur, tmp, meta)
                except Exception as exc:
                    log('区间解码失败，回退整盘 WAV：%s' % str(exc)[:300])
                    if os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass
                    wav = self.ensure_wav(a)
                    self._slice(wav, t.start, dur, tmp, meta)
            elif is_tak and self.backend == 'wine':
                wav = self.ensure_wav(a)
                self._slice(wav, t.start, dur, tmp, meta)
            else:
                self._slice(src, t.start, dur, tmp, meta)
            if not os.path.exists(tmp) or os.path.getsize(tmp) < 1024:
                raise RuntimeError('产物为空: ' + out)
            os.replace(tmp, out)
            self._prune()
            self._expire()
            return out

    def _wine_env(self):
        env = dict(os.environ)
        env.setdefault('WINEPREFIX', os.environ.get('WINEPREFIX', '/wine'))
        env.setdefault('WINEDEBUG', '-all')
        env.setdefault('WINEDLLOVERRIDES', 'mscoree,mshtml=')
        return env

    def _build_tak_wine_range(self, a, t, dur, tmp, meta):
        """wine 后端：让 takdec.py 只解这一轨的样本区间，WAV 直接走管道进 ffmpeg。

        比「先把整盘解成 ~500MB WAV 再切」省掉一次性大文件，冷门歌曲起播快一个数量级。
        """
        cmd1 = [self.wine, self.wine_python, self.takdec,
                '--tak', a.audio_path(), '--dll', self.tak_dll,
                '--wav', os.devnull, '--stdout-wav',
                '--start-sec', '%.6f' % t.start, '--dur-sec', '%.6f' % dur]
        cmd2 = [self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
                '-i', 'pipe:0', '-c:a', 'flac', '-compression_level', '8',
                '-map_metadata', '-1']
        for k, v in meta.items():
            if v:
                cmd2 += ['-metadata', '%s=%s' % (k, v)]
        cmd2 += ['-f', 'flac', tmp]
        p1 = subprocess.Popen(cmd1, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, env=self._wine_env())
        try:
            p2 = subprocess.run(cmd2, stdin=p1.stdout, capture_output=True,
                                text=True, timeout=3600)
        finally:
            try:
                p1.stdout.close()
            except Exception:
                pass
            rc1 = p1.wait()
        if rc1 != 0 or p2.returncode != 0 or not os.path.exists(tmp):
            raise RuntimeError('tak range decode failed rc=%s/%s %s'
                               % (rc1, p2.returncode, (p2.stderr or '')[-400:]))

    def _slice(self, src, start, dur, tmp, meta):
        cmd = [self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
               '-ss', '%.6f' % start, '-i', src, '-t', '%.6f' % dur,
               '-map', '0:a:0', '-c:a', 'flac', '-compression_level', '8',
               '-map_metadata', '-1']
        for k, v in meta.items():
            if v:
                cmd += ['-metadata', '%s=%s' % (k, v)]
        cmd += ['-f', 'flac', tmp]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if r.returncode != 0 or not os.path.exists(tmp):
            raise RuntimeError('ffmpeg failed: ' + (r.stderr or '')[-600:])

    def _build_tak_dll(self, a, t, dur, tmp, meta):
        import taklib
        dec = taklib.TakFile(a.audio_path(), self.tak_dll)
        try:
            rate, ch, bits = dec.sample_rate, dec.channels, dec.bits
            fmt = {16: 's16le', 24: 's24le', 32: 's32le'}.get(bits, 's16le')
            total = int(round(dur * rate))
            cmd = [self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
                   '-f', fmt, '-ar', str(rate), '-ac', str(ch), '-i', 'pipe:0',
                   '-c:a', 'flac', '-compression_level', '8', '-map_metadata', '-1']
            for k, v in meta.items():
                if v:
                    cmd += ['-metadata', '%s=%s' % (k, v)]
            cmd += ['-f', 'flac', tmp]
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            dec.seek(int(round(t.start * rate)))
            left = total
            try:
                while left > 0:
                    n = min(left, 262144)
                    data = dec.read(n)
                    if not data:
                        break
                    p.stdin.write(data)
                    left -= n
            finally:
                try:
                    p.stdin.close()
                except Exception:
                    pass
            err = p.stderr.read().decode('utf-8', 'replace')
            if p.wait() != 0:
                raise RuntimeError('ffmpeg(tak) failed: ' + err[-500:])
        finally:
            dec.close()

    def build_all(self, a):
        """整张专辑一次性生成（PROPFIND 时用），完了按需清掉整盘 WAV。"""
        from concurrent.futures import ThreadPoolExecutor
        if any(self.cached(a, t) is None for t in a.tracks):
            # 只有 wav 模式才需要先把整盘解成 WAV；range 模式下每轨自己 seek，别多解一次整盘
            if (self.tak_mode == 'wav' and a.audio_path().lower().endswith('.tak')
                    and self.backend == 'wine'):
                try:
                    self.ensure_wav(a)
                except Exception as e:  # noqa: BLE001
                    log('ensure_wav failed: %s' % str(e)[:200])
        errs = []

        def one(t):
            try:
                return self.build(a, t)
            except Exception as e:  # noqa: BLE001
                errs.append((t.no, str(e)))
                return None

        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            list(ex.map(one, a.tracks))
        if errs:
            log('build_all errors', a.cue_path, errs[:3])
        if not self.keep_wav:
            wav = self.wav_path(a)
            if os.path.exists(wav) and all(self.cached(a, t) for t in a.tracks):
                try:
                    os.remove(wav)
                except OSError:
                    pass
        return errs

    def prefetch_all(self):
        for key in sorted(self.albums):
            t0 = time.time()
            self.build_all(self.albums[key])
            log('prefetch %s done %.1fs' % (key, time.time() - t0))

    def _ttl_label(self):
        sec = self.cache_ttl_h * 3600.0
        if sec >= 3600:
            return '%.4g h' % self.cache_ttl_h
        if sec >= 60:
            return '%d min' % round(sec / 60.0)
        return '%d s' % round(sec)

    def _expire(self):
        """按 TTL 删除长期没人读的缓存（TTL=0 表示永不过期）。"""
        if not self.cache_ttl_h:
            return 0
        cutoff = time.time() - self.cache_ttl_h * 3600.0
        removed = 0
        for dp, _dn, fn in os.walk(self.cache, topdown=False):
            for f in fn:
                if not (f.endswith('.flac') or f.endswith('.wav')):
                    continue
                p = os.path.join(dp, f)
                try:
                    if os.path.getmtime(p) < cutoff:
                        os.remove(p)
                        removed += 1
                except OSError:
                    pass
            if os.path.abspath(dp) != os.path.abspath(self.cache):
                try:
                    if not os.listdir(dp):
                        os.rmdir(dp)
                except OSError:
                    pass
        if removed:
            log('cache ttl %s: 过期清理 %d 个文件' % (self._ttl_label(), removed))
        return removed

    def _prune(self):
        if not self.cache_max_gb:
            return
        limit = self.cache_max_gb * (1024 ** 3)
        files, total = [], 0
        for dp, _dn, fn in os.walk(self.cache):
            for f in fn:
                p = os.path.join(dp, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                files.append((st.st_mtime, st.st_size, p))
                total += st.st_size
        if total <= limit:
            return
        files.sort()
        for _mt, sz, p in files:
            if total <= limit:
                break
            try:
                os.remove(p)
                total -= sz
            except OSError:
                pass


# ---------------------------------------------------------------- WebDAV
class Handler(BaseHTTPRequestHandler):
    server_version = 'cuefs/' + VERSION
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        if os.environ.get('CUEFS_QUIET'):
            return
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

    # -- 基础 ------------------------------------------------------
    @property
    def media(self):
        return self.server.media

    def _parts(self):
        return [x for x in unquote(urlparse(self.path).path).split('/') if x]

    def _overlay_path(self, parts):
        p = os.path.normpath(os.path.join(self.media.overlay, *parts)) if parts else self.media.overlay
        root = os.path.normpath(self.media.overlay)
        if not (p == root or p.startswith(root + os.sep)):
            return None
        return p

    def _send(self, code, body=b'', ctype='text/plain; charset=utf-8', extra=None, head=False):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('DAV', '1, 2')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body and not head and self.command != 'HEAD':
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    @staticmethod
    def _href(path):
        return quote(path, safe='/')

    def _check_auth(self):
        want = self.server.auth
        if not want:
            return True
        got = self.headers.get('Authorization') or ''
        if got.startswith('Basic '):
            try:
                if base64.b64decode(got[6:]).decode('utf-8', 'replace') == want:
                    return True
            except Exception:
                pass
        self._send(401, b'auth required', extra={'WWW-Authenticate': 'Basic realm="cuefs"'})
        return False

    # -- 资源解析 ---------------------------------------------------
    def _resolve(self, parts):
        """返回 (kind, album, track, overlay_path, overlay_exists)"""
        media = self.media
        op = self._overlay_path(parts)
        exists = bool(op) and os.path.exists(op)
        if not parts:
            return 'root', None, None, op, exists
        key = parts[0]
        a = media.albums.get(key)
        if a is None:
            return ('overlay' if exists else 'missing'), None, None, op, exists
        if len(parts) == 1:
            return 'album', a, None, op, exists
        tname = parts[1]
        if len(parts) == 2:
            t = next((x for x in a.tracks if media.track_name(x) == tname), None)
            if t is not None:
                return 'track', a, t, op, exists
            sp = media.sidecar_lookup(a, tname)
            if sp:
                return 'file', a, None, sp, True
        return ('overlay' if exists else 'missing'), a, None, op, exists

    # -- 方法 ------------------------------------------------------
    def do_OPTIONS(self):
        if not self._check_auth():
            return
        self._send(200, extra={
            'Allow': 'OPTIONS, GET, HEAD, PROPFIND, PUT, DELETE, MKCOL, PROPPATCH, '
                     'LOCK, UNLOCK, COPY, MOVE',
            'MS-Author-Via': 'DAV',
            'Accept-Ranges': 'bytes',
        })

    def do_GET(self):
        if not self._check_auth():
            return
        parts = self._parts()
        if not parts:
            return self._index()
        kind, a, t, op, exists = self._resolve(parts)
        if kind == 'track':
            try:
                path = self.media.build(a, t)
            except Exception as e:  # noqa: BLE001
                return self._send(500, ('build failed: %s' % e).encode('utf-8'))
            return self._send_file(path, 'audio/flac')
        if kind == 'file' and op and os.path.isfile(op):
            return self._send_file(op, self._ctype(op))
        if exists and os.path.isfile(op):
            return self._send_file(op, self._ctype(op))
        if kind == 'album':
            return self._listing(a)
        self._send(404, b'not found')

    def do_HEAD(self):
        if not self._check_auth():
            return
        parts = self._parts()
        kind, a, t, op, exists = self._resolve(parts)
        if kind == 'track':
            try:
                path = self.media.build(a, t)
            except Exception as e:  # noqa: BLE001
                return self._send(500, str(e).encode('utf-8'), head=True)
            return self._send_file(path, 'audio/flac', head=True)
        if exists and os.path.isfile(op):
            return self._send_file(op, self._ctype(op), head=True)
        self._send(404, b'', head=True)

    def _ctype(self, p):
        ext = os.path.splitext(p)[1].lower()
        return {'.flac': 'audio/flac', '.nfo': 'application/xml', '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg', '.png': 'image/png', '.lrc': 'text/plain; charset=utf-8',
                '.cue': 'application/octet-stream', '.m3u': 'audio/x-mpegurl'}.get(ext, 'application/octet-stream')

    def _send_file(self, path, ctype, head=False):
        try:
            size = os.path.getsize(path)
        except OSError:
            return self._send(404, b'gone', head=head)
        start, end, code = 0, size - 1, 200
        rng = self.headers.get('Range')
        if rng:
            m = re.match(r'bytes=(\d*)-(\d*)', rng.strip())
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
                if start >= size:
                    return self._send(416, b'', extra={'Content-Range': 'bytes */%d' % size})
                code = 206
        length = end - start + 1
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(length))
        self.send_header('DAV', '1, 2')
        self.send_header('ETag', '"%s-%d-%d"' % (hashlib.md5(path.encode()).hexdigest()[:8], size,
                                                int(os.path.getmtime(path))))
        if code == 206:
            self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, size))
        self.end_headers()
        if head:
            return
        with open(path, 'rb') as f:
            f.seek(start)
            remain = length
            while remain > 0:
                chunk = f.read(min(262144, remain))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remain -= len(chunk)

    # -- PROPFIND --------------------------------------------------
    def do_PROPFIND(self):
        if not self._check_auth():
            return
        parts = self._parts()
        depth = (self.headers.get('Depth') or '1').strip().lower()
        kind, a, t, op, exists = self._resolve(parts)

        if kind == 'root':
            entries = [('/', True, None, None)]
            if depth != '0':
                for key in sorted(self.media.albums):
                    entries.append(('/%s/' % key, True, None, None))
                for name in self._overlay_children([]):
                    if name not in self.media.albums:
                        entries.append(('/%s' % name, os.path.isdir(os.path.join(self.media.overlay, name)),
                                        None, None))
            return self._xml(entries, 207)

        if kind == 'album':
            entries = [('/%s/' % parts[0], True, None, None)]
            if depth != '0':
                try:
                    errs = self.media.build_all(a)
                except Exception as e:  # noqa: BLE001
                    log('propfind build_all failed: %s' % str(e)[:200])
                    errs = []
                shadow = set(self._overlay_children(parts))
                sidecars = self.media.sidecar_list(a)
                shadow |= set(sidecars)
                for tr in a.tracks:
                    nm = self.media.track_name(tr)
                    if nm in shadow:
                        continue
                    entries.append(('/%s/%s' % (parts[0], nm), False, tr, self.media.cached(a, tr)))
                for nm in sorted(shadow):
                    real = sidecars.get(nm)
                    entries.append(('/%s/%s' % (parts[0], nm),
                                    bool(real is None and os.path.isdir(os.path.join(op, nm))),
                                    None, None, real))
                if errs:
                    log('propfind build errors', parts[0], errs[:2])
            return self._xml(entries, 207)

        if kind == 'track':
            try:
                p = self.media.build(a, t)
            except Exception as e:  # noqa: BLE001
                return self._send(500, str(e).encode('utf-8'))
            return self._xml([('/%s/%s' % (parts[0], parts[1]), False, t, p)], 207)

        if kind == 'overlay':
            entries = [('/' + '/'.join(parts) + ('/' if os.path.isdir(op) else ''), os.path.isdir(op), None, None)]
            if depth != '0' and os.path.isdir(op):
                for nm in self._overlay_children(parts):
                    full = os.path.join(op, nm)
                    entries.append(('/%s/%s' % ('/'.join(parts), nm), os.path.isdir(full), None, None))
            return self._xml(entries, 207)

        self._send(404, b'not found')

    def _overlay_children(self, parts):
        op = self._overlay_path(parts)
        if not op or not os.path.isdir(op):
            return []
        try:
            return sorted(os.listdir(op))
        except OSError:
            return []

    def _xml(self, entries, code):
        out = ['<?xml version="1.0" encoding="utf-8"?>', '<D:multistatus xmlns:D="DAV:">']
        for entry in entries:
            href, isdir, tr, cache_path = entry[:4]
            real_hint = entry[4] if len(entry) > 4 else None
            op = self._overlay_path([x for x in unquote(href).split('/') if x])
            real = op if (op and os.path.exists(op) and not isdir) else (real_hint or cache_path)
            out.append('<D:response><D:href>%s</D:href><D:propstat><D:prop>'
                       % sx.escape(self._href(href)))
            if isdir:
                out.append('<D:resourcetype><D:collection/></D:resourcetype>')
            else:
                out.append('<D:resourcetype/>')
                size, mt = 0, time.time()
                if real and os.path.exists(real):
                    st = os.stat(real)
                    size, mt = st.st_size, st.st_mtime
                out.append('<D:getcontentlength>%d</D:getcontentlength>' % size)
                out.append('<D:getcontenttype>%s</D:getcontenttype>'
                           % sx.escape(self._ctype(real or 'x.flac')))
                out.append('<D:getlastmodified>%s</D:getlastmodified>' % formatdate(mt, usegmt=True))
                out.append('<D:getetag>"%s-%d"</D:getetag>'
                           % (hashlib.md5((href or '').encode()).hexdigest()[:8], int(mt)))
                out.append('<D:supportedlock><D:lockentry><D:lockscope><D:exclusive/>'
                           '</D:lockscope><D:locktype><D:write/></D:locktype></D:lockentry>'
                           '</D:supportedlock>')
            out.append('</D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>')
        out.append('</D:multistatus>')
        self._send(code, ''.join(out).encode('utf-8'), 'application/xml; charset=utf-8')

    # -- 写操作（全部重定向到 B） -----------------------------------
    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(n) if n > 0 else b''

    def do_PUT(self):
        if not self._check_auth():
            return
        parts = self._parts()
        op = self._overlay_path(parts)
        if not op or not parts:
            return self._send(403, b'bad path')
        data = self._body()
        existed = os.path.exists(op)
        try:
            os.makedirs(os.path.dirname(op), exist_ok=True)
            tmp = op + '.part'
            with open(tmp, 'wb') as f:
                f.write(data)
            os.replace(tmp, op)
        except OSError as e:
            return self._send(500, ('write failed: %s' % e).encode('utf-8'))
        self._send(204 if existed else 201, b'')
        log('PUT', '/'.join(parts), len(data), '->B')

    def do_MKCOL(self):
        if not self._check_auth():
            return
        parts = self._parts()
        op = self._overlay_path(parts)
        if not op:
            return self._send(403, b'bad path')
        if os.path.exists(op):
            return self._send(405, b'exists')
        try:
            os.makedirs(op, exist_ok=True)
        except OSError as e:
            return self._send(500, str(e).encode('utf-8'))
        self._send(201, b'')

    def do_DELETE(self):
        if not self._check_auth():
            return
        parts = self._parts()
        kind, a, t, op, exists = self._resolve(parts)
        if not exists:
            if kind in ('track', 'album', 'root'):
                return self._send(403, b'virtual resource is read-only')
            return self._send(404, b'not found')
        try:
            if os.path.isdir(op):
                shutil.rmtree(op)
            else:
                os.remove(op)
        except OSError as e:
            return self._send(500, str(e).encode('utf-8'))
        self._send(204, b'')
        log('DELETE', '/'.join(parts), '(from B)')

    def do_PROPPATCH(self):
        if not self._check_auth():
            return
        self._body()
        parts = self._parts()
        kind, a, t, op, exists = self._resolve(parts)
        if kind == 'missing':
            return self._send(404, b'not found')
        href = '/' + '/'.join(parts) + ('/' if kind in ('album', 'root') else '')
        xml = ('<?xml version="1.0" encoding="utf-8"?><D:multistatus xmlns:D="DAV:">'
               '<D:response><D:href>%s</D:href><D:propstat><D:prop/>'
               '<D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>'
               '</D:multistatus>' % sx.escape(self._href(href)))
        self._send(207, xml.encode('utf-8'), 'application/xml; charset=utf-8', {'Cache-Control': 'no-cache'})

    def do_LOCK(self):
        if not self._check_auth():
            return
        self._body()
        # WebDAV LOCK 令牌前缀，不是凭据；命中的是 secret-scan 的 zh-credential-assignment 误报
        token = 'opaquelocktoken:%s' % hashlib.md5(('%s-%f' % (self.path, time.time())).encode()).hexdigest()  # gitleaks:allow
        href = self._href(self.path)
        xml = ('<?xml version="1.0" encoding="utf-8"?><D:prop xmlns:D="DAV:"><D:lockdiscovery>'
               '<D:activelock><D:locktype><D:write/></D:locktype><D:lockscope><D:exclusive/>'
               '</D:lockscope><D:depth>infinity</D:depth><D:timeout>Second-600</D:timeout>'
               '<D:locktoken><D:href>%s</D:href></D:locktoken>'
               '<D:lockroot><D:href>%s</D:href></D:lockroot></D:activelock>'
               '</D:lockdiscovery></D:prop>' % (token, sx.escape(href)))
        self._send(200, xml.encode('utf-8'), 'application/xml; charset=utf-8',
                   {'Lock-Token': '<%s>' % token})

    def do_UNLOCK(self):
        if not self._check_auth():
            return
        self._send(204, b'')

    def do_COPY(self):
        self._copy_move(False)

    def do_MOVE(self):
        self._copy_move(True)

    def _copy_move(self, move):
        if not self._check_auth():
            return
        src = self._overlay_path(self._parts())
        dst_parts = [x for x in unquote(urlparse(self.headers.get('Destination') or '').path).split('/') if x]
        dst = self._overlay_path(dst_parts)
        if not src or not dst or not os.path.exists(src):
            return self._send(404, b'not found')
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if move:
                shutil.move(src, dst)
            elif os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        except OSError as e:
            return self._send(500, str(e).encode('utf-8'))
        self._send(201, b'')

    # -- 浏览页 ----------------------------------------------------
    def _index(self):
        rows = []
        for key in sorted(self.media.albums):
            a = self.media.albums[key]
            rows.append('<li><a href="/%s/">%s</a> — %d 轨 · %s</li>'
                        % (quote(key), sx.escape(key), len(a.tracks),
                           sx.escape(os.path.basename(a.audio_path()))))
        html = ('<!doctype html><meta charset="utf-8"><title>cuefs %s</title>'
                '<style>body{font-family:system-ui;margin:2rem;max-width:60rem}'
                'code{background:#f3f3f3;padding:.1rem .3rem;border-radius:.2rem}</style>'
                '<h1>cuefs · TAK/CUE 虚拟音乐库</h1>'
                '<p>backend=<code>%s</code> · 专辑 <b>%d</b> · 轨道 <b>%d</b> · '
                'overlay=<code>%s</code></p><ul>%s</ul>'
                '<p>挂载示例：<code>rclone mount cuefs:/ /mnt/cuefs --vfs-cache-mode off</code> '
                '（详见 README）</p>'
                % (VERSION, self.media.backend, len(self.media.albums),
                   sum(len(a.tracks) for a in self.media.albums.values()),
                   sx.escape(self.media.overlay), ''.join(rows)))
        self._send(200, html.encode('utf-8'), 'text/html; charset=utf-8')

    def _listing(self, a):
        items = ['<li><a href="/%s/%s">%s</a></li>' % (quote(self.media.album_key(a)),
                                                       quote(self.media.track_name(t)),
                                                       sx.escape(self.media.track_name(t)))
                 for t in a.tracks]
        for nm, sp in sorted(self.media.sidecar_list(a).items()):
            items.append('<li><a href="/%s/%s">%s</a> <small>%s</small></li>'
                         % (quote(self.media.album_key(a)), quote(nm), sx.escape(nm),
                            sx.escape('overlay' if sp.startswith(self.media.overlay) else 'src')))
        html = '<!doctype html><meta charset="utf-8"><h1>%s</h1><ul>%s</ul>' % (
            sx.escape(self.media.album_key(a)), ''.join(items))
        self._send(200, html.encode('utf-8'), 'text/html; charset=utf-8')


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description='cuefs — CUE+TAK 虚拟切片 WebDAV 服务')
    ap.add_argument('--src', default=os.environ.get('CUEFS_SRC', '/music-src'),
                    help='只读输入目录 A（CUE/TAK 原盘）')
    ap.add_argument('--overlay', default=os.environ.get('CUEFS_OVERLAY', '/music-overlay'),
                    help='可写覆盖层 B（Jellyfin 写入的 nfo/封面等）')
    ap.add_argument('--cache', default=os.environ.get('CUEFS_CACHE', '/cache'))
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=int(os.environ.get('CUEFS_PORT', '8099')))
    ap.add_argument('--ffmpeg', default=os.environ.get('FFMPEG', 'ffmpeg'))
    ap.add_argument('--ffprobe', default=os.environ.get('FFPROBE', 'ffprobe'))
    ap.add_argument('--backend', default=os.environ.get('CUEFS_BACKEND', 'auto'),
                    choices=('auto', 'wine', 'dll', 'ffmpeg'))
    ap.add_argument('--tak-dll', default=os.environ.get('CUEFS_TAK_DLL', '/app/tak_deco_lib.dll'))
    ap.add_argument('--wine', default=os.environ.get('CUEFS_WINE', 'wine'))
    ap.add_argument('--wine-python', default=os.environ.get('CUEFS_WINE_PYTHON', '/winepy/python.exe'))
    ap.add_argument('--takdec', default=os.environ.get('CUEFS_TAKDEC', '/app/takdec.py'))
    ap.add_argument('--keep-wav', action='store_true', default=os.environ.get('CUEFS_KEEP_WAV') == '1')
    ap.add_argument('--pregap', choices=('prev', 'next'), default=os.environ.get('CUEFS_PREGAP', 'prev'))
    ap.add_argument('--cache-max-gb', type=float, default=float(os.environ.get('CUEFS_CACHE_MAX_GB', '0')))
    ap.add_argument('--tak-mode', choices=('range', 'wav'),
                    default=os.environ.get('CUEFS_TAK_MODE', 'range'),
                    help='wine 后端如何取 TAK 音频：range=只解这一轨（默认），wav=先整盘解成 WAV')
    ap.add_argument('--cache-ttl', type=float, default=float(os.environ.get('CUEFS_CACHE_TTL', '0')),
                    help='缓存保留小时数，0=永不过期；访问命中会续期')
    ap.add_argument('--sidecar', choices=('both', 'src', 'overlay'),
                    default=os.environ.get('CUEFS_SIDECAR', 'both'),
                    help='封面/歌词/nfo 从哪里读：both=A(源目录)+B 都看，B 优先；src=只看源目录；overlay=只看 B')
    ap.add_argument('--workers', type=int, default=int(os.environ.get('CUEFS_WORKERS', '3')))
    ap.add_argument('--auth', default=os.environ.get('CUEFS_AUTH', ''),
                    help='Basic 认证 user:password（可选）')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--prefetch', default='')
    ap.add_argument('--export', default='')
    args = ap.parse_args()

    media = Media(args.src, args.overlay, args.cache, args.ffmpeg, args.ffprobe,
                  backend=args.backend, tak_dll=args.tak_dll, wine=args.wine,
                  wine_python=args.wine_python, takdec=args.takdec,
                  keep_wav=args.keep_wav, cache_max_gb=args.cache_max_gb,
                  cache_ttl_h=args.cache_ttl, tak_mode=args.tak_mode,
                  sidecar=args.sidecar,
                  pregap=args.pregap, workers=args.workers)

    if args.list:
        for k, a in sorted(media.albums.items()):
            print('%s\t%d tracks\t%s' % (k, len(a.tracks), a.audio_path()))
        return

    if args.export:
        total = 0
        for key in sorted(media.albums):
            a = media.albums[key]
            dest = os.path.join(args.export, key)
            os.makedirs(dest, exist_ok=True)
            for t in a.tracks:
                src = media.build(a, t)
                dst = os.path.join(dest, media.track_name(t))
                if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
                    shutil.copyfile(src, dst + '.part')
                    os.replace(dst + '.part', dst)
                total += os.path.getsize(dst)
        print('exported %d tracks, %s -> %s' % (sum(len(a.tracks) for a in media.albums.values()),
                                               human(total), args.export))
        return

    if args.prefetch:
        if args.prefetch == 'all':
            media.prefetch_all()
        else:
            a = media.albums.get(args.prefetch)
            if not a:
                print('no such album:', args.prefetch)
                return sys.exit(2)
            media.build_all(a)
        return

    if media.cache_ttl_h > 0:
        def _reaper():
            while True:
                time.sleep(max(30.0, min(600.0, media.cache_ttl_h * 1800)))
                try:
                    media._expire()
                except Exception:  # noqa: BLE001
                    pass
        media._expire()
        threading.Thread(target=_reaper, daemon=True).start()
        log('cache ttl %s，后台回收线程已启动' % media._ttl_label())

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.media = media
    srv.auth = args.auth
    srv.daemon_threads = True
    log('cuefs %s on http://%s:%d/ src=%s overlay=%s backend=%s'
        % (VERSION, args.host, args.port, args.src, args.overlay, media.backend))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
