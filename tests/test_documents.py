from io import BytesIO

import fitz
import pytest
from docx import Document

from app.ingestion.document_reader import (
    DocumentPage,
    extract_document,
    split_pages_into_chunks,
)


def test_text_document_extraction_and_page_citations():
    result = extract_document("identity.txt", "Nama: Siti\nNIK: 123".encode())

    assert result.pages == [DocumentPage(None, "Nama: Siti\nNIK: 123")]
    assert result.ocr_pages == 0


def test_docx_paragraphs_and_tables_are_extracted():
    document = Document()
    document.add_paragraph("Nama: Siti")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "NIK"
    table.cell(0, 1).text = "1234567890123456"
    buffer = BytesIO()
    document.save(buffer)

    result = extract_document("identity.docx", buffer.getvalue())

    assert "Nama: Siti" in result.pages[0].text
    assert "NIK | 1234567890123456" in result.pages[0].text


def test_pdf_text_is_extracted_with_page_number():
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Nama: Siti NIK: 1234567890123456")
    content = document.tobytes()
    document.close()

    result = extract_document("identity.pdf", content)

    assert result.pages[0].page_number == 1
    assert "Nama: Siti NIK: 1234567890123456" in result.pages[0].text


def test_long_text_is_split_with_overlap_and_page_provenance():
    text = " ".join(f"kata{i}" for i in range(600))

    chunks = split_pages_into_chunks(
        [DocumentPage(3, text)], chunk_size=300, overlap=50
    )

    assert len(chunks) > 1
    assert all(chunk.page_number == 3 for chunk in chunks)
    assert all(len(chunk.text) <= 300 for chunk in chunks)
    assert set(chunks[0].text.split()) & set(chunks[1].text.split())


def test_unsupported_document_extension_is_rejected():
    with pytest.raises(ValueError, match="Format dokumen tidak didukung"):
        extract_document("program.exe", b"")
