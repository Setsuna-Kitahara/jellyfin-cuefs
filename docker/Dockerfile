# syntax=docker/dockerfile:1
# cuefs 完整版（full）：带 Wine，可解码 TAK —— 但 TAK 解码库本身不随镜像分发，
# 需要安装后由使用者自己导入（见 docs/02-TAK-LICENSE.md）。
FROM debian:trixie-slim

ARG http_proxy
ARG https_proxy
ARG FFMPEG_URL=https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
ARG APT_MIRROR=

ENV DEBIAN_FRONTEND=noninteractive \
    WINEPREFIX=/wine \
    WINEDEBUG=-all \
    WINEDLLOVERRIDES=mscoree,mshtml= \
    PYTHONUNBUFFERED=1 \
    CUEFS_BACKEND=auto \
    CUEFS_TAK_HOME=/opt/tak \
    CUEFS_TAK_DLL=/opt/tak/Deco_Lib/x64/tak_deco_lib.dll \
    CUEFS_WINE=/usr/lib/wine/wine64 \
    CUEFS_WINE_PYTHON=/winepy/python.exe \
    CUEFS_TAKDEC=/app/takdec.py \
    CUEFS_SRC=/music-src \
    CUEFS_OVERLAY=/music-overlay \
    CUEFS_CACHE=/cache

RUN set -eux; \
    if [ -n "$APT_MIRROR" ]; then \
      sed -i "s|deb.debian.org|$APT_MIRROR|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
      sed -i "s|deb.debian.org|$APT_MIRROR|g" /etc/apt/sources.list 2>/dev/null || true; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends python3 ca-certificates curl xz-utils wine64; \
    for i in 1 2 3 4 5; do \
      curl -fsSL --retry 3 --retry-delay 5 --retry-all-errors --connect-timeout 20 \
        "$FFMPEG_URL" -o /tmp/ff.tar.xz && break; \
      echo "ffmpeg 下载失败（第 $i 次），10 秒后重试"; sleep 10; \
    done; \
    test -s /tmp/ff.tar.xz; \
    mkdir -p /tmp/ff; tar -xJf /tmp/ff.tar.xz -C /tmp/ff --strip-components=1; \
    install -m 0755 /tmp/ff/ffmpeg /usr/local/bin/ffmpeg; \
    install -m 0755 /tmp/ff/ffprobe /usr/local/bin/ffprobe; \
    ffmpeg -hide_banner -version | head -1; \
    W=/usr/lib/x86_64-linux-gnu/wine/x86_64-windows; \
    rm -f $W/mshtml.dll $W/wined3d.dll $W/msxml3.dll $W/jscript.dll $W/d2d1.dll \
          $W/d3d11.dll $W/dxgi.dll $W/d3d10core.dll $W/ddraw.dll $W/light.msstyles \
          $W/winedbg.exe $W/ieframe.dll; \
    apt-get purge -y libllvm19 mesa-libgallium libgl1 libglx-mesa0 libflite1 >/dev/null 2>&1 || true; \
    ln -sf /usr/lib/wine/wine64 /usr/local/bin/wine; \
    rm -rf /tmp/ff /tmp/ff.tar.xz /usr/share/doc/* /usr/share/man/* /usr/share/locale/* \
           /var/cache/apt/* /var/lib/apt/lists/* /wine; \
    mkdir -p /wine /music-src /music-overlay /cache /opt/tak

COPY app/ /app/
COPY winepy/ /winepy/
COPY LICENSE THIRD_PARTY_NOTICES.md /usr/share/doc/cuefs/

# 注意：这里没有任何 TAK 解码库。装好后用 import_tak.py 导入（见 docs/02-TAK-LICENSE.md）。
EXPOSE 8099
VOLUME ["/cache"]
ENTRYPOINT ["python3", "-u", "/app/cuefs.py"]
CMD ["--src", "/music-src", "--overlay", "/music-overlay", "--cache", "/cache", \
     "--host", "0.0.0.0", "--port", "8099"]
