"""Parâmetros que variam por provedor. No DeepSeek (endpoint compatível com a Anthropic) `output_config` liga o modo de raciocínio, que NÃO aceita tool_choice
forçado (erro 400 "Thinking mode does not support this tool_choice"): lá o raciocínio é desligado explicitamente."""


def deepseek(cliente) -> bool:
    return "deepseek" in str(getattr(cliente, "base_url", "")).lower()


def gemini(cliente) -> bool:
    return "generativelanguage.googleapis.com" in str(getattr(cliente, "base_url", "")).lower()


def extras(cliente, esforco: str = "low") -> dict:
    if deepseek(cliente):
        return {"thinking": {"type": "disabled"}}
    if gemini(cliente):
        return {}
    return {"output_config": {"effort": esforco}}
