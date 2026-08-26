from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "backend"
    / "ingestion"
    / "output"
    / "bns_2023.json"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "backend"
    / "ingestion"
    / "output"
    / "chunks"
    / "bns"
)


# ============================================================
# PATTERNS
# ============================================================

# Matches:
# 1. Title
# 1.—Title
# 1. — Title
# 255.—Title
SECTION_PATTERN = re.compile(
    r"^\s*(\d{1,3})\.\s*(?:[—–-]\s*)?(.+?)\s*$"
)

CHAPTER_PATTERN = re.compile(
    r"^\s*CHAPTER\s+[IVXLCDM]+\s*$",
    re.IGNORECASE,
)


# ============================================================
# LOAD DOCUMENT
# ============================================================

def load_document() -> dict[str, Any]:
    with INPUT_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


# ============================================================
# FIND ACT BODY
# ============================================================

def detect_body_start_page(
    pages: list[dict[str, Any]],
) -> int:
    """
    Find the actual beginning of the statutory body.

    The BNS PDF contains front matter and an arrangement of
    sections before the actual provisions.

    The last occurrence of CHAPTER I + PRELIMINARY is used.
    """

    candidates: list[int] = []

    for page in pages:

        upper = page["text"].upper()

        if (
            "CHAPTER I" in upper
            and "PRELIMINARY" in upper
        ):
            candidates.append(
                page["page_number"]
            )

    if not candidates:
        raise RuntimeError(
            "Could not detect the beginning of the BNS body."
        )

    return candidates[-1]


# ============================================================
# SECTION HEADER PARSING
# ============================================================

def split_section_heading(
    content: str,
) -> tuple[str, str]:
    """
    Split a section's first line into:

        title
        opening body text

    Handles several dash/spacing variants commonly produced
    by legal PDFs.
    """

    # Try to split at the first statutory dash.
    match = re.search(
        r"^(.*?)\.\s*[—–-]\s*(.*)$",
        content,
    )

    if match:

        title = match.group(1).strip()
        body = match.group(2).strip()

        return (
            title.rstrip("."),
            body,
        )

    # Some PDFs may omit the period before the dash.
    match = re.search(
        r"^(.*?)\s*[—–-]\s+(.*)$",
        content,
    )

    if match:

        title = match.group(1).strip()
        body = match.group(2).strip()

        return (
            title.rstrip("."),
            body,
        )

    return (
        content.strip().rstrip("."),
        "",
    )


def parse_section_header(
    line: str,
) -> tuple[int, str, str] | None:

    match = SECTION_PATTERN.match(
        line.strip()
    )

    if not match:
        return None

    section_number = int(
        match.group(1)
    )

    raw_content = match.group(2).strip()

    title, opening_text = (
        split_section_heading(
            raw_content
        )
    )

    return (
        section_number,
        title,
        opening_text,
    )


# ============================================================
# FINALIZE SECTION
# ============================================================

def finalize_section(
    current: dict[str, Any],
    page_end: int,
) -> dict[str, Any]:

    body_text = "\n".join(
        current["lines"]
    ).strip()

    section_number = current["section_number"]
    title = current["section_title"]

    if body_text:

        full_text = (
            f"Section {section_number}. "
            f"{title}.\n\n"
            f"{body_text}"
        )

    else:

        full_text = (
            f"Section {section_number}. "
            f"{title}."
        )

    return {
        "chunk_id": f"BNS_{section_number}",
        "document": (
            "Bharatiya Nyaya Sanhita, 2023"
        ),
        "short_name": "BNS",
        "document_type": "central_act",
        "legal_domain": "criminal_law",
        "status": "current",
        "jurisdiction": "India",
        "chapter": current["chapter"],
        "section_number": section_number,
        "section_title": title,
        "page_start": current["page_start"],
        "page_end": page_end,
        "text": full_text,
    }


# ============================================================
# CREATE CHUNKS
# ============================================================

def create_chunks(
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    body_start_page = detect_body_start_page(
        pages
    )

    print(
        f"Detected Act body start: "
        f"page {body_start_page}"
    )

    chunks: list[dict[str, Any]] = []

    current_section: dict[str, Any] | None = None
    current_chapter: str | None = None

    # Important:
    # BNS sections are expected in ascending order.
    next_expected_section = 1

    for page in pages:

        page_number = page["page_number"]

        # Ignore the front matter / contents.
        if page_number < body_start_page:
            continue

        for line in page["text"].splitlines():

            clean_line = line.strip()

            if not clean_line:

                if current_section:
                    current_section["lines"].append("")

                continue

            # ------------------------------------------------
            # CHAPTER
            # ------------------------------------------------

            chapter_match = CHAPTER_PATTERN.match(
                clean_line
            )

            if chapter_match:

                current_chapter = clean_line

                continue

            # ------------------------------------------------
            # POSSIBLE SECTION
            # ------------------------------------------------

            parsed = parse_section_header(
                clean_line
            )

            if parsed:

                (
                    section_number,
                    title,
                    opening_text,
                ) = parsed

                # --------------------------------------------
                # SEQUENTIAL VALIDATION
                # --------------------------------------------
                #
                # Only accept the next expected statutory
                # section.
                #
                # This eliminates false matches such as
                # notification dates beginning with:
                #
                # 1. ...
                # 2. ...
                #
                # after those sections have already been seen.

                if section_number != next_expected_section:

                    # It is not the next actual section.
                    # Treat it as ordinary body text.
                    if current_section:

                        current_section["lines"].append(
                            clean_line
                        )

                    continue

                # --------------------------------------------
                # SAVE PREVIOUS SECTION
                # --------------------------------------------

                if current_section is not None:

                    chunks.append(
                        finalize_section(
                            current_section,
                            page_number,
                        )
                    )

                # --------------------------------------------
                # START NEW SECTION
                # --------------------------------------------

                current_section = {
                    "section_number": section_number,
                    "section_title": title,
                    "chapter": current_chapter,
                    "page_start": page_number,
                    "lines": [],
                }

                if opening_text:

                    current_section["lines"].append(
                        opening_text
                    )

                next_expected_section += 1

                continue

            # ------------------------------------------------
            # NORMAL BODY TEXT
            # ------------------------------------------------

            if current_section:

                current_section["lines"].append(
                    clean_line
                )

    # --------------------------------------------------------
    # SAVE FINAL SECTION
    # --------------------------------------------------------

    if current_section is not None:

        chunks.append(
            finalize_section(
                current_section,
                pages[-1]["page_number"],
            )
        )

    return chunks


# ============================================================
# VALIDATION
# ============================================================

def validate_chunks(
    chunks: list[dict[str, Any]],
) -> None:

    expected = set(
        range(1, 359)
    )

    actual = {
        chunk["section_number"]
        for chunk in chunks
    }

    missing = sorted(
        expected - actual
    )

    unexpected = sorted(
        actual - expected
    )

    duplicates: list[int] = []

    seen: set[int] = set()

    for chunk in chunks:

        number = chunk["section_number"]

        if number in seen:
            duplicates.append(number)

        seen.add(number)

    print(
        f"\nExpected sections: 358"
    )

    print(
        f"Actual chunks: {len(chunks)}"
    )

    print(
        f"Missing sections: {missing}"
    )

    print(
        f"Unexpected sections: {unexpected}"
    )

    print(
        f"Duplicate section numbers: "
        f"{sorted(set(duplicates))}"
    )


# ============================================================
# SAVE CHUNKS
# ============================================================

def save_chunks(
    chunks: list[dict[str, Any]],
) -> None:

    # Delete previously generated BNS chunks.
    if OUTPUT_DIR.exists():

        for old_file in OUTPUT_DIR.glob(
            "BNS_*.json"
        ):
            old_file.unlink()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for chunk in chunks:

        output_file = (
            OUTPUT_DIR
            / f"{chunk['chunk_id']}.json"
        )

        with output_file.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                chunk,
                file,
                ensure_ascii=False,
                indent=2,
            )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print("=" * 70)
    print("DOEMAI LEGAL CHUNKER - V3")
    print("=" * 70)

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"Missing input file: {INPUT_FILE}"
        )

    data = load_document()

    chunks = create_chunks(
        data["pages"]
    )

    validate_chunks(
        chunks
    )

    save_chunks(
        chunks
    )

    print(
        f"\nSaved chunks to:"
        f"\n{OUTPUT_DIR}"
    )

    # --------------------------------------------------------
    # FIRST 3
    # --------------------------------------------------------

    print("\nFIRST 3 CHUNKS")
    print("-" * 70)

    for chunk in chunks[:3]:

        print(
            f"\n[{chunk['chunk_id']}]"
        )

        print(
            f"Title: "
            f"{chunk['section_title']}"
        )

        print(
            f"Chapter: "
            f"{chunk['chapter']}"
        )

        print(
            f"Pages: "
            f"{chunk['page_start']}"
            f"-"
            f"{chunk['page_end']}"
        )

        print(
            f"\n{chunk['text'][:1000]}"
        )

    # --------------------------------------------------------
    # SECTION 103
    # --------------------------------------------------------

    section_103 = next(
        (
            chunk
            for chunk in chunks
            if chunk["section_number"] == 103
        ),
        None,
    )

    if section_103:

        print(
            "\nSECTION 103 CHECK"
        )

        print(
            "-" * 70
        )

        print(
            f"Title: "
            f"{section_103['section_title']}"
        )

        print(
            f"Chapter: "
            f"{section_103['chapter']}"
        )

        print(
            f"Pages: "
            f"{section_103['page_start']}"
            f"-"
            f"{section_103['page_end']}"
        )

    # --------------------------------------------------------
    # LAST SECTION
    # --------------------------------------------------------

    last = chunks[-1]

    print(
        "\nLAST SECTION"
    )

    print(
        "-" * 70
    )

    print(
        f"[{last['chunk_id']}] "
        f"{last['section_title']}"
    )

    print(
        f"Pages: "
        f"{last['page_start']}"
        f"-"
        f"{last['page_end']}"
    )


if __name__ == "__main__":
    main()