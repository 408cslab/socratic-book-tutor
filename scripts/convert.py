#!/usr/bin/env python3
"""多格式文档 → Markdown 转换（含批量建库与扫描 PDF 渲染）。

支持：.txt/.md（直读）、.docx（python-docx，保留标题层级 + 提取内嵌图片）、
.pdf（PyMuPDF 文本层，按页插入标记；无文本层的扫描件返回 [SCANNED] 信号且不写空 md，
     --render-scanned 时把扫描页渲染成 PNG 交给 ocr.py）、
.epub（解析 OPF spine 保证阅读顺序，含解压体积上限防护）、.html/.htm（HTMLParser 保留标题/列表/表格并解码实体）。

扫描 PDF / 图片的 OCR 不在此处理，交给 ocr.py（本脚本负责 PDF → 页图的渲染步骤）。

用法：
  python3 scripts/convert.py <输入文件> --out <md 输出目录> [--json] [--yes]
  python3 scripts/convert.py <扫描PDF> --render-scanned --out <根目录>     # 渲染页图到 <根目录>/pages/
  python3 scripts/convert.py --dir <目录> --recursive --out <根目录>       # 批量建库（md/<相对路径>.md，同名去重）+ manifest.json 断点

依赖：PyMuPDF(pymupdf/fitz)、python-docx；缺失时不自动安装——先提示、加 --yes 才安装（阿里云镜像）。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import posixpath
import re
import subprocess
import sys
from html.parser import HTMLParser
from urllib.parse import unquote
from xml.etree import ElementTree as ET

MIRROR = "https://mirrors.aliyun.com/pypi/simple"
INSTALL_TIMEOUT = 540  # 秒，低于宿主 Bash 单次执行上限

# --yes 时才允许自动安装（默认先询问）
AUTO_INSTALL = False

SUPPORTED_EXTS = {".txt", ".md", ".markdown", ".docx", ".pdf", ".epub", ".html", ".htm"}


def _install(pkgs: list[str], size_mb: int, timeout: int = INSTALL_TIMEOUT) -> None:
    """缺依赖时先询问、--yes 才安装（阿里云镜像），失败给可执行的手动命令。"""
    specs = " ".join(f'"{p}"' for p in pkgs)
    if not AUTO_INSTALL:
        raise SystemExit(
            f"[需确认] 需要安装 {' '.join(pkgs)}（约 {size_mb} MB）。"
            f"回复「装」后加 --yes 重跑即可自动安装（阿里云镜像）。\n"
            f"手动安装：pip install {specs} -i {MIRROR}"
        )
    print(f"[安装] 正在安装 {' '.join(pkgs)}（阿里云镜像）…", file=sys.stderr)
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", *pkgs, "-i", MIRROR, "--quiet"],
        capture_output=True, text=True, timeout=timeout,
    )
    if r.returncode != 0:
        raise SystemExit(
            f"[error] 自动安装 {' '.join(pkgs)} 失败，请手动执行："
            f"pip install {specs} -i {MIRROR}\n{r.stderr[-500:]}"
        )


def _import_pymupdf():
    """优先 pymupdf，回退 fitz（旧版 PyMuPDF），缺失则提示安装。"""
    for name in ("pymupdf", "fitz"):
        try:
            return __import__(name)
        except ImportError:
            continue
    _install(["PyMuPDF>=1.22.0"], 20)
    return __import__("pymupdf")


def _import_docx():
    try:
        return __import__("docx")
    except ImportError:
        _install(["python-docx>=1.1.0"], 5)
        return __import__("docx")


def _probe_spec(module: str) -> bool:
    """用 importlib.util.find_spec 探测模块是否已安装（不真正 import）。"""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _precheck_deps(files: list[str]) -> None:
    """批量开工前预检：按目录内实际出现的扩展名聚合缺失依赖，一次性提示。

    避免「半途遇到缺依赖整批中止、已处理文件的 manifest 不落盘」。
    仅 .docx（python-docx）与 .pdf（PyMuPDF）需要外部依赖，其余格式走标准库。
    """
    counts: dict[str, int] = {}
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        counts[ext] = counts.get(ext, 0) + 1
    missing: list[tuple[str, list[str], int, int]] = []  # (扩展名, 安装包, 体积MB, 数量)
    if counts.get(".docx") and not _probe_spec("docx"):
        missing.append((".docx", ["python-docx>=1.1.0"], 5, counts[".docx"]))
    if counts.get(".pdf") and not (_probe_spec("pymupdf") or _probe_spec("fitz")):
        missing.append((".pdf", ["PyMuPDF>=1.22.0"], 20, counts[".pdf"]))
    if not missing:
        return
    desc = "；".join(
        f"本批含 {n} 个 {ext}，需安装 {' '.join(pkgs)}（约 {mb} MB）"
        for ext, pkgs, mb, n in missing
    )
    if not AUTO_INSTALL:
        specs = " ".join(f'"{p}"' for _e, pkgs, _m, _n in missing for p in pkgs)
        raise SystemExit(
            f"[需确认] {desc}。回复「装」后加 --yes 重跑即可自动安装（阿里云镜像）。\n"
            f"手动安装：pip install {specs} -i {MIRROR}"
        )
    print(f"[提示] {desc}，已带 --yes，将自动安装。", file=sys.stderr)


# ---------------------------------------------------------------- PDF

def convert_pdf(path: str) -> tuple[str, bool, int]:
    """返回 (markdown文本, 是否扫描件, 页数)。扫描件 = 近乎无文本层且页面含图片。"""
    pdf = _import_pymupdf()
    doc = pdf.open(path)
    parts = []
    total_chars = 0
    has_images = False
    for i, page in enumerate(doc):
        text = page.get_text()
        total_chars += len(text.strip())
        if text.strip():
            parts.append(f"\n<!-- 第 {i + 1} 页 -->\n\n{text}")
        if page.get_images():
            has_images = True
    page_count = doc.page_count
    doc.close()
    # 既有图片又几乎无文本层 → 扫描件；短文本 PDF（无图片）不再被误判。
    scanned = total_chars < 50 and has_images
    return "\n".join(parts), scanned, page_count


def render_pdf_pages(path: str, pages_dir: str, base: str, dpi: int = 200) -> list[str]:
    """把 PDF 每页渲染成 PNG（默认 200 dpi），返回图片路径列表。"""
    pdf = _import_pymupdf()
    doc = pdf.open(path)
    os.makedirs(pages_dir, exist_ok=True)
    out: list[str] = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi)
        fn = f"{base}-page-{i + 1:03d}.png"
        fp = os.path.join(pages_dir, fn)
        pix.save(fp)
        out.append(fp)
    doc.close()
    return out


def _existing_pages(page_dir: str, base: str) -> list[str]:
    """返回 page_dir 下已存在的 <base>-page-*.png 页图（按文件名排序），无则空列表。"""
    if not os.path.isdir(page_dir):
        return []
    prefix = f"{base}-page-"
    return sorted(
        os.path.join(page_dir, fn)
        for fn in os.listdir(page_dir)
        if fn.startswith(prefix) and fn.endswith(".png")
    )


# ---------------------------------------------------------------- DOCX

def _heading_level(style_name: str | None) -> int | None:
    """把 Word 样式名（Heading 1 / 标题 1 / Title）映射为 Markdown 标题级别。"""
    if not style_name:
        return None
    m = re.search(r"heading\s*(\d)", style_name, re.I)
    if m:
        return min(int(m.group(1)), 6)
    m = re.search(r"标题\s*(\d)", style_name)
    if m:
        return min(int(m.group(1)), 6)
    if style_name.lower().startswith("title"):
        return 1
    return None


def _extract_docx_images(doc, out_dir: str) -> list[str]:
    """把 docx 内嵌图片（公式/插图）落到 assets/，返回文件名列表，供 latex_ocr.py 使用。"""
    from docx.parts.image import ImagePart

    saved: list[str] = []
    try:
        shapes = doc.inline_shapes
    except Exception:
        return saved
    assets = os.path.join(out_dir, "assets")
    os.makedirs(assets, exist_ok=True)
    for i, shape in enumerate(shapes, 1):
        try:
            blip = shape._inline.graphic.graphicData.pic.blipFill.blip
            part = doc.part.related_parts.get(blip.embed)
            if not isinstance(part, ImagePart):
                continue
            ct = getattr(part, "content_type", "") or ""
            ext = ct.rsplit("/", 1)[-1] if ct.startswith("image/") else "png"
            if ext == "jpeg":
                ext = "jpg"
            fn = f"img-{i:03d}.{ext}"
            with open(os.path.join(assets, fn), "wb") as f:
                f.write(part.blob)
            saved.append(fn)
        except Exception:
            continue
    return saved


def convert_docx(path: str, out_dir: str) -> str:
    docx = _import_docx()
    d = docx.Document(path)
    lines = []
    for p in d.paragraphs:
        if not p.text.strip():
            continue
        level = _heading_level(p.style.name)
        if level:
            lines.append("#" * level + " " + p.text.strip())
        else:
            lines.append(p.text)
    for table in d.tables:
        rows = list(table.rows)
        if not rows:
            continue
        ncols = len(rows[0].cells)
        md_rows = [
            " | ".join(c.text.strip() for c in rows[0].cells),
            " | ".join("---" for _ in range(ncols)),
        ]
        md_rows += [" | ".join(c.text.strip() for c in row.cells) for row in rows[1:]]
        lines.append("\n".join(md_rows))
    imgs = _extract_docx_images(d, out_dir)
    if imgs:
        lines.append("")
        lines.append("## 内嵌图片（公式/插图，如需转 LaTeX 请逐个喂给 latex_ocr.py）")
        for fn in imgs:
            lines.append(f"![{fn}](assets/{fn})")
    return "\n\n".join(lines)


# ---------------------------------------------------------------- HTML

class _HtmlToMarkdown(HTMLParser):
    """轻量 HTML → Markdown：保留 h1-h6 标题、ul/ol 列表、table 表格，解码实体，抽取图片引用。"""

    _SKIP = {"script", "style", "head", "noscript", "template", "nav", "footer"}
    _BLOCK = {"p", "div", "section", "article", "blockquote", "figure", "figcaption"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.heading = 0
        self.heading_buf: list[str] = []
        self.list_depth = 0
        # 表格状态
        self.table = 0
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.cell_buf: list[str] = []
        self.in_cell = False

    def _nl(self) -> None:
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def _flush_table(self) -> None:
        if not self.rows:
            return
        self._nl()
        for ri, row in enumerate(self.rows):
            cells = [c.replace("|", "\\|").strip() for c in row]
            self.parts.append("| " + " | ".join(cells) + " |\n")
            if ri == 0:
                self.parts.append("| " + " | ".join("---" for _ in cells) + " |\n")
        self._nl()
        self.rows = []

    def handle_starttag(self, tag, attrs) -> None:
        t = tag.lower()
        if t in self._SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if t == "table":
            self.table += 1
            self.rows = []
            return
        if self.table:
            if t == "tr":
                self.current_row = []
            elif t in ("td", "th"):
                self.in_cell = True
                self.cell_buf = []
            return
        if t in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.heading = int(t[1])
            self.heading_buf = []
        elif t == "br":
            self.parts.append("\n")
        elif t in self._BLOCK:
            self._nl()
        elif t == "li":
            self._nl()
            self.parts.append("  " * self.list_depth + "- ")
        elif t in ("ul", "ol"):
            self.list_depth += 1
            self._nl()
        elif t == "img":
            a = dict(attrs)
            src = a.get("src") or a.get("data-src")
            alt = a.get("alt") or ""
            if src:
                self.parts.append(f"![{alt}]({src})")

    def handle_endtag(self, tag) -> None:
        t = tag.lower()
        if t in self._SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if t == "table":
            self.table = max(0, self.table - 1)
            if self.table == 0:
                self._flush_table()
            return
        if self.table:
            if t in ("td", "th") and self.in_cell:
                self.in_cell = False
                if self.current_row is not None:
                    self.current_row.append(" ".join(self.cell_buf).strip())
            elif t == "tr":
                if self.current_row is not None:
                    self.rows.append(self.current_row)
                self.current_row = None
            return
        if t in ("h1", "h2", "h3", "h4", "h5", "h6"):
            txt = " ".join(x for x in self.heading_buf if x).strip()
            if txt:
                self.parts.append("#" * self.heading + " " + txt + "\n")
            self.heading = 0
            self.heading_buf = []
        elif t in self._BLOCK:
            self._nl()
        elif t in ("ul", "ol"):
            self.list_depth = max(0, self.list_depth - 1)
            self._nl()

    def handle_data(self, data) -> None:
        if self.skip:
            return
        if self.table:
            if self.in_cell and data.strip():
                self.cell_buf.append(data.strip())
            return
        if self.heading:
            if data.strip():
                self.heading_buf.append(data.strip())
        else:
            s = re.sub(r"\s+", " ", data)
            if s:
                self.parts.append(s)

    def result(self) -> str:
        if self.table:
            self._flush_table()
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def _html_to_markdown(html_text: str) -> str:
    p = _HtmlToMarkdown()
    p.feed(html_text)
    p.close()
    return p.result()


def convert_html(path: str) -> str:
    with open(path, encoding="utf-8", errors="ignore") as f:
        html_text = f.read()
    return _html_to_markdown(html_text)


# ---------------------------------------------------------------- EPUB

# 解压后总体积上限（防 zip 炸弹）
MAX_EPUB_UNCOMPRESSED = 200 * 1024 * 1024  # 200 MB


def _epub_opf_path(z) -> str | None:
    """从 META-INF/container.xml 定位 OPF 路径。"""
    try:
        container = z.read("META-INF/container.xml").decode("utf-8", "ignore")
    except KeyError:
        return None
    root = ET.fromstring(container)
    rootfile = root.find(".//{*}rootfile")
    if rootfile is None:
        return None
    return rootfile.get("full-path")


def _epub_spine_html(z, opf_path: str) -> list[str]:
    """按 OPF spine 顺序返回 html 路径列表（相对 zip 内根目录）。"""
    base = posixpath.dirname(opf_path)
    opf = z.read(opf_path).decode("utf-8", "ignore")
    root = ET.fromstring(opf)
    manifest: dict[str, str] = {}
    for item in root.findall(".//{*}item"):
        iid = item.get("id")
        href = item.get("href")
        if iid and href:
            manifest[iid] = href
    order: list[str] = []
    for itemref in root.findall(".//{*}itemref"):
        href = manifest.get(itemref.get("idref"))
        if href:
            href = unquote(href.split("#", 1)[0])  # 剥 fragment 与 URL 编码
            order.append(posixpath.normpath(posixpath.join(base, href)))
    return order


def convert_epub(path: str) -> str:
    import zipfile

    parts: list[str] = []
    with zipfile.ZipFile(path) as z:
        total = sum(i.file_size for i in z.infolist())
        if total > MAX_EPUB_UNCOMPRESSED:
            raise ValueError(
                f"EPUB 解压后体积超限（{total / 1024 / 1024:.0f} MB > 200 MB），已拒绝处理"
            )
        names = set(z.namelist())
        order: list[str] = []
        opf = _epub_opf_path(z)
        if opf:
            try:
                order = _epub_spine_html(z, opf)
            except Exception:
                order = []
        if not order:
            # 兜底：按文件名排序（保持旧行为，但不再是首选路径）。
            order = sorted(
                n for n in names if n.endswith((".xhtml", ".html", ".htm", ".xml"))
            )
        for name in order:
            if name not in names:
                continue
            try:
                info = z.getinfo(name)
                if info.file_size > MAX_EPUB_UNCOMPRESSED:
                    continue
                html_text = z.read(name).decode("utf-8", "ignore")
            except Exception:
                continue
            md = _html_to_markdown(html_text)
            if md:
                parts.append(md)
    return "\n\n".join(parts)


# ---------------------------------------------------------------- 处理与批量

def _unique_path(candidate: str, used: set[str]) -> str:
    """同名去重：candidate 已被占用时追加 -2 / -3 后缀，直到唯一。返回最终路径。"""
    key = os.path.abspath(candidate)
    if key not in used:
        used.add(key)
        return candidate
    root, ext = os.path.splitext(candidate)
    i = 2
    while True:
        alt = f"{root}-{i}{ext}"
        if os.path.abspath(alt) not in used:
            used.add(os.path.abspath(alt))
            return alt
        i += 1


def process_one(path: str, md_path: str, page_dir: str, base: str,
                render_scanned: bool = False, render_dpi: int = 200,
                force: bool = False) -> dict:
    """处理单个文档，返回结果 dict（source/md/status/chars/scanned/images/note）。

    md_path 为最终 Markdown 输出路径（调用方负责同名去重 / 保留目录层级）；
    page_dir / base 用于扫描件渲染页图（页图存 page_dir，命名 <base>-page-###.png）；
    force=True 时忽略「页图已存在」断点，强制重新渲染。
    """
    ext = os.path.splitext(path)[1].lower()
    result = {
        "source": os.path.abspath(path),
        "md": None,
        "status": "failed",
        "chars": 0,
        "scanned": False,
        "images": [],
        "note": "",
    }
    try:
        if ext in (".txt", ".md", ".markdown"):
            with open(path, encoding="utf-8", errors="ignore") as f:
                md = f.read()
        elif ext == ".docx":
            # assets 与 md 同级，保证 ![img](assets/...) 相对引用成立
            md = convert_docx(path, os.path.dirname(md_path))
        elif ext == ".pdf":
            md, scanned, page_count = convert_pdf(path)
            result["scanned"] = scanned
            if scanned:
                result["status"] = "skipped"
                if render_scanned:
                    existing = [] if force else _existing_pages(page_dir, base)
                    if existing and len(existing) >= page_count:
                        result["images"] = existing
                        result["note"] = f"扫描件，pages/ 已存在 {len(existing)} 页图，跳过渲染（--force 可强制重渲染）"
                    else:
                        result["images"] = render_pdf_pages(path, page_dir, base, render_dpi)
                        result["note"] = f"扫描件，已渲染 {len(result['images'])} 页到 pages/，请用 ocr.py 逐页识别"
                else:
                    result["note"] = "扫描件（无文本层），请加 --render-scanned 渲染后交给 ocr.py"
                return result
        elif ext == ".epub":
            md = convert_epub(path)
        elif ext in (".html", ".htm"):
            md = convert_html(path)
        else:
            result["note"] = f"不支持的格式：{ext}"
            return result

        os.makedirs(os.path.dirname(md_path), exist_ok=True)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)
        result["md"] = md_path
        result["chars"] = len(md)
        result["status"] = "done"
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        result["note"] = str(e)
    return result


def _load_manifest(manifest_path: str) -> list[dict]:
    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (OSError, ValueError):
        pass
    return []


def _write_manifest(manifest_path: str, results: list[dict]) -> None:
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def _report(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False))
        return
    src = os.path.basename(result["source"])
    if result["status"] == "done":
        print(f"[完成] {result['md']}（{result['chars']} 字符）")
    elif result["status"] == "skipped":
        print(f"[SKIPPED] {src}：{result['note']}", file=sys.stderr)
        for img in result["images"]:
            print(f"  - {img}")
    else:
        print(f"[error] {src}：{result['note']}", file=sys.stderr)


def run_single(args) -> None:
    if not args.path:
        raise SystemExit("[error] 需提供输入文件，或改用 --dir")
    if not os.path.exists(args.path):
        raise SystemExit(f"[error] 文件不存在：{args.path}")
    base = os.path.splitext(os.path.basename(args.path))[0]
    md_path = os.path.join(args.out, f"{base}.md")
    page_dir = os.path.join(args.out, "pages")
    result = process_one(args.path, md_path, page_dir, base,
                         args.render_scanned, args.render_dpi, args.force)
    _report(result, args.json)


def run_dir(args) -> None:
    dir_root = os.path.abspath(args.dir)
    if not os.path.isdir(dir_root):
        raise SystemExit(f"[error] 目录不存在：{args.dir}")
    files: list[str] = []
    if args.recursive:
        for dp, _dirs, fns in os.walk(dir_root):
            for fn in fns:
                files.append(os.path.join(dp, fn))
    else:
        for fn in sorted(os.listdir(dir_root)):
            fp = os.path.join(dir_root, fn)
            if os.path.isfile(fp):
                files.append(fp)
    files = sorted(set(os.path.abspath(f) for f in files))

    _precheck_deps(files)

    md_dir = os.path.join(args.out, "md")
    pages_dir = os.path.join(args.out, "pages")
    manifest_path = os.path.join(args.out, "manifest.json")
    manifest = _load_manifest(manifest_path)
    done = {e["source"] for e in manifest if e.get("status") == "done"}
    if args.force:
        done = set()

    # 同名去重：seed 已占用 md 路径（含历史 manifest），避免重跑时与旧产物撞名
    used: set[str] = {os.path.abspath(e["md"]) for e in manifest if e.get("md")}

    results: list[dict] = []
    resumed_sources: set[str] = set()
    for fp in files:
        ext = os.path.splitext(fp)[1].lower()
        if ext not in SUPPORTED_EXTS:
            continue
        if fp in done:
            entry = next(e for e in manifest if e.get("source") == fp)
            results.append(entry)
            resumed_sources.add(entry["source"])
        else:
            # 保留相对子目录层级：md/<相对路径去扩展名>.md，重名再加 -2 后缀
            rel_base = os.path.splitext(os.path.relpath(fp, dir_root))[0]
            md_path = _unique_path(os.path.join(md_dir, rel_base + ".md"), used)
            page_dir = os.path.join(pages_dir, os.path.dirname(rel_base))
            base = os.path.basename(rel_base)
            results.append(process_one(fp, md_path, page_dir, base,
                                       args.render_scanned, args.render_dpi, args.force))
        # 增量落盘：每处理完一个文件就重写 manifest（几十 KB 级），超时/崩溃后可从断点续跑
        _write_manifest(manifest_path, results)

    summary = {
        "total": len(results),
        "done": sum(1 for r in results
                    if r["status"] == "done" and r["source"] not in resumed_sources),
        "resumed": sum(1 for r in results
                       if r["status"] == "done" and r["source"] in resumed_sources),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
    }
    if args.json:
        print(json.dumps({"manifest": manifest_path, "summary": summary}, ensure_ascii=False))
    else:
        print(f"[完成] 批量处理 {summary['total']} 个文档："
              f"done {summary['done']} / resumed {summary['resumed']} "
              f"/ skipped {summary['skipped']} / failed {summary['failed']}")
        print(f"[清单] {manifest_path}")


# ---------------------------------------------------------------- main

def main() -> None:
    p = argparse.ArgumentParser(description="多格式文档 → Markdown 转换（含批量与扫描件渲染）")
    p.add_argument("path", nargs="?", help="输入文件路径（--dir 模式下省略）")
    p.add_argument("--dir", help="批量：输入目录")
    p.add_argument("--recursive", action="store_true", help="--dir 时递归子目录")
    p.add_argument("--out", required=True, help="输出目录（单文件=md 目录；--dir=领域根目录）")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    p.add_argument("--yes", action="store_true", help="缺依赖时直接自动安装（默认先询问）")
    p.add_argument("--force", action="store_true", help="--dir 重跑时忽略已 done 项与已渲染页图断点")
    p.add_argument("--render-scanned", action="store_true", help="扫描 PDF 渲染成页图到 <out>/pages/")
    p.add_argument("--render-dpi", type=int, default=200, help="扫描页渲染 DPI（默认 200）")
    args = p.parse_args()

    global AUTO_INSTALL
    AUTO_INSTALL = args.yes

    if args.dir:
        run_dir(args)
    else:
        run_single(args)


if __name__ == "__main__":
    main()
