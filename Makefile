# cuefs —— 一个镜像两个变体：
#   full  : 带 Wine，能解 TAK（解码库需安装后自行导入）
#   slim  : 不带 Wine / TAK，只有 ffmpeg，可跨架构（amd64 + arm64）
VERSION   ?= 1.5.0
REGISTRY  ?= cuefs
PROXY     ?=
ARCH      ?= amd64
PLATFORMS ?= linux/amd64,linux/arm64
BUILDARG   = $(if $(PROXY),--build-arg http_proxy=$(PROXY) --build-arg https_proxy=$(PROXY),)

.PHONY: all full slim latest multiarch test sample clean
all: full slim

# 完整版：也打 latest（用户 docker pull 不写 tag 时拿到的就是这个）
full:
	docker build -f docker/Dockerfile $(BUILDARG) \
	  -t $(REGISTRY):$(VERSION) -t $(REGISTRY):latest .

# 精简版：也打 slim（它的“默认 tag”）
slim:
	docker build -f docker/Dockerfile.slim $(BUILDARG) \
	  --build-arg TARGETARCH=$(ARCH) \
	  -t $(REGISTRY):$(VERSION)-slim -t $(REGISTRY):slim .

# 交叉构建 slim 的多架构版本（需要 buildx + qemu）
multiarch:
	docker buildx build -f docker/Dockerfile.slim $(BUILDARG) \
	  --platform $(PLATFORMS) \
	  -t $(REGISTRY):$(VERSION)-slim -t $(REGISTRY):slim --push .

test:
	bash tools/smoke_test.sh

sample:
	python3 sample/build_sample.py --help

clean:
	docker rmi -f $(REGISTRY):$(VERSION) $(REGISTRY):latest $(REGISTRY):$(VERSION)-slim $(REGISTRY):slim 2>/dev/null || true
	docker builder prune -f
