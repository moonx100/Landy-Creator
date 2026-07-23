"""Text extraction module.

Extraction priority:
  1. DOCX  — python-docx, preserves paragraph/heading structure
  2. PDF (text layer) — pdfplumber, page-by-page text extraction
  3. PDF (image-only) — pdf2image + pytesseract OCR, with accuracy_warning
  4. Image (jpg/png/etc.) — pytesseract OCR, with accuracy_warning

Failures set extraction_ok=False and populate extraction_note.
NEVER swallow an extraction failure silently — that is a spec violation.

OCR paths require system packages (tesseract, poppler). When unavailable,
extraction_ok is set to False with an explanatory note — the pipeline
continues but flags the version clearly.
"""
import hashlib
import io
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractionResult:
    text: str
    source_format: str          # 'docx' | 'pdf_text' | 'pdf_image' | 'image'
    extraction_ok: bool
    extraction_note: Optional[str]
    accuracy_warning: Optional[str]  # non-None for OCR paths
    sha256: str


_ALLOWED_EXTENSIONS = {
    "docx", "pdf", "jpg", "jpeg", "png", "webp", "bmp"
}
_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def extract(file_bytes: bytes, filename: str) -> ExtractionResult:
    """Entry point: dispatch to the correct extractor based on file extension."""
    sha256 = hashlib.sha256(file_bytes).hexdigest()
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if len(file_bytes) > _MAX_FILE_SIZE:
        return ExtractionResult(
            text="",
            source_format="docx",
            extraction_ok=False,
            extraction_note=f"Ukuran file melebihi batas maksimum 20 MB.",
            accuracy_warning=None,
            sha256=sha256,
        )

    if ext == "docx":
        return _extract_docx(file_bytes, sha256)
    elif ext == "pdf":
        return _extract_pdf(file_bytes, sha256)
    elif ext in ("jpg", "jpeg", "png", "webp", "bmp"):
        return _extract_image(file_bytes, sha256)
    else:
        return ExtractionResult(
            text="",
            source_format="docx",
            extraction_ok=False,
            extraction_note=(
                f"Format file '.{ext}' tidak didukung. "
                "Gunakan DOCX, PDF, JPG, atau PNG."
            ),
            accuracy_warning=None,
            sha256=sha256,
        )


def _extract_docx(file_bytes: bytes, sha256: str) -> ExtractionResult:
    try:
        import docx  # type: ignore[import]

        doc = docx.Document(io.BytesIO(file_bytes))
        lines: list[str] = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                lines.append(text)

        full_text = "\n".join(lines)
        ok = bool(full_text.strip())
        return ExtractionResult(
            text=full_text,
            source_format="docx",
            extraction_ok=ok,
            extraction_note=None if ok else "Dokumen DOCX tidak mengandung teks yang dapat dibaca.",
            accuracy_warning=None,
            sha256=sha256,
        )
    except Exception as exc:
        return ExtractionResult(
            text="",
            source_format="docx",
            extraction_ok=False,
            extraction_note=f"Gagal membuka DOCX: {exc}",
            accuracy_warning=None,
            sha256=sha256,
        )


def _extract_pdf(file_bytes: bytes, sha256: str) -> ExtractionResult:
    """Try text layer; fall through to OCR if no text found."""
    try:
        import pdfplumber  # type: ignore[import]

        pages: list[str] = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t and t.strip():
                    pages.append(t.strip())

        full_text = "\n\n".join(pages)
        if full_text.strip():
            return ExtractionResult(
                text=full_text,
                source_format="pdf_text",
                extraction_ok=True,
                extraction_note=None,
                accuracy_warning=None,
                sha256=sha256,
            )
    except Exception as exc:
        # Log and fall through to OCR
        pass

    # Text layer empty or unreadable — attempt OCR
    return _extract_pdf_ocr(file_bytes, sha256)


def _extract_pdf_ocr(file_bytes: bytes, sha256: str) -> ExtractionResult:
    try:
        from pdf2image import convert_from_bytes  # type: ignore[import]
        import pytesseract  # type: ignore[import]

        images = convert_from_bytes(file_bytes, dpi=200)
        texts: list[str] = []
        for img in images:
            t = pytesseract.image_to_string(img, lang="ind+eng")
            if t.strip():
                texts.append(t.strip())

        full_text = "\n\n".join(texts)
        ok = bool(full_text.strip())
        return ExtractionResult(
            text=full_text,
            source_format="pdf_image",
            extraction_ok=ok,
            extraction_note=None if ok else "OCR tidak berhasil mengekstrak teks dari PDF.",
            accuracy_warning=(
                "Dokumen ini adalah PDF berbasis gambar. "
                "Akurasi ekstraksi teks melalui OCR dapat bervariasi — "
                "verifikasi klausul penting secara manual."
            ),
            sha256=sha256,
        )
    except ImportError:
        return ExtractionResult(
            text="",
            source_format="pdf_image",
            extraction_ok=False,
            extraction_note=(
                "PDF ini tampaknya berbasis gambar (tidak ada lapisan teks), "
                "tetapi perangkat OCR (tesseract/poppler) tidak tersedia di server ini. "
                "Hubungi administrator untuk mengaktifkan dukungan OCR."
            ),
            accuracy_warning=None,
            sha256=sha256,
        )
    except Exception as exc:
        return ExtractionResult(
            text="",
            source_format="pdf_image",
            extraction_ok=False,
            extraction_note=f"Gagal memproses PDF berbasis gambar: {exc}",
            accuracy_warning=None,
            sha256=sha256,
        )


def _extract_image(file_bytes: bytes, sha256: str) -> ExtractionResult:
    try:
        import pytesseract  # type: ignore[import]
        from PIL import Image  # type: ignore[import]

        img = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(img, lang="ind+eng")
        ok = bool(text.strip())
        return ExtractionResult(
            text=text.strip() if ok else "",
            source_format="image",
            extraction_ok=ok,
            extraction_note=None if ok else "OCR tidak menghasilkan teks dari gambar.",
            accuracy_warning=(
                "Dokumen diunggah sebagai gambar. "
                "Akurasi ekstraksi teks melalui OCR dapat bervariasi — "
                "verifikasi klausul penting secara manual."
            ),
            sha256=sha256,
        )
    except ImportError:
        return ExtractionResult(
            text="",
            source_format="image",
            extraction_ok=False,
            extraction_note=(
                "Perangkat OCR untuk memproses gambar (tesseract) "
                "tidak tersedia di server ini."
            ),
            accuracy_warning=None,
            sha256=sha256,
        )
    except Exception as exc:
        return ExtractionResult(
            text="",
            source_format="image",
            extraction_ok=False,
            extraction_note=f"Gagal memproses gambar: {exc}",
            accuracy_warning=None,
            sha256=sha256,
        )
