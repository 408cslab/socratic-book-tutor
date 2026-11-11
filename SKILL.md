---
name: socratic-book-tutor
display_name: 榨书成师
display_name_en: Distill Books into Wisdom
description: "把你手里的一批电子书（PDF/扫描件/图片/Word/EPUB 等）榨成一位「只问不答、追问到底」的苏格拉底老师：先自动建库（转 Markdown、扫描件 OCR、公式转 LaTeX、校对），再从零开始逐知识点用「问→答→诘问→自省→讲→再问」循环教你——答对才前进、答错讲透再问，进度记忆支持断点续学，讲解提问严格照书。当用户要上传图书、指定书目目录、或开始问答式学习某个领域时使用；即使用户只说「帮我把这几本书读进去」「考考我这本书的内容」，或提到「用书里的知识出题教我」，也优先考虑本 skill。"
description_zh: "图书驱动的苏格拉底式学习：多格式图书 OCR / 转 Markdown / 公式转 LaTeX / 校对，按知识点循环提问-诘问-讲解，进度记忆支持中断续学。不用于与书籍无关的通用格式转换/发票票据识别；不用于代替教材系统讲授（无书源时仅作补充讲解）；不处理无权使用的书源。"
description_en: "Not for generic file conversion/OCR, textbook-style teaching without a book, or sources you lack rights to use. Turn books into a tutor: converts ebooks (PDF/scans/Word/EPUB) into a knowledge base, then teaches via Socratic Q&A with resume support."
allowed-tools: Read, ViewImage, Write, Glob, Grep, Bash
examples_zh:
  - "把 /books/机器学习 里的书整理成知识库，然后开始教我"
  - "这几本扫描版 PDF 帮我识别成文字，公式转成 LaTeX"
  - "从零开始教我线性代数"
examples_en:
  - "Turn the books in /books/machine-learning into a knowledge base, then teach me."
  - "OCR these scanned PDFs and convert formulas to LaTeX."
  - "Teach me linear algebra from scratch."
version: 1.0.1
author: "1024dev"
---

# 榨书成师（Distill Books into Wisdom）Skill

## 总览

本 Skill 是**通用框架**：用户提供某个细分领域的一批电子书（上传文件或指定本地目录），Skill 把它们转成一个可学习的知识库，再用「问 → 答 → 诘问 → 自省 → 讲、问 → 答…」的苏格拉底式循环，带用户从该领域的**小白知识**开始、逐知识点学习，直到全部学完。

- **两条阶段**：① 建库（图书 → Markdown 知识库）；② 学习（苏格拉底式问答循环）。
- **内容依据（红线）**：讲解**严格照书**；提问**优先照书，书里没有现成题目时允许基于书的内容现出题**。书籍内容完全没有覆盖的点，才用模型生成，并显式标注「书籍未涉及，以下为补充」。
- **OCR / 公式**：模型读图（`Read` + `ViewImage`）是可选优化，本地 `ocr.py` / `latex_ocr.py` 是兜底，两条路径都要能独立跑通；路由、依赖与降级见 @references/kb-building-rules.md §1–§3。
- **存储**：转换后的 Markdown、知识索引、学习进度，统一存用户工作区 `<workspace>/.socratic-tutor/<领域>/`（`<workspace>` 的三级解析见 @references/memory-rules.md §4），不写进 Skill 包。

## 两条阶段

| 阶段 | 触发 | 产出 |
|---|---|---|
| **① 建库** | 用户上传电子档 / 指定目录，说「建库 / 整理成知识库 / 处理这些书」 | `<workspace>/.socratic-tutor/<领域>/md/*.md` + `index.md` |
| **② 学习** | 用户说「开始学 / 教我 / 继续上次」 | 逐知识点苏格拉底式问答，更新 `progress.md` |

> 阶段一/二 的意图识别（含「建库然后教我」这类复合请求）见 @references/routing-rules.md §1。

## 阶段①：建库（执行步骤）

1. 输入侧校验与告知（先做）：确认用户对该书源有合法使用权，**拒绝处理盗版 / 无权使用的书源**；扫描件 / 图片内容会发送给模型做 OCR 或公式识别，处理前一句话告知并征得同意。随后定位领域名与目录：用户指定目录则递归列出该目录**所有**文档（去重、按文件名排序）；上传文件则逐个处理。（红线细节见 @references/compliance-rules.md §0）
2. 逐个文档按 @references/kb-building-rules.md §1–§3 转换（格式路由、OCR、公式转 LaTeX 以该文件为单一信息源）。
3. 每个 Markdown 用模型校对：修正错别字、漏字、段落错乱、公式符号、数字；不确定处标 `[待核]`。
4. 存 `<workspace>/.socratic-tutor/<领域>/md/`。
5. 提炼「文档 → 章 → 节 → 知识点」四级索引，存 `<workspace>/.socratic-tutor/<领域>/index.md`（见 @references/kb-building-rules.md §5）。

## 阶段②：学习（执行步骤）

1. 读 `<workspace>/.socratic-tutor/<领域>/progress.md`：无 → 从 `index.md` 第一个知识点开始；有 → 从上次位置继续。
2. 检索该知识点的书籍原文（`md/` 中对应章节）。
3. **提问**：按 @references/socratic-rules.md 出题，先不给答案；提问依据书（书无现成题则基于书的内容现出）。
4. **诘问**：学习者回答后，先不判分、不给答案，按六类提问追问其理由 / 假设 / 反例 / 后果，引导自省（见 @references/socratic-rules.md §3）；记忆性 / 事实性知识点跳过诘问，直接进评价。
5. **评价**：诘问引导不出时，判「对 / 部分对 / 错 / 不会」，给依据（引书籍哪章哪节原文）。
6. **讲解**：结合书籍原文讲解 + 易错点（严格照书，定义用书中原文）。
7. **递进**：答对 → 下一知识点；答错 / 不会 → 讲解后**同一知识点换角度再问**，直到掌握。
8. 每步更新 `progress.md` 的当前知识点位置。
9. 全部学完 → 总结 + 建议复习薄弱点（见 @references/memory-rules.md）。

## 红线

- **严格依据书籍（贯穿所有环节）**：讲解照书；提问照书 / 基于书现出；**诘问、评价、递进中凡涉及知识点定义 / 结论，一律用书中原文**；书籍没有才模型生成，并标注「书籍未涉及，以下为补充」。
- **版权边界**：只做学习性引用，**不整本复述**；引用标注来源（书名 + 章 + 节）。
- **输入侧红线**：只处理用户有权使用的合法书源，**拒绝盗版 / 无权使用的书源**；转换产物（Markdown / 索引）**不分发给第三方、不上传外发**，仅作内部学习依据。
- **公式**：一律 LaTeX，识别失败标 `[公式待核]`，不硬猜。
- **语气**：鼓励、可执行；评价先肯定对的，再温和指出错点（见 @references/compliance-rules.md）。

## 脚本调用

**先求 Skill 根目录 `SKILL_ROOT`**（= 含本 `SKILL.md` 的那一级目录；技能加载时通常会给出技能目录，直接赋值即可，未给出时才用下面第一行的 `find` 探测一次）。此后一律 `python3 "$SKILL_ROOT/scripts/..."`，与 Bash 的 cwd 无关；**仅当 cwd 已在技能根目录内时**，才可用简写 `python3 scripts/...`：

```bash
SKILL_ROOT="$(cd "$(dirname "$(find . -maxdepth 3 -name SKILL.md | head -1)")" && pwd)"   # 技能目录未给出时才探测
WS="${WORKSPACE:-$PWD}"
python3 "$SKILL_ROOT/scripts/convert.py" "输入.pdf" --out "$WS/.socratic-tutor/机器学习/md"
python3 "$SKILL_ROOT/scripts/convert.py" "扫描书.pdf" --render-scanned --out "$WS/.socratic-tutor/机器学习"   # 扫描件先渲染成页图
python3 "$SKILL_ROOT/scripts/ocr.py" "页图-001.png" "页图-002.png" --out "$WS/.socratic-tutor/机器学习/md" --name 扫描书  # 逐页 OCR 合并
python3 "$SKILL_ROOT/scripts/latex_ocr.py" "公式.png"     # 离线公式转 LaTeX（兜底）
```

- `SKILL_ROOT` 是技能包目录（含 `SKILL.md` 那一级），脚本统一在 `$SKILL_ROOT/scripts/`；存在多个技能的工作区里 `find` 可能命中别的技能，因此能用平台给出的目录就不要用 `find`。
- 路径含空格 / 中文请加双引号；`$WORKSPACE` 取不到时回退 `$PWD`（三级解析见 @references/memory-rules.md §4）。
- 自动安装统一用阿里云镜像：`pip install <包> -i https://mirrors.aliyun.com/pypi/simple`。缺包时脚本先打印「需要安装 X（约 N MB）」并退出，**加 `--yes` 才会真正安装**（见 @references/kb-building-rules.md §6）。
- 安装 / OCR / 公式失败 → 如实说明并降级（见 @references/kb-building-rules.md §6）。

## 文件结构

```
socratic-book-tutor/
├─ SKILL.md
├─ LICENSE
├─ CHANGELOG.md                 ← 版本记录（打包时不进 zip）
├─ icon.png                     ← 512×512 图标（走表单上传，不进 zip）
├─ references/
│  ├─ routing-rules.md          ← 阶段一/二 路由与意图识别
│  ├─ kb-building-rules.md      ← OCR / 公式转 LaTeX / 转换 / 校对 / 索引
│  ├─ socratic-rules.md         ← 提问 / 诘问 / 评价 / 讲解 / 递进 / 续学（内容依据红线）
│  ├─ memory-rules.md           ← 进度记忆（workspace 路径 + 续学）
│  └─ compliance-rules.md       ← 版权边界 + 内容依据红线
├─ scripts/
│  ├─ convert.py                ← 多格式 → Markdown
│  ├─ ocr.py                    ← PaddleOCR（批量/兜底 OCR，缺依赖需 --yes 安装，镜像源）
│  └─ latex_ocr.py              ← 公式 → LaTeX（离线兜底，缺依赖需 --yes 安装，镜像源）
├─ templates/
│  └─ question-templates.md     ← 提问 / 评价 / 讲解 句式
└─ tests/                       ← 回归样本（打包时不进 zip）
   ├─ README.md
   └─ samples/
      ├─ text.pdf               ← 文本层 PDF 样本
      ├─ scanned.pdf            ← 扫描件样本
      ├─ formula.png            ← 公式图样本
      ├─ table.html             ← HTML 表格样本
      ├─ sample.docx            ← DOCX 样本
      └─ book.epub              ← EPUB 样本
```

> 运行数据（转换后的 md、index.md、progress.md）**不在 Skill 包内**，统一在 `<workspace>/.socratic-tutor/<领域>/`。打包提交时排除 `CHANGELOG.md`、`tests/`、`scripts/__pycache__/`、`.DS_Store`；`icon.png` 走表单上传、不进 zip。
