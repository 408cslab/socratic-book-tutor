# Changelog

本文件记录 `socratic-book-tutor` 的版本变更。按开放平台评审口径，`CHANGELOG.md` 与 `tests/` 属于开发/回归资料，**打包提交时不进 zip**。

## [1.0.1] - 2026-11-09

第三轮评审整改：修复批量建库的健壮性缺口与 `--rm-pages` 的尾部删除风险。

### 修复（P1）

- **P1-1 批量缺依赖整批中止 / manifest 不落盘**：`convert.py --dir` 开工前按目录内实际扩展名做依赖预检（`importlib.util.find_spec`，不 import），缺哪个一次性汇总提示、`--yes` 才开工；manifest 改为**每处理完一个文件增量落盘**，超时/崩溃后可从任意断点续跑。
- **P1-2 `--rm-pages` 可删任意原始图片**：`ocr.py --rm-pages` 现在**仅删除** `pages/<文档名>-page-###.png` 渲染中间页图，其余输入即使带该 flag 也跳过并提示「仅清理渲染中间页图，原始图片未删除」。

### 修复（P2）

- DOCX 表格补 Markdown 分隔行（`| --- |`），与 HTML 路径对齐。
- 批量 summary 新增 `resumed` 计数：从 manifest 恢复的已完成项与「本轮实际处理」分开统计。
- `tests/README` 补「首次运行缺依赖会提示，--yes 安装」。
- `examples_en` 补 1 条（扫描书逐章 OCR 建库），与 `examples_zh` 5 条对齐。

## [1.0.0] - 2026-11-07

首发正式版（自 0.1.0 评审整改而来）。重点是把「写得漂亮」变成「真的能跑通」：

### 修复（阻断项）

- **P0-1 扫描 PDF 主链路打通**：`convert.py` 新增 `--render-scanned`（PyMuPDF `page.get_pixmap(dpi=200)` 渲染扫描页到 `pages/`），补上「PDF → 页图」这一步，使「扫描 PDF → 渲染 → 逐页 OCR → 合并」在包内闭环。
- **P0-2 读图工具名与白名单修正**：全库 8 处小写 read（工具名）改为「先 `Read` 取路径、再 `ViewImage` 读图」；`allowed-tools` 补 `ViewImage`；明确「模型读图是可选优化，本地 `ocr.py` 是可预期路径」。
- **P0-3 输入侧红线与第三方共享告知**：新增「合法书源 / 拒绝盗版 / 产物不分发」，并在处理扫描件/图片前告知「将发送给模型识别」并征得同意。

### 修复（高优先级）

- 示例命令去 `<...>` 占位符、可原样粘贴执行；`$SKILL_ROOT` 作为主路径求值，命令统一用 `"$SKILL_ROOT/scripts/..."`（cwd 相对路径仅当已在技能根时作简写）。
- `<workspace>` 三级解析（`$WORKSPACE` → cwd → `$HOME`），首轮告知持久化状态。
- description/description_zh/description_en 补「不用于」负向排除。
- 新增「无书可依」分支（routing-rules §2）。
- 三脚本缺依赖改为「先询问、`--yes` 才安装」，超时降到 540 s，依赖版本给下限。
- 公式脚本 `pix2tex.py` 重命名为 `latex_ocr.py`：修复「脚本名遮蔽同名 pip 包」导致 `from pix2tex.cli import LatexOCR` 永远失败的 bug；安装探测改用不 import 的 `importlib.metadata.version('pix2tex')`。
- `convert.py` 新增 `--dir/--recursive` 批量建库 + `manifest.json` 断点续建。
- `convert.py --dir` 同名文件不再互相覆盖：按相对子目录层级落盘（`md/<相对路径>.md`），同目录重名加 `-2` 后缀并在 manifest 记录实际路径。
- `progress.md` 拆「覆盖区（当前位置）+ 追加区（薄弱点累计）」。
- `convert.py --render-scanned` 增加渲染断点：`pages/` 已有完整页图时重跑跳过渲染（`--force` 强制），避免上千页重复渲染。
- `ocr.py` 提供 `--rm-pages` 开关（默认保留输入页图，显式删除以省磁盘）。

### 修复（建议项）

- `ocr.py --out` 增加 `--name`，避免多文档合并互相覆盖。
- HTML `<table>` 转为 Markdown 表格；EPUB 增加 200 MB 解压体积上限。
- `version` 由 0.1.0 提升为 1.0.0。
- 补 `LICENSE`、`icon.png`（走表单上传，不进 zip）、`tests/` 最小回归样本。

## [0.1.0] - 2026-10

初版：苏格拉底六类追问 + 两阶段建库/学习 + 三脚本（convert/ocr/latex_ocr）。
