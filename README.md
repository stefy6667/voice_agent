# QR Studio pentru experiențe personalizabile

Aplicație FastAPI gata de deploy în Render pentru generarea și administrarea de coduri QR personalizabile.

## Ce face

- doar administratorul care cunoaște `ADMIN_ACCESS_CODE` poate genera QR-uri noi;
- fiecare QR primește automat un `edit_code` unic pentru client;
- codul QR poate fi descărcat în format PNG;
- la prima scanare clientul își personalizează pagina cu text, culori, font, imagine și video embed;
- la scanările ulterioare apare conținutul salvat;
- clientul poate relua editarea din `/edit/<slug>` folosind `edit_code`;
- totul rulează dintr-un singur serviciu web, potrivit pentru hosting în Render.

## Rulare locală

```bash
cd voice_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Variabile importante

- `PUBLIC_BASE_URL` – URL-ul public Render folosit în QR;
- `ADMIN_ACCESS_CODE` – codul secret pe care îl știi doar tu pentru a genera noi QR-uri;
- `DATABASE_URL` – baza SQLite locală;
- `STORAGE_DIR` – locația fișierelor uploadate.

## Endpoints utile

- `GET /` – dashboard admin + listă QR-uri;
- `POST /api/admin/create` – generează un QR nou;
- `GET /api/qr/{slug}.png` – descarcă PNG;
- `GET /p/{slug}` – pagina publică după scanare;
- `GET /edit/{slug}` – formularul de editare cu cod alfanumeric;
- `POST /api/qr/{slug}/content` – salvează personalizarea clientului.
