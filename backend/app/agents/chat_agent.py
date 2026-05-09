from pydantic import BaseModel
from pydantic_ai import Agent


class ChatAssistantResult(BaseModel):
    response: str


def build_chat_agent() -> Agent[None, ChatAssistantResult]:
    return Agent(
        "openai:gpt-4o-mini",
        result_type=ChatAssistantResult,
        system_prompt=(
            "You are the general assistant for a Targeted File Review application. "
            "Help users navigate reviews, forms, dashboard data, and evaluation workflows. "
            "When connected to the UI, synchronize useful state through the CopilotKit AG-UI "
            "protocol rather than inventing hidden state."
        ),
    )

