# purpose: 底层转换引擎 —— 按格式分发到 LibreOffice / Chrome / img2pdf
# 创建时间: 2026-06-29 14:56:01
# 更新时间: 2026-06-29 14:56:01
# 时区: Asia/Shanghai
"""每个引擎函数接收源文件路径 + 目标 pdf 路径,渲染并落地 PDF。

设计要点:
- LibreOffice / Chrome 都用独立临时 profile 目录,避免与正在运行的实例或并发调用冲突。
- 两个引擎都可能 exit 0 却没产出文件,统一以"目标文件是否存在且非空"为成功判据(对齐 build≠渲染)。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

# Word 常用 Windows 中文字体名 → macOS 自带等价字体。
# LibreOffice 路径靠 fontmap.conf(fontconfig)解决;Chrome 不认 fontconfig,
# 故对 html/md 在渲染前直接改写 font-family 里的字体名。
_CJK_FONT_MAP = {
    "宋体": "Songti SC", "SimSun": "Songti SC", "NSimSun": "Songti SC", "新宋体": "Songti SC",
    "黑体": "Heiti SC", "SimHei": "Heiti SC",
    "仿宋": "STFangsong", "仿宋_GB2312": "STFangsong", "FangSong": "STFangsong",
    "楷体": "Kaiti SC", "楷体_GB2312": "Kaiti SC", "KaiTi": "Kaiti SC",
    "微软雅黑": "PingFang SC", "Microsoft YaHei": "PingFang SC",
    "等线": "PingFang SC", "DengXian": "PingFang SC",
}
_CJK_NAMES = sorted(_CJK_FONT_MAP, key=len, reverse=True)

# LibreOffice(macOS,homebrew 版)只认中文/显示名,不认 "STFangsong" 这类 PostScript 名,
# 也不认 fontconfig 别名;故 OOXML 路径单独用一套"华文/macOS 中文名"映射(已实测可命中)。
_CJK_FONT_MAP_LO = {
    "宋体": "华文宋体", "SimSun": "华文宋体", "新宋体": "华文宋体", "NSimSun": "华文宋体",
    "仿宋": "华文仿宋", "仿宋_GB2312": "华文仿宋", "FangSong": "华文仿宋",
    "楷体": "华文楷体", "楷体_GB2312": "华文楷体", "KaiTi": "华文楷体",
    "黑体": "黑体-简", "SimHei": "黑体-简",
    "微软雅黑": "苹方-简", "Microsoft YaHei": "苹方-简",
    "等线": "苹方-简", "DengXian": "苹方-简",
}


def _remap_cjk_fonts(html: str) -> str:
    """把 HTML 里 font-family 引用的 Windows 中文字体名替换成 macOS 等价名。"""
    names = "|".join(re.escape(n) for n in _CJK_NAMES)
    # 1) 带引号的字体名(最常见):'宋体' / "SimSun" → "Songti SC"
    html = re.sub(rf'(["\'])({names})\1',
                  lambda m: f"{m.group(1)}{_CJK_FONT_MAP[m.group(2)]}{m.group(1)}", html)

    # 2) font-family 值里未加引号的字体名(只在 font-family 声明内替换,不碰正文)
    def _ff(m):
        val = m.group(2)
        for n in _CJK_NAMES:
            val = re.sub(rf'(^|[,:\s]){re.escape(n)}(?=$|[,;\s])',
                         lambda mm, _n=n: mm.group(1) + _CJK_FONT_MAP[_n], val)
        return m.group(1) + val

    html = re.sub(r'(font-family\s*:)([^;}{<]+)', _ff, html, flags=re.I)
    # 我们统一以 utf-8 写出临时文件,故把声明里的 gbk/gb2312 charset 同步成 utf-8
    html = re.sub(r'charset\s*=\s*["\']?(gb2312|gbk|gb18030)["\']?',
                  "charset=utf-8", html, flags=re.I)
    return html

# Chrome 不带独立 profile 时用临时默认 headless profile,可与用户 GUI Chrome 共存并干净退出;
# 但多个 headless 进程并发会争用同一 profile,故用锁串行化(单次转换 ~2s,串行可接受)。
_CHROME_LOCK = threading.Lock()


# ---- 引擎可执行文件定位 ----------------------------------------------------
def _find_soffice() -> str:
    cand = [
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/opt/homebrew/bin/soffice",
        "/usr/bin/soffice",
    ]
    for c in cand:
        if c and Path(c).exists():
            return c
    raise EngineNotFound("未找到 LibreOffice(soffice)。office 类格式需要它,请安装 LibreOffice。")


def _find_chrome() -> str:
    cand = [
        os.environ.get("ANY2PDF_CHROME"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chrome"),
    ]
    for c in cand:
        if c and Path(c).exists():
            return c
    raise EngineNotFound("未找到 Chrome/Chromium。html/md 渲染需要它,请安装 Google Chrome。")


_FONTMAP = Path(__file__).parent / "fontmap.conf"


def _lo_env() -> dict:
    """给 LibreOffice 注入字体映射:把 Word 的 Windows 字体名(宋体/SimSun/黑体/仿宋…)
    映射到 macOS 自带等价字体,避免"宋体被替成无衬线"等乱替。"""
    env = os.environ.copy()
    if _FONTMAP.exists():
        env["FONTCONFIG_FILE"] = str(_FONTMAP)
    return env


class EngineNotFound(RuntimeError):
    pass


class ConversionError(RuntimeError):
    pass


def _ensure_output(out_pdf: Path, log: str = "") -> Path:
    """统一成功判据:文件存在且非空。否则抛错并带上引擎日志。"""
    if not out_pdf.exists() or out_pdf.stat().st_size == 0:
        raise ConversionError(f"转换未产出有效 PDF: {out_pdf.name}\n引擎输出:\n{log[-2000:]}")
    return out_pdf


# OOXML(zip 包)字体名改写:对 docx/xlsx/pptx 直接把 XML 里的 Windows 字体名换成 macOS 等价名。
# 比依赖 LibreOffice/fontconfig 的字体替换更确定(homebrew 版 LibreOffice 不完全认 fontconfig)。
_OOXML_EXT = {".docx", ".xlsx", ".pptx"}
import zipfile  # noqa: E402


def _remap_ooxml_fonts(src: Path) -> Path | None:
    """把 OOXML 里引用的 Windows 中文字体名改写成 macOS 等价名,返回改写后的临时文件;
    若无需改写(没命中任何字体名)返回 None。"""
    try:
        with zipfile.ZipFile(src) as zin:
            names = zin.namelist()
            parts = {n: zin.read(n) for n in names}
    except (zipfile.BadZipFile, OSError):
        return None  # 不是合法 zip(理论上不会),交给 LibreOffice 原样处理

    changed = False
    for n, data in parts.items():
        if not n.endswith(".xml"):
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        new = text
        for win, mac in _CJK_FONT_MAP_LO.items():
            # 字体名在 OOXML 里总是带双引号出现(w:eastAsia="宋体" / w:name="宋体" / typeface="宋体"),
            # 正文文字在 <w:t> 里不带引号,故按带引号精确替换不会误伤正文。
            new = new.replace(f'"{win}"', f'"{mac}"')
        if new != text:
            parts[n] = new.encode("utf-8")
            changed = True

    if not changed:
        return None
    tmp = Path(tempfile.gettempdir()) / f"any2pdf_ox_{uuid.uuid4().hex}{src.suffix}"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in names:
            zout.writestr(n, parts[n])
    return tmp


# ---- LibreOffice:office 全家桶 --------------------------------------------
def libreoffice_to_pdf(src: Path, out_pdf: Path) -> Path:
    """doc/docx/ppt/pptx/xls/xlsx/odt/ods/odp/rtf/txt/csv → PDF。"""
    soffice = _find_soffice()
    remapped = _remap_ooxml_fonts(src) if src.suffix.lower() in _OOXML_EXT else None
    conv_src = remapped or src
    try:
        return _libreoffice_convert(soffice, conv_src, out_pdf)
    finally:
        if remapped:
            remapped.unlink(missing_ok=True)


def _libreoffice_convert(soffice: str, conv_src: Path, out_pdf: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="any2pdf_lo_") as tmp:
        profile = f"file://{tmp}/profile"
        outdir = Path(tmp) / "out"
        outdir.mkdir()
        cmd = [
            soffice, "--headless", "--norestore", "--nologo",
            f"-env:UserInstallation={profile}",
            "--convert-to", "pdf", "--outdir", str(outdir), str(conv_src),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                              env=_lo_env())
        # LibreOffice 把输出命名为 <输入名>.pdf 放进 outdir
        produced = outdir / (conv_src.stem + ".pdf")
        log = proc.stdout + proc.stderr
        if not produced.exists():
            # 个别 filter 下命名可能不同,兜底取 outdir 里唯一的 pdf
            pdfs = list(outdir.glob("*.pdf"))
            if pdfs:
                produced = pdfs[0]
        if produced.exists():
            out_pdf.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(produced), str(out_pdf))
        return _ensure_output(out_pdf, log)


# ---- Chrome:HTML 渲染(html 直转 / md 先转 html) -------------------------
def chrome_html_to_pdf(html_path: Path, out_pdf: Path) -> Path:
    chrome = _find_chrome()
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        chrome, "--headless", "--disable-gpu",
        "--no-first-run", "--no-default-browser-check",
        "--no-pdf-header-footer",
        "--virtual-time-budget=10000",  # 等待远程图片/CSS 加载,虚拟时间到点即出
        f"--print-to-pdf={out_pdf}",
        html_path.as_uri(),
    ]
    with _CHROME_LOCK:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return _ensure_output(out_pdf, proc.stdout + proc.stderr)


def html_to_pdf(src: Path, out_pdf: Path) -> Path:
    raw = src.read_bytes()
    text = None
    for enc in ("utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return chrome_html_to_pdf(src, out_pdf)  # 解码不了就原样渲染,不冒损坏内容的险

    text = _remap_cjk_fonts(text)
    # 写在源目录,保证相对路径的图片/CSS 仍可解析
    tmp_html = src.parent / f".any2pdf_{uuid.uuid4().hex}.html"
    try:
        tmp_html.write_text(text, encoding="utf-8")
        return chrome_html_to_pdf(tmp_html, out_pdf)
    finally:
        tmp_html.unlink(missing_ok=True)


# ---- Markdown:md → html(套样式) → Chrome --------------------------------
_MD_CSS = """
body{font-family:-apple-system,'PingFang SC','Helvetica Neue',Arial,sans-serif;
  line-height:1.7;color:#24292f;max-width:820px;margin:40px auto;padding:0 24px;font-size:15px}
h1,h2,h3,h4{font-weight:600;line-height:1.3;margin-top:1.6em;margin-bottom:.6em}
h1{font-size:2em;border-bottom:1px solid #eaecef;padding-bottom:.3em}
h2{font-size:1.5em;border-bottom:1px solid #eaecef;padding-bottom:.3em}
code{background:#f6f8fa;padding:.2em .4em;border-radius:4px;font-size:85%;
  font-family:'SF Mono',Menlo,Consolas,monospace}
pre{background:#f6f8fa;padding:16px;border-radius:6px;overflow:auto;line-height:1.45}
pre code{background:none;padding:0}
blockquote{margin:0;padding:0 1em;color:#57606a;border-left:.25em solid #d0d7de}
table{border-collapse:collapse;width:100%;margin:1em 0}
th,td{border:1px solid #d0d7de;padding:6px 13px}
th{background:#f6f8fa}
img{max-width:100%}
a{color:#0969da;text-decoration:none}
@page{margin:1.5cm}
"""


def markdown_to_pdf(src: Path, out_pdf: Path) -> Path:
    import markdown  # 延迟导入,缺依赖时报错更清晰

    text = src.read_text(encoding="utf-8", errors="replace")
    html_body = markdown.markdown(
        text,
        extensions=["extra", "tables", "fenced_code", "sane_lists", "toc"],
    )
    full = (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{_MD_CSS}</style></head><body>{html_body}</body></html>"
    )
    full = _remap_cjk_fonts(full)  # md 里若内嵌了指定中文字体的 html,也一并修正
    # 写在源文件同目录(而非系统临时目录),保证 md 里相对路径的图片能被 Chrome 解析
    tmp_html = src.parent / f".any2pdf_{uuid.uuid4().hex}.html"
    try:
        tmp_html.write_text(full, encoding="utf-8")
        return chrome_html_to_pdf(tmp_html, out_pdf)
    finally:
        tmp_html.unlink(missing_ok=True)


# ---- 图片:img2pdf 无损嵌入 -----------------------------------------------
def image_to_pdf(src: Path, out_pdf: Path) -> Path:
    import img2pdf

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(out_pdf, "wb") as f:
            f.write(img2pdf.convert(str(src)))
    except Exception as e:
        # webp / 部分 tiff 需 Pillow 先转 RGB
        try:
            from PIL import Image

            with Image.open(src) as im:
                rgb = im.convert("RGB")
                rgb.save(out_pdf, "PDF", resolution=100.0)
        except Exception:
            raise ConversionError(f"图片转 PDF 失败: {src.name} ({e})")
    return _ensure_output(out_pdf)
