# cuefs 文档索引

按「我现在想干什么」找：

| 我想…… | 看这个 |
|---|---|
| 先跑起来听一首 | [01-QUICKSTART.md](01-QUICKSTART.md) |
| 搞清楚 TAK 解码库为什么不能随镜像发 | [02-TAK-LICENSE.md](02-TAK-LICENSE.md) |
| 查某个参数/环境变量 | [03-CONFIG.md](03-CONFIG.md) |
| 挂进 Jellyfin（rclone / davfs2 / 导出） | [04-JELLYFIN.md](04-JELLYFIN.md) |
| 放封面、歌词、NFO | [05-SIDECAR.md](05-SIDECAR.md) |
| 用 FLAC/APE/WavPack 的整盘，不用 TAK | [06-IMAGE-CUE.md](06-IMAGE-CUE.md) |
| 自己造一个 TAK 测试盘 | [07-MAKE-TAK.md](07-MAKE-TAK.md) |
| 部署完做冒烟 / 缓存 / 缓外效率测试 | [08-SAMPLE-TEST.md](08-SAMPLE-TEST.md) |
| 我的机器是 ARM64 | [09-ARM64.md](09-ARM64.md) |
| 安全：只听 127.0.0.1、加认证、放反代后面 | [10-SECURITY.md](10-SECURITY.md) |
| NFO 能补哪些元数据、补不了哪些 | [11-METADATA.md](11-METADATA.md) |
| 更新 / 卸载 / 备份 / 排错 | [12-OPS.md](12-OPS.md) |
| 常见问题 | [13-FAQ.md](13-FAQ.md) |

## 术语

| 词 | 意思 |
|---|---|
| **整盘 / 镜像** | 一张 CD 的所有音轨存在**一个**音频文件里（TAK/FLAC/APE/WV…），配合一个 `.cue` 描述轨道边界 |
| **CUE** | 文本文件，记录每轨的 `INDEX 00`（pregap 起点）和 `INDEX 01`（正片起点），时间格式 `mm:ss:ff`，ff = 1/75 秒 |
| **目录 A（src）** | 你的整盘目录。cuefs **只读**，绝不写入 |
| **目录 B（overlay）** | 可写目录，Jellyfin 写的 NFO/封面落这里；也可以放你自己的封面/歌词 |
| **虚拟轨** | WebDAV 里看起来是 `NN - 曲名.flac`，实际上是 cuefs 按需切片 + 缓存出来的 |
| **pregap** | `INDEX 00` 到 `INDEX 01` 之间的静音/过渡段。cuefs 默认把它**归到上一轨的尾巴**（见 [03-CONFIG.md](03-CONFIG.md) 的 `--pregap`） |
| **sidecar（侧车）** | 与音频同目录的附属文件：`cover.jpg`、`album.nfo`、`*.lrc` |
