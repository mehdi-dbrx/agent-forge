"""Generate agent prompt files from a domain description using the LLM."""
from __future__ import annotations

from data.gen.llm_client import call_llm_json


SYSTEM_PROMPT = """\
You are an expert AI agent designer for Databricks-native agentic applications.

Given the user's domain description and existing table schemas, generate three prompt files that define the agent's behavior:

Return ONLY a JSON object — no markdown, no explanation:
{{
  "main_prompt": "The full system prompt for the agent. This defines persona, scope, response style, tool usage rules, and domain-specific behavior flows. Use {{{{KNOWLEDGE_BASE}}}} placeholder where the knowledge base should be injected. Be detailed and specific — this is the agent's complete instruction manual.",
  "knowledge_base": "An operational FAQ / knowledge base with domain-specific Q&A entries. Use markdown headers (##) for each topic, bold for questions, and bullet points for answers. Include 4-8 practical entries relevant to the domain.",
  "user_prompt": "A single example first message the user might send to the agent. Keep it short and realistic."
}}

Rules:
- main_prompt: 80-200 lines, highly structured with bold headers and clear sections
- Include a response style section (concise, factual, bullet points, no emojis, use Unicode symbols)
- Include tool usage rules referencing the table names if provided
- If tables are provided, include a DATA ACCESS section explaining the agent queries data through a Genie tool (natural language to SQL). List each table with its columns and describe what data it contains. The agent does NOT write SQL directly — it asks the Genie tool in natural language.
- Include a {{{{KNOWLEDGE_BASE}}}} placeholder for knowledge base injection
- knowledge_base: 4-8 practical operational FAQ entries with ## headers
- user_prompt: one realistic first message, 5-15 words
- All content must be domain-appropriate and production-quality
- Do NOT use emojis anywhere — use Unicode symbols (✓, ✗, ▸, →, ●, ■, ⚠, △) instead"""


def generate_prompts(domain: str, table_schemas: list[dict] | None = None) -> dict:
    """Call the LLM to generate prompt files for the given domain.

    Returns dict with keys: main_prompt, knowledge_base, user_prompt
    """
    print("[~] Generating prompts from domain description...")

    user_msg = f"Domain: {domain}"
    if table_schemas:
        table_lines = []
        for t in table_schemas:
            cols = t.get('columns', [])
            col_desc = ", ".join(f"{c['name']} ({c.get('type', 'STRING')})" for c in cols)
            table_lines.append(f"  - {t['name']}: {col_desc}")
        user_msg += f"\n\nTables accessible via Genie tool (natural language to SQL):\n" + "\n".join(table_lines)

    print(f"[~] Calling model endpoint...")
    result = call_llm_json(SYSTEM_PROMPT, user_msg, max_tokens=8192)

    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object, got {type(result).__name__}")

    for key in ("main_prompt", "knowledge_base", "user_prompt"):
        if key not in result:
            raise ValueError(f"Missing key in response: {key}")

    print(f"[+] Generated main.prompt ({len(result['main_prompt'].splitlines())} lines)")
    print(f"[+] Generated knowledge.base ({len(result['knowledge_base'].splitlines())} lines)")
    print(f"[+] Generated user.prompt")

    return result
