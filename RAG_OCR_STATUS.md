# Status OCR dan RAG

Dokumen ini merangkum dukungan OCR, proses RAG, serta batas konfigurasi aplikasi saat ini.

## Cara kerja

1. Unggah dokumen melalui menu **Dokumen & Pencarian (RAG)**.
2. Aplikasi mengekstrak teks dari dokumen. PDF hasil pindai dan gambar diproses dengan OCR Tesseract bahasa Indonesia dan Inggris.
3. Teks hasil ekstraksi dipecah menjadi potongan dan diindeks di PostgreSQL pada tabel `local_documents` dan `local_document_chunks`.
4. Pencarian mengambil potongan teks yang cocok. Untuk admin dan analyst, Ollama lokal dapat menyusun jawaban dari kutipan tersebut dan menyertakan sumber.

File asli tidak disimpan oleh alur indeks dokumen; teks hasil ekstraksi disimpan di PostgreSQL. Perlakukan teks indeks dan backup database sebagai data sensitif.

## Batas konfigurasi saat ini

| Batas | Nilai |
|---|---:|
| Ukuran unggahan maksimum | 100 MB |
| Teks hasil ekstraksi maksimum per dokumen | 10 juta karakter |
| Halaman PDF maksimum | 1.000 halaman |
| Halaman pindai PDF maksimum untuk OCR | 20 halaman per dokumen |
| Ukuran potongan teks | 1.400 karakter |
| Tumpang tindih antar-potongan | 200 karakter |
| Jumlah potongan maksimum per dokumen | 10.000 |
| Potongan hasil pencarian maksimum untuk konteks Ollama | 8 |
| Panjang kueri pencarian maksimum | 256 karakter |

Batas tersebut tidak menjamin semua dokumen berukuran maksimum dapat diproses dengan cepat. Waktu OCR bergantung pada ukuran, kualitas, dan keterbacaan hasil pindai.

## Jenis pencarian

RAG saat ini menggunakan pencarian teks PostgreSQL (`tsvector` dan indeks GIN), pencocokan teks, serta pencocokan NIK secara tepat. **pgvector belum dipasang atau digunakan**, sehingga belum ada embedding maupun pencarian semantik berdasarkan kedekatan vector. Ollama menerima kutipan hasil pencarian teks sebagai konteks; Ollama tidak menggantikan mekanisme pencarian tersebut.

## Status data saat pemeriksaan terakhir

Pemeriksaan database server terakhir menunjukkan:

- Ekstensi PostgreSQL `vector` belum aktif.
- Tabel `local_documents`: 0 baris.
- Tabel `local_document_chunks`: 0 baris.

Artinya, fitur OCR tersedia di aplikasi, tetapi saat pemeriksaan tersebut belum ada dokumen terindeks di server untuk dicari atau dipakai sebagai konteks RAG. Status jumlah dokumen dapat berubah setelah ada unggahan.
