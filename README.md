# Local AI Data Intelligence Platform

MVP lokal dengan PostgreSQL sebagai database utama. Docker Compose menjalankan PostgreSQL, API FastAPI, dashboard Streamlit, dan Ollama. Dependensi Python dipasang ke image saat proses build; Python dan PostgreSQL tidak perlu dipasang langsung di server.

## Target server pengujian

- Dashboard: `http://192.168.1.89:8501`
- PostgreSQL, API, dan Ollama hanya dapat diakses dari jaringan internal Docker.
- Server harus memiliki alamat `192.168.1.89` pada salah satu interface. Jika alamat berbeda, ubah `SERVER_BIND_IP` di `.env`.
- Batasi akses firewall ke port `8501` hanya untuk jaringan/pengguna penguji yang berwenang.

## Persiapan pertama kali

Pastikan Docker Engine dan Docker Compose sudah tersedia di server. Tidak perlu memasang Python, PostgreSQL, atau Ollama langsung di host.

1. Letakkan/clone repository pada server, lalu masuk ke folder proyek.
2. Buat konfigurasi lokal dari template:

   ```powershell
   Copy-Item .env.example .env
   ```

   Di Linux:

   ```sh
   cp .env.example .env
   ```

3. Edit `.env`:
   - Biarkan `SERVER_BIND_IP=192.168.1.89` jika itu memang IP server.
   - Ganti `POSTGRES_PASSWORD` dengan password acak kuat 32+ karakter alfanumerik.
   - Atur `POSTGRES_DB`/`POSTGRES_USER` hanya jika diperlukan.
   - Jangan commit atau mengirim `.env`.
4. Build image, pasang dependency di dalam image, dan jalankan stack:

   ```sh
   docker compose config
   docker compose up -d --build
   docker compose ps
   ```

   Saat volume PostgreSQL baru dibuat, migrasi awal dari `migrations/001_initial_schema.sql` diterapkan otomatis. Docker menyimpan database, model, dan dependency di volume/image yang sesuai.
5. Unduh model lokal ke Ollama container satu kali:

   ```sh
   docker compose exec ollama ollama pull llama3.2:3b
   ```

6. Buka `http://192.168.1.89:8501`. Periksa status melalui:

   ```sh
   docker compose logs --tail=100 dashboard api postgres ollama
   ```

## Update versi berikutnya

Setelah perubahan tersedia di folder repository server (misalnya dengan `git pull`):

```sh
docker compose up -d --build
docker compose ps
```

Volume `postgres_data` dan `ollama_data` tetap dipertahankan. Jangan gunakan `docker compose down -v`, karena opsi tersebut menghapus volume database dan model. Migrasi baru untuk database yang sudah ada harus dijalankan secara eksplisit; file migrasi awal tidak otomatis dijalankan ulang pada volume lama.

## Dashboard dan cakupan MVP saat ini

Dashboard menampilkan status layanan dan membaca ringkasan sumber, batch, aturan, audit, serta hasil korelasi dari PostgreSQL. Jika database belum tersedia, dashboard menampilkan peringatan dan keadaan kosong, bukan data contoh seolah nyata. Upload dan chat AI masih dinonaktifkan sampai endpoint operasional dan kontrol aksesnya diimplementasikan.

## Keamanan jaringan

- Hanya port dashboard yang dipublikasikan, terikat ke `SERVER_BIND_IP`.
- PostgreSQL (`5432`), API (`8000`), dan Ollama (`11434`) tidak dipublikasikan ke host.
- Gunakan firewall server untuk membatasi akses dashboard. Jangan mengikat ke `0.0.0.0` atau meneruskan port database/Ollama ke internet.
- Gunakan data sintetis/de-identifikasi untuk pengujian dan jangan menyimpan kredensial atau data produksi di repository.

## Backup database

```sh
docker compose exec -T postgres pg_dump -U app_user -d local_ai_intel > local_ai_intel-backup.sql
```

Simpan backup dengan akses terbatas di luar repository. Sesuaikan user/database jika `.env` menggunakan nama lain.

## Struktur utama

```text
app/                 FastAPI dan modul backend
dashboard/           Streamlit
migrations/          Skema PostgreSQL berversi
tests/               Tes otomatis
data/synthetic/      Fixture sintetis
Dockerfile           Image aplikasi Python
docker-compose.yml   PostgreSQL, API, Ollama, dan dashboard
```
