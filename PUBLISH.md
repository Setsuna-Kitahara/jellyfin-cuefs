# 发布到 GitHub 的检查清单

> 目标：把 `_cuefs/repo/` 这个目录推上去，别人 `git clone` + `docker build` 就能用。

## 0. 先自检：不该进仓库的东西

```bash
# 必须在 .gitignore 里，且 `git status` 看不到：
git check-ignore -v tak233.zip sample/sample-disc/sample-disc.tak test/src/*.tak 2>/dev/null
```

- ❌ `tak233.zip`（TAK 解码库，许可证禁止随镜像/仓库分发）
- ❌ 任何真实专辑的音频（`.tak/.flac/.wav/.cue`）—— 示例盘是公有领域素材，例外
- ❌ 歌词文件（有版权）
- ✅ `sample/src/*.mp3`（LOC 公有领域子集，保留 `CREDITS.md`）

## 1. 建仓库

```bash
cd _cuefs/repo
git init -b main
git add -A
git commit -m "cuefs: expose TAK/CUE disc images to Jellyfin over WebDAV"
```

仓库名建议：`jellyfin-cuefs`（GitHub topics：`jellyfin`、`webdav`、`tak`、`cue`、`flac`、`docker`、`music`）

## 2. 推之前再跑一遍测试

```bash
docker build -f docker/Dockerfile.slim -t cuefs:slim .
bash tools/smoke_test.sh   # 先用 docker-compose.sample.yml 起一个
```

## 3. 写 Release 时**不要**附带

- 带 TAK 库的镜像 tar（`docker save` 出来的也不行）
- `tak233.zip`

可以附带：源码 zip、`docker-compose*.yml`、截图。

## 4. 镜像托管（可选）

GitHub Container Registry：

```bash
echo $GITHUB_TOKEN | docker login ghcr.io -u <user> --password-stdin
docker tag cuefs:slim ghcr.io/<user>/jellyfin-cuefs:slim
docker push ghcr.io/<user>/jellyfin-cuefs:slim
```

`latest` 用完整版（amd64），`slim` 用精简版（amd64+arm64）。

## 5. 发布后

- README 顶部的镜像名改成你的（`cuefs:latest` → `ghcr.io/<user>/jellyfin-cuefs:latest`）
- 在 Jellyfin 论坛 / Reddit r/jellyfin 发帖时，**重点讲“不改原盘 + 按需切片”**，
  并如实说明 TAK 需要用户自己导入官方库（这是合规点，也是加分项）
