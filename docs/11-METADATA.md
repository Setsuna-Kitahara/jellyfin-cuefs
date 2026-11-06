# 11 · 元数据：NFO 能补什么、补不了什么

先回答那个问题：**“专辑元数据能不能全交给 NFO？”**
—— 能覆盖大部分**专辑级**字段，但**曲目级**的字段覆盖很有限，尤其是“每首歌不同的作者/作曲/来源链接”。
下面把边界讲清楚，并给出 cuefs 的补法（`meta.json`）。

## Jellyfin 从哪儿读音乐元数据（优先级从高到低）

1. **内嵌标签**（FLAC 的 Vorbis comments、MP3 的 ID3）—— 优先级最高
2. **`album.nfo` / `artist.nfo` / `*.nfo`** —— 补充或覆盖专辑/艺人级信息
3. **文件夹/文件名**（cuefs 生成的是 `<专辑名>/NN - <曲名>.flac`，`NN` = CUE 的 `TRACK` 号，见 [14-NAMING.md](14-NAMING.md)）
4. **在线抓取**（MusicBrainz / TheAudioDB，默认开）

注意 1 和 2 的关系：**Jellyfin 对专辑级字段（标题/年份/厂牌/简介/风格）以 NFO 为准；
曲目级字段（每首的 Title/Artist/Track）主要看文件内嵌标签**，NFO 里逐轨写的能力很弱
（Jellyfin 会读 `<track>` 块里的 `title`，但 `artist`/`composer` 之类经常被忽略）。

## `album.nfo` 能可靠表达的（专辑级）

| 字段 | 说明 |
|---|---|
| `<title>` | 专辑名 |
| `<artist>` / `<albumartist>` | 艺人 / 专辑艺人 |
| `<year>` / `<premiered>` / `<releasedate>` | 年份 / 首发日 / 发行日 |
| `<genre>` | 风格（可多个） |
| `<label>` | 厂牌 |
| `<catalognumber>` | 目录号（CD 封套/碟片上印的那串，如 `PD-SAMPLE-001`） |
| `<type>` | Album / EP / Single / Soundtrack |
| `<review>` / `<outline>` | 长简介 / 一句话 |
| `<lockdata>true</lockdata>` | 锁定，防止 Jellyfin 联网覆盖 |
| `<rating>` / `<criticrating>` | 评分 |
| `<studios>` / `<tags>` / `<taglines>` | 其它分类信息 |
| `<musicbrainzalbumid>` 等 | 外部 ID |

## NFO 补不了的（曲目级）

| 想要 | 现实 |
|---|---|
| 每首不同的 `artist`（合辑/OST 常见） | NFO 逐轨支持很差，Jellyfin 基本不认 |
| 每首的 `composer` / `lyricist` | 同上 |
| 每首的来源 URL / 版权说明 | NFO 没有对应字段 |
| 每首的 `isrc` / `bpm` / `media`（CD/SACD） | 同上 |
| 每首的 `discsubtitle` | 同上 |

这些**必须写进 FLAC 的内嵌标签**，Jellyfin 才稳定读得到。

## cuefs 的方案：内嵌标签为主，`meta.json` 补 CUE 没有的

cuefs 切片时会把 CUE 里的信息写成 FLAC 标签：

```
title          该轨 TITLE；没写就是 Track NN
artist         该轨 PERFORMER（没有就用专辑 PERFORMER）
album          CUE 顶层 TITLE 原文   ← 这就是媒体库里显示的专辑名
album_artist   专辑 PERFORMER
track          TRACK 号（两位）
date           REM DATE
genre          REM GENRE
```

文件名和标签用的是同一批字段，但**目录/文件名是清洗过的，标签是原文**：
`TITLE "A/B: Test?"` → 目录 `A_B_ Test_`、标签里仍是 `A/B: Test?`。清洗规则见
[14-NAMING.md](14-NAMING.md)。

CUE 表达不了的字段，放一个 `meta.json` 在专辑目录里（A 或 B 均可，优先 B）：

```json
{
  "album": {
    "label": "Library of Congress",
    "catalognumber": "PD-SAMPLE-001",
    "comment": "CC0 sample disc bundled with the repo",
    "copyright": "CC0 1.0",
    "genre": "Test"
  },
  "tracks": {
    "1": { "composer": "Monplaisir", "comment": "https://example.com/source/1" },
    "3": { "composer": "Komiku", "isrc": "ZZZZZ0000003" }
  }
}
```

规则：

- 键名必须在上面的白名单里（`META_KEYS`：title/artist/album/album_artist/track/disc/date/genre/
  composer/lyricist/label/catalognumber/isrc/comment/copyright/grouping/media/bpm/discsubtitle）
- 值一律当字符串写入 FLAC
- `tracks` 的键是**轨号字符串**（`"7"`）
- 改了 `meta.json` 之后要清掉该专辑的缓存（或等 TTL 过期），否则还是旧标签

## 封面

| 位置 | 谁写 | 建议 |
|---|---|---|
| A（原盘目录） | 你自己 | 放 `cover.jpg`，最省事（原盘目录里本来就该有） |
| B（overlay） | Jellyfin 或你 | 让 Jellyfin 自己管理，或者手工放同名 `cover.jpg` |

cuefs 会把 `cover.jpg` 作为 WebDAV 里的一个**文件**暴露在专辑目录下；
Jellyfin 扫库时会把它当作封面。侧车位置规则见 [05-SIDECAR.md](05-SIDECAR.md)。

## 歌词

`.lrc` 同样当侧车暴露。Jellyfin 10.10+ 会把与音频**同名**的 `.lrc` 读进去
（`/Audio/{id}/Lyrics` 接口可验证）。所以命名规则：

```
01 - A Good Start.flac
01 - A Good Start.lrc      ← 同名（`NN - <曲名>` 都来自 CUE，规则见 14-NAMING）
```

双语歌词的写法（同时间戳两行，翻译在上、原文在下）：

```
[00:12.34]翻译的那一句
[00:12.34]the original line
```

Jellyfin 会显示成两行；只想要一行就只留原文。

## 实践建议

- **OST / 同人碟**：CUE 里通常只有 PERFORMER 和 TITLE，够用；厂牌/目录号写进 `meta.json`。
- **合辑**：每轨 PERFORMER 不同，CUE 里本来就写了 —— cuefs 会逐轨写入 `artist`，这是 NFO 做不到的。
- **想让 Jellyfin 不联网覆盖**：`album.nfo` 里加 `<lockdata>true</lockdata>`。
- **改完元数据没生效**：Jellyfin 里对该专辑「刷新元数据」；cuefs 侧确认缓存已清。
