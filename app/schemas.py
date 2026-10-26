
from pydantic import BaseModel, Field, field_validator


class AgentRequest(BaseModel):
    request: str = Field(
        min_length=1,
        max_length=5000,
        description="Natural-language business document request",
    )

    @field_validator("request")
    @classmethod
    def normalize_request(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Request cannot be empty.")
        return value


class AgentResponse(BaseModel):
    status: str
    request_summary: str
    title: str
    plan: list[str]
    assumptions: list[str]
    validation: dict
    document_id: str
    agent_summary: str
