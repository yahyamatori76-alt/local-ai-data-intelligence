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
   - Ganti `APP_ADMIN_PASSWORD` dengan password admin yang berbeda, minimal 12 karakter dan maksimal 72 byte UTF-8.
   - Catat username/password admin secara aman. Untuk menampilkan nilai pada server: `grep '^APP_ADMIN_' .env` (jangan kirim output ke chat atau commit).
   - Atur `POSTGRES_DB`/`POSTGRES_USER` hanya jika diperlukan.
   - Jangan commit atau mengirim `.env`.
4. Build image, pasang dependency di dalam image, dan jalankan stack:

   ```sh
   docker compose config
   docker compose up -d --build
   docker compose ps
   ```

   Saat volume baru dibuat, skema awal diterapkan PostgreSQL. API menerapkan migrasi operasional `002` saat startup dan membuat akun admin serta sumber/rule awal secara idempotent.
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

## Penggunaan dashboard

1. Masuk ke `http://192.168.1.89:8501` menggunakan akun admin dari `.env`.
2. Pada **Input & Knowledge Base**, pilih sumber terotorisasi dan unggah file CSV/XLSX/JSON. System log menerima JSON Lines (`.log`). Data uji tersedia di `data/synthetic/`.
3. Pada **Dokumen & Pencarian**, unggah PDF, TXT, DOC/DOCX, ODT, RTF, HTML, atau Markdown. PDF hasil pindai diproses dengan OCR Tesseract bahasa Indonesia/Inggris. Dokumen dipecah menjadi bagian dan indeks teksnya disimpan di PostgreSQL lokal; file asli tidak disimpan.
4. Cari NIK 16 digit secara tepat atau nama/teks secara penuh/parsial. Hanya kutipan yang ditemukan di dokumen lokal yang dikirim ke Ollama lokal untuk diringkas, dengan nama file/halaman sebagai sumber. Dokumen tidak dikirim ke layanan cloud.
5. Jalankan `TX_EVENT_300S` dari halaman **AI Chat & Analisis** setelah file transaksi dan event diimpor.
6. Tinjau atau tolak korelasi yang belum direview; aktivitas tersimpan di audit.
7. Chat ringkasan dashboard tetap hanya menggunakan agregat terverifikasi. Analisis dokumen menggunakan halaman terpisah **Dokumen & Pencarian**.

Format impor minimum:

- Marketplace: `transaction_ref,event_time,authorized_join_ref`; `status`, `amount`, dan `currency` opsional.
- System log: `event_time,event_ref,authorized_join_ref`; `severity`, `event_type`, dan `message` opsional.
- Population: `record_ref`; `masked_identity_ref`, `region_code`, dan atribut tambahan opsional. Kolom pengenal pribadi mentah seperti nama, NIK, email, telepon, atau alamat ditolak.

Timestamp tanpa zona waktu dianggap UTC. Duplikat referensi dalam satu file ditolak per baris; alasan penolakan disimpan tanpa isi sensitif baris. Batas default upload 100 MB.

Admin dapat membuat akun `analyst`/`viewer` melalui endpoint `POST /auth/users` dengan HTTP Basic. Endpoint operasional mewajibkan autentikasi; peran admin mengelola sumber dan user, analyst/admin dapat impor, korelasi dan review, sedangkan viewer hanya membaca.

Unggah dokumen dan pencarian dokumen dibatasi untuk admin/analyst. Teks dokumen yang diekstrak berisi data sensitif dan disimpan pada tabel `local_documents` serta `local_document_chunks` di PostgreSQL. Aktivitas audit menyimpan jenis dan panjang kueri serta jumlah hasil, bukan nilai NIK/nama yang dicari. Pastikan pengguna memiliki dasar/otorisasi pemrosesan; batasi akses jaringan dan lindungi backup database. OCR dibatasi maksimal 20 halaman pindai per dokumen.

Jalankan acceptance/unit tests di server:

```sh
docker compose exec api pytest -q
```

Semua metrik, status batch, hasil, dan aktivitas dashboard dibaca melalui API terautentikasi dari PostgreSQL; dashboard tidak mendapat kredensial database.

## Keamanan jaringan

- Hanya port dashboard yang dipublikasikan, terikat ke `SERVER_BIND_IP`.
- PostgreSQL (`5432`), API (`8000`), dan Ollama (`11434`) tidak dipublikasikan ke host.
- Gunakan firewall server untuk membatasi akses dashboard. Jangan mengikat ke `0.0.0.0` atau meneruskan port database/Ollama ke internet.
- Gunakan data sintetis/de-identifikasi untuk pengujian dan jangan menyimpan kredensial atau data produksi di repository.

## Backup database

```sh
docker compose exec -T postgres pg_dump -U app_user -d local_ai_intel > local_ai_intel-backup.sql
```

Simpan backup dengan akses terbatas di luar repository. Sesuaikan user/database jika `.env` menggunakan nama lain. Untuk restore ke database yang sudah ada, hentikan penulis aplikasi dan uji restore pada backup terpisah sebelum memulihkan data.

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
