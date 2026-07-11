# purpose: Web 服务 —— 拖拽/上传文件 → 转 PDF → 下载(Web 与桌面 GUI 共用)
# 创建时间: 2026-06-29 14:56:01
# 更新时间: 2026-06-29 15:10:00
# 时区: Asia/Shanghai
from __future__ import annotations

import io
import shutil
import sys
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

# 允许 `python server/app.py` 直接跑时也能 import 到 any2pdf 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from any2pdf import convert, supported_extensions  # noqa: E402
from any2pdf.engines import ConversionError, EngineNotFound  # noqa: E402

ROOT = Path(__file__).resolve().parent
JOBS = ROOT.parent / "tmp" / "jobs"
JOBS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="any2pdf")


@app.get("/api/formats")
def formats():
    return {"formats": sorted(supported_extensions())}


@app.post("/api/convert")
async def api_convert(files: list[UploadFile] = File(...)):
    """接收多文件,逐个转 PDF,返回每个文件的结果与下载地址。"""
    job_id = uuid.uuid4().hex
    job_dir = JOBS / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, up in enumerate(files):
        name = Path(up.filename or "file").name  # 去掉任何路径成分
        # 每个文件独立子目录,避免同名(如 报告.docx 与 报告.md)输出互相覆盖
        sub = job_dir / str(i)
        sub.mkdir(exist_ok=True)
        src = sub / name
        try:
            with open(src, "wb") as f:
                shutil.copyfileobj(up.file, f)
            out = src.with_suffix(".pdf")
            convert(src, out)
            results.append({
                "name": name, "ok": True,
                "pdf": out.name, "size": out.stat().st_size,
                "url": f"/api/download/{job_id}/{i}/{out.name}",
            })
        except (ConversionError, EngineNotFound, ValueError, FileNotFoundError) as e:
            results.append({"name": name, "ok": False, "error": str(e)})
        except Exception as e:  # noqa: BLE001 兜底,避免单文件异常拖垮整批
            results.append({"name": name, "ok": False, "error": f"未预期错误: {e}"})
        finally:
            src.unlink(missing_ok=True)  # 删掉源文件,只留 PDF
    ok_count = sum(1 for r in results if r["ok"])
    return JSONResponse({
        "job_id": job_id, "results": results,
        "ok": ok_count, "fail": len(results) - ok_count,
        "zip_url": f"/api/zip/{job_id}" if ok_count > 1 else None,
    })


@app.get("/api/download/{job_id}/{idx}/{filename}")
def download(job_id: str, idx: str, filename: str):
    path = JOBS / job_id / Path(idx).name / Path(filename).name
    if not path.exists():
        return JSONResponse({"error": "文件不存在或已过期"}, status_code=404)
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@app.get("/api/zip/{job_id}")
def download_zip(job_id: str):
    job_dir = JOBS / job_id
    # 按子目录序号收集,保留原名;zip 内重名时追加序号后缀
    pdfs = sorted(job_dir.glob("*/*.pdf"), key=lambda p: int(p.parent.name)) if job_dir.exists() else []
    if not pdfs:
        return JSONResponse({"error": "无可打包文件"}, status_code=404)
    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in pdfs:
            arc = p.name
            if arc in used:
                arc = f"{p.stem}_{p.parent.name}{p.suffix}"
            used.add(arc)
            z.write(p, arc)
    buf.seek(0)
    return Response(
        buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="converted_pdfs.zip"'},
    )


# 静态前端挂在最后(根路径),避免盖住 /api
app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")


def run(host: str = "127.0.0.1", port: int = 8765):
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    run()
