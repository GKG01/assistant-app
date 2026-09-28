from fastapi import APIRouter, HTTPException

from agent.schemas import AgentRequest, AgentResponse

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/message", response_model=AgentResponse)
async def message(request: AgentRequest) -> AgentResponse:
    raise HTTPException(501, "Agent orchestration is not implemented.")
