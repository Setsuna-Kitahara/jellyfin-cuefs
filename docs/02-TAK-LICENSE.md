# 02 · TAK 解码库：为什么不能随镜像发、怎么导入

## 一句话

TAK（Tom's lossless Audio Kompressor）的**解码器是闭源 freeware**，作者 Thomas Becker 的条款只允许
**私人、非商业**使用，并要求分发时**保持原始压缩包完整、不得修改、不得收费**。
所以镜像里**不放**它，只放一个导入脚本 —— 由你自己下载、自己同意条款、自己导入。
这和“盗版分发闭源组件”是两件事，请别把导入后的容器再打包分发。

## 原作者条款（TAK 2.3.3 SDK 的 Readme，原文摘录）

> This software is provided as FREEWARE, but only for private, non-commercial use…
> The use of this software in a commercial application is only allowed with prior written
> approval by the author (Thomas Becker).

> The software may be freely distributed provided that it is not modified and the original
> archive remains intact with all accompanying files, and provided that no fee is charged.

翻译：

1. 免費用，但**只限私人、非商业**；商用要作者书面许可。
2. 可以再分发，但**必须原包完整、未修改、不收费** —— 所以“把 DLL 抽出来塞进镜像”是不行的。

（`Sdk/Source/` 里只有 `takStream.pas`，那是 Delphi 的封装，不含解码内核；网上也没有可编译的
完整开源 TAK 解码器。FFmpeg 的 `libavcodec/takdec.c` 只覆盖早期格式，遇到这类文件会报
`TAK codec type 0 is not implemented`，ticket 2837 挂了十年没人做。Rockbox 的 `libtta` 是 TTA，不是 TAK。）

## 导入流程

```bash
# 1) 官方站点下载 SDK（大约 1.7 MB）
#    https://www.tak-audio.com/  →  TAK 2.3.3  →  tak233.zip
sha256sum tak233.zip
# 40d26992266f1377d576b88b84b88d2ab256dc321e47f90314402a80692aba6a  tak233.zip

# 2) 导入（--accept-license 就是“我已阅读并接受上面那两条”）
docker exec -i cuefs python3 /app/import_tak.py --accept-license - < tak233.zip

# 3) 检查
docker exec cuefs python3 /app/import_tak.py --status
```

输出示例：

```
TAK decoder: INSTALLED
  dll       : /opt/tak/Deco_Lib/x64/tak_deco_lib.dll (323072 bytes, machine=0x8664, x86-64)
  imported  : 2026-11-06T10:38:52+0000
  sha256    : 40d26992266f1377d576b88b84b88d2ab256dc321e47f90314402a80692aba6a
  license   : private / non-commercial only (accepted by user at import time)
```

**不用重启容器**：下一次播放请求就会用上新库。

### 参数

| 参数 | 作用 |
|---|---|
| `--accept-license` | 必填。表示你接受原作者的私人/非商业条款 |
| `<zip 或 ->` | `tak233.zip` 的路径；写 `-` 表示从 stdin 读（配合 `docker exec -i`） |
| `--status` | 只打印当前状态，不做任何事 |
| `--dst DIR` | 指定安装目录，默认 `/opt/tak` |

导入脚本会校验：

- 压缩包 sha256（防止下到被改过的包）、大小；
- PE 头 `Machine` 字段必须是 `0x8664`（x86-64）——ARM64 的 Windows DLL 在这条链路上用不了；
- 只解出 `Deco_Lib/x64/tak_deco_lib.dll`（+ 许可证文本），其余文件丢掉，但**原始 zip 保持不动**；
- 记下导入时间和 sha256，`--status` 可查。

## 为什么非要用它

因为 TAK 是**算术编码 + MDCT + LPC** 的自研格式，没有公开规范。想解码只有三条路：

1. 官方 DLL（就是这条路）；
2. 反编译那 300 KB 的 x64 机器码 —— 无许可依据，工程量也不现实；
3. 等 FFmpeg 补完 —— 十年了没有。

## 法律与良心

- 你自己用：只要不商用，符合作者条款。
- 你想给公司用：请先联系作者拿书面许可（`https://www.tak-audio.com/`）。
- 你想发布带解码库的镜像：**别**。那违反“原包完整”的要求，也会把本项目拖进麻烦里。
  真要分发，请分发**导入脚本 + 说明**，让人自己下载。
- 本项目仓库里也**没有** `tak233.zip`（`.gitignore` 已排除），示例素材是公有领域音频。

## 精简版为什么不能解 TAK

DLL 是 **Windows x86-64 的 PE**，Linux 上要靠 Wine 才能加载；Wine 自带一堆 32/64 位 PE 组件，
镜像一下子就 1.5 GB。精简版（`cuefs:slim`）为了体积和 ARM 兼容性，干脆不带 Wine，
自然也就不用 TAK —— 换来 408 MB 和 arm64 支持。两者取一，按需选。
