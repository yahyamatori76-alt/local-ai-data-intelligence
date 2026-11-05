"""Extract searchable text from local office documents and PDFs."""

import html
import io
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

import fitz
import pytesseract
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from PIL import Image
from striprtf.striprtf import rtf_to_text

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".doc", ".docx", ".odt", ".rtf", ".html", ".htm", ".md"}
MAX_EXTRACTED_CHARACTERS = 10_000_000
MAX_PDF_PAGES = 1000
MAX_OCR_PAGES = 20
MAX_OFFICE_UNCOMPRESSED_BYTES = 100_000_000
MAX_OFFICE_COMPRESSION_RATIO = 200
MIN_TEXT_PER_PAGE = 40


@dataclass(frozen=True)
class DocumentPage:
    page_number: int | None
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    pages: list[DocumentPage]
    ocr_pages: int
    page_count: int | None = None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden_depth += 1
        elif tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def extract_document(filename: str, content: bytes) -> ExtractedDocument:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Format dokumen tidak didukung.")
    if not content:
        raise ValueError("Dokumen kosong.")

    if extension == ".pdf":
        pages, ocr_pages, page_count = _extract_pdf(content)
    elif extension in {".txt", ".md"}:
        pages = [DocumentPage(None, _decode_text(content))]
        ocr_pages = 0
        page_count = None
    elif extension == ".docx":
        pages = [_extract_docx(content)]
        ocr_pages = 0
        page_count = None
    elif extension == ".doc":
        pages = [_extract_doc(content)]
        ocr_pages = 0
        page_count = None
    elif extension == ".odt":
        pages = [_extract_odt(content)]
        ocr_pages = 0
        page_count = None
    elif extension == ".rtf":
        pages = [DocumentPage(None, rtf_to_text(_decode_text(content)))]
        ocr_pages = 0
        page_count = None
    else:
        pages = [DocumentPage(None, _extract_html(_decode_text(content)))]
        ocr_pages = 0
        page_count = None

    pages = [
        DocumentPage(page.page_number, _clean_text(page.text))
        for page in pages
        if _clean_text(page.text)
    ]
    total_characters = sum(len(page.text) for page in pages)
    if not total_characters:
        raise ValueError(
            "Tidak ada teks yang dapat dibaca. PDF hasil pindai memerlukan OCR yang tersedia."
        )
    if total_characters > MAX_EXTRACTED_CHARACTERS:
        raise ValueError("Teks dokumen melebihi batas pemrosesan 10 juta karakter.")
    return ExtractedDocument(pages, ocr_pages, page_count)


def split_pages_into_chunks(
    pages: list[DocumentPage], *, chunk_size: int = 1400, overlap: int = 200
) -> list[DocumentPage]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Ukuran potongan dokumen tidak valid.")
    chunks: list[DocumentPage] = []
    for page in pages:
        text = page.text.strip()
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start + chunk_size // 2, end)
                if boundary > start:
                    end = boundary
            content = text[start:end].strip()
            if content:
                chunks.append(DocumentPage(page.page_number, content))
            if end >= len(text):
                break
            start = max(start + 1, end - overlap)
    return chunks


def _extract_pdf(content: bytes) -> tuple[list[DocumentPage], int, int]:
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except (fitz.FileDataError, RuntimeError) as exc:
        raise ValueError("PDF tidak dapat dibuka.") from exc
    pages: list[DocumentPage] = []
    ocr_pages = 0
    try:
        if document.needs_pass:
            raise ValueError("PDF terenkripsi/kata sandi tidak didukung.")
        page_count = document.page_count
        if page_count > MAX_PDF_PAGES:
            raise ValueError(f"PDF melebihi batas {MAX_PDF_PAGES} halaman.")
        for index, page in enumerate(document):
            text = page.get_text("text")
            if len(text.strip()) < MIN_TEXT_PER_PAGE:
                if ocr_pages >= MAX_OCR_PAGES:
                    raise ValueError(f"OCR dibatasi maksimal {MAX_OCR_PAGES} halaman per dokumen.")
                pixmap = page.get_pixmap(dpi=180, alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                try:
                    text = pytesseract.image_to_string(
                        image, lang="ind+eng", timeout=5
                    )
                except (pytesseract.TesseractNotFoundError, RuntimeError) as exc:
                    raise ValueError(
                        "OCR PDF tidak tersedia atau waktu pemrosesan habis."
                    ) from exc
                ocr_pages += 1
            pages.append(DocumentPage(index + 1, text))
    finally:
        document.close()
    return pages, ocr_pages, page_count


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Encoding file teks tidak didukung.")


def _extract_docx(content: bytes) -> DocumentPage:
    try:
        _validate_office_archive(content)
        document = Document(io.BytesIO(content))
    except (PackageNotFoundError, KeyError, ValueError, OSError, zipfile.BadZipFile) as exc:
        raise ValueError("Dokumen DOCX tidak dapat dibaca.") from exc
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        parts.extend(
            " | ".join(cell.text for cell in row.cells) for row in table.rows
        )
    return DocumentPage(None, "\n".join(parts))


def _extract_doc(content: bytes) -> DocumentPage:
    executable = shutil.which("antiword")
    if executable is None:
        raise ValueError("Pembaca dokumen DOC lama tidak tersedia.")
    with tempfile.NamedTemporaryFile(suffix=".doc") as temporary:
        temporary.write(content)
        temporary.flush()
        try:
            result = subprocess.run(
                [executable, temporary.name],
                capture_output=True,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Waktu pembacaan dokumen DOC habis.") from exc
    if result.returncode:
        raise ValueError("Dokumen DOC tidak dapat dibaca.")
    return DocumentPage(None, result.stdout.decode("utf-8", errors="replace"))


def _extract_odt(content: bytes) -> DocumentPage:
    try:
        _validate_office_archive(content)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            root = ElementTree.fromstring(archive.read("content.xml"))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ValueError("Dokumen ODT tidak dapat dibaca.") from exc
    text_nodes = [
        node.text or ""
        for node in root.iter()
        if node.tag.endswith(("}p", "}h"))
    ]
    return DocumentPage(None, "\n".join(text_nodes))


def _validate_office_archive(content: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        files = archive.infolist()
        uncompressed_size = sum(file.file_size for file in files)
        if uncompressed_size > MAX_OFFICE_UNCOMPRESSED_BYTES:
            raise ValueError("Ukuran dokumen setelah ekstraksi melebihi batas.")
        if any(
            file.file_size > MAX_OFFICE_COMPRESSION_RATIO * max(file.compress_size, 1)
            for file in files
        ):
            raise ValueError("Rasio kompresi dokumen tidak aman.")


def _extract_html(content: str) -> str:
    parser = _TextExtractor()
    parser.feed(content)
    return html.unescape("".join(parser.parts))


def _clean_text(value: str) -> str:
    value = value.replace("\x00", " ")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()
