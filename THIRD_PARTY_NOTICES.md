# 第三方组件与许可（开源许可清单）

本仓库**自己的**代码（`app/`、`docker/`、`tools/`、`docs/`、`sample/` 的脚本与 CUE、
根目录的 compose 文件）以 **MIT** 授权，见 [`LICENSE`](LICENSE)。

下面列的是**别人的东西**，各自条款独立生效。分三类看，混在一起最容易出错：

| 类别 | 含义 | 谁要履约 |
|---|---|---|
| **① 仓库里就有** | 跟着 `git clone` 下来 | 我们（每次发布） |
| **② 仓库里没有、镜像里有** | 构建时下载/安装进去 | 我们（发镜像时）+ 你（再分发镜像时） |
| **③ 谁都没有、你自己装** | 只在你的机器上 | 你 |

## 总览

| 组件 | 版本 | 许可 | 类别 | 在本项目的哪里 |
|---|---|---|---|---|
| TAK SDK（`tak_deco_lib.dll`） | 2.3.3 | **Freeware，仅私人非商业**（非开源） | ③ | 运行时由使用者导入，**仓库和镜像都不含** |
| Wine | Debian trixie 的 `wine64` | LGPL-2.1-or-later | ② | 完整版镜像 |
| CPython embeddable | 3.12.8 | PSF-2.0 | ① | `winepy/`（`LICENSE.txt` 原样保留） |
| ├ OpenSSL | 3.x | Apache-2.0 | ① | `winepy/libcrypto-3.dll`、`libssl-3.dll` |
| ├ libffi | 3.x | MIT | ① | `winepy/libffi-8.dll` |
| ├ SQLite | 3.x | Public Domain | ① | `winepy/sqlite3.dll` |
| └ MS VC++ 运行库 | 14.x | Microsoft 可再分发运行库条款 | ① | `winepy/vcruntime140.dll`、`vcruntime140_1.dll`、`python.cat` |
| 静态 ffmpeg / ffprobe | 构建当日的 release | **GPLv3**（johnvansickle 构建版） | ② | 构建时下载，**不进仓库**；镜像里 `/usr/local/bin` |
| Debian 基础镜像与 apt 包 | `debian:trixie-slim` + python3 / ca-certificates / curl / xz-utils | 各包自带（多为 MIT / PSF / curl / MPL-2.0 / 0BSD） | ② | 镜像内 `/usr/share/doc/*/copyright` |
| Pillow | 任意近期版本 | MIT-CMU（HPND 变体） | ③ | 只在 `sample/make_cover.py` 里，可选 |
| Liberation Sans 字体 | 系统包 | SIL OFL 1.1 | ③ | 封面脚本用的系统字体，**字体文件不随仓库** |
| 示例音频 | — | **CC0 1.0** | ① | `sample/src/*.mp3`、`sample-disc/`，署名见 `sample/CREDITS.md` |
| GitHub Actions | `checkout@v4`、`setup-python@v5` | MIT | ① | 只在 `.github/workflows/ci.yml` 里引用 |
| Dockerfile 前端 | `docker/dockerfile:1` | Apache-2.0 | ① | 两个 Dockerfile 的 `# syntax=` 行 |
| rclone / davfs2 / Jellyfin | 你选 | MIT / GPL-2.0 / GPL-2.0 | ③ | **不由本项目分发**，只是客户端 |

---

## 1. TAK SDK 2.3.3 —— Freeware，不是开源

- 作者：Thomas Becker（TAK / Tom's lossless Audio Kompressor）。
- 条款原文（`Deco_Lib/Readme.html`）：

  > This software is provided as FREEWARE, but only for private, non-commercial use…
  > The use of this software in a commercial application is only allowed with prior
  > written approval by the author (Thomas Becker).

- 再分发条件（原文）：

  > The software may be freely distributed provided that it is not modified and the
  > original archive remains intact with all accompanying files, and provided that
  > no fee is charged.

- 所以本项目：**仓库不收录**（`vendor/README.md` 只写怎么自己下）、**镜像不内置**。
  1.5.0 起镜像只带导入脚本 `app/import_tak.py`，由你执行：

  ```bash
  docker exec -i cuefs python3 /app/import_tak.py --accept-license - < tak233.zip
  ```

  脚本会校验 sha256、**保留原包不动**、只解出 x64 的 DLL —— 满足「原包完整、未修改」。
- **它不是开源许可**：本项目的 MIT 只覆盖我们自己的文件，不能也不试图把这部分 MIT 化。
- 商用前必须拿到作者书面许可。也不要分发「已导入解码库」的镜像 —— 那等于重新打包闭源库。
- 详见 [docs/02-TAK-LICENSE.md](docs/02-TAK-LICENSE.md)。

## 2. Wine —— LGPL-2.1-or-later

- 来源：Debian `wine64` 包，完整许可文本在镜像内 `/usr/share/doc/wine*/copyright`。
- 我们**不修改** Wine 的库代码，只是删掉了用不到的文件（`mshtml.dll`、`wined3d.dll`、
  `msxml3.dll`、`jscript.dll`、`d2d1.dll`、`d3d11.dll`、`dxgi.dll`、`d3d10core.dll`、
  `ddraw.dll`、`light.msstyles`、`winedbg.exe`、`ieframe.dll`）—— 属于「移除文件」，LGPL 允许。
- 对应源码由 Debian 镜像站提供（`deb-src` / `sources.debian.org`），换库需要时自行重编。
- 用途：在 Linux 上加载 Windows 版 TAK 解码 DLL。不用 TAK 的话完全可以不装（用 `cuefs:slim`）。

## 3. CPython embeddable 3.12.8（`winepy/`）—— PSF-2.0

- 官方 Windows embeddable 发行包，`winepy/LICENSE.txt` **原样保留**，未改动任何文件。
- 它内部还捆了几个第三方 DLL，各自的许可：

  | 文件 | 组件 | 许可 |
  |---|---|---|
  | `libcrypto-3.dll`、`libssl-3.dll` | OpenSSL 3.x | Apache-2.0 |
  | `libffi-8.dll` | libffi | MIT |
  | `sqlite3.dll` | SQLite | Public Domain |
  | `vcruntime140.dll`、`vcruntime140_1.dll` | Microsoft Visual C++ 运行库 | Microsoft 可再分发运行库条款（随 Python 官方包一起分发） |
  | `python.cat` | Windows 目录签名 | 同上 |
  | `python312.zip` 及其它 `.pyd` | CPython 标准库（zlib / bz2 / lzma / expat / unicodedata…） | PSF-2.0 或各自上游许可，见 `python312.zip` 内 `LICENSE.txt` |

- 用途：Wine 里跑一个 Windows 版 Python，由它用 `ctypes` 调 `tak_deco_lib.dll`。
  这个目录**只有完整版镜像**用到，slim 不需要。

## 4. 静态 ffmpeg —— GPLv3 构建版，只在镜像里

- 构建时从 `https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-<arch>-static.tar.xz`
  下载（该构建**启用了 GPL 组件**，故整体 GPLv3），解出 `ffmpeg`、`ffprobe` 放进镜像。
- **不进仓库**（49 MB 的仓库里没有它），GPL 义务落在「分发镜像」这一步：
  分发镜像 = 分发 GPL 二进制，需要随附①许可全文②获取对应源码的途径。
  我们的做法是指向上游：源码见 johnvansickle.com 的 `ffmpeg-release-<arch>-static.tar.xz`
  解压后的 `ffmpeg-*-static/` 说明与 FFmpeg 官方 `git://git.ffmpeg.org/ffmpeg.git`
  （对应 tag 见构建版里的 `VERSION`）。**你自己构建镜像再分发时，这条义务是你的。**
- 我们**没有修改** ffmpeg，只是调用它（`-ss/-t` 切片、`-c:a flac` 编码）。
- 想完全避开 GPL：自己换一个 LGPL 构建的 ffmpeg（去掉 `--enable-gpl`），
  命令行用到的功能都在 LGPL 范围内。

## 5. Debian 基础镜像与 apt 包

- 基础镜像 `debian:trixie-slim`（Debian 的社会契约 + 各包许可）。
- `apt-get install` 装的：`python3`（PSF-2.0）、`ca-certificates`（MPL-2.0）、
  `curl`（curl 许可）、`xz-utils`（0BSD / LGPL-2.1 混合）、完整版另加 `wine64`（见上）。
- 完整许可文本在镜像内 `/usr/share/doc/<包>/copyright`。
  （我们的 Dockerfile 删了 `/usr/share/doc/*` 来瘦身 —— **如果你打算分发镜像并需要随附许可文本，
  请把那一行 `rm -rf /usr/share/doc/*` 去掉**，这是已知的合规取舍。）

## 6. 示例专辑（`sample/`）

- 音频：Library of Congress「Citizen DJ / Free Music Archive」里**公有领域奉献（CC0）**的子集，
  作者 Monplaisir、Komiku；逐首来源与署名在 `sample/CREDITS.md`。
- 封面：`sample/make_cover.py` 用 **Pillow**（MIT-CMU / HPND）绘制，字体 **Liberation Sans**
  （**SIL OFL 1.1**）。字体文件**不随仓库**，脚本用系统里的 `/usr/share/fonts/...`。
- `sample-disc.cue` 里的 `TITLE` / `PERFORMER` 只是示例数据。
- 这些素材只用于跑通测试流程，不代表任何正式发行。

## 7. 只被「引用」、不被分发的

- **GitHub Actions**：`actions/checkout@v4`、`actions/setup-python@v5`，MIT；只在 CI 里跑。
- **Dockerfile 前端**：`# syntax=docker/dockerfile:1`，Apache-2.0；构建期由 BuildKit 拉取。
- **客户端**：rclone（MIT）、davfs2（GPL-2.0）、Jellyfin（GPL-2.0）、Windows 资源管理器 ——
  都在**你的**机器上，本项目不分发、不打包、不修改。
- `docs/configurator/index.html` 是纯前端单页，**无**第三方 JS/CSS 依赖。

## 8. 合规自查（分发前照着勾）

- [ ] 仓库里没有 `tak233.zip`、没有 `tak_deco_lib.dll`、没有任何商业专辑音频/歌词
- [ ] 镜像里没有 TAK 解码库（`import_tak.py --status` 在全新镜像上应是 NOT INSTALLED）
- [ ] 要发镜像：随附 GPLv3 文本 + ffmpeg 源码获取途径；如需 Debian 包许可文本，去掉删 `/usr/share/doc` 的那行
- [ ] 要商用：先解决 TAK freeware 的「非商业」限制（找作者要书面许可，或只发 slim 版）
- [ ] 示例素材署名（`sample/CREDITS.md`）没被删
