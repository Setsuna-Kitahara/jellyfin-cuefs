# 10 · 安全

cuefs 是一个**没有任何鉴权也能用**的 WebDAV 服务（默认无认证），所以默认姿势是：
**只监听 127.0.0.1，只给本机的 Jellyfin / rclone 用。**

## 默认：只听回环

```bash
-p 127.0.0.1:8099:8099      # ✅ 推荐
-p 8099:8099                # ⚠️ 等于对整个局域网开放
```

容器里的进程虽然监听 `0.0.0.0:8099`，但 Docker 的端口映射把**宿主机侧**限制在 `127.0.0.1`，
所以局域网里的其它机器连不上。

> 如果你用 `--network host` 跑容器（有些 Jellyfin 部署是这样），端口映射就不存在了 ——
> 这时必须显式 `-e CUEFS_HOST=127.0.0.1`（或 `--host 127.0.0.1`），否则是真的对全网开放。

## 加一层 Basic 认证

```bash
-e CUEFS_AUTH=alice:s3cret
```

- 所有方法（GET / PROPFIND / PUT …）都要认证；
- 明文传输，**只适合局域网**；
- rclone 侧：

```bash
rclone config create cuefs webdav url=http://127.0.0.1:8099/ vendor=other \
  user=alice pass=$(rclone obscure s3cret)
```

## 要跨机用：加 TLS 反代

不要直接把 8099 暴露出去。用 nginx / Caddy 反代并加证书：

```nginx
location /cuefs/ {
    proxy_pass http://127.0.0.1:8099/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
    proxy_request_buffering off;    # 大文件 PUT 别缓冲
    client_max_body_size 50m;
}
```

注意 WebDAV 的 `Destination` 头里带绝对 URL（COPY/MOVE），反代要rewrite：

```nginx
proxy_set_header Destination $scheme://$host/cuefs$request_uri_tail;
```

（更省事：Caddy 的 `reverse_proxy` + `header_up Destination {scheme}://{host}/cuefs...`。）

## 写权限

- **目录 A 只读**：挂载时务必带 `:ro`。cuefs 本身也只读 A，双保险。
- **目录 B 可写**：Jellyfin 会往里写 NFO/封面。B 里的文件会被 web 用户读到，
  不要在里面放敏感东西。
- **缓存目录**：只存 FLAC，无敏感数据；可以 `--tmpfs` 干脆不落盘。

## 其它建议

| 项 | 建议 |
|---|---|
| 镜像来源 | 自己 build 或官方仓库；别用来历不明的 `cuefs:xxx` |
| 容器权限 | 不需要 `--privileged`，不需要 `/dev/fuse`（FUSE 在宿主机侧） |
| 只读根文件系统 | 可以加 `--read-only --tmpfs /tmp`，只要 `/cache` 与 B 是可写卷 |
| 资源限制 | `--memory 512m --cpus 2` 足够；解码是 CPU 密集的 |
| 日志 | 默认打到 stdout；`docker logs` 里有访问记录（含路径），别当隐私日志 |

## 不要做的事

- ❌ 把 8099 直接映射到公网（无认证 = 谁都能读你的音乐库）
- ❌ 在 A 目录里放不该公开的文件（cuefs 只暴露 CUE 解析出的专辑目录，但 B 里放什么就暴露什么）
- ❌ 把导入过 TAK 库的容器镜像推到公开仓库（违反作者条款，见 [02-TAK-LICENSE.md](02-TAK-LICENSE.md)）
