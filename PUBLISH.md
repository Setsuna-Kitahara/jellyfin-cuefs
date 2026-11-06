# 发布 / 维护清单

> 目标：仓库推上去之后，别人 `git clone` 就能用；文档和镜像都由 Actions 自动出。

## 0. 先自检：不该进仓库的东西

```bash
# 必须在 .gitignore 里，且 `git status` 看不到：
git check-ignore -v tak233.zip test/src/*.tak 2>/dev/null
```

- ❌ `tak233.zip`（TAK 解码库，许可证禁止随镜像/仓库分发）
- ❌ 任何真实专辑的音频（`.tak/.flac/.wav/.cue`）—— 示例盘是公有领域素材，例外
- ❌ 歌词文件（有版权）
- ✅ `sample/src/*.mp3`（LOC 公有领域子集，保留 `CREDITS.md`）

## 1. 仓库

- 仓库名：`jellyfin-cuefs`
- topics：`jellyfin`、`webdav`、`tak`、`cue`、`flac`、`docker`、`music`、`rclone`
- 分支：`main`（历史里没有需要清理的东西；发布前用 gitleaks / secret-scan 过一遍）

## 2. 推之前再跑一遍测试

```bash
docker build -f docker/Dockerfile.slim -t cuefs:slim .
bash tools/smoke_test.sh   # 先用 docker-compose.sample.yml 起一个
python3 tools/build_docs_site.py _site && ls _site/*.html | wc -l   # 文档站点能渲染
```

## 3. 写 Release 时**不要**附带

- 带 TAK 库的镜像 tar（`docker save` 出来的也不行）
- `tak233.zip`

可以附带：源码 zip、`docker-compose*.yml`、截图。

## 4. 镜像：由 Actions 构建（`.github/workflows/docker.yml`）

打一个 `v*` 标签就会自动构建并推送（等价于 `make full` + `make slim`）：

```bash
git tag -a v1.5.0 -m "cuefs 1.5.0" && git push origin v1.5.0
```

产出两个变体：

| 变体 | Dockerfile | 平台 | 标签 |
| --- | --- | --- | --- |
| full | `docker/Dockerfile` | linux/amd64（带 Wine，可解 TAK） | `<ver>`、`latest` |
| slim | `docker/Dockerfile.slim` | linux/amd64 + linux/arm64 | `<ver>-slim`、`slim` |

推送目标：

- **GHCR**：`ghcr.io/<owner>/cuefs` —— 用仓库自带的 `GITHUB_TOKEN`，不需要配任何东西
- **Docker Hub**：`docker.io/<用户名>/cuefs` —— 需要先在仓库里加两个 secret：
  `DOCKERHUB_USERNAME`、`DOCKERHUB_TOKEN`（Settings → Secrets and variables → Actions）

> Docker Hub 的 token 在 hub.docker.com → Account settings → Personal access tokens 里生成，
> 权限给 Read & Write 就够。没配这两个 secret 时，工作流只推 GHCR，不会失败。

只想验证不推送：在 Actions 页面手动跑 `docker` 工作流，把 **真正推送** 取消勾选。

## 5. 在线文档：由 Actions 渲染（`.github/workflows/pages.yml`）

`README.md` + `docs/*.md` 用仓库自带的 `tools/build_docs_site.py` 渲染成静态站点，发到 GitHub Pages：

- <https://setsuna-kitahara.github.io/jellyfin-cuefs/>
- 配置生成器：<https://setsuna-kitahara.github.io/jellyfin-cuefs/configurator.html>

Pages 需要先在 Settings → Pages 里把 **Source** 选成 **GitHub Actions**（只需做一次）。
之后改 `docs/` 或 `README.md`，工作流会自动重新渲染并发布。

## 6. 发布后

- README 里的镜像名 / 站点地址若与实际不符，先改 README 再发 Release
- 在 Jellyfin 论坛 / Reddit r/jellyfin 发帖时，**重点讲“不改原盘 + 按需切片”**，
  并如实说明 TAK 需要用户自己导入官方库（这是合规点，也是加分项）
