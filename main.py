import io
import json
import os
import sys
import uuid
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from engine import build_mapping, build_report, compare, read_actual, read_ideal

_PORT = 7373
_HOST = "127.0.0.1"

# Holds the last generated file bytes keyed by token — single-user desktop app
_pending: dict[str, tuple[bytes, str]] = {}  # token -> (data, suggested_filename)


def _static_dir() -> str:
    base = (
        sys._MEIPASS
        if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.abspath(__file__))
    )
    return os.path.join(base, "static")


def _ideals_dir() -> str:
    if getattr(sys, "frozen", False):
        user_path = os.path.join(os.path.dirname(sys.executable), "ideals")
        if not os.path.exists(user_path):
            import shutil

            shutil.copytree(os.path.join(sys._MEIPASS, "ideals"), user_path)
        return user_path
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "ideals")


def _load_checks() -> dict:
    with open(os.path.join(_ideals_dir(), "checks.json")) as f:
        return json.load(f)


class _DesktopApi:
    """Exposed to JavaScript via window.pywebview.api in frozen (exe) mode."""

    def download_ideal(self, check_id: str) -> dict:
        """Exe mode: show Save As dialog directly for an ideal file — no HTTP round-trip."""
        import subprocess
        import tkinter
        import tkinter.filedialog

        try:
            checks = _load_checks()
            if check_id not in checks:
                return {"error": f"Unknown check: '{check_id}'"}
            check = checks[check_id]
            path = os.path.join(_ideals_dir(), check["file"])
            with open(path, "rb") as f:
                data = f.read()
        except Exception as exc:
            return {"error": f"Could not read file: {exc}"}

        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        try:
            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            save_path = tkinter.filedialog.asksaveasfilename(
                parent=root,
                initialdir=downloads,
                initialfile=check["file"],
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx")],
                title="Save Ideal File",
            )
            root.destroy()
        except Exception as exc:
            return {"error": f"Dialog failed: {exc}"}

        if not save_path:
            return {"cancelled": True}

        if not save_path.lower().endswith(".xlsx"):
            save_path += ".xlsx"

        try:
            with open(save_path, "wb") as fh:
                fh.write(data)
        except Exception as exc:
            return {"error": f"Could not save: {exc}"}

        subprocess.Popen(f'explorer /select,"{save_path}"', shell=True)
        return {"saved_to": save_path, "filename": os.path.basename(save_path)}

    def run_audit(
        self,
        file_b64: str,
        filename: str,
        check_id: str,
        sheet_name: str,
        fuzzy_threshold: int,
    ) -> dict:
        """Exe mode: decode base64 file, run audit pipeline, show Save As dialog."""
        import base64
        import subprocess
        import tkinter
        import tkinter.filedialog

        try:
            actual_bytes = base64.b64decode(file_b64)
            checks = _load_checks()
            if check_id not in checks:
                return {"error": f"Unknown check: '{check_id}'"}
            check = checks[check_id]
            ideal_path = os.path.join(_ideals_dir(), check["file"])
            with open(ideal_path, "rb") as f:
                ideal_bytes = f.read()
            ideal_name = check["name"]
            effective_sheet = (
                sheet_name or check.get("default_sheet") or "INV_ORGANIZATION_PARAMETER"
            )
            actual_df = read_actual(
                io.BytesIO(actual_bytes), sheet_name=effective_sheet
            )
            ideal_df = read_ideal(io.BytesIO(ideal_bytes))
            mapping = build_mapping(
                ideal_df, list(actual_df.columns), fuzzy_threshold=fuzzy_threshold
            )
            cip, gaps, extra = compare(actual_df, mapping)
            excel_bytes = build_report(
                cip,
                gaps,
                extra,
                mapping,
                actual_filename=filename,
                ideal_filename=ideal_name,
                total_bu_rows=len(actual_df),
                fuzzy_threshold=fuzzy_threshold,
            )
        except ValueError as exc:
            return {"error": str(exc)}
        except Exception as exc:
            return {"error": f"Could not process file: {exc}"}

        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        suggested = f"AuditForge_{check_id}_{stamp}.xlsx"
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")

        try:
            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = tkinter.filedialog.asksaveasfilename(
                parent=root,
                initialdir=downloads,
                initialfile=suggested,
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx")],
                title="Save AuditForge Report",
            )
            root.destroy()
        except Exception as exc:
            return {"error": f"Dialog failed: {exc}"}

        if not path:
            return {"cancelled": True}

        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            with open(path, "wb") as fh:
                fh.write(excel_bytes)
        except Exception as exc:
            return {"error": f"Could not save: {exc}"}

        subprocess.Popen(f'explorer /select,"{path}"', shell=True)
        return {"saved_to": path, "filename": os.path.basename(path)}

    def upload_ideal(self, check_id: str, file_b64: str) -> dict:
        """Exe mode: decode base64 file and save it as the ideal file for a check."""
        import base64

        try:
            checks = _load_checks()
            if check_id not in checks:
                return {"error": f"Unknown check: '{check_id}'"}
            check = checks[check_id]
            path = os.path.join(_ideals_dir(), check["file"])
            content = base64.b64decode(file_b64)
            with open(path, "wb") as fh:
                fh.write(content)
            return {"status": "ok", "message": f"Updated '{check['name']}'"}
        except Exception as exc:
            return {"error": str(exc)}

    def save_file(self, token: str) -> dict:
        """Show a native Save As dialog and write the pending file."""
        import subprocess
        import tkinter
        import tkinter.filedialog

        if token not in _pending:
            return {"error": "File not found — run the audit again."}

        data, suggested_name = _pending.pop(token)
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")

        try:
            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = tkinter.filedialog.asksaveasfilename(
                parent=root,
                initialdir=downloads,
                initialfile=suggested_name,
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx")],
                title="Save AuditForge Report",
            )
            root.destroy()
        except Exception as exc:
            return {"error": f"Dialog failed: {exc}"}

        if not path:
            _pending[token] = (data, suggested_name)
            return {"cancelled": True}

        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            with open(path, "wb") as fh:
                fh.write(data)
        except Exception as exc:
            return {"error": f"Could not save: {exc}"}

        subprocess.Popen(f'explorer /select,"{path}"', shell=True)
        return {"saved_to": path, "filename": os.path.basename(path)}


app = FastAPI(title="AuditForge", docs_url="/docs", redoc_url=None)


@app.get("/api/checks")
def list_checks():
    checks = _load_checks()
    return [
        {"id": k, "name": v["name"], "default_sheet": v.get("default_sheet") or ""}
        for k, v in checks.items()
    ]


@app.post("/api/audit")
async def run_audit(
    actual_file: UploadFile = File(...),
    ideal_file: Optional[UploadFile] = File(None),
    check_id: Optional[str] = Query(None),
    sheet_name: Optional[str] = Query(None),
    fuzzy_threshold: int = Query(80, ge=50, le=100),
):
    actual_bytes = await actual_file.read()

    if ideal_file is not None:
        ideal_bytes = await ideal_file.read()
        ideal_name = ideal_file.filename or ""
        effective_sheet = sheet_name or "INV_ORGANIZATION_PARAMETER"
    elif check_id is not None:
        checks = _load_checks()
        if check_id not in checks:
            raise HTTPException(status_code=404, detail=f"Unknown check: '{check_id}'")
        check = checks[check_id]
        ideal_path = os.path.join(_ideals_dir(), check["file"])
        with open(ideal_path, "rb") as f:
            ideal_bytes = f.read()
        ideal_name = check["name"]
        effective_sheet = (
            sheet_name or check.get("default_sheet") or "INV_ORGANIZATION_PARAMETER"
        )
    else:
        raise HTTPException(
            status_code=400, detail="Provide either check_id or ideal_file."
        )

    try:
        actual_df = read_actual(io.BytesIO(actual_bytes), sheet_name=effective_sheet)
        ideal_df = read_ideal(io.BytesIO(ideal_bytes))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {exc}")

    mapping = build_mapping(
        ideal_df, list(actual_df.columns), fuzzy_threshold=fuzzy_threshold
    )
    cip, gaps, extra = compare(actual_df, mapping)
    excel_bytes = build_report(
        cip,
        gaps,
        extra,
        mapping,
        actual_filename=actual_file.filename or "",
        ideal_filename=ideal_name,
        total_bu_rows=len(actual_df),
        fuzzy_threshold=fuzzy_threshold,
    )

    token = uuid.uuid4().hex
    slug = check_id or "report"
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    suggested = f"AuditForge_{slug}_{stamp}.xlsx"
    _pending[token] = (excel_bytes, suggested)
    return {"token": token, "suggested_name": suggested}


@app.get("/api/download/{token}")
def download_by_token(token: str):
    """Dev-mode only: stream pending file bytes to browser."""
    if token not in _pending:
        raise HTTPException(
            status_code=404, detail="File not found — run the operation again."
        )
    data, filename = _pending.pop(token)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/admin/checks/{check_id}/download")
def download_ideal(check_id: str):
    checks = _load_checks()
    if check_id not in checks:
        raise HTTPException(status_code=404, detail=f"Unknown check: '{check_id}'")
    check = checks[check_id]
    path = os.path.join(_ideals_dir(), check["file"])
    with open(path, "rb") as f:
        data = f.read()
    token = uuid.uuid4().hex
    _pending[token] = (data, check["file"])
    return {"token": token, "suggested_name": check["file"]}


@app.post("/api/admin/checks/{check_id}/upload")
async def upload_ideal(check_id: str, file: UploadFile = File(...)):
    checks = _load_checks()
    if check_id not in checks:
        raise HTTPException(status_code=404, detail=f"Unknown check: '{check_id}'")
    check = checks[check_id]
    path = os.path.join(_ideals_dir(), check["file"])
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    return {"status": "ok", "message": f"Updated '{check['name']}'"}


app.mount("/", StaticFiles(directory=_static_dir(), html=True), name="static")


def _wait_for_server(timeout: float = 10.0) -> None:
    import socket
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((_HOST, _PORT), timeout=0.3):
                return
        except OSError:
            time.sleep(0.1)


if __name__ == "__main__":
    import threading

    url = f"http://{_HOST}:{_PORT}"

    if getattr(sys, "frozen", False):
        import webview

        api = _DesktopApi()
        threading.Thread(
            target=lambda: uvicorn.run(app, host=_HOST, port=_PORT, log_level="error"),
            daemon=True,
        ).start()
        _wait_for_server()
        webview.create_window(
            "AuditForge",
            url,
            width=580,
            height=700,
            resizable=True,
            min_size=(480, 580),
            js_api=api,
        )
        webview.start()
    else:
        import webbrowser

        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        print(f"\n  AuditForge -> {url}\n")
        uvicorn.run(app, host=_HOST, port=_PORT, log_level="warning")
