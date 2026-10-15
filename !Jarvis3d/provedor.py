"""Parâmetros que variam por provedor. No DeepSeek (endpoint compatível com a Anthropic) `output_config` liga o modo de raciocínio, que NÃO aceita tool_choice
forçado (erro 400 "Thinking mode does not support this tool_choice"): lá o raciocínio é desligado explicitamente."""


def deepseek(cliente) -> bool:
    return "deepseek" in str(getattr(cliente, "base_url", "")).lower()


def extras(cliente, esforco: str = "low") -> dict:
    return {"thinking": {"type": "disabled"}} if deepseek(cliente) else {"output_config": {"effort": esforco}}
