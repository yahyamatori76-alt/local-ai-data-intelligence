"""Extract searchable text from local office documents and PDFs."""

import html
import io
import re
import shutil
import subprocess
import tempfile
import zipfile
import csv
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

import pymupdf
import openpyxl
import xlrd
import pytesseract
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from PIL import Image
from pptx import Presentation
from pptx.exc import PackageNotFoundError as PptxPackageNotFoundError
from striprtf.striprtf import rtf_to_text

SUPPORTED_EXTENSIONS = {
    ".pdf", ".txt", ".md", ".csv", ".doc", ".docx", ".docm",
    ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx", ".odt", ".rtf",
    ".html", ".htm", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp",
}
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
    elif extension in {".docx", ".docm"}:
        pages = [_extract_docx(content)]
        ocr_pages = 0
        page_count = None
    elif extension == ".doc":
        pages = [_extract_doc(content)]
        ocr_pages = 0
        page_count = None
    elif extension in {".xlsx", ".xlsm"}:
        pages = [_extract_xlsx(content)]
        ocr_pages = 0
        page_count = None
    elif extension == ".xls":
        pages = [_extract_xls(content)]
        ocr_pages = 0
        page_count = None
    elif extension == ".pptx":
        pages = _extract_pptx(content)
        ocr_pages = 0
        page_count = len(pages)
    elif extension == ".ppt":
        pages = [_extract_ppt(content)]
        ocr_pages = 0
        page_count = None
    elif extension == ".csv":
        pages = [DocumentPage(None, _extract_csv(content))]
        ocr_pages = 0
        page_count = None
    elif extension == ".odt":
        pages = [_extract_odt(content)]
        ocr_pages = 0
        page_count = None
    elif extension in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        pages = [_extract_image(content)]
        ocr_pages = 1
        page_count = 1
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
        document = pymupdf.open(stream=content, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError) as exc:
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


def _extract_xlsx(content: bytes) -> DocumentPage:
    _validate_office_archive(content)
    try:
        workbook = openpyxl.load_workbook(
            io.BytesIO(content), read_only=True, data_only=True
        )
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise ValueError("Dokumen XLSX tidak dapat dibaca.") from exc
    parts: list[str] = []
    row_count = 0
    try:
        for sheet in workbook.worksheets:
            parts.append(f"[Sheet: {sheet.title}]")
            rows = sheet.iter_rows(values_only=True)
            headers = next(rows, ())
            for row in rows:
                row_count += 1
                if row_count > 100_000:
                    raise ValueError("Spreadsheet melebihi batas 100.000 baris.")
                fields = [
                    f"{headers[index] if index < len(headers) and headers[index] else f'kolom_{index + 1}'}: {value}"
                    for index, value in enumerate(row)
                    if value is not None and str(value).strip()
                ]
                if fields:
                    parts.append(" | ".join(fields))
    finally:
        workbook.close()
    return DocumentPage(None, "\n".join(parts))


def _extract_xls(content: bytes) -> DocumentPage:
    try:
        workbook = xlrd.open_workbook(file_contents=content, on_demand=True)
    except (xlrd.XLRDError, ValueError) as exc:
        raise ValueError("Dokumen XLS tidak dapat dibaca.") from exc
    parts: list[str] = []
    row_count = 0
    for sheet in workbook.sheets():
        parts.append(f"[Sheet: {sheet.name}]")
        headers = sheet.row_values(0) if sheet.nrows else []
        for row_index in range(1, sheet.nrows):
            row_count += 1
            if row_count > 100_000:
                raise ValueError("Spreadsheet melebihi batas 100.000 baris.")
            values = sheet.row_values(row_index)
            fields = [
                f"{headers[index] if index < len(headers) and headers[index] else f'kolom_{index + 1}'}: {value}"
                for index, value in enumerate(values)
                if value not in ("", None)
            ]
            if fields:
                parts.append(" | ".join(fields))
    workbook.release_resources()
    return DocumentPage(None, "\n".join(parts))


def _extract_csv(content: bytes) -> str:
    text = _decode_text(content)
    rows = csv.reader(io.StringIO(text))
    headers = next(rows, [])
    parts = []
    for row_index, row in enumerate(rows, start=1):
        if row_index > 100_000:
            raise ValueError("CSV melebihi batas 100.000 baris.")
        fields = [
            f"{headers[index] if index < len(headers) and headers[index] else f'kolom_{index + 1}'}: {value}"
            for index, value in enumerate(row)
            if value.strip()
        ]
        if fields:
            parts.append(" | ".join(fields))
    return "\n".join(parts)


def _extract_pptx(content: bytes) -> list[DocumentPage]:
    _validate_office_archive(content)
    try:
        presentation = Presentation(io.BytesIO(content))
    except (
        OSError,
        ValueError,
        zipfile.BadZipFile,
        PptxPackageNotFoundError,
    ) as exc:
        raise ValueError("Dokumen PPTX tidak dapat dibaca.") from exc
    pages = []
    for slide_number, slide in enumerate(presentation.slides, start=1):
        parts = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text.strip():
                parts.append(shape.text)
            if shape.has_table:
                parts.extend(
                    " | ".join(cell.text for cell in row.cells)
                    for row in shape.table.rows
                )
        if parts:
            pages.append(DocumentPage(slide_number, "\n".join(parts)))
    return pages


def _extract_ppt(content: bytes) -> DocumentPage:
    executable = shutil.which("catppt")
    if executable is None:
        raise ValueError("Pembaca dokumen PPT lama tidak tersedia.")
    with tempfile.NamedTemporaryFile(suffix=".ppt") as temporary:
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
            raise ValueError("Waktu pembacaan dokumen PPT habis.") from exc
    if result.returncode:
        raise ValueError("Dokumen PPT tidak dapat dibaca.")
    return DocumentPage(None, result.stdout.decode("utf-8", errors="replace"))


def _extract_image(content: bytes) -> DocumentPage:
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > 40_000_000:
                raise ValueError("Resolusi gambar melebihi batas pemrosesan OCR.")
            text = pytesseract.image_to_string(
                image.convert("RGB"), lang="ind+eng", timeout=15
            )
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Gambar tidak dapat dibaca untuk OCR.") from exc
    except (pytesseract.TesseractNotFoundError, RuntimeError) as exc:
        raise ValueError("OCR gambar tidak tersedia atau waktu pemrosesan habis.") from exc
    return DocumentPage(1, text)


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
