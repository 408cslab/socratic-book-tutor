#!/usr/bin/env python3
"""扫描件 / 图片 OCR 识别（PaddleOCR，兼容 2.x 与 3.x）。

用法：
  python3 scripts/ocr.py <图片路径> [<图片路径2> ...] --out <输出目录> [--name 文档名] [--yes] [--rm-pages]
  python3 scripts/ocr.py <图片路径> --json

依赖：paddleocr + paddlepaddle；缺失时不自动安装——先提示、加 --yes 才安装（阿里云镜像）。
说明：
- 兼容 PaddleOCR 2.x（use_angle_cls + ocr.ocr）与 3.x（use_textline_orientation + predict）。
- 识别结果按行输出；不确定处由模型校对环节标 [待核]。不构成任何内容的权威识别。
- --out 为输出目录时，合并写为 <out>/<name>.md（默认 ocr-merged.md），避免多文档互相覆盖。
- 合并成 md 后**默认保留**输入页图（不删除，安全）；确需释放磁盘时加 `--rm-pages` 显式删除。
- `--rm-pages` **仅删除** convert.py --render-scanned 渲染的中间页图（路径含 `pages/` 且命名
  为 `<文档名>-page-###.png`）；其余输入即使带该 flag 也跳过并提示，原始图片绝不删除。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

MIRROR = "https://mirrors.aliyun.com/pypi/simple"
INSTALL_TIMEOUT = 540  # 秒，低于宿主 Bash 单次执行上限

# 进程级单例：PaddleOCR 初始化很重，多图只初始化一次。
_OCR = None
_PADDLE_MAJOR = 0

# --yes 时才允许自动安装（默认先询问）
AUTO_INSTALL = False

# 仅 convert.py --render-scanned 的中间页图（pages/<base>-page-###.png）可被 --rm-pages 删除
_RENDERED_PAGE_RE = re.compile(r"(?:^|/)pages/[^/]+-page-\d+\.png$")


def _is_rendered_page(path: str) -> bool:
    """判断路径是否为 convert.py --render-scanned 渲染的中间页图。"""
    return bool(_RENDERED_PAGE_RE.search(path.replace("\\", "/")))


def _paddle_major() -> int:
    try:
        import paddleocr
    except ImportError:
        return 0
    v = str(getattr(paddleocr, "__version__", ""))
    seg = v.split(".")[0]
    return int(seg) if seg.isdigit() else 0


def _ensure_paddle() -> None:
    try:
        import paddleocr  # noqa: F401
        return
    except ImportError:
        pass
    pkgs = ["paddleocr>=2.7", "paddlepaddle>=2.6"]
    specs = " ".join(f'"{p}"' for p in pkgs)
    if not AUTO_INSTALL:
        raise SystemExit(
            f"[需确认] 需要安装 paddleocr/paddlepaddle（约 600 MB）。"
            f"回复「装」后加 --yes 重跑即可自动安装（阿里云镜像）。\n"
            f"手动安装：pip install {specs} -i {MIRROR}"
        )
    print("[安装] 正在安装 paddleocr/paddlepaddle（阿里云镜像，较大，请耐心）…", file=sys.stderr)
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", *pkgs, "-i", MIRROR, "--quiet"],
        capture_output=True, text=True, timeout=INSTALL_TIMEOUT,
    )
    if r.returncode != 0:
        raise SystemExit(
            f"[error] 自动安装 paddleocr 失败，请手动执行：\n"
            f"pip install {specs} -i {MIRROR}\n{r.stderr[-800:]}"
        )


def _make_ocr():
    _ensure_paddle()
    global _PADDLE_MAJOR
    _PADDLE_MAJOR = _paddle_major()  # 安装后再探测版本，避免首次运行探测在安装前失效
    from paddleocr import PaddleOCR  # noqa: E402

    if _PADDLE_MAJOR >= 3:
        return PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=True,
            lang="ch",
        )
    return PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)


def _get_ocr():
    global _OCR
    if _OCR is None:
        _OCR = _make_ocr()
    return _OCR


def _ocr_2x(ocr, path: str) -> str:
    result = ocr.ocr(path, cls=True)
    lines = []
    for page in result or []:
        if not page:
            continue
        for item in page:
            try:
                lines.append(item[1][0])
            except (TypeError, IndexError, KeyError):
                continue
    return "\n".join(lines)


def _result_to_dict(res) -> dict | None:
    """把 3.x 的 OCRResult 归一为 dict（兼容 .json 属性/方法、dict、字典式访问）。"""
    if isinstance(res, dict):
        return res
    j = getattr(res, "json", None)
    if isinstance(j, dict):
        return j
    if callable(j):
        try:
            v = j()
            if isinstance(v, dict):
                return v
        except Exception:
            pass
    try:
        v = dict(res)
        if isinstance(v, dict):
            return v
    except Exception:
        pass
    return None


def _ocr_3x(ocr, path: str) -> str:
    result = ocr.predict(path)
    lines = []
    for res in result:
        data = _result_to_dict(res)
        if not data:
            continue
        inner = data.get("res") if isinstance(data.get("res"), dict) else data
        for t in inner.get("rec_texts") or []:
            if t:
                lines.append(t)
    return "\n".join(lines)


def ocr_image(path: str) -> str:
    ocr = _get_ocr()
    if _PADDLE_MAJOR >= 3:
        return _ocr_3x(ocr, path)
    return _ocr_2x(ocr, path)


def main() -> None:
    p = argparse.ArgumentParser(description="扫描件 / 图片 OCR（PaddleOCR，兼容 2.x/3.x）")
    p.add_argument("paths", nargs="+", help="图片路径，可多个")
    p.add_argument("--out", help="输出目录（合并写为 <out>/<name>.md）")
    p.add_argument("--name", default="ocr-merged", help="合并输出 md 的文件名（不含扩展名，默认 ocr-merged）")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    p.add_argument("--yes", action="store_true", help="缺依赖时直接自动安装（默认先询问）")
    p.add_argument("--rm-pages", action="store_true", help="合并成 md 后删除渲染中间页图（仅 pages/*-page-###.png，默认保留）")
    args = p.parse_args()

    global AUTO_INSTALL
    AUTO_INSTALL = args.yes

    results = {}
    for path in args.paths:
        if not os.path.exists(path):
            print(f"[跳过] 文件不存在：{path}", file=sys.stderr)
            continue
        try:
            text = ocr_image(path)
        except SystemExit:
            raise
        except Exception as e:
            print(f"[error] {path} OCR 失败：{e}", file=sys.stderr)
            continue
        results[path] = text
        if args.json:
            print(json.dumps({"file": path, "text": text}, ensure_ascii=False))
        else:
            print(f"===== {path} =====")
            print(text)
            print()

    if args.out and results:
        os.makedirs(args.out, exist_ok=True)
        merged = "\n\n".join(f"<!-- {k} -->\n\n{v}" for k, v in results.items())
        out_path = os.path.join(args.out, f"{args.name}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(merged)
        print(f"[完成] 合并 OCR 结果已写：{out_path}")
        if args.rm_pages:
            removed = 0
            skipped_rm = 0
            for path in results:
                if not _is_rendered_page(path):
                    skipped_rm += 1
                    continue
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass
            if removed:
                print(f"[清理] 已删除 {removed} 张渲染中间页图")
            if skipped_rm:
                print(f"[提示] 仅清理渲染中间页图，原始图片未删除（跳过 {skipped_rm} 个输入）", file=sys.stderr)


if __name__ == "__main__":
    main()
