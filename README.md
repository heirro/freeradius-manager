# RadiusManager API

REST API berbasis **Python FastAPI** untuk manajemen multi-instance **FreeRADIUS** di server Linux Debian 12/13.  
Setiap instance dibuat secara penuh otomatis: konfigurasi FreeRADIUS, database MariaDB, clone repo API, setup venv, hingga systemd service.

---

## Fitur

- Buat & hapus instance FreeRADIUS secara otomatis via endpoint REST
- Database MariaDB dibuat + schema diimport otomatis per instance
- Clone [heirro/freeradius-api](https://github.com/heirro/freeradius-api/) per instance dengan nama folder sesuai nama instance
- Setup Python venv + `pip install` otomatis
- File `.env` ditulis otomatis dari `.env.example` dengan credentials yang sudah terisi
- Systemd service `<name>-api.service` dibuat, di-enable, dan distart otomatis
- Port API dicari otomatis (mulai `9100`), dicek ke sistem agar tidak bentrok
- CRUD user RADIUS (`radcheck`, `radusergroup`, `radreply`)
- Statistik sesi aktif dari tabel `radacct`
- Auth via API Key (`X-API-Key` header)

---

## Struktur Project

```
radiusmanager-api/
├── api/
│   ├── __init__.py
│   ├── config.py          ← Konfigurasi via .env
│   ├── auth.py            ← API Key authentication
│   ├── main.py            ← FastAPI app factory
│   └── routers/
│       ├── radius.py      ← Manajemen instance FreeRADIUS
│       └── database.py    ← CRUD user RADIUS & statistik
├── radius-manager.sh      ← Bash script multi-instance FreeRADIUS
├── requirements.txt
├── run.py                 ← Entry point langsung
├── setup.sh               ← Setup venv + jalankan server
└── env.example            ← Template konfigurasi
```

---

## Persyaratan

- Debian 12 / 13 (Bookworm / Trixie)
- Python 3.11+
- FreeRADIUS 3.x (`apt install freeradius freeradius-mysql`)
- MariaDB / MySQL
- `git` terinstall

---

## Instalasi & Menjalankan

### 1. Clone repo ini

```bash
git clone <repo-url> /root/radiusmanager-api
cd /root/radiusmanager-api
```

### 2. Salin dan isi konfigurasi

```bash
cp env.example .env
nano .env
```

Minimal isi:

```env
API_KEY=isi_dengan_string_rahasia_panjang
DB_ROOT_PASSWORD=password_root_mariadb
```

Generate API key:

```bash
openssl rand -hex 32
```

### 3. Jalankan setup (install venv + start dev server)

```bash
sudo bash setup.sh
```

Atau step by step:

```bash
sudo bash setup.sh install   # install deps Python saja
bash setup.sh run            # dev server port 8000 (--reload)
bash setup.sh prod           # production (multi-worker)
sudo bash setup.sh service   # daftarkan sebagai systemd service
```

### 4. Akses API

```
http://server:8000/docs      ← Swagger UI interaktif
http://server:8000/redoc     ← ReDoc
```

Semua request wajib menyertakan header:

```
X-API-Key: <nilai API_KEY di .env>
```

---

## Konfigurasi `.env`

| Variabel | Default | Keterangan |
|---|---|---|
| `API_KEY` | *(auto-generate)* | API key untuk autentikasi semua request |
| `HOST` | `0.0.0.0` | Bind address server |
| `PORT` | `8000` | Port server utama |
| `DEBUG` | `false` | Mode debug (aktifkan CORS `*`) |
| `FREERADIUS_DIR` | `/etc/freeradius/3.0` | Direktori konfigurasi FreeRADIUS |
| `RADIUS_MANAGER_SCRIPT` | `./radius-manager.sh` | Path ke bash script |
| `DB_HOST` | `localhost` | Host MariaDB |
| `DB_PORT` | `53360` | Port MariaDB |
| `DB_ROOT_USER` | `root` | User root MariaDB |
| `DB_ROOT_PASSWORD` | *(kosong)* | Password root MariaDB |
| `API_INSTANCES_DIR` | `/root` | Direktori clone repo API per instance |
| `API_GIT_REPO` | `https://github.com/heirro/freeradius-api/` | Repo yang di-clone per instance |
| `API_PORT_START` | `9100` | Port awal untuk API instance |
| `API_PORT_REGISTRY` | `/root/.api_port_registry` | File registry port API |

---

## Endpoint

### FreeRADIUS — `/api/v1/radius`

#### `POST /api/v1/radius/instances`

Buat instance baru secara penuh otomatis. Pipeline yang dijalankan:

1. `radius-manager.sh create <name>` → konfigurasi FreeRADIUS + database MariaDB + import schema
2. Baca credentials dari `/etc/freeradius/3.0/.instance_<name>`
3. Cari port kosong mulai `API_PORT_START` (cek `ss -tulnp` + registry)
4. `git clone https://github.com/heirro/freeradius-api/ /root/<name>-api`
5. `python3 -m venv /root/<name>-api/venv` + `pip install -r requirements.txt`
6. Tulis `/root/<name>-api/.env` dari `.env.example` dengan credentials DB yang terisi
7. Buat `/etc/systemd/system/<name>-api.service`, `enable`, `start`

**Request body:**
```json
{
  "admin_username": "replaymedia"
}
```

**Response:**
```json
{
  "message": "Instance 'replaymedia' berhasil dibuat.",
  "name": "replaymedia",
  "api_port": 9100,
  "api_dir": "/root/replaymedia-api",
  "env_file": "/root/replaymedia-api/.env",
  "service_file": "/etc/systemd/system/replaymedia-api.service",
  "service_url": "http://<server>:9100",
  "docs_url": "http://<server>:9100/docs",
  "credentials": {
    "db_name": "replaymedia",
    "db_user": "replaymedia",
    "db_pass": "...",
    "auth_port": "11000",
    "acct_port": "11001",
    "coa_port": "13000"
  }
}
```

**Systemd service yang dihasilkan** (`/etc/systemd/system/replaymedia-api.service`):
```ini
[Unit]
Description=RadiusAPI with Uvicorn
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/root/replaymedia-api
ExecStart=/root/replaymedia-api/venv/bin/uvicorn main:app --host 0.0.0.0 --port 9100
Restart=always
RestartSec=5
SyslogIdentifier=replaymedia-api

[Install]
WantedBy=multi-user.target
```

---

| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/api/v1/radius/instances` | Daftar semua instance |
| `POST` | `/api/v1/radius/instances` | Buat instance baru (pipeline lengkap) |
| `DELETE` | `/api/v1/radius/instances/{name}?confirm=true` | Hapus instance + API dir + service |
| `DELETE` | `/api/v1/radius/instances/{name}?confirm=true&with_db=true` | + hapus database MariaDB |
| `GET` | `/api/v1/radius/instances/{name}/status` | Status systemd FreeRADIUS instance |
| `POST` | `/api/v1/radius/instances/{name}/restart` | Restart FreeRADIUS instance |
| `POST` | `/api/v1/radius/instances/{name}/api/restart` | Restart API service instance |
| `GET` | `/api/v1/radius/ports` | Registry port FreeRADIUS |
| `GET` | `/api/v1/radius/api-ports` | Registry port API instances |

---

### Database — `/api/v1/database`

| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/api/v1/database/list` | Daftar database `radius_*` |
| `GET` | `/api/v1/database/{db}/tables` | Daftar tabel dalam database |
| `GET` | `/api/v1/database/{db}/users` | Daftar user RADIUS (`radcheck`) |
| `POST` | `/api/v1/database/{db}/users` | Tambah user RADIUS |
| `DELETE` | `/api/v1/database/{db}/users/{username}` | Hapus user RADIUS |
| `GET` | `/api/v1/database/{db}/stats` | Statistik sesi aktif (`radacct`) |

**Contoh tambah user RADIUS:**
```json
POST /api/v1/database/radius_replaymedia/users
{
  "username": "pelanggan01",
  "password": "pass1234",
  "password_type": "Cleartext-Password",
  "group": "pppoe-10mbps"
}
```

---

## Keamanan

- Semua endpoint dilindungi **API Key** via header `X-API-Key`
- Perbandingan key menggunakan **constant-time comparison** (anti timing attack)
- Nama instance/database divalidasi ketat dengan regex (hanya `a-z`, `0-9`, `_`)
- Semua query database menggunakan **parameterized query** (anti SQL injection)
- CORS hanya aktif ke `*` saat `DEBUG=true`; di production tidak ada origins yang diizinkan kecuali dikonfigurasi manual

---

## Lisensi

MIT
