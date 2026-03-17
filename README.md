# OEE System — Backend API

Backend Python untuk sistem **Overall Equipment Effectiveness (OEE)** menggunakan FastAPI, SQLAlchemy, dan PostgreSQL dengan arsitektur **multi-schema per plant**.

---

## 🏗️ Arsitektur Database

```
PostgreSQL
├── schema: public           ← shared (user, plant, role, token)
│   ├── users
│   ├── roles
│   ├── plants
│   ├── user_plants
│   └── refresh_tokens
│
├── schema: plant_a          ← data eksklusif Plant A
│   ├── loss_level_1
│   ├── loss_level_2
│   ├── loss_level_3
│   ├── master_shifts
│   ├── master_feed_codes
│   ├── master_lines
│   └── master_standard_throughputs
│
└── schema: plant_b          ← data eksklusif Plant B
    └── (tabel yang sama)
```

---

## 🚀 Cara Menjalankan

### 1. Prerequisites
- Python 3.11+
- PostgreSQL 14+

### 2. Clone & Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env
# Edit .env → sesuaikan DATABASE_URL dan SECRET_KEY
```

### 3. Buat Database PostgreSQL
```sql
CREATE DATABASE oee_db;
```

### 4. Inisialisasi Tabel & Seed Data
```bash
python -m app.db.init_db
```
Ini akan membuat semua tabel di schema `public` dan membuat user admin default:
- **Username:** `admin`
- **Password:** `Admin@1234`  ⚠️ Ganti segera!

### 5. Jalankan Server
```bash
# Development
uvicorn main:app --reload --port 8000

# Production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 📡 API Endpoints

### Base URL: `http://localhost:8000/api/v1`
### Docs: `http://localhost:8000/docs`

---

### 🔐 Auth — `/api/v1/auth`

| Method | Endpoint | Auth | Deskripsi |
|--------|----------|------|-----------|
| POST | `/auth/login` | ❌ | Login, dapat access + refresh token |
| POST | `/auth/refresh` | ❌ | Perbarui access token |
| POST | `/auth/logout` | ✅ | Revoke refresh token |
| GET | `/auth/me` | ✅ | Data user saat ini |
| GET | `/auth/me/plants` | ✅ | List plant yang bisa diakses |

**Login Request:**
```json
POST /api/v1/auth/login
{
  "username": "admin",
  "password": "Admin@1234"
}
```

**Login Response:**
```json
{
  "token": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 28800
  },
  "user": { "id": 1, "username": "admin", ... },
  "accessible_plants": [...]
}
```

---

### 🏭 Plants — `/api/v1/plants` *(Superuser only)*

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/plants/` | List semua plant |
| POST | `/plants/` | Buat plant baru (otomatis buat schema DB) |
| DELETE | `/plants/{id}` | Nonaktifkan plant |

**Buat Plant Baru:**
```json
POST /api/v1/plants/
Authorization: Bearer <token>

{
  "name": "Plant Surabaya",
  "code": "PLT-SBY",
  "description": "Pabrik unit Surabaya"
}
```
→ Otomatis membuat schema PostgreSQL `plant_plt_sby` beserta semua tabelnya.

---

### 👥 Users — `/api/v1/users` *(Superuser only)*

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/users/` | List semua user |
| POST | `/users/` | Buat user baru |
| PUT | `/users/{id}` | Update user |
| DELETE | `/users/{id}` | Nonaktifkan user |

---

### 📋 Master Data — `/api/v1/master`

> **Wajib:** sertakan header `X-Plant-ID: <plant_id>` di semua request master data.

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET/POST/PUT/DELETE | `/master/loss-level-1` | Loss Category Level 1 |
| GET/POST/PUT/DELETE | `/master/loss-level-2` | Loss Category Level 2 |
| GET/POST/PUT/DELETE | `/master/loss-level-3` | Loss Category Level 3 |
| GET/POST/PUT | `/master/shifts` | Master Shift |
| GET/POST/PUT | `/master/feed-codes` | Master Feed Code |
| GET/POST/PUT | `/master/lines` | Master Line |
| GET/POST/PUT | `/master/standard-throughputs` | Standard Throughput |

**Contoh request master data:**
```bash
curl -X GET http://localhost:8000/api/v1/master/shifts \
  -H "Authorization: Bearer eyJ..." \
  -H "X-Plant-ID: 1"
```

---

## 🔑 Headers yang Dibutuhkan

| Header | Wajib | Keterangan |
|--------|-------|------------|
| `Authorization` | ✅ (semua endpoint selain login) | `Bearer <access_token>` |
| `X-Plant-ID` | ✅ (endpoint master data) | ID plant yang dipilih user |

---

## 👤 Roles Default

| Role | Deskripsi |
|------|-----------|
| `administrator` | Full access semua plant |
| `plant_manager` | Manage plant yang di-assign |
| `operator` | Input data OEE |
| `viewer` | Read-only |

---

## 🗂️ Struktur Project

```
oee-backend/
├── main.py                          # Entry point FastAPI
├── requirements.txt
├── .env.example
├── alembic.ini                      # Konfigurasi migrasi DB
├── alembic/
│   ├── env.py
│   └── versions/                   # File migrasi
└── app/
    ├── core/
    │   ├── config.py                # Settings dari .env
    │   ├── security.py              # JWT + bcrypt
    │   ├── deps.py                  # FastAPI dependencies & guards
    │   └── exceptions.py            # Custom error handlers
    ├── db/
    │   ├── database.py              # Engine, session, schema provisioning
    │   └── init_db.py               # Script init + seed
    ├── models/
    │   ├── public.py                # Model schema public
    │   └── plant_schema.py          # Model per-plant schema
    ├── schemas/
    │   ├── auth.py                  # Pydantic: auth & user
    │   └── master.py                # Pydantic: master data
    └── api/v1/
        ├── router.py
        └── endpoints/
            ├── auth.py
            ├── plants.py
            ├── users.py
            └── master.py
```

---

## ⚙️ Environment Variables (`.env`)

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/oee_db
SECRET_KEY=your-super-secret-key-min-32-characters
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
REFRESH_TOKEN_EXPIRE_DAYS=7
```

---

## 🔒 Security Notes

- Password di-hash menggunakan **bcrypt**
- Token menggunakan **JWT (HS256)**
- Refresh token disimpan di DB dan bisa di-revoke
- Akses plant divalidasi per-request via `X-Plant-ID` header
- Setiap data insert menyimpan `created_by_id` dan `updated_by_id`
