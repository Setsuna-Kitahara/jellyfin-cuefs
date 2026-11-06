# -*- coding: utf-8 -*-
"""交付规范用 Markdown -> HTML 渲染器（纯标准库，无第三方依赖）。

用法:
    python3 md2html.py 源.md 目标.html [标题]
    python3 md2html.py --check 目录            # 检查目录下 *.md 是否都有同名 .html
    python3 md2html.py --render-missing 目录   # 只给缺 HTML 的 .md 补渲染（已存在的不动）

支持的语法：标题 / 段落 / 表格 / 引用 / 有序与无序列表 / 分隔线 /
行内 code、粗体、斜体、删除线、链接 / ``` 围栏代码块。
对应 skill：20260923-naming-convention-for-user-delivered-documents 规则 3。
"""
import io, os, re, sys, html

CSS = """  body { font-family: -apple-system, "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
         max-width: 980px; margin: 0 auto; padding: 24px 20px 80px; line-height: 1.75;
         color: #24292f; background: #fff; }
  h1 { border-bottom: 3px solid #2f6f4e; padding-bottom: .3em; }
  h2 { border-bottom: 1px solid #d8dee4; padding-bottom: .25em; margin-top: 2em; color: #1f5138; }
  h3 { color: #2f6f4e; }
  table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 14px; }
  th, td { border: 1px solid #d0d7de; padding: 6px 10px; text-align: left; vertical-align: top; }
  th { background: #f0f6f2; font-weight: 600; }
  tr:nth-child(even) td { background: #fafbfc; }
  blockquote { border-left: 4px solid #7fbf9a; background: #f5faf7; margin: 1em 0; padding: .6em 1em; color: #3a4a41; }
  code { background: #f3f4f6; padding: 1px 5px; border-radius: 4px; font-size: 90%; }
  pre { background: #f6f8fa; border: 1px solid #d8dee4; border-radius: 6px; padding: 12px 14px; overflow-x: auto; }
  pre code { background: none; padding: 0; font-size: 13px; line-height: 1.5; }
  strong { color: #14392a; }
  hr { border: none; border-top: 1px solid #d8dee4; margin: 2em 0; }
  ul, ol { padding-left: 1.6em; }
  li { margin: .25em 0; }"""

MARK = "\x00%d\x00"   # 占位符标记（不是凭据，名字避开 token 以免被密钥扫描器误报）


def inline(t):
    """行内标记 -> HTML；纯文本做转义，生成的标签不被二次转义。
    占位符替换写成迭代，因此支持嵌套（如 **加粗里带 `代码`**）。"""
    store = []

    def stash(open_tag, inner, close_tag):
        store.append(open_tag + inline(inner) + close_tag)
        return MARK % (len(store) - 1)

    t = re.sub(r"`([^`]+)`", lambda m: stash("<code>", m.group(1), "</code>"), t)
    t = re.sub(r"~~(.+?)~~", lambda m: stash("<del>", m.group(1), "</del>"), t)
    t = re.sub(r"\*\*(.+?)\*\*", lambda m: stash("<strong>", m.group(1), "</strong>"), t)
    t = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", lambda m: stash("<em>", m.group(1), "</em>"), t)
    t = re.sub(r"\[([^\]]+)\]\(((?:[^()]|\([^()]*\))+)\)",
               lambda m: stash('<a href="%s">' % html.escape(m.group(2), quote=True), m.group(1), "</a>"), t)
    out = html.escape(t, quote=False)
    # 迭代替换：某个片段自身可能还嵌着更内层的占位符，需要多轮展开
    for _ in range(8):
        before = out
        for i in range(len(store)):
            out = out.replace(MARK % i, store[i])
        if out == before:
            break
    return out


def slug(t, seen):
    s = re.sub(r"<[^>]+>", "", t)
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", s, flags=re.U).strip("-") or "sec"
    n, base = 1, s
    while s in seen:
        n += 1
        s = "%s-%d" % (base, n)
    seen.add(s)
    return s


def convert(md):
    lines = md.split("\n")
    out, i, seen = [], 0, set()
    para, quote, lst = [], [], None  # lst: (tag, [items])

    def flush_para():
        if para:
            out.append("<p>" + inline(" ".join(para).strip()) + "</p>")
            para.clear()

    def flush_quote():
        if quote:
            out.append("<blockquote>\n" + convert("\n".join(quote)) + "\n</blockquote>")
            quote.clear()

    def flush_list():
        nonlocal lst
        if lst:
            tag, items = lst
            body = "\n".join("<li>" + inline(x) + "</li>" for x in items)
            out.append("<%s>\n%s\n</%s>" % (tag, body, tag))
            lst = None

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        # ``` / ~~~ 围栏代码块：原样转义输出，不做行内解析
        fence = re.match(r"^\s*(`{3,}|~{3,})\s*([\w+#.-]*)\s*$", line)
        if fence:
            flush_para(); flush_quote(); flush_list()
            marker, lang = fence.group(1)[0], fence.group(2)
            i += 1
            body = []
            while i < len(lines) and not re.match(r"^\s*%s{3,}\s*$" % re.escape(marker), lines[i]):
                body.append(lines[i])
                i += 1
            i += 1  # 跳过收尾围栏
            cls = ' class="language-%s"' % html.escape(lang) if lang else ""
            out.append("<pre><code%s>%s</code></pre>"
                       % (cls, html.escape("\n".join(body), quote=False)))
            continue
        # 表格：当前行是 |...| 且下一行是分隔行
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i+1].strip()):
            flush_para(); flush_quote(); flush_list()
            cells = lambda r: [c.strip() for c in r.strip().strip("|").split("|")]
            head = cells(line)
            out.append("<table>\n<thead>\n<tr>" + "".join("<th>%s</th>" % inline(c) for c in head) + "</tr>\n</thead>\n<tbody>")
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                out.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in cells(lines[i])) + "</tr>")
                i += 1
            out.append("</tbody>\n</table>")
            continue
        if re.match(r"^-{3,}$", line.strip()) and not line.startswith(" "):
            flush_para(); flush_quote(); flush_list()
            out.append("<hr>")
            i += 1; continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_para(); flush_quote(); flush_list()
            lvl = len(m.group(1)); txt = m.group(2).strip()
            out.append('<h%d id="%s">%s</h%d>' % (lvl, slug(txt, seen), inline(txt), lvl))
            i += 1; continue
        if line.startswith(">"):
            flush_para(); flush_list()
            quote.append(line[1:].lstrip() if line.startswith("> ") else line[1:])
            i += 1; continue
        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m and (not line.startswith("  ")):
            flush_para(); flush_quote()
            if not lst or lst[0] != "ol":
                flush_list(); lst = ("ol", [])
            lst[1].append(m.group(2))
            i += 1; continue
        if re.match(r"^[-*]\s+", line):
            flush_para(); flush_quote()
            if not lst or lst[0] != "ul":
                flush_list(); lst = ("ul", [])
            lst[1].append(re.sub(r"^[-*]\s+", "", line))
            i += 1; continue
        if not line.strip():
            flush_para(); flush_quote(); flush_list()
            i += 1; continue
        if line.startswith("  ") or line.startswith("\t"):
            # 续行：接到上一条列表项
            if lst and lst[1]:
                lst[1][-1] += " " + line.strip()
                i += 1; continue
        flush_quote(); flush_list()
        para.append(line.strip())
        i += 1
    flush_para(); flush_quote(); flush_list()
    return "\n".join(out)


def render_file(src, dst, title=None):
    md = io.open(src, encoding="utf-8", errors="replace").read()
    body = convert(md)
    if title is None:
        title = src
    doc = ('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
           '<title>%s</title>\n<style>\n%s\n</style>\n</head>\n<body>\n%s\n</body>\n</html>\n'
           % (html.escape(title), CSS, body))
    io.open(dst, "w", encoding="utf-8").write(doc)
    return len(doc)


def missing_in(dirname):
    """返回目录下缺少同名 .html 的 .md 文件绝对路径列表。"""
    res = []
    for name in sorted(os.listdir(dirname)):
        if not name.endswith(".md"):
            continue
        src = os.path.join(dirname, name)
        if not os.path.isfile(src):
            continue
        if not os.path.exists(src[:-3] + ".html"):
            res.append(src)
    return res


def main():
    args = sys.argv[1:]
    if args and args[0] == "--check":
        dirs = args[1:] or ["."]
        bad = []
        for d in dirs:
            for src in missing_in(d):
                bad.append(src)
                print("缺 HTML: " + src)
        print("检查完成：%d 个目录，%d 个 .md 缺同名 .html" % (len(dirs), len(bad)))
        return 0 if not bad else 1
    if args and args[0] == "--render-missing":
        dirs = args[1:] or ["."]
        n = 0
        for d in dirs:
            for src in missing_in(d):
                size = render_file(src, src[:-3] + ".html", os.path.basename(src[:-3]))
                print("已渲染: %s (%d bytes)" % (src[:-3] + ".html", size))
                n += 1
        print("补渲染完成：%d 个文件" % n)
        return 0
    if len(args) < 2:
        sys.stderr.write(__doc__)
        return 2
    src, dst = args[0], args[1]
    title = args[2] if len(args) > 2 else src
    size = render_file(src, dst, title)
    print("html written: %s (%d bytes)" % (dst, size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
