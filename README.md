<!-- purpose: any2pdf 项目说明 —— 各种文档一键转 PDF(CLI + Web + 桌面 GUI) -->
- 创建时间: 2026-06-29 15:14:00
- 更新时间: 2026-06-29 17:36:23
- 时区: Asia/Shanghai

# 一键转 PDF (any2pdf)

把 **Word / Excel / PPT / HTML / Markdown / 图片** 等各种文档一键转成 PDF。
三种用法共享同一个转换内核:命令行、Web 上传、桌面拖拽小窗。

---

## 🚀 快速启动(日常就看这一段)

在**访达(Finder)**里进入本项目文件夹,**双击**下面任一文件即可:

| 双击这个 | 打开什么 | 怎么用 | 怎么停 |
|---|---|---|---|
| **`run-desktop.command`** | 一个桌面小窗 | 把文件拖进窗口 → 自动转好 | 关掉窗口 |
| **`run-web.command`** | 浏览器打开 `localhost:8765` | 把文件拖进网页 → 点下载 | 关掉那个黑色终端窗口 |

> 两个都行,**推荐 `run-desktop.command`**(更省事,不占端口)。每次双击都是全新启动、自动用最新代码 —— 不用担心"改了没生效"。
>
> 首次双击若提示「无法打开,因为来自身份不明的开发者」:在该文件上**右键 → 打开 → 再点打开**,之后就能直接双击了。

**命令行党**(可选):`conda activate any2pdf && any2pdf 文件1 文件2 …` 就地批量转。

---

## 原理:转 PDF = "先渲染,再打印"

没有单个引擎能吃所有格式,所以本工具是个**按扩展名分发的路由器**:

| 源格式 | 引擎 | 说明 |
|---|---|---|
| doc/docx/ppt/pptx/xls/xlsx/odt/ods/odp/rtf/txt/csv | **LibreOffice**(无头) | Office 全家桶,版式保真最高 |
| html/htm | **Chrome**(无头 `--print-to-pdf`) | 浏览器渲染,CSS 保真最高 |
| md/markdown | Markdown → HTML(套样式)→ Chrome | GitHub 风样式 |
| png/jpg/jpeg/gif/bmp/tif/tiff/webp/heic | **img2pdf**(Pillow 兜底) | 无损嵌入 |

## 依赖

**系统(需自行安装):**
- [LibreOffice](https://www.libreoffice.org/)(office 类格式)
- [Google Chrome](https://www.google.com/chrome/)(html/md)

**Python:** 见 `requirements.txt`,已建在 conda 环境 `any2pdf`。

```bash
conda create -y -n any2pdf python=3.12
conda activate any2pdf
pip install -e .          # 同时把 any2pdf 命令装进 PATH
```

## 三种用法

### 1. 命令行(CLI)
```bash
conda activate any2pdf
any2pdf 报告.docx 表格.xlsx 笔记.md          # 各自就地生成同名 .pdf
any2pdf -o ~/输出目录 *.html                  # 指定输出目录
any2pdf --list                               # 看支持的格式
```

### 2. Web 上传服务
```bash
./run-web.command        # 或:python server/app.py
```
浏览器打开 <http://127.0.0.1:8765>,把文件拖进去,逐个下载或打包 zip。
适合跨机访问 / 分享给别人用(改 `server/app.py` 里 `host="0.0.0.0"` 即可局域网访问)。

### 3. 桌面拖拽小窗
```bash
./run-desktop.command    # 或:python desktop/app.py
```
弹出原生小窗,把文件拖进去即转。内部就是把上面的 Web 界面用 WebView 包成桌面应用,
**和 Web 版同一套界面、同一个内核**。

> macOS 双击运行:`run-web.command` / `run-desktop.command` 可在访达里直接双击。

## 目录结构
```
any2pdf/        转换内核(可独立 import / 装成 CLI)
  core.py       扩展名 → 引擎 路由
  engines.py    LibreOffice / Chrome / img2pdf 三引擎
  cli.py        命令行入口
server/         FastAPI Web 服务 + 拖拽前端(static/)
desktop/        pywebview 桌面小窗(复用 server)
tests/samples/  各格式样例
```

## 中文字体处理(宋体/仿宋不再变形)

Word/HTML 常指定 **宋体 / SimSun / 黑体 / 仿宋 / 仿宋_GB2312 / 楷体 / 微软雅黑** 等 Windows 字体,
macOS 没有它们,转换器会乱替 —— 实测见过宋体被替成无衬线黑体、**仿宋_GB2312 被替成卡通手写体
(华康娃娃体)**。本工具在转换前把这些字体名改写成 macOS 自带等价字体。两条路径各用一招(因为
LibreOffice 和 Chrome 认的字体名不一样,**用了两套映射表**):

| 路径 | 机制 | 映射目标 |
|---|---|---|
| **Office docx/xlsx/pptx**(LibreOffice) | 解压 OOXML、改写 XML 里的字体名、重新打包再转 | **中文名**:宋体→华文宋体、仿宋(_GB2312)→华文仿宋、楷体→华文楷体、黑体→黑体-简、雅黑/等线→苹方-简 |
| **HTML / MD**(Chrome) | 渲染前改写 `font-family` 里的字体名 | 宋体→Songti SC、仿宋→STFangsong、黑体→Heiti SC、楷体→Kaiti SC、雅黑→PingFang SC |

> 关键坑:homebrew 版 LibreOffice **只认中文/显示名**(华文仿宋),不认 `STFangsong` 这类
> PostScript 名,也不认 fontconfig 别名;Chrome 则认 `Songti SC` 这类名、但对 `宋体` 有内建
> 处理压不过 @font-face —— 所以两边都改成"直接写对方认识的字体名",而非靠字体替换机制。

改映射规则:编辑 `engines.py` 的 `_CJK_FONT_MAP_LO`(LibreOffice 路径)和 `_CJK_FONT_MAP`
(Chrome 路径)。要 100% 还原 Word 原貌,把真的 SimSun / 仿宋_GB2312 等字体装进
`~/Library/Fonts/`(此时这些字体存在,LibreOffice/Chrome 会直接用,改写命中的是同名 macOS 字体)。
(`any2pdf/fontmap.conf` 是给 .doc 旧二进制 / .odt 等非 OOXML 格式的 fontconfig 兜底。)

## 已知边界
- LibreOffice / Chrome 首次冷启动略慢(~1-2s/文件)。
- Chrome 转换在进程内串行(避免与正在运行的 GUI Chrome 争用 profile),批量大时按队列处理。
- 远程图片/外链 CSS 的 HTML 给 10s 加载预算,超大页面可在 `engines.py` 调 `--virtual-time-budget`。
- HTML 按 utf-8 / gb18030 解码后做字体名改写;若两者都解不了,则原样渲染(不做字体修正、但不损坏内容)。
