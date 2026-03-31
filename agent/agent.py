import os
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
from tools.back_to_normal import back_to_normal
from tools.confirm_arrival import confirm_arrival
from tools.create_border_incident import create_border_incident
from tools.create_checkin_incident import create_checkin_incident
from tools.get_current_time import get_current_time
from tools.placeholder_tool import placeholder_tool
from tools.query_available_agents_for_redeployment import query_available_agents_for_redeployment
from tools.query_border_officer_staffing import query_border_officer_staffing
from tools.query_border_officers_by_post import query_border_officers_by_post
from tools.query_border_terminal_details import query_border_terminal_details
from tools.query_checkin_agent_staffing import query_checkin_agent_staffing
from tools.query_checkin_agents_by_counter_status import query_checkin_agents_by_counter_status
from tools.query_checkin_performance_metrics import query_checkin_performance_metrics
from tools.query_staffing_duties import query_staffing_duties
from tools.query_egate_availability import query_egate_availability
from tools.query_flights_at_risk import query_flights_at_risk
from tools.update_border_officer import update_border_officer
from tools.update_checkin_agent import update_checkin_agent
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
    mcp_client = init_mcp_client(workspace_client or sp_workspace_client)
    mcp_tools = await mcp_client.get_tools()
    wrapped_tools = [wrap_for_genie_capture(t) for t in mcp_tools]
    tools = list(wrapped_tools) + [
        get_current_time,
        query_egate_availability,
        query_flights_at_risk,
        query_checkin_performance_metrics,
        query_available_agents_for_redeployment,
        query_border_officer_staffing,
        query_checkin_agent_staffing,
        query_border_terminal_details,
        query_border_officers_by_post,
        query_checkin_agents_by_counter_status,
        query_staffing_duties,
        update_flight_risk,
        back_to_normal,
        create_border_incident,
        create_checkin_incident,
        update_checkin_agent,
        update_border_officer,
        confirm_arrival,
        placeholder_tool,
    ]
    endpoint = os.environ.get("AGENT_MODEL_ENDPOINT", "").strip()
    if not endpoint:
        raise ValueError("AGENT_MODEL_ENDPOINT must be set (e.g. claude-sonnet-4-6, databricks-gpt-5-2)")
    return create_agent(tools=tools, model=ChatDatabricks(endpoint=endpoint))


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


@stream()
async def streaming(
    request: ResponsesAgentRequest,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    try:
        agent = await init_agent()
        user_messages = to_chat_completions_input([i.model_dump() for i in request.input])
        system_content = _load_system_prompt()
        messages = (
            {"messages": [{"role": "system", "content": system_content}] + user_messages}
            if system_content
            else {"messages": user_messages}
        )

        async for event in process_agent_astream_events(
            agent.astream(input=messages, stream_mode=["updates", "messages"])
        ):
            yield event
    except BaseException as e:
        # Unwrap ExceptionGroup (e.g. from MCP/anyio TaskGroup) so the real error is surfaced
        if isinstance(e, BaseExceptionGroup) and len(e.exceptions) == 1:
            raise e.exceptions[0] from e
        raise
