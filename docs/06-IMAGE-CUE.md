# 任何「整盘 + CUE」都能切（不只 TAK）

cuefs 的切片逻辑与编码无关：**按 CUE 算出每轨的采样区间，取那段 PCM，再编码成 FLAC**。
所以「用哪个解码器把源文件变成 PCM」是可以换的：

| 源文件 | 解码器 | 说明 |
|---|---|---|
| `.tak` | **Wine + 官方 `tak_deco_lib.dll`** | FFmpeg 的 TAK 解码器只覆盖早期格式，TAK 1.0+ 会报 `TAK codec type 0 is not implemented`，必须用官方库 |
| `.flac` / `.wv` / `.tta` / `.m4a`(ALAC) / `.aiff` / `.wav` / `.ape` / `.mpc` / `.shn` … | **ffmpeg `-ss/-t`** | 直接按时间切，无损格式逐位一致 |

判定方式：源文件扩展名是 `.tak` → 走 Wine 分支；其它 → 走 ffmpeg 分支。
（`--backend ffmpeg` 可强制全走 ffmpeg，但那样 TAK 会失败。）

## 关键：精确到样本的时长

`ffprobe` 的 `format=duration` 只有百分之一秒，末轨按它会**少 100 多个样本**，
于是「逐轨拼接」永远差几百字节。1.4.0 起：

- 镜像里同时装了 `ffprobe`（静态版，和 ffmpeg 同一个包）；
- `exact_duration()` 用 `stream.duration_ts × time_base` 取精确样本数；
- WAV 仍优先用 RIFF 头直接算（`wav_duration`）。

## 实测矩阵（一张 25 轨、43.5 分钟的真实专辑）

同一段 PCM 分别封装成不同「整盘」格式，各跑一遍 `--export`，把所有轨解码后拼接求 MD5：

| 整盘格式 | 大小 | 逐轨拼接 PCM | MD5 | 与整盘一致 |
|---|---|---|---|---|
| FLAC | 270,598,260 | 521,320,800 | `c14fd3763fdbf2647662023c74a2a782` | ✅ |
| WavPack `.wv` | 283,947,912 | 521,320,800 | 同上 | ✅ |
| TTA `.tta` | 270,758,705 | 521,320,800 | 同上 | ✅ |
| ALAC `.m4a` | 281,643,098 | 521,320,800 | 同上 | ✅ |
| AIFF `.aiff` | 521,320,854 | 521,320,800 | 同上 | ✅ |
| TAK（Wine 后端） | 261,446,390 | 521,320,800 | 同上 | ✅ |

> APE / Musepack / Shorten 走的是同一条 ffmpeg 分支（镜像里 `ape`/`mpc7`/`mpc8`/`shorten`
> 解码器都在），只是没有合适的编码器来生成测试盘，所以没有纳入这张表。

## CUE 里怎么写

```cue
FILE "sample-disc.flac" WAVE    ← 扩展名换成 .wv / .tta / .m4a / .ape 都行
  TRACK 01 AUDIO
    TITLE "A Good Start"   ← 这行就是曲目名（见 docs/14-NAMING.md）
    INDEX 01 00:00:00
```

多盘（`CD1.flac` + `CD2.flac`）就放两个 `.cue`，各自指向自己的整盘文件。

## 一个已知取舍

ffmpeg 的 `-ss` 是「输入 seek + 精度丢弃」，对无损音频是采样精确的（上表已验证）；
但对**有损**源（mp3/aac 整盘）切片点会落在帧边界附近，属于有损格式的固有特性。

## 走 WebDAV 也一致（不只是 --export）

同一张 FLAC+CUE 盘，用 WebDAV **逐轨 HTTP GET** 下来再解码拼接：

```
tracks=25  pcm_bytes=521,320,800  md5=c14fd3763fdbf2647662023c74a2a782   ← 与整盘 PCM 完全相同
```

也就是说 Jellyfin 从 WebDAV 读到的每一轨，拼回去就是原始整盘的比特流。
