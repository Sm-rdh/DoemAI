from pathlib import Path
import json


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "backend"
    / "ingestion"
    / "output"
    / "bns_2023.json"
)


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Could not find: {INPUT_FILE}"
        )

    with INPUT_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:
        data = json.load(file)

    print("=" * 70)
    print("DOEMAI DOCUMENT INSPECTION")
    print("=" * 70)

    document = data["document"]

    print("\nDOCUMENT METADATA")
    print("-" * 70)

    for key, value in document.items():
        print(f"{key}: {value}")

    print("\nDOCUMENT STATISTICS")
    print("-" * 70)

    print(f"Pages:      {data['page_count']}")
    print(f"Characters: {data['character_count']:,}")

    print("\nFIRST 3 PAGES")
    print("-" * 70)

    for page in data["pages"][:3]:
        print(f"\n--- PAGE {page['page_number']} ---\n")
        print(page["text"][:4000])


if __name__ == "__main__":
    main()