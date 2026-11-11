# 回归测试样本与预期输出

> 打包提交时 `tests/` 不进 zip。这里的样本是最小回归集，用于验证三脚本的主链路。

## 样本

| 文件 | 类型 | 预期 |
|---|---|---|
| `samples/text.pdf` | 有文本层 PDF | `convert.py` 输出 `.md`，无 `[SCANNED]`，字符数 > 0 |
| `samples/scanned.pdf` | 无文本层、仅图片层 PDF | `convert.py` 输出 `[SCANNED]` 且不写空 md；加 `--render-scanned` 渲染出 1 张 `pages/scanned-page-001.png` |
| `samples/formula.png` | 含公式文本的图片 | `latex_ocr.py` 输出近似 LaTeX；`ocr.py` 输出识别文字 |
| `samples/table.html` | 含表格的 HTML | `convert.py` 输出含 Markdown 表格（`\| 列A \| 列B \|`）的 md |
| `samples/sample.docx` | 含标题/段落/表格的 Word | `convert.py` 输出 `# 第一章 标题` + 正文 + Markdown 表格（含 `---` 分隔行） |
| `samples/book.epub` | 最小 EPUB（OPF spine） | `convert.py` 按 spine 顺序输出 `# 第一章 标题` + 正文 |

## 跑法

```bash
# 文本层 PDF → md
python3 scripts/convert.py tests/samples/text.pdf --out /tmp/sbt-md

# 扫描 PDF → 渲染页图（OCR 链路第一步）
python3 scripts/convert.py tests/samples/scanned.pdf --render-scanned --out /tmp/sbt-root
# 期望：/tmp/sbt-root/pages/scanned-page-001.png 存在

# HTML 表格 → md
python3 scripts/convert.py tests/samples/table.html --out /tmp/sbt-html

# DOCX → md（需 python-docx）
python3 scripts/convert.py tests/samples/sample.docx --out /tmp/sbt-docx

# EPUB → md
python3 scripts/convert.py tests/samples/book.epub --out /tmp/sbt-epub

# 批量 + manifest 断点
python3 scripts/convert.py --dir tests/samples --recursive --out /tmp/sbt-root2
# 首次运行缺依赖（如 python-docx）会一次性汇总提示，加 --yes 即可自动安装
# 期望：md/text.md、md/table.md 存在；manifest.json 里 scanned.pdf 为 skipped

# 公式 → LaTeX（首次缺依赖会先提示，加 --yes 才安装）
python3 scripts/latex_ocr.py tests/samples/formula.png
```

## 复评 Checklist（提审前逐项打勾）

- [ ] 8 项必填字段仍在；`allowed-tools` 含 `ViewImage`
- [ ] 全库无小写 read 作为工具名
- [ ] 扫描 PDF：`convert.py --render-scanned` → `pages/*.png` → `ocr.py` → md 落盘
- [ ] 文本层 PDF / docx / epub / html 各自跑通（见上 6 个样本）
- [ ] 示例命令可原样粘贴执行（无 `<...>`，含空格路径有引号）
- [ ] 三脚本缺依赖时先提示、`--yes` 才安装；超时 ≤ 540 s
- [ ] `convert.py --dir` 缺依赖时一次性预检提示、manifest 增量落盘（可断点续跑）
- [ ] `ocr.py --rm-pages` 仅删 `pages/*-page-###.png`，原始图片不删
- [ ] `progress.md` 薄弱点可累计（追加区）
- [ ] 打包排除：`scripts/__pycache__/`、`.DS_Store`、`tests/`、`CHANGELOG.md`
