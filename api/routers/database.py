"""
Database router — operasi MariaDB untuk FreeRADIUS.

Endpoint:
  GET  /api/v1/database/list              — daftar database radius_*
  GET  /api/v1/database/{db}/tables       — daftar tabel dalam database
  GET  /api/v1/database/{db}/users        — daftar user radius di radcheck
  POST /api/v1/database/{db}/users        — tambah user radius
  DELETE /api/v1/database/{db}/users/{u}  — hapus user radius
  GET  /api/v1/database/{db}/stats        — statistik radacct
"""
import re
from typing import Literal, Optional

import pymysql
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from api.auth import require_api_key
from api.config import get_settings

router = APIRouter(dependencies=[Depends(require_api_key)])

# ─────────────────────────────────────────────
# Validasi nama
# ─────────────────────────────────────────────
_DB_RE   = re.compile(r"^radius_[a-zA-Z][a-zA-Z0-9_]{1,30}$")
_NAME_RE = re.compile(r"^[a-zA-Z0-9@._\-]{1,64}$")


def _safe_db(name: str) -> str:
    """Pastikan nama database hanya radius_* dan alfanumerik."""
    if not _DB_RE.match(name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nama database harus diawali 'radius_' dan hanya alfanumerik/_.",
        )
    return name


def _safe_user(name: str) -> str:
    if not _NAME_RE.match(name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nama user tidak valid.",
        )
    return name


# ─────────────────────────────────────────────
# Koneksi MariaDB
# ─────────────────────────────────────────────
def _get_conn(db: Optional[str] = None):
    settings = get_settings()
    kwargs = dict(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_root_user,
        password=settings.db_root_password,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
    if db:
        kwargs["database"] = db
    try:
        conn = pymysql.connect(**kwargs)
        return conn
    except pymysql.OperationalError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Tidak bisa konek ke MariaDB: {e}",
        )


# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────
class AddRadiusUserRequest(BaseModel):
    username:   str = Field(..., description="Username RADIUS")
    password:   str = Field(..., min_length=4, description="Password teks-polos")
    password_type: Literal["Cleartext-Password", "MD5-Password", "NT-Password"] = \
        Field("Cleartext-Password")
    group:      Optional[str] = Field(None, max_length=64)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError("Username mengandung karakter tidak valid.")
        return v


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────
@router.get("/list", summary="Daftar database FreeRADIUS")
async def list_databases():
    """Kembalikan daftar database yang diawali dengan `radius_`."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW DATABASES LIKE 'radius\\_%';")
            rows = cur.fetchall()
    finally:
        conn.close()
    databases = [list(r.values())[0] for r in rows]
    return {"databases": databases, "count": len(databases)}


@router.get("/{db}/tables", summary="Daftar tabel dalam database")
async def list_tables(db: str):
    _safe_db(db)
    conn = _get_conn(db)
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES;")
            rows = cur.fetchall()
    finally:
        conn.close()
    tables = [list(r.values())[0] for r in rows]
    return {"database": db, "tables": tables}


@router.get("/{db}/users", summary="Daftar user RADIUS (radcheck)")
async def list_radius_users(db: str, limit: int = 100):
    _safe_db(db)
    if not 1 <= limit <= 1000:
        raise HTTPException(400, "limit harus 1–1000")
    conn = _get_conn(db)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, attribute, op, value "
                "FROM radcheck ORDER BY username LIMIT %s;",
                (limit,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return {"database": db, "users": rows, "count": len(rows)}


@router.post("/{db}/users", summary="Tambah user RADIUS", status_code=201)
async def add_radius_user(db: str, body: AddRadiusUserRequest):
    _safe_db(db)
    conn = _get_conn(db)
    try:
        with conn.cursor() as cur:
            # Cek duplikat
            cur.execute(
                "SELECT id FROM radcheck WHERE username=%s AND attribute=%s;",
                (body.username, body.password_type),
            )
            if cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"User '{body.username}' sudah ada.",
                )
            cur.execute(
                "INSERT INTO radcheck (username, attribute, op, value) "
                "VALUES (%s, %s, ':=', %s);",
                (body.username, body.password_type, body.password),
            )
            user_id = cur.lastrowid

            # Group (opsional)
            if body.group:
                cur.execute(
                    "INSERT INTO radusergroup (username, groupname, priority) "
                    "VALUES (%s, %s, 1) "
                    "ON DUPLICATE KEY UPDATE groupname=VALUES(groupname);",
                    (body.username, body.group),
                )
    finally:
        conn.close()
    return {"message": f"User '{body.username}' ditambahkan.", "id": user_id}


@router.delete("/{db}/users/{username}", summary="Hapus user RADIUS")
async def delete_radius_user(db: str, username: str):
    _safe_db(db)
    _safe_user(username)
    conn = _get_conn(db)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM radcheck WHERE username=%s;", (username,))
            deleted_check = cur.rowcount
            cur.execute("DELETE FROM radusergroup WHERE username=%s;", (username,))
            cur.execute("DELETE FROM radreply WHERE username=%s;", (username,))
    finally:
        conn.close()
    if deleted_check == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{username}' tidak ditemukan.",
        )
    return {"message": f"User '{username}' dihapus.", "rows_deleted": deleted_check}


@router.get("/{db}/stats", summary="Statistik sesi (radacct)")
async def accounting_stats(db: str):
    _safe_db(db)
    conn = _get_conn(db)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total_sessions FROM radacct;")
            total = cur.fetchone()
            cur.execute(
                "SELECT COUNT(*) AS active_sessions FROM radacct "
                "WHERE acctstoptime IS NULL;"
            )
            active = cur.fetchone()
            cur.execute(
                "SELECT username, nasipaddress, framedipaddress, "
                "acctstarttime, callingstationid "
                "FROM radacct WHERE acctstoptime IS NULL "
                "ORDER BY acctstarttime DESC LIMIT 20;"
            )
            sessions = cur.fetchall()
    finally:
        conn.close()
    return {
        "database":        db,
        "total_sessions":  total["total_sessions"],
        "active_sessions": active["active_sessions"],
        "active_list":     sessions,
    }
