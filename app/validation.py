
from pathlib import Path
from docx import Document


def validate_document(
    file_path: str,
    required_sections: list[str],
) -> dict:

    path = Path(file_path)

    if not path.is_file():
        return {"valid": False, "issues": ["Document does not exist."]}

    if path.stat().st_size == 0:
        return {"valid": False, "issues": ["Document is empty."]}

    try:
        doc = Document(path)
    except Exception:
        return {
            "valid": False,
            "issues": ["The file could not be opened as a DOCX document."],
        }

    headings = {
        p.text.strip().casefold()
        for p in doc.paragraphs
        if p.style.name.startswith("Heading")
    }

    missing = [
        section for section in required_sections
        if section.strip().casefold() not in headings
    ]

    issues = []
    if missing:
        issues.append("Missing required sections: " + ", ".join(missing))

    return {
        "valid": not issues,
        "issues": issues,
        "missing_sections": missing,
        "file_size_bytes": path.stat().st_size,
    }
