# purpose: CLI 入口 —— any2pdf 文件1 文件2 ... 批量转 PDF
# 创建时间: 2026-06-29 14:56:01
# 更新时间: 2026-06-29 14:56:01
# 时区: Asia/Shanghai
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, convert, supported_extensions
from .engines import ConversionError, EngineNotFound


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="any2pdf",
        description="把 html / md / doc / docx / ppt / xls / 图片 等一键转成 PDF。",
    )
    p.add_argument("files", nargs="*", help="要转换的源文件(可多个)")
    p.add_argument("-o", "--outdir", help="输出目录(默认与源文件同目录)")
    p.add_argument("--list", action="store_true", help="列出支持的格式")
    p.add_argument("-v", "--version", action="version", version=f"any2pdf {__version__}")
    args = p.parse_args(argv)

    if args.list:
        print("支持的格式:", ", ".join(sorted(supported_extensions())))
        return 0
    if not args.files:
        p.print_help()
        return 1

    outdir = Path(args.outdir).expanduser().resolve() if args.outdir else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

    ok, fail = 0, 0
    for f in args.files:
        src = Path(f)
        out = (outdir / (src.stem + ".pdf")) if outdir else None
        try:
            result = convert(src, out)
            print(f"✅ {src.name} → {result}")
            ok += 1
        except (ConversionError, EngineNotFound, ValueError, FileNotFoundError) as e:
            print(f"❌ {src.name}: {e}", file=sys.stderr)
            fail += 1
    print(f"\n完成:{ok} 成功 / {fail} 失败")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
