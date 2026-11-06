# 03 · 配置：CLI 参数 / 环境变量 / 推荐组合

两种写法等价：命令行 `--cache-ttl 24`，或者环境变量 `CUEFS_CACHE_TTL=24`（docker `-e`）。

## 参数总表

| 参数 | 环境变量 | 默认 | 说明 |
|---|---|---|---|
| `--src` | `CUEFS_SRC` | `/music-src` | **目录 A**：整盘目录，只读。可以放多层子目录 |
| `--overlay` | `CUEFS_OVERLAY` | `/music-overlay` | **目录 B**：可写层。Jellyfin 写的 NFO/封面、你自己的侧车都落这里 |
| `--cache` | `CUEFS_CACHE` | `/cache` | 切片缓存目录。可换成 tmpfs 做“零落盘” |
| `--host` | — | `0.0.0.0` | 监听地址。**建议改成 127.0.0.1**（见 [10-SECURITY.md](10-SECURITY.md)） |
| `--port` | `CUEFS_PORT` | `8099` | 端口 |
| `--backend` | `CUEFS_BACKEND` | `auto` | `auto` / `wine`（用 Wine+官方 DLL）/ `dll`（原生 Linux 直接加载 DLL，几乎不可用）/ `ffmpeg`（纯 ffmpeg，不支持 TAK） |
| `--tak-dll` | `CUEFS_TAK_DLL` | `/app/tak_deco_lib.dll` | DLL 路径。完整版镜像里是 `/opt/tak/Deco_Lib/x64/tak_deco_lib.dll`（导入后自动探测） |
| `--wine` | `CUEFS_WINE` | `wine` | Wine 可执行文件。Debian 包里是 `/usr/lib/wine/wine64`（镜像已设好） |
| `--wine-python` | `CUEFS_WINE_PYTHON` | `/winepy/python.exe` | 跑在 Wine 里的 Windows Python（镜像内置） |
| `--takdec` | `CUEFS_TAKDEC` | `/app/takdec.py` | TAK→WAV 的小程序 |
| `--pregap` | `CUEFS_PREGAP` | `prev` | `prev`：把下一轨的 `INDEX 00` 段算进**上一轨**（逐轨拼接=整盘，推荐）；`next`：算进下一轨开头（少数播放器的理解） |
| `--tak-mode` | `CUEFS_TAK_MODE` | `range` | `range`：只解这一轨的样本区间（默认，冷启动 1–3 s）；`wav`：先把整盘解成 WAV 再切（吃 ~500 MB 临时空间，只在调试时用） |
| `--cache-ttl` | `CUEFS_CACHE_TTL` | `0` | 缓存保留小时数；`0`=永不过期；**命中会续期** |
| `--cache-max-gb` | `CUEFS_CACHE_MAX_GB` | `0` | 缓存上限（GB），超了按 LRU 删；`0`=不限 |
| `--sidecar` | `CUEFS_SIDECAR` | `both` | 封面/歌词/NFO 从哪读：`both`（B 优先，A 兜底）/ `src`（A 优先，B 兜底）/ `overlay`（只看 B） |
| `--workers` | `CUEFS_WORKERS` | `3` | 并发解码数。机械盘/ARM 建议 1–2 |
| `--auth` | `CUEFS_AUTH` | 空 | Basic 认证 `user:password`；空=不认证 |
| `--keep-wav` | `CUEFS_KEEP_WAV=1` | 关 | `tak-mode=wav` 时保留整盘 WAV（默认用完就删） |
| `--ffmpeg` / `--ffprobe` | `FFMPEG` / `FFPROBE` | `ffmpeg` / `ffprobe` | 外部二进制路径 |
| `--list` | — | — | 打印解析结果（专辑名 / 轨数 / 源文件）后退出，用来查 CUE 有没有解析对 |
| `--prefetch` | — | 空 | `all`：启动时把**所有**轨都生成一遍（预热；对小库还行，大库别用） |
| `--export` | — | 空 | 把缓存里的轨复制成真实目录 `DIR/<专辑名>/NN - 曲名.flac` 后退出（静态方案用）。`<专辑名>`/`曲名` 与 WebDAV 里的完全一致，见 [14-NAMING.md](14-NAMING.md) |

## 环境变量里没有的（只能用 CLI 的场景）

`--list`、`--prefetch`、`--export` 是一次性动作，直接在命令行给：

```bash
docker run --rm -v /mnt/music-src:/music-src:ro cuefs:latest --list
docker run --rm -v /mnt/music-src:/music-src:ro -v /mnt/export:/export \
  cuefs:latest --export /export
```

## 推荐组合

### 家用 NAS，一套 30 张 TAK（典型）

```bash
docker run -d --name cuefs --restart unless-stopped \
  -p 127.0.0.1:8099:8099 \
  -v /mnt/music-src:/music-src:ro \
  -v /mnt/music-overlay:/music-overlay \
  -v cuefs-cache:/cache \
  -e CUEFS_PREGAP=prev \
  -e CUEFS_TAK_MODE=range \
  -e CUEFS_CACHE_TTL=72 \
  -e CUEFS_CACHE_MAX_GB=4 \
  -e CUEFS_WORKERS=2 \
  cuefs:latest
```

### 小硬盘 / 只想“让 Jellyfin 看到文件”

```bash
-e CUEFS_CACHE_TTL=6 -e CUEFS_CACHE_MAX_GB=1
# 或者干脆不落盘：
--tmpfs /cache:size=512m
```

### 多人共用、想有点门槛

```bash
-e CUEFS_AUTH=alice:s3cret
# rclone 侧： rclone config → WebDAV → vendor=other → url=http://127.0.0.1:8099/ → user/pass
```

### 老机械盘 / 树莓派

```bash
-e CUEFS_WORKERS=1 -e CUEFS_CACHE_TTL=0 -e CUEFS_CACHE_MAX_GB=8
# 宁可缓存久一点，也别反复解码
```

## 缓存机制

- 路径：`/cache/<sha1(绝对路径 of .cue) 前 12 位>/NN.flac`
- **缓存键只跟 CUE 的路径有关**，跟 CUE 内容无关：改了 CUE 的 `TITLE`、或者改了 `meta.json`
  的标签，缓存里的 FLAC 还是旧的（标签是切片那一刻烧进去的）。要么清缓存，要么等 TTL 过期
- 只有 Jellyfin 真去读某一轨时才生成；`PROPFIND` 不生成（`--prefetch` 除外）
- 命中时刷新 mtime（所以“常听的留着、不听的过期”）
- TTL 清理：后台线程每 `max(30s, min(600s, ttl*1800s))` 扫一次；`--cache-max-gb` 另外按 LRU 删
- 想立刻清空：`docker exec cuefs sh -c 'rm -rf /cache/*'`（只影响缓存，不碰 A/B）；
  想只清某一张：`ls /cache` 找到那 12 位哈希再删那一个子目录。改名相关的完整说明见
  [14-NAMING.md](14-NAMING.md) 第四节

## 验证配置是否生效

```bash
docker logs cuefs | head -5
# [..] albums: 4 backend: wine tracks: 119
# [..] cuefs 1.5.0 on http://0.0.0.0:8099/ src=/music-src overlay=/music-overlay backend=wine
```

`backend` 的三个可能值：`wine`（完整版，可用）、`ffmpeg`（精简版或没装 Wine）、`none`（既没 Wine 也没 DLL）。
`albums: 0` 说明 A 目录没挂对，或者 CUE 的 `FILE` 指向的文件不存在。
