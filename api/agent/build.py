from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware

from api.agent.fake import ScriptedChatModel
from api.agent.middleware import RouteMiddleware, ShopState, ShortlistGuard
from api.agent.prompts import SYSTEM
from api.agent.tools import TOOLS
from api.settings import get_settings


def build_agent(checkpointer):
    settings = get_settings()
    if settings.fake_llm:
        model = ScriptedChatModel()
    else:
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model="gpt-6-luna",
            use_responses_api=True,
            api_key=settings.openai_api_key or None,
        )
    middleware = [RouteMiddleware(), ShortlistGuard()]
    if not settings.fake_llm:
        middleware.append(SummarizationMiddleware(model=model, trigger=("tokens", 6000), keep=("messages", 12)))
    return create_agent(
        model,
        tools=TOOLS,
        system_prompt=SYSTEM,
        middleware=middleware,
        state_schema=ShopState,
        checkpointer=checkpointer,
    )
