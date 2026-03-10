"""
FreeRADIUS router — manajemen instance FreeRADIUS via radius-manager.sh.

Endpoint:
  GET  /api/v1/radius/instances           — daftar instance aktif
  POST /api/v1/radius/instances           — buat instance baru
  DELETE /api/v1/radius/instances/{name}  — hapus instance
  GET  /api/v1/radius/instances/{name}/status — status instance
  POST /api/v1/radius/instances/{name}/restart — restart instance
"""
import asyncio
import re
import shlex
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from api.auth import require_api_key
from api.config import get_settings

router = APIRouter(dependencies=[Depends(require_api_key)])

# ─────────────────────────────────────────────
# Validasi nama admin (hanya alfanumerik + _)
# ─────────────────────────────────────────────
_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{1,31}$")


def _valid_name(v: str) -> str:
    if not _NAME_RE.match(v):
        raise ValueError(
            "Nama hanya boleh huruf, angka, underscore; "
            "diawali huruf; panjang 2–32 karakter."
        )
    return v


# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────
async def _run_script(args: list[str], timeout: int = 60) -> dict:
    """Panggil radius-manager.sh dengan argumen yang sudah divalidasi."""
    settings = get_settings()
    script = Path(settings.radius_manager_script).resolve()
    if not script.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Script tidak ditemukan: {script}",
        )
    cmd = ["bash", str(script)] + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "command":    shlex.join(cmd),
            "returncode": proc.returncode,
            "stdout":     stdout.decode(errors="replace").strip(),
            "stderr":     stderr.decode(errors="replace").strip(),
            "success":    proc.returncode == 0,
        }
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=f"Script timeout setelah {timeout}s",
        )


def _fr_dir() -> Path:
    return Path(get_settings().freeradius_dir)


# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────
class CreateInstanceRequest(BaseModel):
    admin_username: str = Field(..., description="Nama unik untuk instance (a-z, 0-9, _)")
    description:    Optional[str] = Field(None, max_length=200)

    @field_validator("admin_username")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _valid_name(v)


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────
@router.get("/instances", summary="Daftar instance FreeRADIUS")
async def list_instances():
    """
    Kembalikan daftar instance berdasarkan sites-enabled di direktori FreeRADIUS.
    """
    sites_enabled = _fr_dir() / "sites-enabled"
    if not sites_enabled.exists():
        return {"instances": [], "note": f"{sites_enabled} tidak ditemukan"}

    instances = []
    for entry in sorted(sites_enabled.iterdir()):
        if entry.is_symlink() or entry.is_file():
            name = entry.name
            # Cek apakah ada SQL module untuk instance ini
            sql_module = _fr_dir() / "mods-enabled" / f"sql_{name}"
            instances.append({
                "name":          name,
                "sql_module":    sql_module.exists(),
                "site_file":     str(entry.resolve()) if entry.is_symlink() else str(entry),
            })
    return {"instances": instances, "count": len(instances)}


@router.get("/instances/{name}/status", summary="Status instance FreeRADIUS")
async def instance_status(name: str):
    """Cek apakah service freeradius@<name> berjalan."""
    _valid_name(name)
    res = await _run_script(["status", name], timeout=15)
    return res


@router.post("/instances/{name}/restart", summary="Restart instance FreeRADIUS")
async def instance_restart(name: str):
    """Restart service freeradius@<name>."""
    _valid_name(name)
    result = await asyncio.create_subprocess_exec(
        "systemctl", "restart", f"freeradius@{name}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await result.communicate()
    return {
        "service":    f"freeradius@{name}",
        "action":     "restart",
        "returncode": result.returncode,
        "stdout":     stdout.decode(errors="replace").strip(),
        "stderr":     stderr.decode(errors="replace").strip(),
        "success":    result.returncode == 0,
    }


@router.post("/instances", summary="Buat instance FreeRADIUS baru", status_code=201)
async def create_instance(body: CreateInstanceRequest):
    """
    Buat instance FreeRADIUS baru lewat radius-manager.sh.  
    Script akan membuat database, user MariaDB, SQL module, dan site config.
    """
    res = await _run_script(["create", body.admin_username], timeout=120)
    if not res["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=res,
        )
    return {"message": f"Instance '{body.admin_username}' berhasil dibuat.", **res}


@router.delete("/instances/{name}", summary="Hapus instance FreeRADIUS")
async def delete_instance(name: str, confirm: bool = False):
    """
    Hapus instance FreeRADIUS.  
    Wajib kirim `?confirm=true` untuk menjalankan penghapusan.
    """
    _valid_name(name)
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tambahkan query param '?confirm=true' untuk konfirmasi penghapusan.",
        )
    res = await _run_script(["delete", name], timeout=60)
    if not res["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=res,
        )
    return {"message": f"Instance '{name}' berhasil dihapus.", **res}


@router.get("/ports", summary="Registry port FreeRADIUS")
async def list_ports():
    """Baca file registry port dari FreeRADIUS."""
    registry = _fr_dir() / ".port_registry"
    if not registry.exists():
        return {"ports": [], "note": "Registry belum ada"}
    lines = registry.read_text().splitlines()
    ports = []
    for line in lines:
        line = line.strip()
        if line:
            ports.append(line)
    return {"ports": ports, "count": len(ports)}
