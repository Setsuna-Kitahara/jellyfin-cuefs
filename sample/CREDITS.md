# SAMPLE 专辑素材来源与署名

这张「Public Domain Sampler」只用于测试 cuefs 的部署是否正常（冒烟 / 缓存 / 缓外效率），
音频全部来自 **Library of Congress「Citizen DJ / Free Music Archive」** 项目中
**由创作者以公有领域奉献（Public Domain Dedication / CC0）** 发布的那部分录音。

- 使用条款：<https://citizen-dj.labs.loc.gov/loc-fma/use/>
  （原文：*"have been dedicated to the public domain by their creators, thus are free to use and reuse
  without restriction. You can copy, modify, distribute and perform the works, even for commercial
  purposes, all without asking permission. Attribution is recommended but not required."*）
- 推荐署名：*Citizen DJ Project, Free Music Archive archived website at the Library of Congress,
  Web Archives Division.*

虽然授不授权署名都不影响使用，本项目**仍然逐首标注作者与来源链接**（尊重署名权）。

| # | 曲名 | 作者 | 时长 | 来源（Library of Congress） |
|---|---|---|---:|---|
| 1 | A Good Start | Monplaisir | 0:54 | <https://citizen-dj.labs.loc.gov/items/loc-fma/fma-182157/> |
| 2 | Beach | Komiku | 1:04 | <https://citizen-dj.labs.loc.gov/items/loc-fma/fma-178536/> |
| 3 | Home | Komiku | 1:06 | <https://citizen-dj.labs.loc.gov/items/loc-fma/fma-178534/> |
| 4 | Free To Use 9 | Monplaisir | 3:02 | <https://citizen-dj.labs.loc.gov/items/loc-fma/fma-152618/> |

音频文件（mp3 原件）随仓库一起提供于 `sample/src/`，方便离线复现。

## 封面

`sample/cover.jpg` 由 `sample/make_cover.py` 生成：

- 字体：**Liberation Sans**（SIL Open Font License 1.1，允许商用与再分发）
- 图形：脚本用 Pillow 直接绘制，无第三方素材
- 水印 `SAMPLE` 是刻意加的，避免被误当成正式发行物

## 其它

- CUE / NFO 里同样写入了每首曲目的作者与来源 URL（`REM SOURCE` 与 `<review>`）。
- 音频本身是**有损 mp3（128 kbps）→ 转成整盘 WAV → TAK**，所以「位级一致」指的是
  从这份 WAV 开始的一致性；它不适合用来评价音质，只适合验证流程。
