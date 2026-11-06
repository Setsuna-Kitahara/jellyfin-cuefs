# 本仓库不包含 TAK 解码库

`Dockerfile` 需要构建上下文里有一个 **`tak233.zip`**（TAK 2.3.3 官方发行包）。

**它故意没有进版本库**，原因见 `../THIRD_PARTY_NOTICES.md`：TAK SDK 是
freeware，只允许私人/非商业使用，且要求「原包完整未修改」地分发。
把它放进公开仓库等于由本仓库替所有人做再分发，法律上不干净，所以改成
「你自己下载 → 放到这里 → 自己构建」。

## 怎么拿到它

1. 去 TAK 官方页面下载 **TAK 2.3.3**（文件名 `tak233.zip`，约 1.7 MB）。
   官方入口：<https://sites.google.com/site/taklossless/download>
   （若该页失效，搜「TAK 2.3.3 tak233.zip」，务必核对下面的校验值。）
2. 放到本目录：`vendor/tak233.zip`，然后从仓库根目录构建：

   ```bash
   cp vendor/tak233.zip ./tak233.zip   # Dockerfile 从构建上下文根读取
   docker build -t cuefs:local .
   ```

## 校验值（与本项目验证过的版本逐字节一致）

```
sha256  40d26992266f1377d576b88b84b88d2ab256dc321e47f90314402a80692aba6a
size    1,765,343 bytes
files   Applications/  Deco_Lib/  Sdk/  readme.txt
```

构建时会做两件事，都能在日志里看到：

- `dll bytes: 323072` ← 从包里解出 `Deco_Lib/x64/tak_deco_lib.dll`；
- 原始 `tak233.zip` 被原样复制到镜像的 `/opt/tak/tak233.zip`（含 Readme 与许可全文），
  满足「原包完整」的要求。

## 只想跑、不想自己构建

用别人构建好的镜像时，同样需要自备这个 zip——镜像里已经带了完整原包，
所以**镜像本身**的再分发同样受 TAK SDK 条款约束，请不要把含该包的镜像
推到公共 registry 上做「商业分发」。
