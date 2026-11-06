# 自己把 FLAC 打成 TAK（做测试素材 / 归档）

TAK 的**编码器**只有官方二进制 `Takc.exe`（32 位，随 TAK 2.3.3 包发布，无源码）。
所以「打包」这一步必须在 Windows，或带 i386 前缀的 Wine 里做；本项目的容器只负责**解码**，
在 amd64 镜像里跑不了 `takc.exe`（缺 syswow64）。

需要准备：

- `tak233.zip` 里的 `Applications/Takc.exe`
- `ffmpeg`（任意版本即可，用来 FLAC → WAV）
- 本仓库的 `tools/make_tak_album.py`（可选，一条命令全做完）

## 一、单曲：FLAC → TAK

`takc` 只吃 WAV，所以先还原成未压缩 PCM（不要重采样，否则就不是原盘了）：

```powershell
ffmpeg -y -i "01 - foo.flac" -c:a pcm_s16le -ar 44100 -ac 2 "01.wav"

& 'C:\tak233\Applications\Takc.exe' -e -pMax -md5 -wm0 -overwrite -silent "01.wav" "01.tak"

# 自检（TAK 自带解码器回读并比对 MD5）
& 'C:\tak233\Applications\Takc.exe' -t -md5 "01.tak"
```

- 源是 24 bit 就用 `-c:a pcm_s24le`；
- `-pMax` 最高压缩、`-md5` 存校验、`-wm0` 不弹窗。

## 二、一整张专辑（多曲共用一个 TAK + 一个 CUE）

顺序是关键：**先把所有轨拼成一整个 WAV，再编码一次**。不要每首单独打一个 TAK。

```powershell
# list.txt 每行：file '01.wav'
ffmpeg -f concat -safe 0 -i list.txt -c:a pcm_s16le -ar 44100 -ac 2 album.wav
& 'C:\tak233\Applications\Takc.exe' -e -pMax -md5 -wm0 -overwrite -silent album.wav album.tak
```

然后写 CUE，时间是 `mm:ss:ff`，**1 秒 = 75 帧**：

```
REM GENRE Test
REM DATE 2026
PERFORMER "Artist"
TITLE "Album"
FILE "album.tak" WAVE
  TRACK 01 AUDIO
    TITLE "Track 1"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Track 2"
    INDEX 00 00:20:00
    INDEX 01 00:22:00
```

- `INDEX 00` = 该轨前面那段静音的起点，`INDEX 01` = 音乐真正开始处；
- cuefs 默认 `--pregap prev`，把这段静音算进**上一轨**尾部（和 CD 抓轨的习惯一致），
  这样逐轨拼接起来才和整盘逐位相同；
- `FILE` 行不带 `WAVE` 也能解析，但建议写上。

## 三、一条命令全做完（推荐）

`tools/make_tak_album.py` 会：拼 WAV → 调 `takc` 编码 → 写 CUE → 用 `taklib` 回读做位级自检。

`plan.json`：

```json
{
  "album": "cuefs codec self-test",
  "performer": "Synthetic",
  "genre": "Test",
  "date": "2026",
  "outdir": "C:/out",
  "filename": "selftest",
  "tracks": [
    {"file": "C:/src/a.flac", "title": "Sine 440", "pregap": 0},
    {"file": "C:/src/b.flac", "title": "Sine 660", "pregap": 2.0},
    {"file": "C:/src/c.flac", "title": "Sweep",    "pregap": 1.5}
  ]
}
```

```powershell
$env:TAK_DLL     = 'C:\path\to\tak_deco_lib.dll'   # 自检用
$env:TAKLIB_DIR  = 'C:\path\to\app'                # taklib.py 所在目录
python make_tak_album.py plan.json
```

正常输出以 `RESULT: PASS` 结尾，并打印整盘 PCM MD5（源 WAV 与 TAK 回读必须相同）。

实测（Windows VM，44.1 kHz / 16 bit / 立体声）：

| 输入 | 结果 |
|---|---|
| 45 s 音乐 | 编码 0.4 s、解码 0.2 s，压缩比 ≈ 0.60，PCM MD5 与源 WAV 一致 |
| 63.5 s 三轨（含 2.0 s / 1.5 s pregap） | 生成 `selftest.tak` 675,645 B，轨边界连续，`RESULT: PASS` |

## 四、做公开测试素材时的注意事项

- 只用**公有领域 / CC0** 的录音，或自己合成（正弦、噪声、扫频都可以，压缩比极低，仓库不会变胖）；
- 别把商业录音的 TAK 放进仓库或 Release；
- TAK SDK 本身是 freeware（仅私人非商业、须原包分发），仓库里不收录它，见 `THIRD_PARTY_NOTICES.md`。
