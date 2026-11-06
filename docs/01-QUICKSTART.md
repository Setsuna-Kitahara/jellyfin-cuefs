# 01 · 快速开始

目标：**15 分钟内**在 Jellyfin 里听到一首来自 TAK 整盘的歌。

> 下文用 `cuefs:latest` / `cuefs:slim` 代指官方镜像。完整写法是
> `ghcr.io/setsuna-kitahara/cuefs:latest`、`ghcr.io/setsuna-kitahara/cuefs:slim`
> （Docker Hub 上是 `kitaharasetsuna/cuefs:latest` / `:slim`，内容相同，两边都**匿名可拉**）。
> 复制命令时记得换成完整写法。

## 0. 先确认你要哪种

| | 完整版 `cuefs:latest` | 精简版 `cuefs:slim` |
|---|---|---|
| 镜像大小 | 1.53 GB | 408 MB |
| TAK | ✅（需自行导入解码库） | ❌ |
| FLAC/WV/TTA/ALAC/AIFF/WAV/APE 整盘+CUE | ✅ | ✅ |
| 架构 | 仅 amd64 | amd64 + arm64 |
| 内存（空闲 / 解码时） | ~50 MB / +80 MB | ~30 MB / +20 MB |

只用 FLAC 整盘、或者跑在 ARM 上 → 直接用精简版，跳过第 2 步。

## 1. 起容器

```bash
mkdir -p /mnt/music-overlay
docker run -d --name cuefs --restart unless-stopped \
  -p 127.0.0.1:8099:8099 \
  -v /path/to/你的整盘:/music-src:ro \
  -v /mnt/music-overlay:/music-overlay \
  -v cuefs-cache:/cache \
  cuefs:latest
```

看一眼：

```bash
curl -s http://127.0.0.1:8099/ | head -c 300
# <title>cuefs 1.5.0</title> … backend=wine · 专辑 4 · 轨道 119 … backend 那一栏很关键：
#   wine = 完整版且找得到 Wine；ffmpeg = 精简版；none = 完整版但 TAK 库还没导入
```

## 2. 导入 TAK 解码库（只有完整版需要）

```bash
# 官方下载页：https://www.tak-audio.com/  →  TAK 2.3.3 SDK  →  tak233.zip
sha256sum tak233.zip     # 应为 40d26992266f1377d576b88b84b88d2ab256dc321e47f90314402a80692aba6a

docker exec -i cuefs python3 /app/import_tak.py --accept-license - < tak233.zip
docker exec cuefs python3 /app/import_tak.py --status
# TAK decoder: INSTALLED
```

`--accept-license` 表示你已读过并接受它的条款：**个人、非商业使用**。
不导入也能跑，只是 TAK 专辑会报错、其它格式照常。

## 3. 挂到宿主机上

```bash
# rclone（推荐）
rclone mount cuefs: /mnt/jellyfin-cuefs --allow-other --vfs-cache-mode off --daemon

# 或者 davfs2
mount -t davfs http://127.0.0.1:8099/ /mnt/jellyfin-cuefs
```

没装 rclone？`apt install rclone` / `dnf install rclone`，或者用 davfs2。
Jellyfin 跑在容器里的话，看 [04-JELLYFIN.md](04-JELLYFIN.md) 的「容器内怎么挂」一节。

## 4. Jellyfin 里建库

1. 控制台 → 媒体库 → 添加媒体库 → 内容类型 **音乐**
2. 文件夹填 `/mnt/jellyfin-cuefs`（你挂载的路径）
3. **取消勾选「启用实时监控」**（WebDAV 上的 inotify 没意义，还拖慢扫描）
4. 保存，等扫描

扫完之后：专辑封面、曲目列表都该正常。点一首听 —— 第一次点会有 1–3 秒的准备时间（切片 + 缓存），之后同一轨秒开。

## 5. 验证一切正常（可选）

下面用仓库自带的示例盘举例：CUE 里的 `TITLE "Public Domain Sampler"` 就是**专辑名**，
第 1 轨的 `TITLE "A Good Start"` 就是**曲目名**（所以路径里是 `01 - A Good Start.flac`）。
换你自己的盘时，把 URL 里这两段换成你 CUE 里写的名字即可 —— 规则见
[14-NAMING.md](14-NAMING.md)，中文/空格要 percent-encode。

```bash
curl -s -o /dev/null -w '%{http_code} %{size_download}\n' \
  "http://127.0.0.1:8099/Public%20Domain%20Sampler/01%20-%20A%20Good%20Start.flac"
# 200 + 文件大小

curl -s -H 'Range: bytes=0-4095' -D- -o /dev/null \
  "http://127.0.0.1:8099/Public%20Domain%20Sampler/01%20-%20A%20Good%20Start.flac" | head -5
# HTTP/1.1 206 Partial Content
# Content-Range: bytes 0-4095/…
```

不确定目录名到底叫什么？直接列出来：

```bash
curl -s http://127.0.0.1:8099/ | grep -o 'href="[^"]*"'   # 根目录：所有专辑
curl -s "http://127.0.0.1:8099/Public%20Domain%20Sampler/" | grep -o 'href="[^"]*"'  # 一张专辑的全部轨
```

更完整的冒烟测试（含缓存、缓外效率、位级一致性）见 [08-SAMPLE-TEST.md](08-SAMPLE-TEST.md)。

## 出问题了

| 现象 | 先看 |
|---|---|
| 首页 `专辑 0` | 目录挂错了？CUE 里 `FILE "xxx.tak"` 的文件名要和实际一致（大小写敏感） |
| 点 TAK 轨 500 | `import_tak.py --status` 是不是 NOT INSTALLED；`docker logs cuefs` 里应有 `TAK 解码器未导入` |
| Jellyfin 找不到文件 | 挂载点路径、容器内的可见性，见 [04-JELLYFIN.md](04-JELLYFIN.md#排错) |
| 播放卡顿/超时 | 降低 `CUEFS_WORKERS`；或把 `/cache` 放到 SSD 上 |

其余见 [12-OPS.md](12-OPS.md) 的排错表。
