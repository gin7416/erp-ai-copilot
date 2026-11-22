"""MCP server exposing the warehouse and SOP index as read-only tools for an LLM agent.

    python -m erp_copilot.mcp_server          # stdio transport (e.g. for Claude Desktop / Claude Code)
"""
from __future__ import annotations

import duckdb
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .copilot import Copilot
from .sql_guard import SqlGuardError

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def build_server(copilot: Copilot | None = None) -> MCPServer:
    state: dict[str, Copilot] = {}

    def get() -> Copilot:
        if "c" not in state:
            state["c"] = copilot or Copilot()
        return state["c"]

    server = MCPServer(
        "erp-copilot",
        instructions=("Read-only access to a (synthetic) ERP data warehouse and internal SOP documents. "
                      "Call list_tables before writing SQL; run_sql only accepts one SELECT over marts.* tables."),
    )

    @server.tool(annotations=READ_ONLY)
    def list_tables() -> list[dict]:
        """List marts tables with their business description and columns (the semantic layer)."""
        return get().tables()

    @server.tool(annotations=READ_ONLY)
    def run_sql(sql: str) -> dict:
        """Run one read-only SELECT over marts.* tables (max 200 rows). Returns columns and rows, or an error."""
        try:
            return get().warehouse.run(sql).to_dict(max_rows=200)
        except (SqlGuardError, duckdb.Error) as exc:
            return {"error": str(exc).splitlines()[0]}

    @server.tool(annotations=READ_ONLY)
    def search_sop(query: str, k: int = 3) -> list[dict]:
        """Search internal SOP documents (purchasing, inventory, supplier delays, RMA, order changes, data access)."""
        return get().search_sop(query, k=max(1, min(k, 10)))

    @server.tool(annotations=READ_ONLY)
    def ask_data(question: str) -> dict:
        """Answer a business question with Text-to-SQL using the server's local LLM; returns the SQL and rows."""
        return get().text_to_sql.ask(question).to_dict(max_rows=50)

    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
