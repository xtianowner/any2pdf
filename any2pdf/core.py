# purpose: 转换路由 —— 按扩展名把文件分发到对应引擎,统一对外 API
# 创建时间: 2026-06-29 14:56:01
# 更新时间: 2026-06-29 14:56:01
# 时区: Asia/Shanghai
from __future__ import annotations

from pathlib import Path

from . import engines

# 扩展名 → 类别。新增格式只改这里。
OFFICE = {"doc", "docx", "ppt", "pptx", "xls", "xlsx",
          "odt", "ods", "odp", "rtf", "txt", "csv", "fodt"}
HTML = {"html", "htm"}
MARKDOWN = {"md", "markdown", "mdown", "mkd"}
IMAGE = {"png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff", "webp", "heic"}

_DISPATCH = [
    (OFFICE, engines.libreoffice_to_pdf),
    (HTML, engines.html_to_pdf),
    (MARKDOWN, engines.markdown_to_pdf),
    (IMAGE, engines.image_to_pdf),
]


def supported_extensions() -> set[str]:
    return OFFICE | HTML | MARKDOWN | IMAGE


def is_supported(path: str | Path) -> bool:
    return _ext(path) in supported_extensions()


def _ext(path: str | Path) -> str:
    return Path(path).suffix.lower().lstrip(".")


def convert(src: str | Path, out_pdf: str | Path | None = None) -> Path:
    """把单个文档转成 PDF。

    out_pdf 省略时,输出到源文件同目录、同名 .pdf。
    返回产出的 PDF 路径;失败抛 engines.ConversionError / EngineNotFound。
    """
    src = Path(src).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"源文件不存在: {src}")
    if src.suffix.lower() == ".pdf":
        raise ValueError(f"已经是 PDF: {src.name}")

    ext = _ext(src)
    out_pdf = Path(out_pdf).expanduser().resolve() if out_pdf else src.with_suffix(".pdf")

    for exts, fn in _DISPATCH:
        if ext in exts:
            return fn(src, out_pdf)
    raise ValueError(f"不支持的格式: .{ext}(支持: {', '.join(sorted(supported_extensions()))})")
