# 知识库构建规则（OCR / 公式 / 转换 / 校对 / 索引）

把用户提供的一批电子书转成 `<workspace>/.socratic-tutor/<领域>/md/*.md` + `index.md`（`<workspace>` 三级解析见 @references/memory-rules.md §4）。

> 本文件中 `scripts/xxx.py` 均指 `$SKILL_ROOT/scripts/xxx.py`（`$SKILL_ROOT` = 技能根目录，见 SKILL.md「脚本调用」）；实际执行命令用 `python3 "$SKILL_ROOT/scripts/xxx.py"`。

## 0. 依赖与缺失行为

运行环境：Python ≥ 3.9。三个脚本在**缺依赖时不自动安装**——先打印「需要安装 X（约 N MB）」并退出，回复「装」后加 `--yes` 重跑才会安装（超时 ≤ 540 s，阿里云镜像）。模型读图（`Read` + `ViewImage`）是可选优化，本地脚本是**可预期路径**，两者都要能独立跑通。

| 依赖 | 用途 | 体积量级 | 缺失时行为 |
|---|---|---|---|
| PyMuPDF（pymupdf） | PDF 文本抽取 / 扫描页渲染 | ~20 MB | 提示后 `--yes` 安装 |
| python-docx | .docx 段落与内嵌图抽取 | ~5 MB | 提示后 `--yes` 安装 |
| paddleocr + paddlepaddle | 本地 OCR（兜底） | ~600 MB | 提示后 `--yes` 安装；失败回退模型读图 |
| pix2tex（含 torch；由脚本 `latex_ocr.py` 调用） | 公式图片 → LaTeX（兜底） | ~2 GB | 提示后 `--yes` 安装；失败标 `[公式待核]` |
| 支持图片输入的模型 | 模型读图 OCR / 公式（可选优化） | — | 回退本地 `ocr.py` / `latex_ocr.py` |

- 大依赖（paddleocr+paddlepaddle ≈600 MB、pix2tex 含 torch ≈2 GB）首次安装可能耗时数分钟到十几分钟；若被 540 s 超时中断，重跑 `--yes` 即可续装（pip 幂等/可续传），也可直接在当前终端手动 `pip install ... -i 镜像`。

## 1. 格式识别与转换路由

| 格式 | 处理 |
|---|---|
| `.txt` / `.md` | 直接读取，保留原样 |
| `.docx` | `scripts/convert.py`（python-docx 抽段落） |
| `.epub` / `.html/.htm` | `scripts/convert.py`（解包 / 解析文本） |
| `.pdf`（有文本层） | `scripts/convert.py`（PyMuPDF 抽文本） |
| `.pdf`（扫描） | `convert.py --render-scanned` 渲染成页图 → `ocr.py` 逐页 OCR |
| `.png/.jpg/.jpeg/.webp` | 模型读图（可选优化）或 `scripts/ocr.py` |

- **支持格式**：`.txt / .md / .docx / .epub / .html / .htm / .pdf`（文本层或扫描）与图片 `.png / .jpg / .jpeg / .webp`。**不支持** `.doc / .mobi / .azw3 / .djvu`：`.doc` 请另存为 `.docx`，`.mobi / .azw3 / .djvu` 请先转为 `.epub` 或 `.pdf`。
- 判断 PDF 是否有文本层：`convert.py` 抽文本，若几乎为空且页面含图片 → 判为扫描件。
- **扫描 PDF 的主链路**（PDF → 图片这一步由 `convert.py --render-scanned` 完成，本 Skill 内部可闭环）：

```
扫描 PDF → $SKILL_ROOT/scripts/convert.py --render-scanned（PyMuPDF page.get_pixmap(dpi=200)）
        → <out>/pages/<文档名>-page-###.png
        → $SKILL_ROOT/scripts/ocr.py <页图1> <页图2> ... --out <out>/md --name <文档名>
        → <out>/md/<文档名>.md
```

- 单张图片按文件逐个 OCR。
- **渲染断点**：`convert.py --render-scanned` 重跑时，若 `pages/` 下已存在该扫描件的完整页图，会跳过渲染（`--force` 可强制重渲染），避免上千页重复渲染。
- **页图体积与清理**：页图约 1–2 MB/页（200 dpi），600 页 ≈ 1 GB。`ocr.py` 合并成 md 后**默认保留**输入页图，确需释放磁盘加 `--rm-pages` 显式删除；`--rm-pages` **仅删除** `pages/<文档名>-page-###.png` 渲染中间页图（不校验成该模式的原始图片即使带该 flag 也跳过、不删除）；`pages/` 也可随时用 `--render-scanned` 重新生成。

## 2. OCR（识别文字）

识别图片 / 扫描页里的文字。**模型读图是可选项**：先 `Read` 取图片路径、再 `ViewImage` 读图（能力由用户配置的模型决定，需支持图片输入）。本地 `scripts/ocr.py`（PaddleOCR）作为**批量 / 离线兜底，是可预期路径（不是异常路径）**，两者都要能独立跑通。

| 场景 | 处理 |
|---|---|
| 单页 / 少量图片 / 学习中临时指认 | 模型读图（`Read` + `ViewImage`）直接转写 |
| 整本书扫描件批量建库 | `convert.py --render-scanned` 渲染 → `scripts/ocr.py` 逐页识别 |
| 模型不支持图片输入（纯文本模型） | 回退本地 `scripts/ocr.py` |

- 本地 OCR 缺依赖时**先提示、加 `--yes` 才安装**（`pip install "paddleocr>=2.7" "paddlepaddle>=2.6" -i https://mirrors.aliyun.com/pypi/simple`）；脚本兼容 PaddleOCR 2.x 与 3.x 两套 API（自动探测版本）。
- 中英混合；识别结果按「页 / 行」顺序保留。
- 无论模型读图还是本地 OCR，不确定的字、数字、专有名词一律标 `[待核]`，不硬猜（模型 OCR 尤其要防止「顺手润色 / 臆造」）。
- 本地安装失败 → 降级：模型读图（`Read` + `ViewImage`）逐页识别，或请用户提供可复制文本。

## 3. 公式（转 LaTeX）

公式图片**模型读图是可选项**：先 `Read` 取路径、再 `ViewImage` 读图转 LaTeX（视觉模型对数学公式的语义理解通常优于专用 OCR）。本地 `scripts/latex_ocr.py`（**基于 pip 包 pix2tex**）作为**离线 / 批量兜底**。

| 来源 | 处理 |
|---|---|
| 用户上传的公式图片 | 模型读图（`Read` + `ViewImage`）直接转 LaTeX |
| docx 内嵌图片（公式 / 插图） | `convert.py` 自动抽到 `assets/` 后，模型读图或喂 `latex_ocr.py` |
| 扫描页里的公式 | 模型读图直接转；或裁剪公式区域后喂 `latex_ocr.py` |
| 模型不支持图片输入 | 回退 `scripts/latex_ocr.py` |

- 公式统一 `$...$`（行内）/ `$$...$$`（独立行）。
- 公式识别失败 → 标 `[公式待核]`，交由模型校对环节补写或请用户确认，不硬猜。
- 本地 `latex_ocr.py` 缺依赖（即 pix2tex 包）时**先提示、加 `--yes` 才安装**（`pip install "pix2tex>=0.1.2" -i https://mirrors.aliyun.com/pypi/simple`）；安装失败 → 标 `[公式待核]`，模型凭上下文补，仍不确定请用户提供公式。

## 4. 模型校对（每个 Markdown）

转换 / OCR 后，每个 `md` 用模型校对一遍：

- 修正：错别字、漏字、多字、段落错乱、公式符号、数字 / 单位。
- 不改变原意、不增删内容；修正处不保留「原文 vs 修正」痕迹，直接给最终版。
- 拿不准处标 `[待核]`，不硬改。

## 5. 知识索引（index.md）

对所有 `md` 提炼「文档 → 章 → 节 → 知识点」四级索引，存 `index.md`：

```
# <领域> 知识索引

## <文档名>
### 第 1 章 <标题>
1. <知识点1>
2. <知识点2>
```

- 知识点 = 学习的最小单元（一个概念 / 一个定理 / 一个方法）。
- 顺序 = 文档顺序 × 章顺序 × 节顺序 × 知识点顺序（即学习顺序）。
- 每行知识点可附来源（文档名 + 章节），供提问 / 讲解引用。

### 批量建库与断点（--dir + manifest.json）

目录规模大时用 `$SKILL_ROOT/scripts/convert.py --dir <目录> --recursive --out <out>`：递归处理所有文档，并在 `<out>/manifest.json` 记一份「源文件 → md 路径 → 状态（done / skipped / failed）」清单。重跑时按 manifest 跳过已 done 的项，实现断点续建；scanned 项标记 `skipped`（需走 §1 的渲染 → OCR 链路），failed 项可重跑。

- **开工前依赖预检**：按目录内实际扩展名探测依赖（`importlib.util.find_spec`，不 import），缺哪个一次性汇总提示（如「本批含 N 个 docx，需安装 python-docx（约 5 MB）」），加 `--yes` 才开工，避免半途中止。
- **manifest 增量落盘**：每处理完一个文件即重写 manifest，超时 / 崩溃后可从任意断点续跑；重跑时本轮新处理项计 `done`，从 manifest 恢复的已完成项单独计 `resumed`，两者分开统计。

**同名冲突处理**：Markdown 按「相对子目录层级」落盘——`md/<相对路径去掉扩展名>.md`（如 `a/第一章.pdf → md/a/第一章.md`、`b/第一章.pdf → md/b/第一章.md`），不同目录的同名文件不再互相覆盖。若去除扩展名后仍重名（如同目录下 `foo.txt` 与 `foo.docx` 都产出 `foo.md`），则在文件名后追加 `-2`、`-3` 后缀去重，并在 manifest 里记录实际 md 路径，绝不静默丢弃。

## 6. 降级策略

> 三个脚本（convert.py / ocr.py / latex_ocr.py）在依赖安装失败时以非零退出、**不自行降级**；执行者需捕获脚本报错后，按本表降级。

| 情况 | 行为 |
|---|---|
| 依赖缺失 | 脚本打印「需要安装 X（约 N MB）」并退出；回复「装」后加 `--yes` 重跑 |
| paddleocr / pix2tex 包安装失败 | 明说「自动安装失败」，请用户手动 `pip install ... -i 镜像` 或提供文本 |
| 某文档无法转换 | 跳过并明说「<文件名> 未能处理」，不静默丢弃 |
| 公式识别失败 | 标 `[公式待核]`，不硬猜 |
| 文档无任何文字（纯图且 OCR 失败） | 明说无法提取，请用户换格式 |

## 7. 存储位置

- Markdown 统一存 `<workspace>/.socratic-tutor/<领域>/md/<文档名>.md`。
- 索引存 `<workspace>/.socratic-tutor/<领域>/index.md`。
- 批量清单存 `<workspace>/.socratic-tutor/<领域>/manifest.json`；扫描页渲染图存 `<领域>/pages/`。
- docx 内嵌图落 `md/assets/`，与 `md` 同级（`md/assets/` 与 `md/*.md` 保持同级引用，图片链接用相对路径 `assets/<图>`）。
- 不写 Skill 包内目录，不写系统临时目录作长期存储。
