"""Long-term user memory tools backed by AsyncDatabricksStore.

These tools let the agent save/retrieve/delete user-specific facts
across conversations. Memories are stored as vectors in Lakebase and
searchable via semantic similarity.

Memory is scoped per user_id (from Databricks SSO on deployed apps,
or hardcoded in local dev). Tools are only available when a user_id
is present in the request.
"""

import json
import logging

from langchain_core.tools import tool

_log = logging.getLogger(__name__)


def create_memory_tools(store, user_id: str) -> list:
    """Create memory tools bound to a specific store and user namespace.

    Returns empty list if store is None or user_id is empty.
    """
    if store is None or not user_id:
        return []

    namespace = ("user_memories", user_id.replace(".", "-"))

    @tool
    def get_user_memory(query: str) -> str:
        """Search the user's saved memories by semantic similarity. Use this before answering to check if the user has stated preferences, facts, or context in previous conversations."""
        try:
            results = store.search(namespace, query=query, limit=5)
            if not results:
                return "No memories found for this user."
            return "\n".join(
                f"- {item.value.get('data', str(item.value))}" for item in results
            )
        except Exception as e:
            _log.warning("get_user_memory failed: %s", e)
            return f"Error retrieving memories: {e}"

    @tool
    def save_user_memory(memory_key: str, memory_data_json: str) -> str:
        """Save a fact or preference about the user for future conversations. memory_key is a short identifier (e.g. 'preferred_seat'), memory_data_json is JSON with the data to remember."""
        try:
            data = json.loads(memory_data_json)
        except json.JSONDecodeError:
            data = {"data": memory_data_json}
        try:
            store.put(namespace, memory_key, data)
            return f"Saved memory '{memory_key}'."
        except Exception as e:
            _log.warning("save_user_memory failed: %s", e)
            return f"Error saving memory: {e}"

    @tool
    def delete_user_memory(memory_key: str) -> str:
        """Delete a specific saved memory by key. Use when the user asks to forget something."""
        try:
            store.delete(namespace, memory_key)
            return f"Deleted memory '{memory_key}'."
        except Exception as e:
            _log.warning("delete_user_memory failed: %s", e)
            return f"Error deleting memory: {e}"

    return [get_user_memory, save_user_memory, delete_user_memory]
