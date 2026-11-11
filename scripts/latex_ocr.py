#!/usr/bin/env python3
"""公式图片 → LaTeX（基于 pix2tex / LaTeX-OCR 包）。

用法：
  python3 scripts/latex_ocr.py <公式图片路径> [<图片2> ...] [--yes]
  python3 scripts/latex_ocr.py <公式图片路径> --json

依赖：pix2tex（含 torch）；缺失时不自动安装——先提示、加 --yes 才安装（阿里云镜像）。
说明：
- 脚本名刻意不叫 pix2tex.py：否则以 python3 scripts/xxx.py 运行时，sys.path[0] 就是
  scripts/ 目录，会被脚本自身遮蔽真正的 pix2tex 包（module 而非 package），导致
  from pix2tex.cli import LatexOCR 永远失败。
- 用 importlib.metadata 探测安装状态（不 import 包，不受遮蔽影响）。
- 模型进程级单例，多张公式只初始化一次。公式识别准确率有限，识别结果交给模型校对；
  不确定处标 [公式待核]，不硬猜。
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys

MIRROR = "https://mirrors.aliyun.com/pypi/simple"
INSTALL_TIMEOUT = 540  # 秒，低于宿主 Bash 单次执行上限

# 进程级单例：LatexOCR 加载权重很重，多图只初始化一次。
_MODEL = None

# --yes 时才允许自动安装（默认先询问）
AUTO_INSTALL = False


def _pix2tex_installed() -> bool:
    """用 importlib.metadata 探测 pix2tex 是否已安装（不 import，避免被脚本自身遮蔽）。"""
    try:
        importlib.metadata.version("pix2tex")
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


def _ensure():
    if _pix2tex_installed():
        return
    pkg = "pix2tex>=0.1.2"
    if not AUTO_INSTALL:
        raise SystemExit(
            f"[需确认] 需要安装 pix2tex（含 torch 依赖，约 2 GB）。"
            f"回复「装」后加 --yes 重跑即可自动安装（阿里云镜像）。\n"
            f"手动安装：pip install \"{pkg}\" -i {MIRROR}"
        )
    print("[安装] 正在安装 pix2tex（阿里云镜像，含 torch 依赖，较大，请耐心）…", file=sys.stderr)
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", pkg, "-i", MIRROR, "--quiet"],
        capture_output=True, text=True, timeout=INSTALL_TIMEOUT,
    )
    if r.returncode != 0:
        raise SystemExit(
            f"[error] 自动安装 pix2tex 失败，请手动执行：\n"
            f"pip install \"{pkg}\" -i {MIRROR}\n{r.stderr[-800:]}"
        )


def _get_model():
    global _MODEL
    if _MODEL is None:
        _ensure()
        from pix2tex.cli import LatexOCR  # noqa: E402
        _MODEL = LatexOCR()
    return _MODEL


def tex_image(path: str) -> str:
    model = _get_model()
    return model(path)


def main() -> None:
    p = argparse.ArgumentParser(description="公式图片 → LaTeX（pix2tex）")
    p.add_argument("paths", nargs="+", help="公式图片路径，可多个")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    p.add_argument("--yes", action="store_true", help="缺依赖时直接自动安装（默认先询问）")
    args = p.parse_args()

    global AUTO_INSTALL
    AUTO_INSTALL = args.yes

    for path in args.paths:
        if not os.path.exists(path):
            print(f"[跳过] 文件不存在：{path}", file=sys.stderr)
            continue
        try:
            latex = tex_image(path)
        except SystemExit:
            raise
        except Exception as e:
            print(f"[error] {path} 公式识别失败：{e}", file=sys.stderr)
            continue
        if args.json:
            print(json.dumps({"file": path, "latex": latex}, ensure_ascii=False))
        else:
            print(f"{path}\t$$\n{latex}\n$$")


if __name__ == "__main__":
    main()
