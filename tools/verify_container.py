#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_container.py — 对运行中的 cuefs 容器做端到端校验。

用法：python3 verify_container.py http://127.0.0.1:8099 /path/to/overlay

检查项：
  1. 索引页 / PROPFIND 根
  2. 每张专辑的轨数
  3. 逐轨 GET（带 Range 抽查）→ ffmpeg 解成 s16le → 拼起来算 MD5，与已知整盘 MD5 对比
  4. PUT album.nfo → 文件应落在 B 目录，且 PROPFIND 能看到
"""
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import unquote, quote

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8099').rstrip('/')
OVERLAY = sys.argv[2] if len(sys.argv) > 2 else '/tmp/cuefs-overlay'
FFMPEG = os.environ.get('FFMPEG', 'ffmpeg')

EXPECT = {
    # 专辑名 -> (轨数, 整盘 PCM MD5, 字节数)
    'ef - a tale of melodies. ORIGINAL SOUNDTRACK ～elegia～': (
        25, 'c14fd3763fdbf2647662023c74a2a782', 521320800),
    'ef - a tale of melodies. O.S.T 2 ～felice～': (
        35, 'd7ec4180a09dd3ad7b9ad8be87ab82a3', 683928672),
}
NS = {'D': 'DAV:'}


def propfind(path, depth='1'):
    body = (b'<?xml version="1.0"?><D:propfind xmlns:D="DAV:"><D:prop>'
            b'<D:resourcetype/><D:getcontentlength/><D:getcontenttype/>'
            b'</D:prop></D:propfind>')
    req = urllib.request.Request(BASE + quote(path), data=body, method='PROPFIND',
                                 headers={'Depth': depth, 'Content-Type': 'application/xml'})
    with urllib.request.urlopen(req, timeout=600) as r:
        return ET.fromstring(r.read())


def entries(tree):
    out = []
    for resp in tree.findall('D:response', NS):
        href = unquote(resp.find('D:href', NS).text)
        prop = resp.find('D:propstat/D:prop', NS)
        isdir = prop.find('D:resourcetype/D:collection', NS) is not None
        size = prop.find('D:getcontentlength', NS)
        out.append((href, isdir, int(size.text) if size is not None and size.text else 0))
    return out


def main():
    ok = True
    print('== 根目录 ==')
    root = entries(propfind('/', '1'))
    for href, isdir, size in root:
        print('  %s %s' % ('DIR ' if isdir else 'FILE', href))
    albums = [h for h, d, _ in root if d and h != '/']
    print('专辑数:', len(albums))

    for href in albums:
        name = unquote(href.strip('/'))
        print('\n== 专辑 %s ==' % name)
        items = entries(propfind(href, '1'))
        tracks = sorted([h for h, d, _ in items if not d and h.lower().endswith('.flac')])
        others = [h for h, d, _ in items if not d and not h.lower().endswith('.flac')]
        print('  轨数 %d，非轨道文件 %s' % (len(tracks), others))
        exp = EXPECT.get(name)
        if exp and exp[0] != len(tracks):
            print('  !! 轨数不符，期望', exp[0])
            ok = False

        # Range 抽查：第一轨取前 4096 字节
        if tracks:
            req = urllib.request.Request(BASE + quote(tracks[0]), headers={'Range': 'bytes=0-4095'})
            with urllib.request.urlopen(req, timeout=600) as r:
                chunk = r.read()
                print('  Range 抽查: %s %d 字节 Content-Range=%s'
                      % (r.status, len(chunk), r.headers.get('Content-Range')))

        # 整盘拼接校验
        h = hashlib.md5()
        total = 0
        for t in tracks:
            with urllib.request.urlopen(BASE + quote(t), timeout=1800) as r:
                flac = r.read()
            p = subprocess.run([FFMPEG, '-v', 'error', '-i', 'pipe:0', '-f', 's16le',
                                '-acodec', 'pcm_s16le', 'pipe:1'],
                               input=flac, capture_output=True)
            if p.returncode != 0:
                print('  !! 解码失败', t, p.stderr[-200:])
                ok = False
                continue
            h.update(p.stdout)
            total += len(p.stdout)
        print('  拼接 PCM: %d 字节, MD5 %s' % (total, h.hexdigest()))
        if exp:
            if total == exp[2] and h.hexdigest() == exp[1]:
                print('  ✓ 与整盘 PCM 完全一致')
            else:
                print('  !! 与期望不符 (期望 %d / %s)' % (exp[2], exp[1]))
                ok = False

    # 写入重定向
    print('\n== 写入重定向测试 ==')
    nfo = b'<?xml version="1.0"?><album><title>probe</title></album>'
    first = albums[0] if albums else '/'
    target = first.rstrip('/') + '/album.nfo'
    req = urllib.request.Request(BASE + quote(target), data=nfo, method='PUT',
                                 headers={'Content-Type': 'application/xml'})
    with urllib.request.urlopen(req, timeout=60) as r:
        print('  PUT %s -> %d' % (target, r.status))
    disk = os.path.join(OVERLAY, unquote(target).strip('/'))
    print('  B 目录实际文件:', disk, '存在' if os.path.exists(disk) else '缺失')
    if not os.path.exists(disk):
        ok = False
    items = entries(propfind(first.rstrip('/') + '/', '1'))
    seen = any(h.endswith('album.nfo') for h, _d, _s in items)
    print('  PROPFIND 能看到 album.nfo:', seen)
    ok = ok and seen

    print('\n结果:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
