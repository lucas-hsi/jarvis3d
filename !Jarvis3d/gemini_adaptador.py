"""Adaptador transparente do Google Gemini para a interface da Anthropic usada pelo Jarvis.
Permite usar os modelos do Google (ex.: gemini-3.5-flash-lite) com custo zero e respostas em milissegundos,
preservando suporte completo a streaming, chamada de ferramentas (tool use) e thought signatures.
"""

import asyncio
import json
import httpx


BASE_URL_OPENAI = "https://generativelanguage.googleapis.com/v1beta/openai"


class ToolUseBlock:
    def __init__(self, id: str, name: str, input_dict: dict, thought_signature: str = ""):
        self.type = "tool_use"
        self.id = id
        self.name = name
        self.input = input_dict
        self.thought_signature = thought_signature

    def __repr__(self):
        return f"ToolUseBlock(id={self.id!r}, name={self.name!r}, input={self.input!r})"


class TextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text

    def __repr__(self):
        return f"TextBlock({self.text!r})"


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
                b_type = getattr(b, "type", None) or (b.get("type") if isinstance(b, dict) else None)
                if b_type == "text":
                    t = getattr(b, "text", None) or (b.get("text", "") if isinstance(b, dict) else "")
                    textos.append(t)
                elif b_type == "tool_use":
                    b_id = getattr(b, "id", None) or b.get("id", "")
                    b_name = getattr(b, "name", None) or b.get("name", "")
                    b_inp = getattr(b, "input", None) or b.get("input", {})
                    ts = getattr(b, "thought_signature", "") or (b.get("thought_signature", "") if isinstance(b, dict) else "")
                    tc_dict = {
                        "id": b_id,
                        "type": "function",
                        "function": {"name": b_name, "arguments": json.dumps(b_inp) if isinstance(b_inp, dict) else str(b_inp)}
                    }
                    if ts:
                        tc_dict["extra_content"] = {"google": {"thought_signature": ts}}
                    tool_calls.append(tc_dict)
                elif b_type == "tool_result":
                    t_id = b.get("tool_use_id", "")
                    t_c = b.get("content", "")
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
                    src = b.get("source", {})
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
                            idx = tc.get("index", 0)
                            if idx not in tool_calls_agg:
                                tool_calls_agg[idx] = {
                                    "id": tc.get("id", f"call_{idx}"),
                                    "name": "",
                                    "arguments": "",
                                    "thought_signature": ""
                                }
                            if tc.get("id"):
                                tool_calls_agg[idx]["id"] = tc["id"]
                            extra = tc.get("extra_content", {}).get("google", {})
                            if extra.get("thought_signature"):
                                tool_calls_agg[idx]["thought_signature"] = extra["thought_signature"]

                            fn = tc.get("function", {})
                            if fn.get("name"):
                                tool_calls_agg[idx]["name"] += fn["name"]
                            if fn.get("arguments"):
                                tool_calls_agg[idx]["arguments"] += fn["arguments"]
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
