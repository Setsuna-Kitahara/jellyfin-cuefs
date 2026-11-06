#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 README + docs/ 渲染成一套静态站点（GitHub Pages 用）。

纯标准库，不联网、不装包。用法：
    python3 tools/build_docs_site.py [输出目录]      # 默认 <仓库>/_site

输出是扁平结构：index.html（README）、00-INDEX.html … 14-NAMING.html、
configurator.html、sample/cover.jpg。链接从 .md 改写成 .html，
所以直接丢给 GitHub Pages / 任意静态服务器都能点。
"""
import html
import io
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SRC, '_site')
if not os.path.isabs(OUT):
    OUT = os.path.join(os.getcwd(), OUT)
sys.path.insert(0, HERE)
import md2html  # noqa: E402

VERSION = os.environ.get('CUEFS_VERSION', '1.5.0')
REPO_URL = 'https://github.com/' + os.environ.get('GITHUB_REPOSITORY', 'Setsuna-Kitahara/jellyfin-cuefs')

DOC_ORDER = ['00-INDEX', '01-QUICKSTART', '02-TAK-LICENSE', '03-CONFIG', '04-JELLYFIN',
             '05-SIDECAR', '06-IMAGE-CUE', '07-MAKE-TAK', '08-SAMPLE-TEST', '09-ARM64',
             '10-SECURITY', '11-METADATA', '12-OPS', '13-FAQ', '14-NAMING']

CSS = """
:root { --fg:#1f2328; --muted:#59636e; --line:#d8dee4; --bg:#fff; --soft:#f6f8fa; --accent:#2f6f4e; }
* { box-sizing: border-box; }
body { margin:0; font:16px/1.75 -apple-system,"Noto Sans CJK SC","Source Han Sans SC","Microsoft YaHei",sans-serif;
       color:var(--fg); background:var(--bg); }
a { color:#0b6bcb; text-decoration:none; }
a:hover { text-decoration:underline; }
header.bar { position:sticky; top:0; z-index:10; display:flex; align-items:center; gap:14px; flex-wrap:wrap;
       padding:10px 22px; background:#fff; border-bottom:1px solid var(--line); box-shadow:0 1px 3px rgba(0,0,0,.04); }
header.bar .brand { font-weight:700; color:var(--accent); letter-spacing:.3px; }
header.bar .sep { color:var(--line); }
header.bar .meta { margin-left:auto; color:var(--muted); font-size:13px; }
.wrap { display:grid; grid-template-columns:250px minmax(0,1fr); gap:38px; max-width:1220px;
        margin:0 auto; padding:28px 24px 90px; }
nav.toc { position:sticky; top:64px; align-self:start; font-size:14px; max-height:calc(100vh - 90px); overflow:auto; }
nav.toc .t { font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:.08em; font-size:11px; margin:0 0 8px; }
nav.toc ul { list-style:none; margin:0 0 16px; padding:0; }
nav.toc li { margin:2px 0; }
nav.toc li.h3 { padding-left:14px; font-size:13px; }
nav.toc li.h3 a { color:var(--muted); }
nav.toc a.on { color:var(--accent); font-weight:700; }
article { min-width:0; }
article .doc-title { margin:0 0 6px; font-size:13px; color:var(--muted); letter-spacing:.04em; }
article h1 { font-size:30px; line-height:1.3; margin:.1em 0 .6em; padding-bottom:.35em; border-bottom:3px solid var(--accent); }
article h2 { font-size:22px; margin:2em 0 .6em; padding-bottom:.25em; border-bottom:1px solid var(--line); color:#173d2c; }
article h3 { font-size:17px; margin:1.6em 0 .5em; color:var(--accent); }
article p { margin:.7em 0; }
article table { border-collapse:collapse; width:100%; margin:1.1em 0; font-size:14px; }
article th, article td { border:1px solid var(--line); padding:7px 11px; text-align:left; vertical-align:top; }
article th { background:#eef5f0; font-weight:600; }
article tr:nth-child(even) td { background:#fafbfc; }
article blockquote { border-left:4px solid #7fbf9a; background:#f5faf7; margin:1.1em 0; padding:.6em 1em; color:#38473f; }
article blockquote p { margin:.2em 0; }
article code { background:#f3f4f6; padding:1px 5px; border-radius:4px; font-size:89%;
       font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Noto Sans Mono CJK SC",monospace; }
article pre { background:#f6f8fa; border:1px solid var(--line); border-radius:7px; padding:13px 15px; overflow-x:auto; }
article pre code { background:none; padding:0; font-size:13px; line-height:1.55; }
article hr { border:none; border-top:1px solid var(--line); margin:2.2em 0; }
article ul, article ol { padding-left:1.5em; }
article li { margin:.28em 0; }
article strong { color:#102c1f; }
.pager { display:flex; justify-content:space-between; gap:14px; margin:3em 0 0; padding-top:1.4em; border-top:1px solid var(--line); font-size:14px; }
.pager a { padding:7px 12px; border:1px solid var(--line); border-radius:7px; background:var(--soft); }
.notice { background:#fff8e6; border:1px solid #f0d68a; color:#5a4607; padding:12px 16px; border-radius:8px; margin:0 0 22px; font-size:14px; }
.cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:12px; margin:1.4em 0 2em; }
.cards a { display:block; padding:13px 15px; border:1px solid var(--line); border-radius:9px; background:var(--soft); }
.cards a b { display:block; color:var(--accent); margin-bottom:3px; }
.cards a span { color:var(--muted); font-size:13px; line-height:1.5; }
@media (max-width: 900px) { .wrap { grid-template-columns:1fr; } nav.toc { display:none; } }
"""

DESC = {
    '00-INDEX': '按「我想干什么」找文档',
    '01-QUICKSTART': '15 分钟内听到第一首',
    '02-TAK-LICENSE': 'TAK 解码库为什么不能随镜像发',
    '03-CONFIG': '参数、环境变量、缓存机制',
    '04-JELLYFIN': '挂进 Jellyfin，及库里的名字从哪来',
    '05-SIDECAR': '封面 / 歌词 / album.nfo 放哪一侧',
    '06-IMAGE-CUE': 'FLAC/WV/TTA 等整盘也能切',
    '07-MAKE-TAK': '自己造一张 TAK 测试盘',
    '08-SAMPLE-TEST': '冒烟、缓存、位级一致性实测',
    '09-ARM64': 'ARM 上的三条替代路径',
    '10-SECURITY': '只听 127.0.0.1、认证、反代',
    '11-METADATA': 'NFO 能补什么、补不了什么',
    '12-OPS': '更新 / 卸载 / 备份 / 排错',
    '13-FAQ': '常见问题（含专辑名、重名归并）',
    '14-NAMING': '媒体库里的专辑名与曲目名（新增）',
}


def rewrite_links(body):
    """把 .md 链接改成 .html；去掉 docs/ 前缀；README.md -> index.html。"""
    def fix(m):
        href = m.group(1)
        path, _, anchor = href.partition('#')
        if path.endswith('.md'):
            name = os.path.basename(path)[:-3]
            path = 'index.html' if name.upper() == 'README' else name + '.html'
        elif path in ('', None):
            path = ''
        out = path + (('#' + anchor) if anchor else '')
        return 'href="%s"' % out
    body = body.replace('href="docs/configurator/index.html"', 'href="configurator.html"')
    body = body.replace('href="docs/configurator/"', 'href="configurator.html"')
    # LICENSE 这类只存在于仓库里的文件，指回 GitHub 上的原始文件
    body = body.replace('href="LICENSE"', 'href="%s/blob/main/LICENSE"' % REPO_URL)
    body = re.sub(r'href="([^"]*)"', fix, body)
    # 链接文字里的 .md 也去掉，读起来更像成品文档
    body = re.sub(r'(<a href="[^"]+\.html"[^>]*>)([^<]*?)\.md(</a>)', r'\1\2\3', body)
    return body


def toc_of(body):
    items = []
    for m in re.finditer(r'<h([23]) id="([^"]+)">(.*?)</h\1>', body, re.S):
        lvl, hid, txt = m.group(1), m.group(2), re.sub(r'<[^>]+>', '', m.group(3))
        items.append((int(lvl), hid, txt))
    if not items:
        return ''
    out = ['<p class="t">本页目录</p><ul>']
    for lvl, hid, txt in items:
        out.append('<li class="h%d"><a href="#%s">%s</a></li>' % (lvl, hid, html.escape(txt)))
    out.append('</ul>')
    return '\n'.join(out)


def page(title, body, nav_html, pager_html, docname):
    header = ('<header class="bar"><span class="brand">cuefs %s</span>'
              '<span class="sep">/</span><a href="index.html">文档</a>'
              '<span class="sep">/</span><span>%s</span>'
              '<span class="meta"><a href="configurator.html">配置生成器</a> · '
              '源码见 <a href="https://github.com/Setsuna-Kitahara/jellyfin-cuefs">GitHub 仓库</a>'
              '</span></header>' % (html.escape(VERSION), html.escape(docname)))
    return ('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>%s · cuefs 文档</title>\n<style>%s</style>\n</head>\n<body>\n'
            '%s\n<div class="wrap">\n<nav class="toc">%s</nav>\n'
            '<article>\n%s\n%s\n</article>\n</div>\n</body>\n</html>\n'
            % (html.escape(title), CSS, header, nav_html, body, pager_html))


def build():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    pages = []  # (file, label)

    # README -> index.html
    readme = io.open(os.path.join(SRC, 'README.md'), encoding='utf-8').read()
    readme = re.sub(r'<p align="center">\s*<img [^>]*>\s*</p>', '\n\n@@COVER@@\n\n', readme)
    body = rewrite_links(md2html.convert(readme))
    cover_html = ('<p style="text-align:center;margin:4px 0 20px">'
                  '<img src="sample/cover.jpg" alt="cuefs 示例专辑封面" width="360" '
                  'style="border-radius:10px;border:1px solid #d8dee4"></p>')
    body = (body.replace('<p>@@COVER@@</p>', cover_html)
                .replace('&lt;p&gt;@@COVER@@&lt;/p&gt;', cover_html)
                .replace('@@COVER@@', cover_html))
    cards = ['<div class="cards">']
    for d in DOC_ORDER:
        label = d.split('-', 1)[1]
        cards.append('<a href="%s.html"><b>%s · %s</b><span>%s</span></a>'
                     % (d, d.split('-')[0], label, html.escape(DESC.get(d, ''))))
    cards.append('</div>')
    index_body = ('<div class="notice">这是从仓库里的 <code>README.md</code> 与 <code>docs/*.md</code> '
                  '自动渲染出来的站点；改文档请改 Markdown 源文件，本站跟着 Actions 自动更新。</div>'
                  + body.replace('<h1', '<h1', 1) + '<h2 id="all-docs">全部文档</h2>\n' + '\n'.join(cards))
    nav = '<p class="t">文档</p><ul><li class="h2"><a href="index.html" class="on">README（本页）</a></li>'
    for d in DOC_ORDER:
        nav += '<li class="h2"><a href="%s.html">%s %s</a></li>' % (d, d.split('-')[0], d.split('-', 1)[1])
    nav += '</ul>'
    io.open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(
        page('README', index_body, nav, '', 'README'))
    pages.append(('index.html', 'README'))

    for i, d in enumerate(DOC_ORDER):
        src = os.path.join(SRC, 'docs', d + '.md')
        if not os.path.exists(src):
            print('缺文件:', src)
            continue
        md = io.open(src, encoding='utf-8').read()
        body = rewrite_links(md2html.convert(md))
        label = d.split('-', 1)[1]
        nav = '<p class="t">文档</p><ul><li class="h2"><a href="index.html">README</a></li>'
        for dd in DOC_ORDER:
            cls = ' class="on"' if dd == d else ''
            nav += '<li class="h2"><a href="%s.html"%s>%s %s</a></li>' % (dd, cls, dd.split('-')[0], dd.split('-', 1)[1])
        nav += '</ul>' + toc_of(body)
        prev_p = ('<a href="index.html">← README</a>' if i == 0
                  else '<a href="%s.html">← %s</a>' % (DOC_ORDER[i-1], DOC_ORDER[i-1]))
        next_p = ('<span></span>' if i == len(DOC_ORDER) - 1
                  else '<a href="%s.html">%s →</a>' % (DOC_ORDER[i+1], DOC_ORDER[i+1]))
        pager = '<div class="pager">%s%s</div>' % (prev_p, next_p)
        io.open(os.path.join(OUT, d + '.html'), 'w', encoding='utf-8').write(
            page(label, body, nav, pager, d))
        pages.append((d + '.html', label))

    # 仓库根部的其它 Markdown 也发布出来，免得正文里的链接指向 404
    EXTRA = [('THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.html', '开源许可清单'),
             ('PUBLISH.md', 'PUBLISH.html', '发布清单'),
             ('sample/CREDITS.md', 'CREDITS.html', '示例素材来源')]
    for rel, out_name, label in EXTRA:
        src = os.path.join(SRC, rel)
        if not os.path.exists(src):
            print('缺文件:', src)
            continue
        md = io.open(src, encoding='utf-8').read()
        body = rewrite_links(md2html.convert(md))
        nav = '<p class="t">文档</p><ul><li class="h2"><a href="index.html">README</a></li>'
        for dd in DOC_ORDER:
            nav += '<li class="h2"><a href="%s.html">%s %s</a></li>' % (dd, dd.split('-')[0], dd.split('-', 1)[1])
        nav += '</ul>' + toc_of(body)
        pager = '<div class="pager"><a href="index.html">← README</a><span></span></div>'
        io.open(os.path.join(OUT, out_name), 'w', encoding='utf-8').write(
            page(label, body, nav, pager, label))
        pages.append((out_name, label))

    # configurator 是现成 HTML，直接搬过来，加个返回条
    cfg_src = os.path.join(SRC, 'docs', 'configurator', 'index.html')
    if os.path.exists(cfg_src):
        cfg = io.open(cfg_src, encoding='utf-8').read()
        back = ('<div style="position:fixed;top:0;left:0;right:0;z-index:99;padding:8px 16px;'
                'background:#fff;border-bottom:1px solid #d8dee4;font:14px -apple-system,sans-serif">'
                '<a href="index.html" style="color:#0b6bcb">← 文档预览</a>'
                '<span style="margin-left:12px;color:#59636e">cuefs 配置器（原样页面）</span></div>'
                '<div style="height:40px"></div>')
        cfg = re.sub(r'(<body[^>]*>)', r'\1' + back, cfg, count=1)
        io.open(os.path.join(OUT, 'configurator.html'), 'w', encoding='utf-8').write(cfg)
        pages.append(('configurator.html', '配置器'))

    cover_src = os.path.join(SRC, 'sample', 'cover.jpg')
    if os.path.exists(cover_src):
        os.makedirs(os.path.join(OUT, 'sample'), exist_ok=True)
        shutil.copy(cover_src, os.path.join(OUT, 'sample', 'cover.jpg'))

    # README 里若引用图片，按相对路径备份过去
    for m in re.finditer(r'!\[[^\]]*\]\(([^)]+)\)', readme):
        rel = m.group(1)
        s = os.path.join(SRC, rel)
        d = os.path.join(OUT, rel)
        if os.path.exists(s):
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
    print('生成 %d 页 -> %s' % (len(pages), OUT))


if __name__ == '__main__':
    build()
