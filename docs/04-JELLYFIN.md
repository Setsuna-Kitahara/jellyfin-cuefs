# 04 · 接进 Jellyfin

cuefs 输出的是 **WebDAV**，而 Jellyfin 的媒体库只认**本地路径**。中间必须有东西把 WebDAV 变成一个目录。
三条路，按推荐度排：

| 方案 | 原理 | 优点 | 缺点 |
|---|---|---|---|
| **A. rclone mount** | 把 WebDAV 挂成 FUSE 目录 | 最省事，Jellyfin 无感 | 要 `--allow-other`、要 FUSE |
| **B. davfs2** | 同上，用内核 davfs 模块 | 不用装 rclone | 慢、并发差、对 Range 支持不如 FUSE |
| **C. `--export` 成真实文件** | cuefs 一次性把每轨切出来存盘 | 零依赖、零运行时 | 多占 ~1× 空间，失去“按需”的意义 |

## A. rclone mount（推荐）

### 宿主机（Jellyfin 裸机 / 非 root）

```bash
# 一次性配置
rclone config create cuefs webdav \
  url=http://127.0.0.1:8099/ vendor=other \
  --non-interactive

# 挂载
mkdir -p /mnt/jellyfin-cuefs
rclone mount cuefs: /mnt/jellyfin-cuefs \
  --allow-other \
  --vfs-cache-mode off \
  --dir-cache-time 10m \
  --daemon
```

参数解释：

- `--vfs-cache-mode off`：**流式**读，Jellyfin 要哪段就取哪段。开启 cache 反而会把整文件拉下来。
- `--allow-other`：Jellyfin 如果不是同一个用户跑，没这个就 Permission denied。
- `--dir-cache-time 10m`：目录列表缓存 10 分钟，减少 PROPFIND。

开机自启（systemd）：

```ini
# /etc/systemd/system/cuefs-mount.service
[Unit]
Description=cuefs WebDAV mount
After=network-online.target docker.service

[Service]
Type=simple
ExecStart=/usr/bin/rclone mount cuefs: /mnt/jellyfin-cuefs --allow-other --vfs-cache-mode off
ExecStop=/bin/fusermount -u /mnt/jellyfin-cuefs
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Jellyfin 跑在容器里

容器不会自动继承宿主机的 FUSE 挂载。两种办法：

**① 把挂载点再 bind 进容器**（Jellyfin 官方镜像需要 `--device /dev/fuse` 才能看 FUSE，
更稳的做法是让挂载发生在**宿主机**上，再加一个 bind mount）：

```bash
docker run -d --name jellyfin \
  ...原有参数... \
  -v /mnt/jellyfin-cuefs:/takcuefs:ro \
  jellyfin/jellyfin
```

然后库里填 `/takcuefs`。

> ⚠️ **坑**：如果你用的是 `-v /mnt/smb/...` 这种“宿主机上已经是一个挂载点”的目录，
> 而 rclone 是在容器**启动之后**才挂上去的，Docker 的 `rprivate` 传播策略**不会**把这个子挂载带进容器，
> 容器里只会看到一个空目录，Jellyfin 日志会说 `Library folder is inaccessible or empty`。
> 解决办法：先挂 rclone，再启动 Jellyfin；或者显式 `-v /mnt/jellyfin-cuefs:/takcuefs:ro`（推荐）。

**② 在 Jellyfin 容器里自己挂**（要 `--cap-add SYS_ADMIN --device /dev/fuse`）：

```bash
docker exec -d jellyfin sh -c 'rclone mount cuefs: /media/TAK-cuefs --allow-other --vfs-cache-mode off'
```

不推荐：容器重启就没了，还得在镜像里装 rclone。

## B. davfs2

```bash
apt install davfs2
mkdir -p /mnt/jellyfin-cuefs
mount -t davfs http://127.0.0.1:8099/ /mnt/jellyfin-cuefs
```

`/etc/fstab` 里持久化：

```
http://127.0.0.1:8099/ /mnt/jellyfin-cuefs davfs rw,noauto,user,_netdev 0 0
```

davfs2 默认会尝试把文件缓存到本地（`cache_dir`），对“边播边切”不友好；
在 `/etc/davfs2/davfs2.conf` 里加：

```
cache_size 0
delay_upload 0
```

## C. 导出成真实文件（零依赖）

```bash
docker run --rm \
  -v /mnt/music-src:/music-src:ro \
  -v /mnt/export:/export \
  cuefs:latest --export /export
```

结果：`/export/Public Domain Sampler/01 - A Good Start.flac` 这种普通 FLAC 目录（名字跟 WebDAV 里完全一样，
都来自 CUE 的 `TITLE`，规则见 [14-NAMING.md](14-NAMING.md)），Jellyfin 直接指过去即可。
适合：**库很小**、或者你的 Jellyfin 跑在没法装 FUSE 的地方（比如某些 NAS 的套件版）。

## Jellyfin 侧设置

1. 控制台 → 媒体库 → **添加媒体库** → 内容类型：**音乐**
2. 文件夹：`/takcuefs`（或你挂载的路径）
3. 高级：
   - **取消**「启用实时监控」（WebDAV 上没意义，会拖慢扫描）
   - 「元数据语言」按需
   - 「优先使用内嵌元数据」可以留着
4. 保存 → 扫描

### 库里的专辑名和曲目名从哪来

扫完之后 Jellyfin 里看到的**专辑名就是 CUE 顶层的 `TITLE`**，**曲目名就是每轨的 `TITLE`**
（不是目录名、也不是文件名拼出来的）。所以：

- CUE 里 `TITLE "Public Domain Sampler"` → 库里一张叫 `Public Domain Sampler` 的专辑；
- CUE 里没写 `TITLE` → 目录名退化成 CUE 文件名，标签是空的（Jellyfin 会自己去猜/抓）；
- 目录名会被清掉 `\ / : * ? " < > |` 这些字符，而标签保留原文，所以**目录名和显示名可以不一样**；
- 两张盘的 `TITLE` + `PERFORMER` 完全相同时，Jellyfin 可能把它们**并成一张专辑**（曲目翻倍）。

完整规则、重名处理、改名的四种办法、多碟怎么排：[14-NAMING.md](14-NAMING.md)。

### 关于 NFO 写回

Jellyfin 扫库/编辑元数据时会往专辑目录写 `album.nfo`、`folder.jpg`。
在 cuefs 里，这些写入**自动重定向到目录 B（overlay）**：

```
GET  /<专辑名>/album.nfo   → 先看 B，没有再回 A（取决于 --sidecar）
PUT  /<专辑名>/album.nfo   → 只写 B（A 永远只读）
```

`<专辑名>` 就是 CUE 顶层 `TITLE` 清洗后的目录名（例：`Public Domain Sampler`），
所以 B 里的目录名必须跟 WebDAV 里看到的一模一样，见 [14-NAMING.md](14-NAMING.md)。

所以：

- A 里的原盘目录**永远不会被改**（只读挂载 + cuefs 只写 B，双保险）；
- 你在 Jellyfin 里改了元数据、换了封面，效果会保留在 B 里，重装 cuefs 只要挂回同一个 B 就还在。

验证写重定向生效：看 B 里的 `album.nfo` 字节数是否变成 Jellyfin 自己写的那个（比手写的大很多）。

## 排错

| 现象 | 原因 / 处理 |
|---|---|
| Jellyfin 库里 0 首歌 | 挂载点是空的 → `ls /mnt/jellyfin-cuefs` 有没有专辑目录 |
| 容器里看不到挂载 | `rprivate` 传播问题，见上面 A 的「坑」；或重启 Jellyfin 容器 |
| 能扫到但播放 500 | 看 `docker logs cuefs`：多半是 TAK 库没导入（`import_tak.py --status`） |
| 扫库特别慢 | 关「实时监控」；`--dir-cache-time` 调大；把 `/cache` 放 SSD |
| 播放几秒后卡住 | rclone 的 `--vfs-cache-mode` 别开 `full`；确认 cuefs 的 `Range` 返回 206 |
| 封面不显示 | 侧车没放对位置，见 [05-SIDECAR.md](05-SIDECAR.md) |
| 专辑名跟我以为的不一样 | 库里显示的是 CUE 的 `TITLE`（原文），目录名是它清洗后的版本，见 [14-NAMING.md](14-NAMING.md) |
| 曲目翻倍 / 两张专辑并成一张 | 两张盘的 `TITLE` + `PERFORMER` 相同，Jellyfin 按标签归并；给 TITLE 加区分或改 `album.nfo` 的 `<title>`，见 [14-NAMING.md](14-NAMING.md) 第三节 |
