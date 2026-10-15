"""
Cliente MCP (Model Context Protocol): liga servidores de ferramentas externos configurados em mcp.json (Notion, GitHub, arquivos, bancos, Home Assistant...)
e expõe as ferramentas deles ao Jarvis como `mcp__<servidor>__<ferramenta>`. Cada servidor roda como processo do usuário (stdio) numa tarefa própria.

mcp.json (na pasta de dados):
  {"servidores": {"arquivos": {"comando": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/voce/Documents"],
                                "env": {}, "confiar_leitura": true}}}
Segurança: ferramenta que só LÊ (anotação readOnlyHint do servidor) roda direto se `confiar_leitura` (padrão true); qualquer outra pede confirmação mostrando
servidor, ferramenta e argumentos. O que volta é DADO de terceiros, nunca ordem.
"""

import asyncio
import hashlib
import json
import re
import shutil

import caminhos

ARQ = caminhos.DADOS / "mcp.json"
LIMITE_SAIDA = 8000
TIMEOUT_CHAMADA = 60


def _limpo(t: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", t)[:24] or "x"


def nome_da_ferramenta(servidor: str, ferramenta: str) -> str:
    base = f"mcp__{_limpo(servidor)}__{_limpo(ferramenta)}"
    if len(base) <= 64:
        return base
    return base[:55] + "_" + hashlib.md5(base.encode()).hexdigest()[:8]


class Gerente:
    def __init__(self):
        self.cfg: dict = {}
        self.sessoes: dict = {}
        self.ferramentas: dict[str, dict] = {}          # nome composto -> {servidor, nome, def, leitura}
        self.estado: dict[str, str] = {}                # servidor -> "ok" | "erro: ..." | "conectando"
        self._tarefas: list[asyncio.Task] = []
        self._parar = asyncio.Event()

    def ler_config(self) -> dict:
        try:
            d = json.loads(ARQ.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {k: v for k, v in (d.get("servidores") or {}).items() if isinstance(v, dict) and v.get("comando")}

    async def iniciar(self, espera_s: float = 25.0):
        self.cfg = self.ler_config()
        self._parar = asyncio.Event()
        prontos = []
        for nome, c in self.cfg.items():
            self.estado[nome] = "conectando"
            ev = asyncio.Event()
            prontos.append(ev)
            self._tarefas.append(asyncio.create_task(self._rodar(nome, c, ev)))
        if prontos:
            try:
                await asyncio.wait_for(asyncio.gather(*[e.wait() for e in prontos]), timeout=espera_s)
            except asyncio.TimeoutError:
                pass

    async def _rodar(self, nome: str, c: dict, pronto: asyncio.Event):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        try:
            exe = shutil.which(c["comando"]) or c["comando"]
            params = StdioServerParameters(command=exe, args=[str(a) for a in c.get("args", [])], env={str(k): str(v) for k, v in (c.get("env") or {}).items()} or None)
            async with stdio_client(params) as (leitura, escrita):
                async with ClientSession(leitura, escrita) as sessao:
                    async with asyncio.timeout(20):                     # mesma tarefa do contexto (o anyio não aceita wait_for aqui)
                        await sessao.initialize()
                        lista = await sessao.list_tools()
                    for t in lista.tools[:40]:
                        ann = getattr(t, "annotations", None)
                        leitura_so = bool(getattr(ann, "read_only_hint", None) or getattr(ann, "readOnlyHint", None)) if ann else False
                        comp = nome_da_ferramenta(nome, t.name)
                        esquema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)
                        self.ferramentas[comp] = {
                            "servidor": nome, "nome": t.name, "leitura": leitura_so,
                            "def": {"name": comp, "description": f"[MCP {nome}] " + (t.description or t.name)[:600],
                                    "input_schema": esquema if isinstance(esquema, dict) and esquema.get("type") == "object" else {"type": "object", "properties": {}}}}
                    self.sessoes[nome] = sessao
                    self.estado[nome] = "ok"
                    pronto.set()
                    await self._parar.wait()
        except Exception as e:
            self.estado[nome] = f"erro: {type(e).__name__}: {str(e)[:100]}"
        finally:
            self.sessoes.pop(nome, None)
            for k in [k for k, v in self.ferramentas.items() if v["servidor"] == nome and nome not in self.sessoes]:
                self.ferramentas.pop(k, None)
            pronto.set()

    def definicoes(self) -> list[dict]:
        return [f["def"] for f in self.ferramentas.values()]

    def confiavel_leitura(self, nome: str) -> bool:
        f = self.ferramentas.get(nome)
        return bool(f and f["leitura"] and self.cfg.get(f["servidor"], {}).get("confiar_leitura", True))

    def descrever(self, nome: str, entrada: dict) -> list[str]:
        f = self.ferramentas.get(nome) or {}
        args = json.dumps(entrada, ensure_ascii=False)[:600]
        return [f"Servidor: {f.get('servidor')}", f"Ferramenta: {f.get('nome')}", f"Argumentos: {args}", "É uma ferramenta externa: ela pode alterar dados fora do Jarvis."]

    async def chamar(self, nome: str, entrada: dict) -> tuple[str, bool]:
        f = self.ferramentas.get(nome)
        sessao = self.sessoes.get(f["servidor"]) if f else None
        if not f or sessao is None:
            return "Essa ferramenta externa não está disponível (servidor desligado).", True
        try:
            r = await asyncio.wait_for(sessao.call_tool(f["nome"], entrada if isinstance(entrada, dict) else {}), timeout=TIMEOUT_CHAMADA)
        except asyncio.TimeoutError:
            return f"A ferramenta {f['nome']} demorou mais de {TIMEOUT_CHAMADA} s.", True
        except Exception as e:
            return f"Falha na ferramenta externa ({type(e).__name__}): {str(e)[:200]}", True
        partes = []
        for c in getattr(r, "content", []) or []:
            partes.append(getattr(c, "text", None) or f"[{getattr(c, 'type', 'conteúdo')} não textual]")
        texto = "\n".join(partes).strip() or "(sem saída)"
        if len(texto) > LIMITE_SAIDA:
            texto = texto[:LIMITE_SAIDA] + "\n[... cortado ...]"
        return texto, bool(getattr(r, "is_error", None) or getattr(r, "isError", None))

    async def fechar(self):
        self._parar.set()
        await asyncio.gather(*self._tarefas, return_exceptions=True)
        self._tarefas = []

    async def recarregar(self):
        await self.fechar()
        self.ferramentas.clear()
        self.estado.clear()
        await self.iniciar()

    def resumo(self) -> dict:
        return {"servidores": {n: {"estado": self.estado.get(n, "?"), "ferramentas": sorted(f["nome"] for f in self.ferramentas.values() if f["servidor"] == n)} for n in self.cfg}}
