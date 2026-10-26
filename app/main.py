import logging
import re
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import EXECUTION_RESULTS, TOOL_ATTEMPTS, root_agent
from app.document import OUTPUT_DIR
from app.schemas import AgentRequest, AgentResponse

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_NAME = "docagent"
USER_ID = "docagent-api-user"

adk_app = App(name=APP_NAME, root_agent=root_agent)
runner = InMemoryRunner(app=adk_app)

app = FastAPI(
    title="Docagent",
    description="Autonomous business document generation API",
    version="1.0.0",
)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/agent", response_model=AgentResponse)
async def run_agent(payload: AgentRequest):
    document_id = uuid.uuid4().hex

    try:
        session = await runner.session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=document_id,
        )

        message = types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=(
                        f"Document ID: {document_id}\n\n"
                        f"User request:\n{payload.request}"
                    )
                )
            ],
        )

        final_parts = []

        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session.id,
            new_message=message,
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts or []:
                    if part.text:
                        final_parts.append(part.text)

        result = EXECUTION_RESULTS.get(document_id)

        if result is None:
            raise HTTPException(
                status_code=502,
                detail="The agent did not produce a document result.",
            )

        if not result["validation"]["valid"]:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Document validation failed.",
                    "validation": result["validation"],
                },
            )

        return AgentResponse(
            status="success",
            request_summary=payload.request,
            title=result["title"],
            plan=result["plan"],
            assumptions=result["assumptions"],
            validation=result["validation"],
            document_id=document_id,
            agent_summary="\n".join(final_parts).strip()[:2000],
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Agent execution failed")
        raise HTTPException(
            status_code=500,
            detail="Agent execution failed. Check server logs.",
        ) from exc
    finally:
        EXECUTION_RESULTS.pop(document_id, None)
        TOOL_ATTEMPTS.pop(document_id, None)


@app.get("/documents/{document_id}")
async def open_document(document_id: str):
    if not re.fullmatch(r"[0-9a-f]{32}", document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID.")

    path = OUTPUT_DIR / f"{document_id}.docx"

    if not path.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")

    return FileResponse(
        path=path,
        filename=f"docagent_{document_id}.docx",
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    )
