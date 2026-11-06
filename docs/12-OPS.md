# 12 · 运维：更新、卸载、备份、排错

## 更新

```bash
docker pull cuefs:latest          # 或 cuefs:slim
docker rm -f cuefs
# 用原来的 docker run 参数重新起（建议把它写进 docker-compose.yml）

# 如果换了新容器名，TAK 库要重新导入（它装在容器文件系统里，不在卷上）：
docker exec -i cuefs python3 /app/import_tak.py --accept-license - < tak233.zip
```

> **建议**：把 TAK 库放进一个卷，避免每次更新都重导：
> ```bash
> docker run ... -v cuefs-tak:/opt/tak ...
> docker exec -i cuefs python3 /app/import_tak.py --accept-license --dst /opt/tak - < tak233.zip
> ```

## 备份

要备的只有两样：

| 东西 | 在哪 | 怎么备 |
|---|---|---|
| **目录 B（overlay）** | 宿主机的挂载点 | `tar czf overlay.tgz /mnt/music-overlay` |
| **TAK 解码库**（可选） | 容器内 `/opt/tak` | `docker cp cuefs:/opt/tak ./tak-backup` |

缓存（`/cache`）不用备，删了会自动重建。目录 A 是你自己的原盘，本来就有备份。

## 卸载

```bash
docker rm -f cuefs
docker rmi cuefs:latest cuefs:slim
docker volume rm cuefs-cache      # 缓存卷
rm -rf /mnt/music-overlay         # 目录 B（确认里面没有你想留的 NFO/封面）
```

你的原盘目录 A 一个字节都没被改过 —— 删掉容器即可，无需“还原”。

## 监控

```bash
docker stats cuefs --no-stream
# CONTAINER  CPU%  MEM USAGE / LIMIT
# cuefs      0.2%  50.4MiB / 4GiB        ← 空闲
# 解码瞬间会到 ~130 MiB（Wine + ffmpeg），播放完回落
```

日志（`docker logs cuefs`）里值得关注的几行：

```
albums: 4 backend: wine tracks: 119        ← 启动自检
cuefs 1.5.0 on http://0.0.0.0:8099/ ...    ← 参数确认
decoded wav ... (12.3s) 497.2M             ← 只有 --tak-mode wav 才会出现
区间解码失败，回退整盘 WAV：...             ← range 失败时的自动降级
```

## 排错表

| 症状 | 可能原因 | 处理 |
|---|---|---|
| 首页 `专辑 0` | A 没挂对 / CUE 与音频文件名不一致 | `docker exec cuefs ls -l /music-src`；检查 `FILE "xxx.tak"` 与实际文件名（**大小写敏感**） |
| 首页 `backend= none` | 完整版但既没找到 Wine 也没 DLL | 精简版正常显示 `ffmpeg`；完整版应有 `wine` |
| 点 TAK 轨 → 500 `TAK 解码器未导入` | 没导入 DLL | `import_tak.py --status`，按 [02](02-TAK-LICENSE.md) 导入 |
| 点 TAK 轨 → 500 `tak range decode failed` | DLL 或 Wine 异常 | `docker exec cuefs sh -c '/usr/lib/wine/wine64 /winepy/python.exe /app/takdec.py --tak /music-src/x.tak --dll /opt/tak/Deco_Lib/x64/tak_deco_lib.dll --wav /tmp/t.wav'` 手工复现 |
| 切片有爆音/时长不对 | CUE 的 INDEX 或 pregap 理解差异 | 换 `-e CUEFS_PREGAP=next` 试；用 `--list` 打印解析结果 |
| 播放到一半断 | rclone 开了 `--vfs-cache-mode full` | 改 `off` |
| Jellyfin 扫库超时 | 库太大 + 并发高 | `CUEFS_WORKERS=1`；关实时监控；`--dir-cache-time 30m` |
| 缓存无限涨 | 没设上限也没设 TTL | `CUEFS_CACHE_MAX_GB=4` 或 `CUEFS_CACHE_TTL=72` |
| 改了 meta.json 不生效 | 缓存还是旧的 | `docker exec cuefs sh -c 'rm -rf /cache/*'` |
| 容器里看不到宿主机新挂的目录 | 挂载传播（rprivate） | 见 [04](04-JELLYFIN.md) 的「坑」 |
| 磁盘满 | 缓存 + B + 原盘 | `du -sh /cache /mnt/music-overlay`；设上限 |

## 诊断命令

```bash
# 解析结果（不启动服务）
docker run --rm -v /mnt/music-src:/music-src:ro cuefs:latest --list

# 这个专辑有哪些轨、多长
curl -s http://127.0.0.1:8099/ | sed 's/<[^>]*>/ /g'

# 缓存里到底有什么
docker exec cuefs sh -c 'find /cache -name "*.flac" | head; du -sh /cache'

# 导入的 DLL 是哪个、什么时候导的
docker exec cuefs python3 /app/import_tak.py --status

# 是不是真的在解码（CPU 会跳一下）
docker stats cuefs
```

## 版本兼容

- `cuefs:latest` 与 `cuefs:1.5.0` 是同一个镜像；`cuefs:slim` 与 `cuefs:1.5.0-slim` 是同一个。
- 升级前记下当前 tag：`docker inspect cuefs --format '{{.Config.Image}}'`。
