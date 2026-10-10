from typing import NoReturn

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.ai.errors import AiProviderError
from app.api.deps import get_db
from app.api.errors import api_error
from app.schemas.conversation import ConversationStartResponse, MessageRequest, MessageResponse
from app.services.conversation import ConversationLimitError, UnknownConversationError, orchestrator

router = APIRouter(prefix="/conversations", tags=["conversations"])

# Too many requests is a 429; anything else the limits refuse (too long a
# message, too long a conversation) is about this request itself - 422.
_LIMIT_STATUS = {"rate_limited": 429}


def _client_key(request: Request) -> str | None:
    """The caller's IP, for the orchestrator's per-client limits."""
    return request.client.host if request.client else None


def _limit_error(exc: ConversationLimitError) -> NoReturn:
    api_error(_LIMIT_STATUS.get(exc.code, 422), exc.code, f"Refused by a chat limit: {exc.code}")


@router.post("", response_model=ConversationStartResponse, status_code=201)
def start_conversation(request: Request) -> ConversationStartResponse:
    try:
        conversation_id, intro_message = orchestrator.start_conversation(client_key=_client_key(request))
    except ConversationLimitError as exc:
        _limit_error(exc)
    return ConversationStartResponse(conversation_id=conversation_id, intro_message=intro_message)


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
def send_message(
    conversation_id: str, body: MessageRequest, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    try:
        return orchestrator.handle_message(db, conversation_id, body.text, client_key=_client_key(request))
    except UnknownConversationError:
        api_error(404, "conversation_not_found", f"No conversation with id {conversation_id}")
    except ConversationLimitError as exc:
        _limit_error(exc)
    except RuntimeError as exc:
        # AI layer not configured (missing ANTHROPIC_API_KEY) - see
        # app/ai/client.py.
        api_error(503, "ai_not_configured", str(exc))
    except AiProviderError as exc:
        # The provider rejected/failed the call (bad key, rate limit, ...) -
        # a bad-gateway-style failure, distinct from "not configured" above.
        api_error(502, exc.code, str(exc))
