# 13 · 常见问题

**Q：为什么不干脆把 TAK 转成 FLAC？**
A：也行（`--export` 就是干这个的），但那是“离线拆盘”：多占一份空间、丢掉 CUE 里的 pregap 信息、
以后想换命名/换格式还得重来。cuefs 的价值是**原盘不动、按需切片**。

**Q：Jellyfin 会不会往我的原盘目录里写东西？**
A：不会。A 目录用 `:ro` 挂载，cuefs 本身也只读 A。Jellyfin 的写入（`album.nfo`、`folder.jpg`）
全部落到目录 B。这是设计上的硬约束。

**Q：一次播放会占多少 CPU/内存？**
A：空转约 50 MB（完整版）。解码某一轨时瞬间 +60–80 MB，CPU 1 核跑满 0.5–1.5 秒，完了就释放。
不是“边播边转码”，是“先把这一轨切出来存成 FLAC，再让 Jellyfin 读”，所以播放过程本身零开销。

**Q：为什么第一首特别慢？**
A：完整版第一次请求要先启动 Wine + Windows Python（约 2 秒），之后同一容器的后续请求都是 0.5–1.5 秒。
容器重启后第一次又会慢一次。想避免：用 `--prefetch` 预热，或者干脆接受它。

**Q：缓存会一直涨吗？**
A：默认不会自动清（`CUEFS_CACHE_TTL=0`）。建议至少设一个：`CUEFS_CACHE_MAX_GB=4` 或 `CUEFS_CACHE_TTL=72`。
两者可以同时设，谁先触发谁生效。

**Q：能放无损 24bit/96kHz 的整盘吗？**
A：可以。cuefs 只是按样本位置切片，位深/采样率跟着源文件走，不做重采样。
TAK 那条路径目前按 16bit/44.1k 的常见情形验证得最充分；24bit 的 TAK 建议先用 `--list` + 单轨试听确认。

**Q：多个 CUE 放在同一个目录里会串吗？**
A：不会。目录级侧车（`cover.jpg` 与 CUE 同目录）只在“该目录只有 1 个 CUE”时才启用，
多盘同目录时请用子目录或 `<cue 文件名>.jpg` 前缀式（见 [05-SIDECAR.md](05-SIDECAR.md)）。

**Q：支持 DVD-Audio / SACD ISO 吗？**
A：不支持。ffmpeg 对 SACD-ISO 的 DSF/DFF 支持有限，DVD-A 的 MLP 也不在范围内。
这两类目前没有可靠的“按轨切片”方案。

**Q：能同时在 Windows 上用吗？**
A：可以 —— cuefs 是 WebDAV，Windows 资源管理器「映射网络驱动器」就能挂。
但 Windows 的 WebDAV 客户端对 `Range` 支持一般，适合浏览不适合播放。

**Q：为什么端口只绑 127.0.0.1？我想让电视直接播。**
A：改成 `-p 8099:8099` 并加 `-e CUEFS_AUTH=user:pass`，或者放在有 TLS 的反代后面。
默认绑回环是因为**没有认证的 WebDAV 等于把音乐库公开**。详见 [10-SECURITY.md](10-SECURITY.md)。

**Q：ARM64 上能跑 TAK 吗？**
A：目前不能。见 [09-ARM64.md](09-ARM64.md) 的三条替代路径。

**Q：这个项目跟 Jellyfin 官方有关系吗？**
A：没有。它是一个外挂：Jellyfin 以为自己在读普通 FLAC 文件，实际上读的是 cuefs 现切出来的。
好处是不用等 Jellyfin 支持 TAK/CUE，坏处是多了一层要维护的东西。

**Q：会考虑做成 Jellyfin 插件吗？**
A：插件解决不了“解码 TAK”这件事（插件跑在 .NET 里，还是得调外部解码器），
而且插件没法给媒体库提供“虚拟文件”。WebDAV 这层反而是最通用、最少侵入的做法。
