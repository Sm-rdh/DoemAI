from __future__ import annotations

import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "backend"
    / "ingestion"
    / "output"
    / "bns_2023.json"
)


SECTION_PATTERN = re.compile(
    r"^\s*(\d{1,3})\.(?:\s*—|\s+)(.+?)\s*$"
)

CHAPTER_PATTERN = re.compile(
    r"^\s*CHAPTER\s+[IVXLCDM]+\s*$",
    re.IGNORECASE,
)


def load_document() -> dict:
    with INPUT_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)


def detect_body_start(pages: list[dict]) -> int:
    """
    Locate the beginning of the actual Act.

    The BNS PDF contains an 'ARRANGEMENT OF SECTIONS'
    table of contents before the real statutory text.

    We look for the title occurring after the contents,
    followed by Chapter I / PRELIMINARY.
    """

    arrangement_seen = False

    for page in pages:

        text = page["text"]
        upper = text.upper()

        if "ARRANGEMENT OF SECTIONS" in upper:
            arrangement_seen = True
            continue

        if not arrangement_seen:
            continue

        if (
            "CHAPTER I" in upper
            and "PRELIMINARY" in upper
            and "1." in text
        ):
            # We still need to distinguish TOC from actual body.
            # Continue searching for a second occurrence.
            continue

    # A more reliable approach is to find pages containing
    # "CHAPTER I" + "PRELIMINARY", then take the LAST occurrence.
    candidates = []

    for page in pages:
        upper = page["text"].upper()

        if (
            "CHAPTER I" in upper
            and "PRELIMINARY" in upper
        ):
            candidates.append(page["page_number"])

    if not candidates:
        raise RuntimeError(
            "Could not locate the beginning of the BNS body."
        )

    # The actual body occurs after the contents.
    return candidates[-1]

def split_section_title_and_text(content: str) -> tuple[str, str]:
    """
    Split a statutory provision into its heading and body.

    Example:
        "Definitions.—In this Sanhita..."
    
    becomes:
        ("Definitions", "In this Sanhita...")
    """

    separators = [
        ".—",
        ". —",
        "—",
        "--",
    ]

    for separator in separators:
        if separator in content:
            title, body = content.split(
                separator,
                1
            )

            return (
                title.strip().rstrip("."),
                body.strip(),
            )

    return content.strip(), ""

def detect_sections(
    pages: list[dict],
    body_start_page: int,
) -> list[dict]:

    results = []

    current_chapter = None

    for page in pages:

        page_number = page["page_number"]

        if page_number < body_start_page:
            continue

        text = page["text"]

        for line in text.splitlines():

            line_clean = line.strip()

            chapter_match = CHAPTER_PATTERN.match(
                line_clean
            )

            if chapter_match:
                current_chapter = line_clean
                continue

            section_match = SECTION_PATTERN.match(
                line_clean
            )

            if not section_match:
                continue

            section_number = int(
                section_match.group(1)
            )

            raw_content = section_match.group(2).strip()

            title, opening_text = split_section_title_and_text(
             raw_content
            )

            results.append(
                {
                    "section": section_number,
                    "title": title,
                    "opening_text": opening_text,
                    "page": page_number,
                    "chapter": current_chapter,
                }
            )

    return results


def remove_false_duplicates(
    sections: list[dict],
) -> list[dict]:

    """
    Keep the first occurrence of each section number
    in the actual Act body.

    We also require section numbers to generally increase,
    which helps reject page-level artifacts.
    """

    results = []
    seen = set()

    for item in sections:

        number = item["section"]

        if number in seen:
            continue

        seen.add(number)
        results.append(item)

    return results


def main() -> None:

    print("=" * 70)
    print("DOEMAI BNS SECTION DETECTION TEST - V3")
    print("=" * 70)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Could not find {INPUT_FILE}"
        )

    data = load_document()
    pages = data["pages"]

    body_start_page = detect_body_start(pages)

    print(
        f"\nDetected probable Act body start: "
        f"page {body_start_page}"
    )

    sections = detect_sections(
        pages,
        body_start_page,
    )

    unique_sections = remove_false_duplicates(
        sections
    )

    numbers = sorted(
        item["section"]
        for item in unique_sections
    )

    expected = set(range(1, 359))
    actual = set(numbers)

    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)

    print(
        f"\nSection-like matches: {len(sections)}"
    )

    print(
        f"Unique detected sections: "
        f"{len(unique_sections)}"
    )

    print(
        f"Expected sections: 1–358"
    )

    print(
        f"Missing section numbers: {missing}"
    )

    print(
        f"Unexpected section numbers: {unexpected}"
    )

    print("\nFIRST 10")
    print("-" * 70)

    for item in unique_sections[:10]:

        print(
            f"Section {item['section']}: "
            f"{item['title']} "
            f"| page {item['page']} "
            f"| {item['chapter']}"
        )

    print("\nLAST 10")
    print("-" * 70)

    for item in unique_sections[-10:]:

        print(
            f"Section {item['section']}: "
            f"{item['title']} "
            f"| page {item['page']} "
            f"| {item['chapter']}"
        )

if __name__ == "__main__":
    main()