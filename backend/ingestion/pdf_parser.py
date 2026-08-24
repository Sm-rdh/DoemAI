from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import fitz


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
LEGISLATION_DIR = DATA_DIR / "legislation"

CURRENT_DIR = LEGISLATION_DIR / "current"
HISTORICAL_DIR = LEGISLATION_DIR / "historical"

OUTPUT_DIR = PROJECT_ROOT / "backend" / "ingestion" / "output"


# ============================================================
# DOCUMENT METADATA
# ============================================================

DOCUMENT_METADATA: dict[str, dict[str, Any]] = {
    "bns_2023.pdf": {
        "title": "Bharatiya Nyaya Sanhita, 2023",
        "short_name": "BNS",
        "document_type": "central_act",
        "legal_domain": "criminal_law",
        "status": "current",
        "jurisdiction": "India",
    },
    "bnss_2023.pdf": {
        "title": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "short_name": "BNSS",
        "document_type": "central_act",
        "legal_domain": "criminal_procedure",
        "status": "current",
        "jurisdiction": "India",
    },
    "bsa_2023.pdf": {
        "title": "Bharatiya Sakshya Adhiniyam, 2023",
        "short_name": "BSA",
        "document_type": "central_act",
        "legal_domain": "evidence",
        "status": "current",
        "jurisdiction": "India",
    },
    "constitution_of_india.pdf": {
        "title": "Constitution of India",
        "short_name": "Constitution",
        "document_type": "constitution",
        "legal_domain": "constitutional_law",
        "status": "current",
        "jurisdiction": "India",
    },
    "ipc_1860.pdf": {
        "title": "Indian Penal Code, 1860",
        "short_name": "IPC",
        "document_type": "central_act",
        "legal_domain": "criminal_law",
        "status": "historical",
        "jurisdiction": "India",
    },
    "crpc_1973.pdf": {
        "title": "Code of Criminal Procedure, 1973",
        "short_name": "CrPC",
        "document_type": "central_act",
        "legal_domain": "criminal_procedure",
        "status": "historical",
        "jurisdiction": "India",
    },
    "evidence_act_1872.pdf": {
        "title": "Indian Evidence Act, 1872",
        "short_name": "IEA",
        "document_type": "central_act",
        "legal_domain": "evidence",
        "status": "historical",
        "jurisdiction": "India",
    },
}


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text: str) -> str:
    """
    Perform conservative cleaning.

    We do NOT aggressively rewrite the text because legal wording
    must be preserved as accurately as possible.
    """

    text = text.replace("\u00ad", "")
    text = text.replace("\xa0", " ")

    # Normalize repeated spaces while preserving line breaks.
    text = re.sub(r"[ \t]+", " ", text)

    # Remove excessive blank lines.
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()


# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_pdf(pdf_path: Path) -> dict[str, Any]:
    """
    Extract text from one PDF while preserving page boundaries.
    """

    filename = pdf_path.name

    if filename not in DOCUMENT_METADATA:
        metadata = {
            "title": pdf_path.stem,
            "short_name": pdf_path.stem,
            "document_type": "unknown",
            "legal_domain": "unknown",
            "status": "unknown",
            "jurisdiction": "India",
        }
    else:
        metadata = DOCUMENT_METADATA[filename].copy()

    pages: list[dict[str, Any]] = []

    with fitz.open(pdf_path) as document:

        for page_number, page in enumerate(document, start=1):

            raw_text = page.get_text("text")
            cleaned = clean_text(raw_text)

            pages.append(
                {
                    "page_number": page_number,
                    "text": cleaned,
                    "character_count": len(cleaned),
                }
            )

    full_text = "\n\n".join(
        page["text"]
        for page in pages
        if page["text"]
    )

    return {
        "document": metadata,
        "source_file": str(pdf_path.relative_to(PROJECT_ROOT)),
        "page_count": len(pages),
        "character_count": len(full_text),
        "pages": pages,
    }


# ============================================================
# DISCOVER PDF FILES
# ============================================================

def discover_pdfs() -> list[Path]:
    """
    Find all PDFs in the current and historical legislation folders.
    """

    pdfs = []

    for directory in (CURRENT_DIR, HISTORICAL_DIR):
        if directory.exists():
            pdfs.extend(directory.glob("*.pdf"))

    return sorted(pdfs)


# ============================================================
# SAVE JSON
# ============================================================

def save_json(data: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print("=" * 70)
    print("DOEMAI LEGAL PDF INGESTION TEST")
    print("=" * 70)

    pdfs = discover_pdfs()

    if not pdfs:
        print("No PDF files found.")
        return

    print(f"\nFound {len(pdfs)} PDF files:\n")

    for pdf in pdfs:
        print(f"  ✓ {pdf.name}")

    print("\nExtracting...\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    successful = 0
    failed = 0

    for pdf_path in pdfs:

        print("-" * 70)
        print(f"Processing: {pdf_path.name}")

        try:
            result = extract_pdf(pdf_path)

            output_file = (
                OUTPUT_DIR
                / f"{pdf_path.stem}.json"
            )

            save_json(result, output_file)

            print(f"Pages:      {result['page_count']}")
            print(f"Characters: {result['character_count']:,}")
            print(f"Saved to:   {output_file}")

            successful += 1

        except Exception as exc:
            failed += 1

            print(
                f"ERROR processing {pdf_path.name}: {exc}"
            )

    print("\n" + "=" * 70)
    print("INGESTION SUMMARY")
    print("=" * 70)

    print(f"Successful: {successful}")
    print(f"Failed:     {failed}")
    print(f"Total:      {len(pdfs)}")

    print("\nNext step:")
    print(
        "Inspect the generated JSON files before building "
        "the legal-aware chunking system."
    )


if __name__ == "__main__":
    main()