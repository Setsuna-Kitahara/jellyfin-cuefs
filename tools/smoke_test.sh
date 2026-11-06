#!/usr/bin/env bash
# cuefs 冒烟测试：首页 / 专辑 / 第一轨 200 / Range 206 / 缓存落盘
# 用法： bash tools/smoke_test.sh [http://127.0.0.1:8099] [容器名]
set -u
BASE="${1:-http://127.0.0.1:8099}"
CTR="${2:-}"
pass=0; fail=0
ok(){ printf '  \033[32mPASS\033[0m %s\n' "$1"; pass=$((pass+1)); }
no(){ printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=$((fail+1)); }

echo "== cuefs smoke test: $BASE"

# 1) 首页
html=$(curl -fsS --max-time 15 "$BASE/" 2>/dev/null) || { no "首页不可达"; echo "abort"; exit 1; }
ok "首页可访问"
printf '%s' "$html" | grep -q 'cuefs' && ok "首页含 cuefs 标识" || no "首页内容异常"

albums=$(printf '%s' "$html" | grep -o '<b>[0-9]\+</b>' | head -1 | tr -dc '0-9')
tracks=$(printf '%s' "$html" | grep -o '<b>[0-9]\+</b>' | sed -n 2p | tr -dc '0-9')
[ "${albums:-0}" -gt 0 ] && ok "专辑数 = $albums" || no "专辑数为 0（检查 /music-src 挂载与 CUE）"
[ "${tracks:-0}" -gt 0 ] && ok "轨道数 = $tracks" || no "轨道数为 0"

# 2) 第一张专辑的第一轨
first_album=$(printf '%s' "$html" | grep -o 'href="/[^"]*/"' | head -1 | sed 's/href="//;s/"$//')
[ -n "$first_album" ] || { no "找不到专辑链接"; exit 1; }
alb_html=$(curl -fsS --max-time 30 "$BASE$first_album") || { no "专辑页不可达"; exit 1; }
track=$(printf '%s' "$alb_html" | grep -o 'href="[^"]*\.flac"' | head -1 | sed 's/href="//;s/"$//')
[ -n "$track" ] && ok "找到音频文件: $(basename "$track" | sed 's/%20/ /g')" || { no "专辑里没有 flac"; exit 1; }

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 300 "$BASE$track")
[ "$code" = "200" ] && ok "GET 音频 200" || no "GET 音频返回 $code"

# 3) Range
rh=$(curl -s -H 'Range: bytes=0-4095' -D- -o /dev/null --max-time 300 "$BASE$track")
echo "$rh" | head -1 | grep -q '206' && ok "Range 请求 206" || no "Range 不是 206"
echo "$rh" | grep -qi 'content-range' && ok "有 Content-Range 头" || no "缺 Content-Range"

# 4) 缓存
if [ -n "$CTR" ]; then
  if docker exec "$CTR" sh -c 'find /cache -name "*.flac" | grep -q .' 2>/dev/null; then
    ok "缓存已落盘（$CTR:/cache）"
  else
    no "缓存里没有 flac（$CTR:/cache）"
  fi
else
  echo "  SKIP 缓存检查（未给容器名，用法： smoke_test.sh URL 容器名）"
fi

echo "== 结果: $pass passed, $fail failed"
[ "$fail" -eq 0 ] || exit 1
