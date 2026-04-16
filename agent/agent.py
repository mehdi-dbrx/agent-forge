import os
import re
from pathlib import Path
from typing import AsyncGenerator, Optional

import mlflow
from databricks.sdk import WorkspaceClient
from databricks_langchain import ChatDatabricks, DatabricksMCPServer, DatabricksMultiServerMCPClient
from langchain.agents import create_agent
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
    to_chat_completions_input,
)

from agent.genie_capture import wrap_for_genie_capture
from agent.utils import (
    get_databricks_host_from_env,
    process_agent_astream_events,
)
from tools.query_flights_at_risk import query_flights_at_risk
from tools.update_flight_risk import update_flight_risk

# New same-domain tools: append to tools in init_agent and implement under tools/<name>/
mlflow.langchain.autolog()
sp_workspace_client = WorkspaceClient()



def init_mcp_client(workspace_client: WorkspaceClient) -> DatabricksMultiServerMCPClient:
    host_name = get_databricks_host_from_env()
    servers = []
    genie_checkin_id = os.environ.get("PROJECT_GENIE_CHECKIN", "").strip()
    if genie_checkin_id:
        servers.append(
            DatabricksMCPServer(
                name="genie-checkin",
                url=f"{host_name}/api/2.0/mcp/genie/{genie_checkin_id}",
                workspace_client=workspace_client,
            ),
        )
    return DatabricksMultiServerMCPClient(servers)


async def init_agent(workspace_client: Optional[WorkspaceClient] = None):
    """Returns (agent, llm_supports_streaming).

    llm_supports_streaming=False when the remote endpoint has output guardrails
    that reject streaming calls. The caller must then use stream_mode=["updates"]
    only — LangGraph's "messages" mode forces the LLM into streaming regardless
    of the ChatDatabricks.streaming attribute.
    """
    mcp_client = init_mcp_client(workspace_client or sp_workspace_client)
    mcp_tools = await mcp_client.get_tools()
    wrapped_tools = [wrap_for_genie_capture(t) for t in mcp_tools]
    tools = list(wrapped_tools) + [
        query_flights_at_risk,
        update_flight_risk,
    ]
    endpoint = os.environ.get("AGENT_MODEL_ENDPOINT", "").strip()
    if not endpoint:
        raise ValueError("AGENT_MODEL_ENDPOINT must be set (endpoint name or full invocations URL)")
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        # Cross-workspace endpoint: build a WorkspaceClient for the remote host
        m = re.search(r"/serving-endpoints/([^/]+)/invocations", endpoint)
        if not m:
            raise ValueError(f"Cannot parse endpoint name from URL: {endpoint}")
        name = m.group(1)
        host = endpoint[: m.start()]  # everything before /serving-endpoints/...
        token = os.environ.get("AGENT_MODEL_TOKEN", "").strip()
        if not token:
            raise ValueError("AGENT_MODEL_TOKEN must be set for cross-workspace endpoint")
        # Temporarily remove local-workspace env vars so the SDK uses only the
        # explicitly passed remote host + token. Without this:
        # - On Databricks Apps: CLIENT_ID/SECRET cause "multiple auth methods"
        # - Locally: DATABRICKS_TOKEN (fevm PAT) overrides the remote PAT → "Invalid Token"
        _oauth_keys = [
            "DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET",
            "DATABRICKS_CONFIG_PROFILE",
            "DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WORKSPACE_ID",
        ]
        _saved = {k: os.environ.pop(k) for k in _oauth_keys if k in os.environ}
        try:
            remote_client = WorkspaceClient(host=host, token=token)
        finally:
            os.environ.update(_saved)
        llm = ChatDatabricks(endpoint=name, workspace_client=remote_client)
        return create_agent(tools=tools, model=llm), False
    else:
        llm = ChatDatabricks(endpoint=endpoint)
        return create_agent(tools=tools, model=llm), True


@invoke()
async def non_streaming(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    outputs = [
        event.item
        async for event in streaming(request)
        if event.type == "response.output_item.done"
    ]
    return ResponsesAgentResponse(output=outputs)


def _load_system_prompt() -> str:
    base = Path(__file__).resolve().parents[1] / "prompt"
    main_path = base / "main.prompt"
    kb_path = base / "knowledge.base"
    content = main_path.read_text(encoding="utf-8").strip() if main_path.exists() else ""
    kb_content = kb_path.read_text(encoding="utf-8").strip() if kb_path.exists() else ""
    return content.replace("{{KNOWLEDGE_BASE}}", kb_content)


async def _run_agent(request: ResponsesAgentRequest) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    agent, llm_supports_streaming = await init_agent()
    user_messages = to_chat_completions_input([i.model_dump() for i in request.input])
    system_content = _load_system_prompt()
    messages = (
        {"messages": [{"role": "system", "content": system_content}] + user_messages}
        if system_content
        else {"messages": user_messages}
    )
    # "messages" stream_mode forces LangGraph to call the LLM with stream=True,
    # which breaks endpoints with output guardrails. Use "updates" only in that case.
    stream_mode = ["updates", "messages"] if llm_supports_streaming else ["updates"]
    async for event in process_agent_astream_events(
        agent.astream(input=messages, stream_mode=stream_mode)
    ):
        yield event


@stream()
async def streaming(
    request: ResponsesAgentRequest,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    try:
        async for event in _run_agent(request):
            yield event
    except BaseException as e:
        # Unwrap ExceptionGroup (e.g. from MCP/anyio TaskGroup) so the real error is surfaced
        if isinstance(e, BaseExceptionGroup) and len(e.exceptions) == 1:
            raise e.exceptions[0] from e
        raise
