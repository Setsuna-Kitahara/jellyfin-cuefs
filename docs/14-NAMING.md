# 14 · 媒体库里的名字：专辑名与曲目名

Jellyfin 里看到的**专辑名、曲目名、排序**都不是「目录名拼出来的」，而是**CUE 里写的 `TITLE`**。
这页把规则一次讲清：名字从哪来、被改了什么、重名怎么办、想改怎么改。

> 一句话：**专辑名 = CUE 顶层的 `TITLE`；曲目名 = `NN - 曲名.flac`（NN 是 CUE 的 `TRACK` 号）。**

## 一、从 CUE 到库里（用仓库自带的示例盘）

`sample/sample-disc/sample-disc.cue` 的关键几行：

```
PERFORMER "Monplaisir / Komiku"
TITLE "Public Domain Sampler"
FILE "sample-disc.tak" WAVE

  TRACK 01 AUDIO
    TITLE "A Good Start"
    PERFORMER "Monplaisir"
    INDEX 01 00:00:00
```

挂进 Jellyfin 之后，库里就是：

```
/mnt/jellyfin-cuefs/
└── Public Domain Sampler/          ← 专辑名 = TITLE "Public Domain Sampler"
    ├── 01 - A Good Start.flac      ← 曲目名 = 轨号 + 轨 TITLE
    ├── 02 - Beach.flac
    ├── 03 - Home.flac
    ├── 04 - Free To Use 9.flac
    ├── album.nfo
    └── cover.jpg
```

在容器里核对（不用等 Jellyfin 扫完）：

```bash
docker exec cuefs python3 /app/cuefs.py --src /music-src --overlay /music-overlay \
  --cache /cache --list
# Public Domain Sampler	4 tracks	/music-src/sample-disc/sample-disc.tak
#  ↑ 专辑名                    ↑ 轨数   ↑ 源文件
```

浏览器打开 `http://127.0.0.1:8099/` 看到的是同一份目录：

```
backend=ffmpeg · 专辑 1 · 轨道 4 · overlay=/music-overlay
• Public Domain Sampler — 4 轨 · sample-disc.tak
```

## 二、规则细节

| 环节 | 取值 | 缺失时 |
|---|---|---|
| **专辑目录名** | `safe_name(CUE 顶层 TITLE)` | TITLE 为空 → CUE 文件名去掉 `.cue`；再空 → `album` |
| **目录名清洗** | 连续出现的 `\ / : * ? " < > \|` 与 Tab/CR/LF → 单个 `_`；去掉首尾空白和句点 | 清完为空 → `album` |
| **目录重名** | 后扫到的那张加 `_` + CUE 路径 sha1 前 4 位 | — |
| **曲目文件名** | `%02d - %s.flac`（轨号补零两位 + 曲名 safe_name） | 轨 TITLE 为空 → `trackNN` |
| **专辑标签** `album` | CUE 顶层 `TITLE` 的**原文**（不清洗） | 空字符串 |
| **专辑艺人** `album_artist` | CUE 顶层 `PERFORMER` | 空 |
| **曲目标签** `title` / `artist` | 轨 `TITLE` / 轨 `PERFORMER`（没有则用顶层 `PERFORMER`） | `Track NN` |
| **年份 / 风格** | `REM DATE` / `REM GENRE` | 空 |
| **曲目序号** | `track` = CUE 的 `TRACK` 号（Jellyfin 按它排序） | — |

**注意目录名和标签不是同一个东西**：目录名是清洗过的（`_` 替换非法字符），写进 FLAC 的
`album` 标签是 TITLE 原文。Jellyfin 显示的专辑名优先用**标签**，所以两者不一致是正常的：

```
CUE:  TITLE "A/B: Test?"
目录:  A_B_ Test_            ← 目录名
标签:  A/B: Test?            ← Jellyfin 里显示的名字
```

清洗函数的实测结果（`safe_name`）：

| CUE 里的 TITLE | 目录名 |
|---|---|
| `Public Domain Sampler` | `Public Domain Sampler` |
| `A/B: Test?` | `A_B_ Test_` |
| `Disc 1: Live @ 東京` | `Disc 1_ Live @ 東京` |
| `ガンダム ００８３` | `ガンダム ００８３`（全角字符不受影响） |
| `...` | `album` |
| （空） + `GNCA-1135.cue` | `GNCA-1135` |

## 三、重名会怎样

**文件系统层**：两张不同目录里的盘 TITLE 撞了，cuefs 会给后扫到的那张加 4 位哈希，两张都留得住：

```
Public Domain Sampler/
Public Domain Sampler_a1b2/     ← 同名的那一张
```

哈希取自 CUE 的完整路径，所以同一个文件每次算出来都一样；但**哪一张被加后缀取决于扫描顺序**
（目录遍历顺序），换机器或挪目录可能会反过来。

**Jellyfin 层**：Jellyfin 认专辑主要看 `album` + `album_artist` 两个标签，不看你有几个目录。
两张盘如果 TITLE 和 PERFORMER **完全一样**，Jellyfin 很可能把它们并成一张专辑（曲目翻倍、出现两个 01 轨）。
这是 Jellyfin 侧的行为，cuefs 不干预。要避免：

1. 在 TITLE 里加区分：`TITLE "xxx [Disc 1]"` / `[Edition B]`；
2. 或给每张盘放 `meta.json` 的 `{"album": {"title": "xxx (Disc 1)"}}`；
3. 或放 `album.nfo` 用 `<title>` 指定显示名（见第四节第 3 条）。

## 四、想改名字：四条路

| 改哪里 | 改完的效果 | 代价 |
|---|---|---|
| **1. CUE 的 `TITLE` / 轨 `TITLE`** | 目录名 + FLAC 标签**一起变** | 要清缓存；Jellyfin 当新文件重扫；挂载路径会变 |
| **2. `meta.json` 的 `album.title`** | 只改 FLAC 标签（Jellyfin 显示名变），**目录名不变** | 要清缓存；适合「不想动原盘」 |
| **3. `album.nfo` 的 `<title>`** | 只改 Jellyfin 专辑页标题（专辑级字段以 NFO 为准） | 不用清 cuefs 缓存，但要在 Jellyfin 里刷新元数据 |
| **4. `--export` 后手工改名** | 静态 FLAC 目录，想叫什么都行 | 多占一份空间，失去按需切片 |

**清缓存**（标签是切片时烧进 FLAC 的，缓存命中就不会重新打标签）：

```bash
docker exec cuefs sh -c 'ls /cache'                  # 每个子目录 = 一张专辑的缓存，目录名是 CUE 路径的 sha1 前 12 位
docker exec cuefs sh -c 'rm -rf /cache/<12位哈希>'   # 只清这一张
docker exec cuefs sh -c 'rm -rf /cache/*'            # 全清（下次播放重新切，不会丢原盘）
```

`meta.json` 的键名白名单与写法见 [11-METADATA.md](11-METADATA.md)；
`album.nfo` 能表达哪些字段见同一篇。

## 五、中文 / 日文 / 特殊字符

- **CUE 编码**：按 `utf-8-sig → utf-8 → gbk → shift_jis → cp1252` 依次尝试，全失败才按 UTF-8 替换坏字节。
  日文碟常见 Shift_JIS、老中文碟常见 GBK，通常不用你自己转码。
- **只替换 ASCII 那 10 个字符**和控制字符；中文、日文、`～`、`·`、`×` 之类原样保留。
- **URL**：名字里有空格/中文时，浏览器看得到、`curl` 要 percent-encode（`%20`）；挂载成目录后 Jellyfin 不受影响。
- **`[ ]`**：名字里有方括号时，bash 里要加引号，否则被当通配符展开。

## 六、多碟（Disc 1 / Disc 2）

CUE 里没有碟号，cuefs 也不解析 `REM DISC`。一张碟一个 CUE 时：

- 两张碟 TITLE 相同 → 目录会被加哈希区分，但 **Jellyfin 会把它们并成一张专辑**；
- 想分开：给每张 CUE 的 TITLE 加 `[Disc 1]` / `[Disc 2]`，或用 `meta.json` 补 `disc` 字段
  （`{"tracks": {"1": {"disc": "1"}}}` 这种逐轨写太笨，更实用的做法是每张碟改 TITLE）。

## 七、验证

```bash
# 1) 解析结果（专辑名 / 轨数 / 源文件）
docker exec cuefs python3 /app/cuefs.py --src /music-src --overlay /music-overlay --cache /cache --list

# 2) WebDAV 根目录（专辑列表）
curl -s http://127.0.0.1:8099/ | head -c 400

# 3) 某一轨真的写了什么标签（看缓存里切出来的文件）
docker exec cuefs sh -c 'ls /cache'
docker exec cuefs ffprobe -v error -show_entries format_tags -of default=nw=1 /cache/<12位哈希>/01.flac
# album=Public Domain Sampler
# artist=Monplaisir
# album_artist=Monplaisir / Komiku
# title=A Good Start
# track=1
```
