from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    context: dict = Field(default_factory=dict)


class ChatMessageResponse(BaseModel):
    reply: str
    escalation_triggered: bool = False
