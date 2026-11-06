# 第三方组件与许可

本仓库自有的代码（`app/`、`Dockerfile`、`docker-compose.yml`、`tools/`、文档）以
**MIT** 授权，见 `LICENSE`。下面这些不是我们的代码，各自的条款独立生效。

## 1. TAK SDK 2.3.3（`tak_deco_lib.dll`）—— **不在本仓库内**

- 作者：Thomas Becker（TAK / Tom's lossless Audio Kompressor）。
- 性质：**FREEWARE，仅限私人、非商业使用**。原文（`Deco_Lib/Readme.html`）：

  > This software is provided as FREEWARE, but only for private, non-commercial use…
  > The use of this software in a commercial application is only allowed with prior
  > written approval by the author (Thomas Becker).

- 再分发条件（原文）：

  > The software may be freely distributed provided that it is not modified and the
  > original archive remains intact with all accompanying files, and provided that
  > no fee is charged.

- 因此：**本仓库不收录该压缩包**（见 `vendor/README.md`），**镜像里也不内置它**。
  从 1.5.0 起，镜像只带一个导入脚本（`app/import_tak.py`），由使用者自己下载 `tak233.zip`
  并执行 `docker exec -i cuefs python3 /app/import_tak.py --accept-license - < tak233.zip`。
  导入时脚本会校验 sha256、保留原包不动、只解出 x64 DLL —— 符合「原包完整」的要求。
- **它不是开源许可**：本项目的 MIT 只覆盖我们自己的文件，不能也不试图把这部分 MIT 化。
- 商用请先取得作者书面许可；没拿到就不要商用。
- 请不要分发「已导入解码库」的容器镜像（那等于重新打包闭源库）。

## 2. Wine（运行时解 TAK 的唯一途径）

- 镜像里通过 Debian 的 `wine64` 包安装，**LGPL-2.1-or-later**。
- 我们不分发 Wine 源码，只分发 Debian 打包好的二进制；对应源码由 Debian 镜像站提供，
  包内 `/usr/share/doc/wine*/copyright` 保留完整许可文本。
- 镜像内删除了一批用不到的 PE 组件（mshtml / wined3d / d3d11 / dxgi / msxml3 / jscript …），
  属于「移除文件」而非修改库代码，LGPL 允许。

## 3. Python embeddable 3.12.8（`winepy/`）

- **PSF-2.0**，允许再分发；`winepy/LICENSE.txt` 原样保留。
- 用途：让 Wine 里能跑一个 Windows 版 Python，再由它 `ctypes` 调 `tak_deco_lib.dll`。

## 4. 静态 ffmpeg

- 构建时从 `johnvansickle.com` 下载（`ffmpeg-release-amd64-static.tar.xz`，**GPLv3** 构建版），
  **不随仓库分发**，由构建者直接从上游取得，GPL 义务随之落在构建者身上。
- 用途：把解码出来的 PCM 压成 FLAC（`-c:a flac -compression_level 8`）并写标签。

## 5. Debian 基础镜像

- `debian:trixie-slim`，各包许可见镜像内 `/usr/share/doc/*/copyright`。

## 6. 示例专辑（`sample/`）

- 音频：Library of Congress「Citizen DJ / Free Music Archive」的**公有领域奉献（CC0）**子集，
  作者 Monplaisir、Komiku，逐首来源与署名见 `sample/CREDITS.md`。
- 封面：`sample/make_cover.py` 用 Pillow 绘制，字体 **Liberation Sans**（SIL OFL 1.1）。
- 这些素材只用于测试流程，不代表任何正式发行。

## 7. 其它

- `docs/configurator/index.html` 是纯前端页面，无第三方 JS 依赖。
- 仓库与镜像里都不含任何真实商业专辑的音频或歌词。
