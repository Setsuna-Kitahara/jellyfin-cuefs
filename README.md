# cuefs

**把 TAK / FLAC / APE … 的「整盘 + CUE」镜像，变成 Jellyfin 能直接读的单曲库。**
不转码、不拆盘、不改原文件 —— 只在 Jellyfin 真的播放某一轨时，按 CUE 的时间轴把那一轨切出来。

<p align="center">
  <img src="sample/cover.jpg" alt="cuefs sample album cover" width="360">
</p>

- 前端是 **WebDAV**：Jellyfin 侧用 rclone / davfs2 挂上来，库路径照常填。
- 原盘目录 **只读**；Jellyfin 想写 NFO / 封面时，**重定向**到另一个可写目录（overlay）。
- 支持 **TAK**（需要官方的闭源解码库 + Wine），也支持 **FLAC / WavPack / TTA / ALAC / AIFF / WAV / APE / MPC / Shorten** 等 ffmpeg 能解的整盘格式。
- 两个官方镜像，**匿名可拉**（不用登录）：`cuefs:latest`（完整版，含 Wine，可解 TAK，**amd64**；压缩约 363 MB，解开 1.53 GB）
  / `cuefs:slim`（精简版，无 TAK，**amd64 + arm64**；压缩约 103 MB，解开 408 MB）。
- **在线文档**（每次改 `docs/` 由 GitHub Actions 自动渲染后发布）：
  <https://setsuna-kitahara.github.io/jellyfin-cuefs/> ·
  配置生成器 <https://setsuna-kitahara.github.io/jellyfin-cuefs/configurator.html>
- **镜像**：`ghcr.io/setsuna-kitahara/cuefs:latest`、`docker.io/kitaharasetsuna/cuefs:latest`（`:slim` 同上）；
  打 `v*` 标签时由 Actions 自动构建推送，见 [PUBLISH.md](PUBLISH.md)

> **版本说明**：`v1.5.0` 是**首个公开发布的版本**；1.0–1.4 属于内部迭代，没有对外发布过。
> 作者：Setsuna-Kitahara 与 DeepSeek Harness。

> 英文简介：cuefs exposes "disc image + CUE" albums (TAK, FLAC, WavPack, TTA, ALAC, AIFF, WAV, APE…) as a
> read-only WebDAV tree of virtual tracks, so Jellyfin can index and stream them **without transcoding
> the original disc**. The source directory is never modified; Jellyfin's writes (NFO, artwork) are
> redirected to a separate overlay directory. TAK support uses the official freeware decoder library
> through Wine and is therefore **amd64 only**.

---

## 为什么

Jellyfin 至今（10.10 / 10.11）**不认 CUE、也不解码 TAK**，`xxx.tak + xxx.cue` 这种整盘镜像在库里
只是一坨“无法识别的文件”。现有做法几乎都是**离线拆盘转 FLAC**：

- 多占一份空间（原盘 + 拆出来的 FLAC，通常是 2 倍）；
- 原盘信息（pregap、碟号、cue 里的 REM）在转换里丢掉；
- 想换格式/换命名就得重来一遍。

cuefs 的思路反过来：**原盘一个字节都不动**，只在有人播放时按需切片并缓存。
位级验证过：逐轨切片再拼接回来的 PCM，与整盘解码的 PCM **MD5 完全相同**
（见 [docs/06-IMAGE-CUE.md](docs/06-IMAGE-CUE.md)）。

## 30 秒看懂它长什么样

用仓库自带的**公有领域**示例盘举例（下面所有例子都用它，可以直接跑）：

```
/mnt/music-src/                     ← 目录 A（只读）：你自己的整盘
  sample-disc/
    sample-disc.tak                 ← 4 首曲子的整盘镜像
    sample-disc.cue                 ← 分轨表（专辑名和曲名都写在这里）

http://127.0.0.1:8099/              ← cuefs 输出的 WebDAV
  Public Domain Sampler/            ← 专辑名，来自 CUE 里的 TITLE
    01 - A Good Start.flac          ← 虚拟文件，播放时才生成
    02 - Beach.flac
    03 - Home.flac
    04 - Free To Use 9.flac
    cover.jpg                       ← 侧车：A 或 B 里的封面
    album.nfo

/mnt/music-overlay/                 ← 目录 B（可写）：Jellyfin 写的东西落这里
  Public Domain Sampler/
    album.nfo                       ← Jellyfin 自己补全的元数据
```

## 媒体库里的专辑名从哪来

这是最容易踩的一处：**Jellyfin 里的专辑名和曲目名，来自 CUE 里写的 `TITLE`，不是目录名拼出来的。**

```cue
PERFORMER "Monplaisir / Komiku"
TITLE "Public Domain Sampler"       ← 专辑名就是这一行
FILE "sample-disc.tak" WAVE

  TRACK 01 AUDIO
    TITLE "A Good Start"            ← 曲目名是 "01 - A Good Start.flac"
    PERFORMER "Monplaisir"
    INDEX 01 00:00:00
```

规则只有三条：

1. **专辑名** = CUE 顶层的 `TITLE`；WebDAV 里的**目录名**是它清洗掉 `\ / : * ? " < > |` 之后的版本，
   写进 FLAC 的 `album` 标签的是**原文** —— 所以「目录名」和「Jellyfin 里显示的名字」可以不一样。
2. **曲目名** = `NN - 曲名.flac`，`NN` 是 CUE 的 `TRACK` 号（补零两位），曲名是该轨的 `TITLE`。
3. **两张盘 TITLE 完全相同时**：文件系统层 cuefs 会自动加 4 位哈希区分（两张都留得住），
   但 Jellyfin 认的是 `album` + `album_artist` 标签，**可能把它们并成一张专辑**。

想改名字、多碟怎么排、中文/日文 CUE 的编码、重名的完整规则：见
**[docs/14-NAMING.md](docs/14-NAMING.md)**。

## 快速开始

官方镜像已经发布到两个仓库，**内容相同、匿名可拉**（不需要 `docker login`）：

| 从哪里拉 | 完整版（含 TAK 解码，amd64） | 精简版（无 TAK，amd64 + arm64） |
|---|---|---|
| GHCR | `ghcr.io/setsuna-kitahara/cuefs:latest` | `ghcr.io/setsuna-kitahara/cuefs:slim` |
| Docker Hub | `kitaharasetsuna/cuefs:latest` | `kitaharasetsuna/cuefs:slim` |

版本标签另有 `:1.5.0` 与 `:1.5.0-slim`。想自己构建就 `make full` / `make slim`（见 [Makefile](Makefile)）。

> 想少写命令？打开 **[配置生成器](https://setsuna-kitahara.github.io/jellyfin-cuefs/configurator.html)**（纯前端），
> 选完直接复制 `docker run` / `compose` / 安装步骤 / Jellyfin 挂载 / 卸载命令。

### 1) 完整版（要 TAK）

```bash
# 拉镜像（不写 tag 就是 latest = 完整版）
docker pull ghcr.io/setsuna-kitahara/cuefs:latest

# 起服务：A 只读挂进去，B 可写；端口只绑本机回环
docker run -d --name cuefs --restart unless-stopped \
  -p 127.0.0.1:8099:8099 \
  -v /mnt/music-src:/music-src:ro \
  -v /mnt/music-overlay:/music-overlay \
  -v cuefs-cache:/cache \
  ghcr.io/setsuna-kitahara/cuefs:latest
```

**完整版第一次启动还不能解 TAK** —— 解码库是第三方 freeware，不能随镜像分发，需要你自己下载、自己导入：

```bash
# 从 https://www.tak-audio.com/ 下载 TAK 2.3.3 SDK（tak233.zip，1,765,343 字节）
docker exec -i cuefs python3 /app/import_tak.py --accept-license - < tak233.zip
docker exec cuefs python3 /app/import_tak.py --status   # 应显示 INSTALLED
```

细节与许可说明：[docs/02-TAK-LICENSE.md](docs/02-TAK-LICENSE.md)

### 2) 精简版（不要 TAK，能跑 arm64）

```bash
docker pull ghcr.io/setsuna-kitahara/cuefs:slim
docker run -d --name cuefs --restart unless-stopped \
  -p 127.0.0.1:8099:8099 \
  -v /mnt/music-src:/music-src:ro \
  -v /mnt/music-overlay:/music-overlay \
  -v cuefs-cache:/cache \
  ghcr.io/setsuna-kitahara/cuefs:slim
```

精简版没有 Wine，**解不了 TAK**，但 FLAC / WavPack / TTA / ALAC / AIFF / WAV / APE / MPC 的「整盘+CUE」全都能用。
ARM64（树莓派、群晖 ARM、Apple Silicon Docker）只能用这个版本。

### 3) 接进 Jellyfin

```bash
# 宿主机上挂 WebDAV（推荐 rclone；davfs2 也行）
rclone mount cuefs: /mnt/jellyfin-cuefs --allow-other --vfs-cache-mode off --daemon
```

然后在 Jellyfin 里新建音乐库，路径填 `/mnt/jellyfin-cuefs`，**关掉「实时监控」**。
详细（含 Jellyfin 容器里怎么挂、NFO 怎么写回 B）见 [docs/04-JELLYFIN.md](docs/04-JELLYFIN.md)。

## 配置

| 想要 | 怎么做 |
|---|---|
| 改端口 | `-p 127.0.0.1:9000:8099` |
| 加密码 | `-e CUEFS_AUTH=user:pass`（Basic 认证） |
| 缓存上限 | `-e CUEFS_CACHE_MAX_GB=2` |
| 缓存过期 | `-e CUEFS_CACHE_TTL=24`（小时；命中会续期；0=永不过期） |
| 封面/歌词/NFO 从哪读 | `-e CUEFS_SIDECAR=both`（默认）/ `src` / `overlay` |
| 只暴露给局域网 | 别加 `-p 127.0.0.1`，改成 `-p 8099:8099`，然后自己加认证/反代 —— 见 [docs/10-SECURITY.md](docs/10-SECURITY.md) |

全部参数：[docs/03-CONFIG.md](docs/03-CONFIG.md) · 在线配置页（选一选就生成安装命令）：
[docs/configurator/index.html](docs/configurator/index.html)

## 我来测一下（3 分钟冒烟）

仓库里带了一套**公有领域**的示例整盘（TAK + CUE + NFO + SAMPLE 封面），直接拿来验流程：

```bash
git clone https://github.com/Setsuna-Kitahara/jellyfin-cuefs.git && cd jellyfin-cuefs
docker compose -f docker-compose.sample.yml up -d   # 或按 docs/08-SAMPLE-TEST.md 手动跑
curl -s http://127.0.0.1:8099/ | head
```

预期：看到 1 张专辑 `Public Domain Sampler` / 4 轨；`curl` 某一轨能拿到 `200`，`Range` 请求回 `206`。
逐项步骤与预期数字见 [docs/08-SAMPLE-TEST.md](docs/08-SAMPLE-TEST.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [docs/00-INDEX.md](docs/00-INDEX.md) | 全部文档索引 |
| [docs/01-QUICKSTART.md](docs/01-QUICKSTART.md) | 从零到出声的最短路径 |
| [docs/02-TAK-LICENSE.md](docs/02-TAK-LICENSE.md) | TAK 解码库的许可、导入、承诺 |
| [docs/03-CONFIG.md](docs/03-CONFIG.md) | 参数表（全部 CLI / 环境变量 / 默认值） |
| [docs/04-JELLYFIN.md](docs/04-JELLYFIN.md) | 挂载进 Jellyfin（rclone / davfs2 / 导出三种） |
| [docs/05-SIDECAR.md](docs/05-SIDECAR.md) | 封面 / 歌词 / NFO 的两种摆放方式 |
| [docs/06-IMAGE-CUE.md](docs/06-IMAGE-CUE.md) | 非 TAK 的整盘格式、位级一致性验证 |
| [docs/07-MAKE-TAK.md](docs/07-MAKE-TAK.md) | 自己把 FLAC 打成 TAK + CUE |
| [docs/08-SAMPLE-TEST.md](docs/08-SAMPLE-TEST.md) | 示例专辑与冒烟 / 缓存 / 缓外效率测试 |
| [docs/09-ARM64.md](docs/09-ARM64.md) | ARM64 的支持边界与替代方案 |
| [docs/10-SECURITY.md](docs/10-SECURITY.md) | 只听 127.0.0.1、认证、反代、只读 |
| [docs/11-METADATA.md](docs/11-METADATA.md) | NFO 能补什么、补不了什么、meta.json |
| [docs/12-OPS.md](docs/12-OPS.md) | 更新、卸载、备份、排错表 |
| [docs/13-FAQ.md](docs/13-FAQ.md) | 常见问题 |
| [docs/14-NAMING.md](docs/14-NAMING.md) | **媒体库里的专辑名与曲目名怎么来的** |

## 开放源代码许可

本仓库**自有代码**用 MIT；但一套「整盘镜像 → Jellyfin」的链路会牵扯不少第三方组件，
这里把它们**全部**列清楚，逐条写明许可、用途、是否随本仓库/镜像分发。
完整清单（含每个 DLL 的来源与再分发条件）见 **[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**。

### 随本仓库分发的

| 组件 | 版本 | 许可 | 用在哪 |
|---|---|---|---|
| **cuefs 自有代码**（`app/`、`tools/`、`docker/`、`docs/`） | 1.5.0 | **MIT** | 全部功能 |
| **CPython embeddable**（`winepy/`） | 3.12.8 | **PSF-2.0** | Wine 里跑的 Python；`winepy/LICENSE.txt` 原样保留 |
| OpenSSL 运行库（`libcrypto-3.dll` / `libssl-3.dll`） | 3.x | **Apache-2.0** | CPython 的 `ssl`/`hashlib` 依赖 |
| libffi（`libffi-8.dll`） | 3.4 | **MIT** | CPython 的 `ctypes` 依赖 |
| SQLite（`sqlite3.dll`） | 3.x | **公有领域** | CPython 标准库 |
| MSVC 运行库（`vcruntime140.dll` / `vcruntime140_1.dll`） | 14.x | **Microsoft 可再分发组件**（随 VS 再分发许可） | CPython 的 C 运行时 |
| 示例音频（`sample/`，4 首） | — | **CC0 1.0**（公有领域） | 冒烟测试用的整盘 + CUE；来源署名见 [sample/CREDITS.md](sample/CREDITS.md) |
| 示例封面（`sample/cover.jpg`） | — | **CC0 1.0** | 同上；由 `sample/make_cover.py` 生成 |

### 只随**镜像**分发（不随仓库）

| 组件 | 许可 | 说明 |
|---|---|---|
| **ffmpeg / ffprobe**（静态构建，johnvansickle.com） | **GPLv3**（该静态构建启用了 `--enable-gpl`） | 镜像里的 `/usr/local/bin/ffmpeg`；**源码可从构建站获取**，本仓库不分发二进制 |
| Debian `trixie-slim` 基础镜像 | 各包各自许可（多数 GPL/LGPL/BSD/MIT） | apt 只装 `python3 ca-certificates curl xz-utils`（完整版另加 `wine64`） |
| **Wine**（`wine64`，Debian 包） | **LGPL-2.1+**（含若干 MIT/BSD 组件） | 只在完整版镜像里；用来跑官方的 32 位 TAK 解码 DLL |
| Python 3（Debian 包，宿主侧） | PSF-2.0 | 运行 `app/cuefs.py` |

### **不**分发、必须你自己取得

| 组件 | 许可 | 说明 |
|---|---|---|
| **TAK 解码库**（Thomas Becker 的 TAK 2.3.3 SDK，`tak_deco_lib.dll`） | **freeware，仅限私人非商业使用**；分发必须保持原包完整，不得拆分/修改 | 不是开源软件。**不在仓库、也不在镜像里**；由你从 <https://www.tak-audio.com/> 下载 `tak233.zip` 后自行导入（[docs/02-TAK-LICENSE.md](docs/02-TAK-LICENSE.md)） |
| Jellyfin 服务端 | **GPLv2** | 本项目的使用方，不由本项目分发 |
| rclone | **MIT** | 推荐的 WebDAV 客户端，不由本项目分发 |
| davfs2 | **GPLv3** | 可选的 WebDAV 挂载方式，不由本项目分发 |

### 只在开发/构建时才用到的

| 组件 | 许可 | 用在哪 |
|---|---|---|
| Pillow | **MIT-CMU（HPND）** | 仅 `sample/make_cover.py` 生成示例封面，运行时不依赖 |
| Liberation Sans（`/usr/share/fonts/...`） | **SIL OFL 1.1** | 同上，字体文件不随仓库分发，运行时不需要 |
| GitHub Actions：`actions/checkout@v4`、`actions/setup-python@v5` | **MIT** | `.github/workflows/ci.yml` |
| Dockerfile 前端 `docker/dockerfile:1` | **Apache-2.0** | 两个 Dockerfile 的 `# syntax=` 行 |

### 一句话总结

- **本仓库的代码是 MIT**，可以自由使用、修改、商用（MIT 部分）。
- **ffmpeg 是 GPLv3**：你在分发**镜像**（而不是源码）时要一并满足 GPLv3 的源码提供义务；
  只用本项目、不对外分发镜像则不受影响。
- **TAK 解码库不是开源软件**：只授权私人非商业用途，且必须原包分发。商业使用请自行联系 Thomas Becker。
- 任何组件出问题，请先看 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 里对应条目；
  需要替换某个组件（比如换非 GPL 的 ffmpeg 构建）时，改动点只有 `docker/Dockerfile*` 的那一行 `curl`。

## 来源与致谢

- 作者：**Setsuna-Kitahara 与 DeepSeek Harness**。
- 示例音频：Library of Congress「Citizen DJ / FMA」公有领域子集（Monplaisir、Komiku），
  逐条署名见 [sample/CREDITS.md](sample/CREDITS.md)。
- TAK 解码库（`tak_deco_lib.dll`）版权归 **Thomas Becker**，按其 freeware 条款使用。
