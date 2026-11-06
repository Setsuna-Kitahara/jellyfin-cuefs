# 08 · 示例专辑 + 冒烟 / 缓存 / 缓外效率测试

仓库里带了一张**公有领域**的示例整盘，用来验证“装完之后到底通不通”：

```
sample/sample-disc/
  sample-disc.tak     21 MB   ← TAK 整盘（4 轨，6 分 06 秒）
  sample-disc.cue     860 B   ← CUE（带 INDEX 00/01）
  cover.jpg           130 KB  ← 带 SAMPLE 水印的封面
  album.nfo           1 KB    ← 专辑元数据（含每首的来源链接）
  meta.json           791 B   ← 演示 CUE 表达不了的字段
```

素材来自 Library of Congress「Citizen DJ / Free Music Archive」的公有领域子集（CC0 奉献），
逐首署名与链接见 [../sample/CREDITS.md](../sample/CREDITS.md)。

## 0. 先跑起来

```bash
cd cuefs
docker compose -f docker-compose.sample.yml up -d
# 或者手动：
docker run -d --name cuefs-sample -p 127.0.0.1:8099:8099 \
  -v "$PWD/sample/sample-disc:/music-src:ro" \
  -v "$PWD/sample/overlay:/music-overlay" \
  -v cuefs-sample-cache:/cache \
  cuefs:latest
docker exec -i cuefs-sample python3 /app/import_tak.py --accept-license - < tak233.zip
```

> `docker-compose.sample.yml` 里的 `tak233.zip` **不在仓库里**（许可证原因），需要你自己下载。

## 1. 冒烟测试（30 秒）

```bash
curl -s http://127.0.0.1:8099/ | sed 's/<[^>]*>/ /g' | tr -s ' '
#  cuefs · TAK/CUE 虚拟音乐库  backend= wine · 专辑 1 · 轨道 4 · overlay= /music-overlay
#  Public Domain Sampler  — 4 轨 · sample-disc.tak

curl -s "http://127.0.0.1:8099/Public%20Domain%20Sampler/" | grep -o 'href="[^"]*"'
#  .../01 - A Good Start.flac
#  .../02 - Beach.flac
#  .../03 - Home.flac
#  .../04 - Free To Use 9.flac
#  .../album.nfo      (src)
#  .../cover.jpg      (src)
```

**通过标准**：专辑 1、轨道 4、能列出 4 个 flac + nfo + cover。

## 2. Range（拖动进度条）测试

```bash
curl -s -H 'Range: bytes=0-4095' -D- -o /dev/null \
  "http://127.0.0.1:8099/Public%20Domain%20Sampler/01%20-%20A%20Good%20Start.flac" | head -6
```

期望：

```
HTTP/1.1 206 Partial Content
Content-Range: bytes 0-4095/9525634
Content-Length: 4096
Accept-Ranges: bytes
```

（`9525634` 是这一轨的 FLAC 字节数；不同 ffmpeg 版本会有几十字节差异。）

## 3. 缓存测试

```bash
docker exec cuefs-sample sh -c 'ls -R /cache | head'
# /cache/<12位hash>/01 - A Good Start.flac ...

# 听一次之后：文件出现；TTL/上限生效时会被删掉
docker exec cuefs-sample sh -c 'du -sh /cache'
```

期望：第一次 GET 之后 `/cache` 里出现对应文件；配置了 `CUEFS_CACHE_TTL` 的话，过期后目录会被清空。

专门测 TTL 可以用很短的值起一个容器：

```bash
docker run --rm -d --name cuefs-ttl -p 127.0.0.1:8098:8099 \
  -v "$PWD/sample/sample-disc:/music-src:ro" -v cuefs-ttl-cache:/cache \
  -e CUEFS_CACHE_TTL=0.001 cuefs:slim
# 0.001 小时 ≈ 3.6 秒；读一次，等 10 秒，再看 /cache
```

> ⚠️ 缓存只覆盖 `.flac`（以及 `--tak-mode wav` 时的 `.wav`）。用 `--tmpfs /cache` 可以完全不落盘。

## 4. 缓外效率测试（“没缓存的一首歌要等多久”）

```bash
# 清空缓存 → 计时读第 3 轨
docker exec cuefs-sample sh -c 'rm -rf /cache/*'
curl -s -o /dev/null -w 'cold ttfb=%{time_starttransfer}s total=%{time_total}s size=%{size_download}\n' \
  "http://127.0.0.1:8099/Public%20Domain%20Sampler/03%20-%20Home.flac"

# 同一轨再读一次 → 应该明显更快
curl -s -o /dev/null -w 'warm ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  "http://127.0.0.1:8099/Public%20Domain%20Sampler/03%20-%20Home.flac"
```

VPS（2 核 / 4 GB）上的参考值：

| 场景 | 首字节 |
|---|---|
| 冷启动第一轨（含 Wine 初始化） | 2–3 s |
| 同盘其它轨，冷 | 0.5–1.5 s |
| 命中缓存 | < 0.1 s |

第一次慢是正常的：Wine 要先起一个 Windows Python，再加载 DLL。

## 5. 位级一致性（可选，5 分钟）

验证“切片拼回去 = 整盘”，这是本项目最硬的一个指标：

```bash
# 逐轨下载、解码成裸 PCM、拼接，和整盘解码的 PCM 比 MD5
python3 tools/verify_container.py http://127.0.0.1:8099 /music-overlay
```

示例专辑的期望值（16 bit / 44.1 kHz / 立体声）：

```
album: Public Domain Sampler  tracks: 4
concat pcm bytes=64549192  md5=b60b2241a04671e145bc689f94ef4891
disc   pcm bytes=64549192  md5=b60b2241a04671e145bc689f94ef4891
RESULT: PASS
```

> 这组数字是 `sample_disc.wav` 解码出来的 PCM 摘要；`sample-disc.tak` 就是由它编码而来。
> 仓库里的 `tools/verify_container.py` 对真实盘（GNCA-1135/1136/1165/1166）也算过同样的比对。

## 6. 一键脚本

```bash
bash tools/smoke_test.sh http://127.0.0.1:8099
```

会依次检查：首页能开、专辑数 > 0、第一轨 200、Range 206、缓存目录出现文件。
任一失败返回非 0。
