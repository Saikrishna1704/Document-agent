import json
import logging
import os
import re
import uuid

from dotenv import load_dotenv
from google.adk.agents import Agent

from app.document import create_document
from app.validation import validate_document

load_dotenv()

logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
BASE_URL = os.getenv(
    "DOCAGENT_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

EXECUTION_RESULTS: dict[str, dict] = {}
TOOL_ATTEMPTS: dict[str, int] = {}


def create_business_document(
    title: str,
    plan_json: str,
    assumptions_json: str,
    sections_json: str,
    required_sections_json: str,
    document_id: str = "",
) -> dict:

    if not document_id:
        document_id = uuid.uuid4().hex

    if not re.fullmatch(r"[0-9a-f]{32}", document_id):
        return {"status": "error", "message": "Invalid document ID."}

    attempts = TOOL_ATTEMPTS.get(document_id, 0)
    if attempts >= 2:
        return {
            "status": "error",
            "message": "Maximum document creation/repair attempts reached.",
        }

    TOOL_ATTEMPTS[document_id] = attempts + 1

    try:
        title = title.strip()
        if not title or len(title) > 160:
            raise ValueError("Title must contain 1–160 characters.")

        plan = json.loads(plan_json)
        assumptions = json.loads(assumptions_json)
        sections = json.loads(sections_json)
        required = json.loads(required_sections_json)

        if not isinstance(plan, list) or not plan:
            raise ValueError("Plan must be a non-empty list.")

        if not all(isinstance(x, str) and x.strip() for x in plan):
            raise ValueError("Plan items must be non-empty strings.")

        if not isinstance(assumptions, list) or not all(
            isinstance(x, str) for x in assumptions
        ):
            raise ValueError("Assumptions must be strings.")

        if not isinstance(sections, list) or not 1 <= len(sections) <= 20:
            raise ValueError("Provide between 1 and 20 sections.")

        if not isinstance(required, list) or not all(
            isinstance(x, str) and x.strip() for x in required
        ):
            raise ValueError("Required headings must be non-empty strings.")

        for section in sections:
            if not isinstance(section, dict):
                raise ValueError("Every section must be an object.")

            if not isinstance(section.get("heading"), str):
                raise ValueError("Every section needs a heading.")

            if not isinstance(section.get("content"), (str, list)):
                raise ValueError("Section content must be text or a list.")

            if isinstance(section["content"], list):
                for item in section["content"]:
                    if isinstance(item, str):
                        continue
                    if (
                        isinstance(item, dict)
                        and isinstance(item.get("text", ""), str)
                    ):
                        continue
                    raise ValueError("Invalid paragraph or bullet item.")

        file_path = create_document(title, sections, document_id)
        validation = validate_document(file_path, required)

        result = {
            "document_id": document_id,
            "title": title,
            "plan": plan,
            "assumptions": assumptions,
            "file_path": file_path,
            "validation": validation,
            "attempts": TOOL_ATTEMPTS[document_id],
        }
        EXECUTION_RESULTS[document_id] = result

        safe_title = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("._-")
        safe_title = (safe_title or "business_document")[:80] + ".docx"

        return {
            "status": "success" if validation["valid"] else "needs_repair",
            "document_id": document_id,
            "title": title,
            "validation": validation,
            "attempt": TOOL_ATTEMPTS[document_id],
            "document_link": (
                f"[Open {safe_title}]"
                f"({BASE_URL}/documents/{document_id})"
            ) if validation["valid"] else None,
        }

    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("Invalid document tool input: %s", exc)
        return {"status": "error", "message": str(exc)}

    except Exception:
        logger.exception("Document creation failed")
        return {
            "status": "error",
            "message": "Unexpected failure while generating the document.",
        }


root_agent = Agent(
    name="docagent",
    model=MODEL_NAME,
    description=(
        "Plans business document tasks, creates Word documents, "
        "and verifies the resulting artifact."
    ),
    instruction="""
You are Docagent, an autonomous business document agent.

The user may provide a document ID. When one is supplied, pass that exact
ID to create_business_document. When using ADK Web directly, if no ID is
supplied, leave document_id empty so Python generates it.

For every request:

1. Understand the user's goal, audience, and desired document type.
2. Generate a tailored, ordered TODO plan.
3. Identify missing information and state reasonable assumptions explicitly.
4. Create a professional title and useful document content.
5. Choose required headings and use exactly the same heading text in
   the document sections.
6. Call create_business_document with valid JSON strings for the plan,
   assumptions, sections, and required headings.
7. Inspect the tool result.
8. If validation returns needs_repair, fix the missing headings or content
   and retry once, using the same document ID.
9. If the tool reports an error or validation still fails, explain the
   failure honestly.

In your final chat response, display:
- A concise summary of the request.
- The execution plan as a numbered list.
- Any important assumptions.
- The validation outcome.
- The clickable document_link returned by the tool, if successful.

DOCUMENT FORMATTING RULES

- Use clean, semantic section headings without Markdown heading markers.
- Do not wrap headings or labels in literal ** or * characters.
- Use plain text for emphasis labels; the document renderer handles
  Markdown bold and italic within paragraph content.
- Represent bullet lists as individual strings or structured list items
  when possible.
- Avoid HTML entities and escaped whitespace.


The document_link is a browser URL served by the application. Do not
present a local filesystem path as if it were a clickable web link.
Never claim success without a successful tool result.
Do not execute arbitrary code or access unrelated files.
""",
    tools=[create_business_document],
)
