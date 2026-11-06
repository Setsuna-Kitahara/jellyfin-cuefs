#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 TAK 2.3.3 的解码库导入容器（安装时跑一次，不需要重新 build 镜像）。

为什么不在镜像里：TAK 解码器是 Thomas Becker 的 FREEWARE，只允许私人/非商业使用，
且要求「原包完整、未修改、不收费」地分发 —— 所以由使用者自己下载、自己导入。

用法
----
    # 方式 A：从标准输入灌进去（推荐，不落地宿主机临时文件）
    docker exec -i cuefs python3 /app/import_tak.py --accept-license - < tak233.zip

    # 方式 B：先 docker cp 再执行
    docker cp tak233.zip cuefs:/tmp/tak233.zip
    docker exec cuefs python3 /app/import_tak.py --accept-license /tmp/tak233.zip

    # 查看状态
    docker exec cuefs python3 /app/import_tak.py --status

`--accept-license` 表示你已阅读并接受 TAK 解码库的用户协议，承诺仅用于非商业目的。
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import zipfile

KNOWN_SHA256 = '40d26992266f1377d576b88b84b88d2ab256dc321e47f90314402a80692aba6a'
KNOWN_SIZE = 1765343
DLL_REL = 'Deco_Lib/x64/tak_deco_lib.dll'
DEFAULT_DST = os.environ.get('CUEFS_TAK_HOME', '/opt/tak')

NOTICE = """\
TAK (Tom's lossless Audio Kompressor) Decoder Library 2.3.3
Copyright (c) Thomas Becker. FREEWARE — private, non-commercial use only.
Redistribution must keep the original archive intact and unmodified.
https://www.tak-audio.com/  (official site; the SDK zip is linked there)
"""


def log(*a):
    sys.stderr.write(' '.join(str(x) for x in a) + '\n')


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def pe_machine(path):
    """读 PE 头的 Machine 字段：0x8664 = x86-64，0xAA64 = arm64。"""
    try:
        with open(path, 'rb') as f:
            data = f.read(0x400)
        off = int.from_bytes(data[0x3c:0x40], 'little')
        return int.from_bytes(data[off + 4:off + 6], 'little')
    except Exception:
        return 0


def status(dst):
    dll = os.path.join(dst, 'Deco_Lib', 'x64', 'tak_deco_lib.dll')
    acc = os.path.join(dst, 'ACCEPTED.json')
    if not os.path.exists(dll):
        print('TAK decoder: NOT INSTALLED')
        print('  → see docs/02-TAK-LICENSE.md')
        return 1
    info = {}
    if os.path.exists(acc):
        try:
            info = json.load(open(acc, encoding='utf-8'))
        except Exception:
            info = {}
    m = pe_machine(dll)
    print('TAK decoder: INSTALLED')
    print('  dll       : %s (%d bytes, machine=0x%04x%s)'
          % (dll, os.path.getsize(dll), m, ', x86-64' if m == 0x8664 else ''))
    print('  imported  : %s' % info.get('imported_at', '?'))
    print('  sha256    : %s' % info.get('sha256', '?'))
    print('  license   : private / non-commercial only (accepted by user at import time)')
    return 0


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('archive', nargs='?', help='tak233.zip，或 - 表示标准输入')
    ap.add_argument('--accept-license', action='store_true',
                    help='我接受 TAK 解码库的用户协议，并承诺仅用于非商业目的')
    ap.add_argument('--dst', default=DEFAULT_DST)
    ap.add_argument('--sha256', default=KNOWN_SHA256,
                    help='期望的 zip sha256（默认是 2.3.3 官方包）')
    ap.add_argument('--no-verify', action='store_true', help='跳过 sha256 校验（不推荐）')
    ap.add_argument('--status', action='store_true')
    args = ap.parse_args()

    if args.status:
        return status(args.dst)
    if not args.archive:
        ap.error('缺少 tak233.zip（或用 --status 查看状态）')
    if not args.accept_license:
        log('拒绝导入：请先确认你已阅读并接受 TAK 解码库协议（仅限私人/非商业用途）。')
        log('确认后加 --accept-license 重跑。协议摘要：')
        log(NOTICE)
        return 2

    tmp = None
    if args.archive == '-':
        tmp = '/tmp/_tak_import_%d.zip' % int(time.time())
        with open(tmp, 'wb') as f:
            shutil.copyfileobj(sys.stdin.buffer, f)
        path = tmp
    else:
        path = args.archive

    try:
        size = os.path.getsize(path)
        digest = sha256_file(path)
        log('archive: %s (%d bytes)' % (path, size))
        log('sha256 : %s' % digest)
        if not args.no_verify:
            if digest != args.sha256:
                log('校验失败：期望 %s' % args.sha256)
                log('如果你用的是别的版本，确认来源可信后加 --no-verify 重跑。')
                return 3
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if DLL_REL not in [n.replace('\\', '/') for n in names]:
                log('包里没找到 %s，可能不是 TAK 2.3.3 SDK。' % DLL_REL)
                return 4
            if os.path.isdir(args.dst):
                shutil.rmtree(args.dst)
            os.makedirs(args.dst, exist_ok=True)
            z.extractall(args.dst)   # 整包解开：许可要求原包完整
        dll = os.path.join(args.dst, 'Deco_Lib', 'x64', 'tak_deco_lib.dll')
        m = pe_machine(dll)
        if m and m != 0x8664:
            log('警告：这个 dll 不是 x86-64（machine=0x%04x），当前容器多半跑不起来。' % m)
        with open(os.path.join(args.dst, 'ACCEPTED.json'), 'w', encoding='utf-8') as f:
            json.dump({'imported_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                       'archive': os.path.basename(path),
                       'sha256': digest,
                       'license': 'TAK Decoder Library 2.3.3, freeware, private/non-commercial only',
                       'accepted_by': 'user (--accept-license)'}, f, ensure_ascii=False, indent=2)
        log('导入完成 → %s' % dll)
        log('容器无需重启：下一次请求会直接用上。')
        return 0
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


if __name__ == '__main__':
    sys.exit(main())
