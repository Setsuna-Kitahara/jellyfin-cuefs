#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""taklib — tak_deco_lib.dll 的 ctypes 绑定（TAK 官方解码库，带随机访问）。

用途：给 cuefs 提供「按样本位置 seek + 只解码指定区间」的能力，
这样既不拆分原盘，也不用把整张专辑解码一遍。

依赖：tak_deco_lib.dll（x64，来自 TAK 2.3.3 SDK 的 Deco_Lib\x64\）。
"""
import ctypes
import os
import sys

if sys.platform == 'win32':
    from ctypes import wintypes
    c_int32 = ctypes.c_int32
    c_int64 = ctypes.c_int64
else:  # pragma: no cover - 只为在本机做语法/结构自检
    c_int32 = ctypes.c_int32
    c_int64 = ctypes.c_int64


class StreamInfo(ctypes.Structure):
    _fields_ = [
        ('Codec', c_int32),
        ('Profile', c_int32),
        ('FrameSize', c_int32),
        ('FrameSizeInSamples', c_int32),
        ('SampleNum', c_int64),
        ('DataType', c_int32),
        ('SampleRate', c_int32),
        ('SampleBits', c_int32),
        ('ChannelNum', c_int32),
        ('BlockSize', c_int32),
        ('HasExtension', c_int32),
        ('ValidBitsPerSample', c_int32),
        ('HasSpeakerAssignment', c_int32),
        ('SpeakerAssignment', ctypes.c_char * 16),
    ]


class SSDOptions(ctypes.Structure):
    _fields_ = [('Cpu', c_int32), ('Flags', c_int32)]


class StateInfo(ctypes.Structure):
    _fields_ = [
        ('OpenResult', c_int32),
        ('SumResult', c_int32),
        ('StreamSampleNum', c_int64),
        ('ReadSampleNum', c_int64),
        ('DamagedSampleNum', c_int64),
        ('SkippedDataBlockNum', c_int32),
    ]


def _default_dll():
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, 'tak_deco_lib.dll'),
                 os.path.join(here, 'x64', 'tak_deco_lib.dll')):
        if os.path.exists(cand):
            return cand
    return 'tak_deco_lib.dll'


class TakFile(object):
    """单个 TAK 文件的随机访问解码器。"""

    def __init__(self, path, dll=None):
        self.dll_path = dll or _default_dll()
        self.lib = ctypes.WinDLL(self.dll_path)
        self._bind()
        opts = SSDOptions(0, 0)
        self.h = self.lib.tak_SSD_Create_FromFileW(ctypes.c_wchar_p(path),
                                                   ctypes.byref(opts), None, None)
        if not self.h:
            raise RuntimeError('tak_SSD_Create_FromFileW 返回空句柄（文件打不开？）')
        if not self.lib.tak_SSD_Valid(self.h):
            self.close()
            raise RuntimeError('TAK 解码器报告文件无效')
        self.info = StreamInfo()
        r = self.lib.tak_SSD_GetStreamInfo_V22(self.h, ctypes.byref(self.info))
        if r != 0:
            self.close()
            raise RuntimeError('tak_SSD_GetStreamInfo_V22 失败，code=%d' % r)
        self.sample_rate = self.info.SampleRate
        self.channels = self.info.ChannelNum
        self.bits = self.info.SampleBits
        self.samples = self.info.SampleNum
        self.bytes_per_sample = max(1, self.bits // 8)
        self.frame_bytes = self.channels * self.bytes_per_sample
        self.duration = (self.samples / float(self.sample_rate)) if self.sample_rate else 0.0

    def _bind(self):
        L = self.lib
        L.tak_SSD_Create_FromFileW.restype = ctypes.c_void_p
        L.tak_SSD_Create_FromFileW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(SSDOptions),
                                               ctypes.c_void_p, ctypes.c_void_p]
        L.tak_SSD_Valid.restype = c_int32
        L.tak_SSD_Valid.argtypes = [ctypes.c_void_p]
        L.tak_SSD_GetStreamInfo_V22.restype = c_int32
        L.tak_SSD_GetStreamInfo_V22.argtypes = [ctypes.c_void_p, ctypes.POINTER(StreamInfo)]
        L.tak_SSD_GetStateInfo.restype = c_int32
        L.tak_SSD_GetStateInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(StateInfo)]
        L.tak_SSD_Seek.restype = c_int32
        L.tak_SSD_Seek.argtypes = [ctypes.c_void_p, c_int64]
        L.tak_SSD_ReadAudio.restype = c_int32
        L.tak_SSD_ReadAudio.argtypes = [ctypes.c_void_p, ctypes.c_void_p, c_int32,
                                        ctypes.POINTER(c_int32)]
        L.tak_SSD_Destroy.restype = None
        L.tak_SSD_Destroy.argtypes = [ctypes.c_void_p]
        L.tak_SSD_GetErrorString.restype = c_int32
        L.tak_SSD_GetErrorString.argtypes = [c_int32, ctypes.c_char_p, c_int32]

    def errstr(self, code):
        try:
            buf = ctypes.create_string_buffer(64)
            self.lib.tak_SSD_GetErrorString(code, buf, 64)
            return buf.value.decode('utf-8', 'replace')
        except Exception:
            return 'code=%d' % code

    def seek(self, start_sample):
        r = self.lib.tak_SSD_Seek(self.h, c_int64(int(start_sample)))
        if r not in (0, 1):
            raise RuntimeError('seek 失败: ' + self.errstr(r))
        self.pos = int(start_sample)

    def read(self, sample_count, bufsize=1 << 20):
        """从当前位置顺序读 sample_count 个采样帧，返回 bytes（PCM 交错）。"""
        out = bytearray()
        remaining = int(sample_count)
        per_chunk = max(1, int(bufsize) // self.frame_bytes)
        while remaining > 0:
            n = min(remaining, per_chunk)
            buf = ctypes.create_string_buffer(n * self.frame_bytes)
            got = c_int32(0)
            r = self.lib.tak_SSD_ReadAudio(self.h, buf, c_int32(n), ctypes.byref(got))
            if r not in (0, 1):
                raise RuntimeError('read 失败: ' + self.errstr(r))
            if got.value <= 0:
                break
            out += buf.raw[:got.value * self.frame_bytes]
            remaining -= got.value
            self.pos += got.value
        return bytes(out)

    def read_at(self, start_sample, sample_count):
        self.seek(start_sample)
        return self.read(sample_count)

    def close(self):
        if getattr(self, 'h', None):
            try:
                self.lib.tak_SSD_Destroy(self.h)
            except Exception:
                pass
            self.h = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def __del__(self):
        self.close()


if __name__ == '__main__':
    p = sys.argv[1]
    t = TakFile(p)
    print('rate=%d ch=%d bits=%d samples=%d dur=%.3fs' %
          (t.sample_rate, t.channels, t.bits, t.samples, t.duration))
    data = t.read_at(0, 44100)
    print('read bytes', len(data), 'nonzero', any(data[:4096]))
