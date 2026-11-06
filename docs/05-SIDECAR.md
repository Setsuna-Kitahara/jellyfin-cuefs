# 侧车文件：封面、歌词、`album.nfo` 从哪一侧读

Jellyfin 的音乐库会在**音频文件旁边**找这些东西：

| 文件 | 作用 |
|---|---|
| `cover.jpg` / `folder.jpg` / `poster.jpg` | 专辑封面 |
| `album.nfo` | 专辑元数据（标题/艺人/年份/厂牌/曲目数…） |
| `<曲名>.lrc` | 逐轨歌词 |

cuefs 把一张盘切成「虚拟的 FLAC 文件」，所以这些文件也必须由 cuefs 一起发出去。
问题是：**用户想把它们放在哪一侧？** 两种诉求都真实存在：

- **放 A（原盘目录）**：跟 `.tak`/`.cue` 放一起，盘拿走时资料也一起走；
- **放 B（overlay）**：源目录只读、干净，元数据由 Jellyfin 自己写进 B。

`--sidecar` 就是选这个的开关。

## 三种模式

| 模式 | 查找顺序 | 适合 |
|---|---|---|
| `both`（默认） | **B** → A（`<cue 名>/` 子目录）→ A（平铺） | 两种都可能有，谁放了用谁的；B 优先，因为那是 Jellyfin 刚写下的最新版 |
| `src` | A（`<cue 名>/` → 平铺）→ **B 兜底** | 你希望「以原盘目录为准」，只有 A 里没有时才用 B |
| `overlay` | 只用 **B** | 源目录完全只读/不想动，元数据全部自己维护在 B |

环境变量同名：`CUEFS_SIDECAR=both|src|overlay`。

## A 侧的两种摆法

1. **每盘一个子目录**（推荐，多盘同目录不会串味）：

   ```
   /music-src/
     GNCA-1165.cue
     GNCA-1165.tak
     GNCA-1165/
       cover.jpg
       album.nfo
       01 - Overture.lrc
   ```

2. **平铺**：`cover.jpg`、`album.nfo` 直接跟 `.cue` 并排。
   只有当**该目录里只有一个 `.cue`** 时才会启用平铺查找——否则 4 张盘共用一个目录，
   会把 1165 的封面贴到 1166 上。

## B 侧的摆法

B 里的目录名 = cuefs 给这张盘生成的**虚拟专辑名**（即 Jellyfin 里看到的名字）：

```
/music-overlay/
  ef - a tale of melodies. ORIGINAL SOUNDTRACK ～elegia～/
    cover.jpg
    album.nfo
    01 - Overture.lrc
```

Jellyfin 往 A 路径写文件时，cuefs 会用同一个相对路径落到 B 上（PUT/MKCOL/PROPPATCH/DELETE 都支持），
所以即使 A 是 `:ro`，Jellyfin 的「保存图片到媒体文件夹」「写 NFO」也能正常工作。

## 名字识别

- 封面：`cover.jpg|jpeg|png`、`folder.*`、`poster.*`，以及 `<cue 名>.jpg`（如 `GNCA-1165.jpg`）
- 元数据：`album.nfo`，以及 `<cue 名>.nfo`
- 歌词：任意 `*.lrc`；其它 `*.txt` 也会列出来

大小写不敏感。

## 在列表里怎么区分

- 索引页（浏览器打开 `http://nas:8099/`）里，侧车链接后面会标 `overlay` 或 `src`；
- WebDAV 的 `PROPFIND` 里它们就是专辑目录下的普通文件，带真实的 `getcontentlength`。

## 实测（2026-11-06，4 张 ef 原盘）

在 3.83 上用真实数据跑过两条路径，同一份 A 目录 + 同一份 B 目录：

| 模式 | 4 张专辑 `cover.jpg` | `album.nfo` 来源 |
|---|---|---|
| `src` | 200 / 1,823,796 · 179,333 · 1,824,386 · 401,083 B | `srcA` |
| `overlay` | 同上 | `overlay`（B 版带 `<!-- from-overlay -->` 指纹） |

即：同一套文件，切换 `CUEFS_SIDECAR` 就能决定「以原盘为准」还是「以 overlay 为准」，
轨数（31 / 28 / 25 / 35 = 119 轨）与切片结果完全不受影响。

## 一个坑

`--export` 导出真实 FLAC 时，侧车也会一起复制过去，**但那时就没有 A/B 之分了**：
导出的目录里同时有 `cover.jpg` 和 `album.nfo`，Jellyfin 直接读这个目录即可。

## 歌词：Jellyfin 那边真的能读出来吗

会。Jellyfin 10.9+ 会在音频文件**同目录**找同名 `.lrc`（`NN - 曲名.flac` → `NN - 曲名.lrc`），
解析成带时间轴的歌词。cuefs 只要把 `.lrc` 和虚拟轨放在同一层，Jellyfin 就能拿到。

实测（2026-11-06，3.83，4 张 ef 原盘 15 首有人声的曲子）：

| 专辑 | 有歌词轨数 | Jellyfin `/Audio/{id}/Lyrics` |
|---|---|---|
| memories. OST ～espressivo～ | 4 / 31 | 4/4 返回（17、16、16、28 行） |
| memories. OST 2 ～fortissimo～ | 3 / 28 | 3/3（22、29、45 行） |
| melodies. OST ～elegia～ | 2 / 25 | 2/2（72、16 行） |
| melodies. O.S.T 2 ～felice～ | 6 / 35 | 6/6（36、37、11、72、16、23 行） |

其余轨是纯 BGM，网易云本身没有歌词（`/api/song/lyric` 返回空串），不是漏抓。
双语歌词写成「翻译行在上、原文行在下、同一时间戳」的格式，Jellyfin 会显示成两行。

> 脚本：`_cuefs/fetch_lyrics_ef.py`（按专辑 id + 轨序号对齐）与 `_cuefs/push_lyrics_383.py`
> （推到 A/B 两侧并走 WebDAV 复核）。歌词是版权内容，不进公开仓库。
