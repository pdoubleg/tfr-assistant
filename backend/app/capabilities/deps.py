"""Agent dependency objects shared by assistant capabilities."""

from dataclasses import dataclass, field

from pydantic_ai.ag_ui import StateDeps

from app.core.config import Settings, get_settings
from app.models.chat_state import TFRChatState


@dataclass
class TFRChatDeps(StateDeps[TFRChatState]):
    """AG-UI state plus backend services needed by chat capabilities."""

    settings: Settings = field(default_factory=get_settings)
