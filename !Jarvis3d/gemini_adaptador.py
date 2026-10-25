"""Adaptador transparente do Google Gemini para a interface da Anthropic usada pelo Jarvis.
Permite usar os modelos do Google (ex.: gemini-3.5-flash-lite) com custo zero e respostas em milissegundos,
preservando suporte completo a streaming, chamada de ferramentas (tool use) e thought signatures.
"""

import asyncio
import json
import httpx


BASE_URL_OPENAI = "https://generativelanguage.googleapis.com/v1beta/openai"


class _Bloco(dict):
    """Bloco que funciona como objeto (b.name, b.type) E como dict (b.get, json.dumps). Precisa ser dict: quando o Gemini falha no meio
    do pedido, o histórico com estes blocos vai para a reserva (SDK da Anthropic/DeepSeek), que só serializa dicts.
    Antes era só objeto: 'ToolUseBlock is not JSON serializable' e "'ToolUseBlock' object has no attribute 'get'" derrubavam o turno."""

    def __getattr__(self, nome):
        try:
            return self[nome]
        except KeyError:
            raise AttributeError(nome) from None


class ToolUseBlock(_Bloco):
    def __init__(self, id: str, name: str, input_dict: dict, thought_signature: str = ""):
        super().__init__(type="tool_use", id=id, name=name, input=input_dict if isinstance(input_dict, dict) else {})
        self.__dict__["thought_signature"] = thought_signature     # atributo, não chave: a reserva recusaria um campo desconhecido

    def __getattr__(self, nome):
        if nome == "thought_signature":
            return self.__dict__.get(nome, "")
        return super().__getattr__(nome)

    def __repr__(self):
        return f"ToolUseBlock(id={self['id']!r}, name={self['name']!r}, input={self['input']!r})"


class TextBlock(_Bloco):
    def __init__(self, text: str):
        super().__init__(type="text", text=text)

    def __repr__(self):
        return f"TextBlock({self['text']!r})"


def _campo(b, nome: str, padrao=None):
    """Lê um campo de bloco seja ele objeto do SDK, dict ou _Bloco (sem cair no 'or b.get' quando o valor é vazio)."""
    if isinstance(b, dict):
        return b.get(nome, padrao)
    return getattr(b, nome, padrao)


class Usage:
    def __init__(self, prompt_tokens: int = 0, completion_tokens: int = 0):
        self.input_tokens = prompt_tokens
        self.output_tokens = completion_tokens
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0

    def __repr__(self):
        return f"Usage(input_tokens={self.input_tokens}, output_tokens={self.output_tokens})"


class ResponseMessage:
    def __init__(self, content: list, stop_reason: str, usage: Usage):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage


def _converter_ferramentas(tools: list) -> list | None:
    if not tools:
        return None
    res = []
    for t in tools:
        res.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}})
            }
        })
    return res


def _converter_mensagens(mensagens: list, system=None) -> list:
    res = []
    if system:
        if isinstance(system, list):
            sys_txt = "\n".join(b.get("text", "") for b in system if isinstance(b, dict))
        else:
            sys_txt = str(system)
        if sys_txt.strip():
            res.append({"role": "system", "content": sys_txt})

    for m in mensagens:
        role = m["role"]
        content = m["content"]
        if isinstance(content, str):
            res.append({"role": role, "content": content})
        elif isinstance(content, list):
            textos = []
            tool_calls = []
            tool_results = []
            for b in content:
                b_type = _campo(b, "type")
                if b_type == "text":
                    textos.append(_campo(b, "text", "") or "")
                elif b_type == "tool_use":
                    b_id = _campo(b, "id", "") or ""
                    b_name = _campo(b, "name", "") or ""
                    b_inp = _campo(b, "input", {}) or {}
                    ts = getattr(b, "thought_signature", "") or ""
                    tc_dict = {
                        "id": b_id,
                        "type": "function",
                        "function": {"name": b_name, "arguments": json.dumps(b_inp) if isinstance(b_inp, dict) else str(b_inp)}
                    }
                    if ts:
                        tc_dict["extra_content"] = {"google": {"thought_signature": ts}}
                    tool_calls.append(tc_dict)
                elif b_type == "tool_result":
                    t_id = _campo(b, "tool_use_id", "")
                    t_c = _campo(b, "content", "")
                    if isinstance(t_c, list):
                        partes = []
                        for p in t_c:
                            if isinstance(p, dict) and p.get("type") == "image":
                                partes.append("[imagem enviada]")
                            else:
                                partes.append(str(p.get("text", p) if isinstance(p, dict) else p))
                        t_c = " ".join(partes)
                    tool_results.append({"role": "tool", "tool_call_id": t_id, "content": str(t_c)})
                elif b_type == "image":
                    src = _campo(b, "source", {}) or {}
                    if src.get("type") == "base64":
                        mime = src.get("media_type", "image/jpeg")
                        data_b64 = src.get("data", "")
                        textos.append(f"[Imagem anexada: {mime}]")

            if role == "assistant":
                msg = {"role": "assistant", "content": "\n".join(textos) if textos else None}
                if tool_calls:
                    msg["tool_calls"] = tool_calls
                res.append(msg)
            elif role == "user":
                if tool_results:
                    for tr in tool_results:
                        res.append(tr)
                    if textos:
                        res.append({"role": "user", "content": "\n".join(textos)})
                else:
                    res.append({"role": "user", "content": "\n".join(textos)})
    return res


def _json_completo(texto: str) -> bool:
    try:
        json.loads(texto)
        return True
    except Exception:
        return False


def juntar_chamada(agg: dict, tc: dict):
    """Soma um pedaço de tool_call do streaming na chamada certa. O Gemini manda chamadas PARALELAS inteiras, muitas vezes todas com
    index 0 (ou sem index): somar pelo index colava os nomes ('trilha_sonoraterminal_executar') e a ferramenta "não existia".
    Regra: id novo = chamada nova; sem id, um NOME chegando depois de uma chamada já completa (nome + JSON fechado) = chamada nova;
    o resto (pedaços de argumentos) continua a chamada anterior."""
    fn = tc.get("function") or {}
    tid = tc.get("id") or ""
    idx = tc.get("index")
    chave = None
    if tid:
        chave = next((k for k, v in agg.items() if v["id"] == tid), None)
    if chave is None and not tid and agg:
        candidata = next((k for k, v in agg.items() if v.get("index") == idx), None) if idx is not None else None
        candidata = candidata if candidata is not None else list(agg)[-1]
        atual = agg[candidata]
        completa = atual["name"] and (atual["arguments"] == "" or _json_completo(atual["arguments"]))
        if not (fn.get("name") and completa and (atual["arguments"] or fn.get("arguments"))):
            chave = candidata
    if chave is None:
        if not tid and not fn.get("name") and agg:
            chave = list(agg)[-1]                                        # pedaço solto de argumentos: vai para a última
        else:
            chave = len(agg)
            agg[chave] = {"id": tid or f"call_{chave}_{id(agg) % 10000}", "index": idx, "name": "", "arguments": "", "thought_signature": ""}
    alvo = agg[chave]
    extra = (tc.get("extra_content") or {}).get("google", {}) or {}
    if extra.get("thought_signature"):
        alvo["thought_signature"] = extra["thought_signature"]
    if fn.get("name"):
        alvo["name"] = fn["name"] if alvo["name"] and fn["name"].startswith(alvo["name"]) else alvo["name"] + fn["name"]
    if fn.get("arguments"):
        alvo["arguments"] += fn["arguments"]


class _StreamContextManager:
    def __init__(self, cliente_gemini, payload: dict):
        self._cliente = cliente_gemini
        self._payload = payload
        self._cm = None
        self._resp = None
        self._final_message = None

    async def __aenter__(self):
        self._cm = self._cliente._http.stream(
            "POST",
            f"{BASE_URL_OPENAI}/chat/completions",
            headers=self._cliente._headers,
            json=self._payload,
            timeout=30.0
        )
        self._resp = await self._cm.__aenter__()

        if self._resp.status_code != 200:
            err_body = await self._resp.aread()
            raise RuntimeError(f"Erro {self._resp.status_code} na API do Gemini: {err_body.decode('utf-8', errors='replace')}")

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._cm:
            await self._cm.__aexit__(exc_type, exc_val, exc_tb)

    @property
    def text_stream(self):
        return self._iter_stream()

    async def _iter_stream(self):
        text_total = []
        tool_calls_agg = {}
        usage_data = {"prompt_tokens": 0, "completion_tokens": 0}

        async for line in self._resp.aiter_lines():
            if not line or not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                chunk = json.loads(line[6:])
                choices = chunk.get("choices", [])
                if chunk.get("usage"):
                    usage_data["prompt_tokens"] = chunk["usage"].get("prompt_tokens", 0)
                    usage_data["completion_tokens"] = chunk["usage"].get("completion_tokens", 0)

                if choices:
                    delta = choices[0].get("delta", {})
                    if delta.get("content"):
                        pedaco = delta["content"]
                        text_total.append(pedaco)
                        yield pedaco

                    if delta.get("tool_calls"):
                        for tc in delta["tool_calls"]:
                            juntar_chamada(tool_calls_agg, tc)
            except Exception:
                continue

        final_content = []
        if text_total:
            final_content.append(TextBlock("".join(text_total)))

        for tc in tool_calls_agg.values():
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except Exception:
                args = {"raw": tc["arguments"]}
            final_content.append(ToolUseBlock(tc["id"], tc["name"], args, tc["thought_signature"]))

        stop = "tool_use" if tool_calls_agg else "end_turn"
        self._final_message = ResponseMessage(
            final_content,
            stop,
            Usage(usage_data["prompt_tokens"] or 50, usage_data["completion_tokens"] or len(text_total))
        )

    async def get_final_message(self) -> ResponseMessage:
        return self._final_message or ResponseMessage([], "end_turn", Usage())


class _MessagesAPI:
    def __init__(self, cliente_gemini):
        self._cliente = cliente_gemini

    def stream(self, model: str, max_tokens: int = 2000, system=None, tools: list = None, messages: list = None, **kwargs):
        payload = {
            "model": model or self._cliente.modelo_padrao,
            "messages": _converter_mensagens(messages or [], system=system),
            "max_tokens": max_tokens,
            "stream": True
        }
        tools_conv = _converter_ferramentas(tools)
        if tools_conv:
            payload["tools"] = tools_conv
        return _StreamContextManager(self._cliente, payload)

    async def create(self, model: str, max_tokens: int = 2000, system=None, tools: list = None, messages: list = None, tool_choice=None, **kwargs):
        payload = {
            "model": model or self._cliente.modelo_padrao,
            "messages": _converter_mensagens(messages or [], system=system),
            "max_tokens": max_tokens,
            "stream": False
        }
        tools_conv = _converter_ferramentas(tools)
        if tools_conv:
            payload["tools"] = tools_conv
            if tool_choice and isinstance(tool_choice, dict) and tool_choice.get("name"):
                payload["tool_choice"] = {"type": "function", "function": {"name": tool_choice["name"]}}

        resp = await self._cliente._http.post(
            f"{BASE_URL_OPENAI}/chat/completions",
            headers=self._cliente._headers,
            json=payload,
            timeout=35.0
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Erro {resp.status_code} na API do Gemini: {resp.text}")

        data = resp.json()
        choice = data["choices"][0]
        msg = choice.get("message", {})
        final_content = []
        if msg.get("content"):
            final_content.append(TextBlock(msg["content"]))

        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except Exception:
                    args = {"raw": fn.get("arguments", "")}
                ts = tc.get("extra_content", {}).get("google", {}).get("thought_signature", "")
                final_content.append(ToolUseBlock(tc.get("id", "call_0"), fn.get("name", ""), args, ts))

        stop = "tool_use" if msg.get("tool_calls") else "end_turn"
        usage_raw = data.get("usage", {})
        usage = Usage(usage_raw.get("prompt_tokens", 0), usage_raw.get("completion_tokens", 0))
        return ResponseMessage(final_content, stop, usage)


class AsyncGeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-3.5-flash-lite", http_client: httpx.AsyncClient = None):
        self.api_key = api_key
        self.modelo_padrao = model
        self.base_url = BASE_URL_OPENAI
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        self._http = http_client or httpx.AsyncClient(timeout=35.0, limits=httpx.Limits(max_connections=50, max_keepalive_connections=10))
        self.messages = _MessagesAPI(self)

    async def aclose(self):
        await self._http.aclose()
