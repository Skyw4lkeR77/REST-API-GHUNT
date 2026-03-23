# GHunt REST API

REST API untuk [GHunt](https://github.com/mxrch/GHunt) - framework OSINT Google yang bisa di-deploy di server DirectAdmin.

---

## 📋 Endpoints

Base URL: `https://yourdomain.com/api/v1`

Semua endpoint (kecuali `/health`) memerlukan header `X-API-Key`.

### System
| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/health` | Health check (tanpa auth) |

### Session
| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/api/v1/session/check` | Cek validitas session GHunt |
| POST | `/api/v1/session/setup` | Upload credentials GHunt |

### OSINT Modules
| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| POST | `/api/v1/email` | Hunt berdasarkan email address |
| POST | `/api/v1/gaia` | Hunt berdasarkan Gaia ID |
| POST | `/api/v1/drive` | Hunt Drive file/folder |
| POST | `/api/v1/geolocate` | Geolocate BSSID (WiFi MAC) |
| POST | `/api/v1/spiderdal` | Spider Digital Assets Links |

**Swagger UI**: `https://yourdomain.com/docs`  
**ReDoc**: `https://yourdomain.com/redoc`

---

## 🔐 Autentikasi API

Tambahkan header `X-API-Key` ke setiap request:
```bash
curl -H "X-API-Key: ghunt-api-secret-change-me" https://yourdomain.com/api/v1/session/check
```

API key default ada di `api/config.py`. Ganti dengan nilai Anda sendiri, atau gunakan env var:
```bash
export GHUNT_API_KEY="kunci-rahasia-anda"
```

---

## 🚀 Deploy ke DirectAdmin

### 1. Upload file ke server

Upload seluruh folder project ke `public_html/` domain Anda via SSH atau File Manager.

```bash
# Via SSH
scp -r c:/projekan/GHunt/* user@server.com:~/public_html/
```

### 2. Jalankan install.sh

```bash
ssh user@server.com
cd ~/public_html
chmod +x install.sh
./install.sh
```

Script ini otomatis:
- Membuat virtualenv di `~/ghunt_venv`
- Install semua dependencies
- Update `.htaccess` dengan username Anda
- Menawarkan untuk login GHunt

### 3. Konfigurasi .htaccess

Edit `.htaccess` jika path tidak sesuai:
```apache
PassengerPython /home/USERNAME/ghunt_venv/bin/python3
PassengerAppRoot /home/USERNAME/public_html
```

### 4. Set API Key

Di DirectAdmin → **Your Account** → **Environment Variables** (atau Softaculous), tambahkan:
```
GHUNT_API_KEY=kunci-rahasia-anda
```

Atau edit langsung di `api/config.py`:
```python
API_SECRET_KEY = "kunci-rahasia-anda"
```

### 5. Setup GHunt Session

Setelah deploy, upload credentials GHunt via API:

```bash
# Dari GHunt Companion extension (base64 encoded)
curl -X POST https://yourdomain.com/api/v1/session/setup \
  -H "X-API-Key: kunci-rahasia-anda" \
  -H "Content-Type: application/json" \
  -d '{"credentials": "<base64_dari_companion>"}'

# Atau dengan OAuth token langsung
curl -X POST https://yourdomain.com/api/v1/session/setup \
  -H "X-API-Key: kunci-rahasia-anda" \
  -H "Content-Type: application/json" \
  -d '{"oauth_token": "oauth2_4/..."}'
```

### 6. Restart Passenger

Di DirectAdmin panel → **Extra Features** → **Restart Passenger** (jika tersedia), atau:
```bash
touch ~/public_html/tmp/restart.txt
```

---

## 🔧 Menjalankan Secara Lokal (Development)

```bash
# Install dependencies
pip install -e .
pip install -r requirements_api.txt

# Jalankan
uvicorn api.main:app --reload --port 8000
```

Buka: `http://localhost:8000/docs`

---

## 📖 Contoh Penggunaan

### Health Check
```bash
curl http://localhost:8000/health
# {"status":"ok","version":"1.0.0","api":"GHunt REST API"}
```

### Cek Session
```bash
curl -H "X-API-Key: ghunt-api-secret-change-me" \
  http://localhost:8000/api/v1/session/check
# {"valid":true,"message":"Session is valid and authenticated.","creds_path":"..."}
```

### Hunt Email
```bash
curl -X POST http://localhost:8000/api/v1/email \
  -H "X-API-Key: ghunt-api-secret-change-me" \
  -H "Content-Type: application/json" \
  -d '{"email": "target@gmail.com"}'
```

**Response:**
```json
{
  "found": true,
  "message": "Target found.",
  "data": {
    "google_account": {
      "gaia_id": "123456789",
      "email": "target@gmail.com",
      "profile_photo": {
        "is_default": false,
        "url": "https://lh3.googleusercontent.com/..."
      },
      "last_profile_edit": "2024/01/15 10:30:00 (UTC)",
      "user_types": [{"type": "GOOGLE_USER", "definition": "Regular Google user"}]
    },
    "google_chat": {"entity_type": "HUMAN", "customer_id": null},
    "google_plus": {"is_enterprise_user": false, "activated_services": ["gmail", "drive"]},
    "play_games": null,
    "maps": {"review_count": 5, "avg_rating": 4.2},
    "calendar": null
  }
}
```

### Hunt Gaia ID
```bash
curl -X POST http://localhost:8000/api/v1/gaia \
  -H "X-API-Key: ghunt-api-secret-change-me" \
  -H "Content-Type: application/json" \
  -d '{"gaia_id": "103849869241042943497"}'
```

### Hunt Drive File
```bash
curl -X POST http://localhost:8000/api/v1/drive \
  -H "X-API-Key: ghunt-api-secret-change-me" \
  -H "Content-Type: application/json" \
  -d '{"file_id": "1N__vVu4c9fCt4EHxfthUNzVOs_tp8l6tHcMBnpOZv_M"}'
```

### Geolocate BSSID
```bash
curl -X POST http://localhost:8000/api/v1/geolocate \
  -H "X-API-Key: ghunt-api-secret-change-me" \
  -H "Content-Type: application/json" \
  -d '{"bssid": "30:86:2d:c4:29:d0"}'
```

**Response:**
```json
{
  "found": true,
  "message": "Location found.",
  "data": {
    "latitude": 48.8566,
    "longitude": 2.3522,
    "accuracy_meters": 50,
    "pretty_address": "Paris, Île-de-France, France",
    "google_maps_url": "https://www.google.com/maps/search/?q=48.8566,2.3522"
  }
}
```

### SpiderDAL
```bash
curl -X POST http://localhost:8000/api/v1/spiderdal \
  -H "X-API-Key: ghunt-api-secret-change-me" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://cash.app"}'
```

---

## ⚠️ Disclaimer

Tool ini hanya untuk keperluan edukasi, penyelidikan, dan pengujian keamanan yang sah.\
Ikuti lisensi [AGPL-3.0](LICENSE.md) dari GHunt.
