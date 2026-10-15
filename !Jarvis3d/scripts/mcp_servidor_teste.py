"""Servidor MCP de mentira (stdio) para o teste do cliente: uma ferramenta que só LÊ e outra que ALTERA."""
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

app = MCPServer("teste")
NOTAS = []


@app.tool(annotations=ToolAnnotations(read_only_hint=True))
def somar(a: int, b: int) -> str:
    """Soma dois números inteiros."""
    return f"{a} + {b} = {a + b}"


@app.tool()
def gravar_nota(texto: str) -> str:
    """Grava uma nota (altera dados)."""
    NOTAS.append(texto)
    return f"nota {len(NOTAS)} gravada: {texto}"


if __name__ == "__main__":
    import anyio
    anyio.run(app.run_stdio_async)
