from io import BytesIO

import openpyxl
import pymupdf
import pytest
from docx import Document
from pptx import Presentation

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


def test_spreadsheet_and_presentation_text_are_extracted():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Pembeli"
    sheet.append(["nama", "nik"])
    sheet.append(["Budi Contoh", "1234567890123456"])
    workbook_buffer = BytesIO()
    workbook.save(workbook_buffer)
    spreadsheet = extract_document("buyers.xlsx", workbook_buffer.getvalue())

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Ringkasan Pembeli"
    text_buffer = BytesIO()
    presentation.save(text_buffer)
    slides = extract_document("buyers.pptx", text_buffer.getvalue())

    assert "Budi Contoh" in spreadsheet.pages[0].text
    assert "1234567890123456" in spreadsheet.pages[0].text
    assert "Ringkasan Pembeli" in slides.pages[0].text


def test_csv_is_read_as_document_text():
    result = extract_document(
        "buyers.csv", b"nama,nik\nBudi Contoh,1234567890123456\n"
    )

    assert "nama: Budi Contoh" in result.pages[0].text
    assert "nik: 1234567890123456" in result.pages[0].text


def test_pdf_text_is_extracted_with_page_number():
    document = pymupdf.open()
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
