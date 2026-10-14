"""
Testa a voz expressiva e a trilha sonora SEM gastar nada da ElevenLabs (ela é substituída por uma falsa):
- modelo eleven_v3: a emoção vira tag de áudio no texto + estabilidade; modelos antigos: estabilidade/estilo mais intensos;
- todas as emoções (inclusive risada, curioso, irritado, suspiro) existem na voz e são reconhecidas na marca [[...]];
- a ferramenta trilha_sonora avisa a tela (e recusa sem música);
- seletor de voz: lista as amostras, troca a voz na hora, grava só os campos da voz no config.json (sem tocar nas chaves)
  e recusa origem de outro site.

Uso:  .venv\\Scripts\\python.exe -X utf8 scripts\\teste_vozes.py
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="jarvis_vozes_"))
cfg = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
cfg.update(porta=8361, elevenlabs_api_key="chave-falsa-xyz", anthropic_api_key="falsa", cofre_obsidian="")
cfg.pop("elevenlabs_modelo", None)
(TMP / "cfg.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
os.environ.update(JARVIS_CONFIG=str(TMP / "cfg.json"), JARVIS_MEMORIA_DIR=str(TMP / "mem"), ANTHROPIC_BASE_URL="http://127.0.0.1:9", ELEVENLABS_API_KEY="")
sys.path.insert(0, str(BASE))
import server  # noqa: E402

ok_geral = True


def checar(cond, texto):
    global ok_geral
    ok_geral &= bool(cond)
    print("  [%s] %s" % ("OK" if cond else "FALHOU", texto))


class RespostaFalsa:
    status_code = 200
    content = b"MP3-FALSO"

    def json(self):
        return {}


class HttpFalso:
    def __init__(self):
        self.chamadas = []

    async def post(self, url, **kw):
        self.chamadas.append((url, kw))
        return RespostaFalsa()


class Sessao:
    def __init__(self):
        self.enviados, self.controle, self.vai_dormir = [], {"ativo": False}, False

    async def enviar(self, obj):
        self.enviados.append(obj)

    async def confirmar(self, *a):
        return True


class Bloco:
    def __init__(self, nome, entrada):
        self.name, self.input, self.id = nome, entrada, "toolu_x"


async def principal():
    http = HttpFalso()
    server.http = http

    print("1) MODELO EXPRESSIVO (eleven_v3)")
    server.ELEVEN_MODELO = "eleven_v3"
    audio = await server.sintetizar("Consegui, chefe!", "frase anterior", "animado")
    url, kw = http.chamadas[-1]
    corpo = kw["json"]
    checar(audio == b"MP3-FALSO" and url.endswith(server.ELEVEN_VOZ), "chama a voz configurada")
    checar(corpo["text"] == "[excited] Consegui, chefe!" and corpo["model_id"] == "eleven_v3", f"emoção animado vira tag de áudio: {corpo['text']}")
    checar(corpo["voice_settings"] == {"stability": 0.0} and "previous_text" not in corpo, "estabilidade 'criativa' (0.0) e sem campos que o v3 não aceita")
    await server.sintetizar("Tudo certo.", "", None)
    checar(http.chamadas[-1][1]["json"]["text"] == "Tudo certo." and http.chamadas[-1][1]["json"]["voice_settings"]["stability"] == 0.5, "sem emoção: texto limpo, estabilidade natural")
    await server.sintetizar("Que absurdo.", "", "irritado")
    checar(http.chamadas[-1][1]["json"]["text"].startswith("[annoyed] "), "emoção nova (irritado) tem a sua tag")

    print("\n2) MODELOS ANTIGOS FICAM MAIS INTENSOS")
    server.ELEVEN_MODELO = "eleven_flash_v2_5"
    await server.sintetizar("Vamos nessa!", "antes", "adrenalina")
    c = http.chamadas[-1][1]["json"]
    checar(c["text"] == "Vamos nessa!" and c["voice_settings"]["style"] >= 0.7 and c["voice_settings"]["stability"] <= 0.15 and c["previous_text"] == "antes",
           f"adrenalina: estabilidade baixa e estilo alto ({c['voice_settings']})")

    print("\n3) TODAS AS EMOÇÕES")
    nomes = {"neutro", "animado", "adrenalina", "triunfante", "preocupado", "sarcastico", "serio", "risada", "curioso", "irritado", "suspiro"}
    checar(set(server.EMOCOES) == nomes and set(server.EMOCOES_V3) == nomes, "11 emoções, as mesmas nos dois modos de voz")
    for e in ("risada", "curioso", "irritado", "suspiro"):
        texto, emo = server.separar_emocao(f"[[{e}]] Frase de teste.")
        checar(emo == e and texto == "Frase de teste.", f"[[{e}]] é reconhecida e a marca não vai para a fala")
    front = (BASE / "frontend")
    for e in ("risada", "curioso", "irritado", "suspiro"):
        checar(f"{e}:" in (front / "reator.js").read_text(encoding="utf-8") and f'data-emocao="{e}"' in (front / "style.css").read_text(encoding="utf-8"),
               f"a tela tem cor para '{e}' (reator e interface)")
    checar("risada" in server.REGRAS and "suspiro" in server.REGRAS and "Português do Brasil" in server.REGRAS, "o prompt ensina as emoções novas e o português do Brasil")

    print("\n4) TRILHA SONORA")
    s = Sessao()
    antigo = server.achar_musica
    server.achar_musica = lambda: None
    r = await server.rodar_ferramenta(s, Bloco("trilha_sonora", {"acao": "iniciar"}))
    checar(r.get("is_error") and not any(m.get("tipo") == "trilha" for m in s.enviados), "sem música na pasta: recusa e não avisa a tela")
    server.achar_musica = lambda: Path("musica/abertura.m4a")
    r = await server.rodar_ferramenta(s, Bloco("trilha_sonora", {"acao": "iniciar"}))
    checar(not r.get("is_error") and {"tipo": "trilha", "acao": "iniciar"} in s.enviados, "iniciar: a tela é avisada para tocar a trilha")
    await server.rodar_ferramenta(s, Bloco("trilha_sonora", {"acao": "parar"}))
    checar({"tipo": "trilha", "acao": "parar"} in s.enviados, "parar: a tela é avisada")
    r = await server.rodar_ferramenta(s, Bloco("trilha_sonora", {"acao": "dancar"}))
    checar(r.get("is_error"), "ação inválida é recusada")
    server.achar_musica = antigo
    painel = server.painel()
    checar(painel["musica_abertura"] is False, "por padrão a música NÃO toca ao abrir (só nas tarefas grandes)")
    checar("trilha_sonora" in server.REGRAS and "tarefa MAIOR" in server.REGRAS, "o prompt diz quando usar a trilha")

    print("\n4b) MODO CONVERSA (tchau / me aguarda)")
    s2 = Sessao()
    r = await server.rodar_ferramenta(s2, Bloco("encerrar_conversa", {}))
    checar(not r.get("is_error") and {"tipo": "conversa", "ativa": False} in s2.enviados, "encerrar_conversa avisa a tela (volta a exigir o nome)")
    checar(not s2.vai_dormir, "tchau NÃO manda dormir (só 'dormir' faz isso)")
    await server.rodar_ferramenta(s2, Bloco("dormir", {}))
    checar(s2.vai_dormir, "dormir continua existindo para 'pode desligar'")
    checar("encerrar_conversa" in server.REGRAS and "NÃO precisa dizer seu nome" in server.REGRAS, "o prompt diz: conversando = sem nome; tchau/aguarda = encerrar_conversa")
    checar(server.painel()["janela_conversa"] == 45.0, "a conversa fica aberta 45 s sem ninguém falar (ajustável: janela_conversa_seg)")

    print("\n5) SELETOR DE VOZ")
    from fastapi.testclient import TestClient
    server.VOZES_DIR = TMP / "vozes"
    server.VOZES_DIR.mkdir()
    (server.VOZES_DIR / "Paulo.mp3").write_bytes(b"x")
    (server.VOZES_DIR / "vozes.json").write_text(json.dumps({"Paulo": {"voice_id": "voz_paulo", "descricao": "Paulo - teste", "arquivo": "Paulo.mp3"},
                                                              "Rafael": {"voice_id": "voz_rafael", "descricao": "Rafael - teste", "arquivo": "Rafael.mp3"}}), encoding="utf-8")
    cli = TestClient(server.app, base_url=f"http://127.0.0.1:{server.PORTA}")
    r = cli.get("/api/vozes").json()
    checar([v["nome"] for v in r["vozes"]] == ["Paulo", "Rafael"] and not any(v["ativa"] for v in r["vozes"]), "lista as vozes com amostra")
    checar(cli.get("/api/vozes/amostra/Paulo").content == b"x" and cli.get("/api/vozes/amostra/../config").status_code in (404, 400), "serve a amostra e nada fora da lista")
    antes_cfg = (TMP / "cfg.json").read_text(encoding="utf-8")
    r = cli.post("/api/vozes/usar", json={"voice_id": "voz_rafael"}, headers={"Origin": "https://site-malicioso.com"})
    checar(r.status_code == 403 and server.ELEVEN_VOZ != "voz_rafael", "pedido vindo de outro site é recusado (403)")
    r = cli.post("/api/vozes/usar", json={"voice_id": "qualquer-id"})
    checar(r.status_code == 400, "voz que não está na lista é recusada")
    r = cli.post("/api/vozes/usar", json={"voice_id": "voz_rafael"})
    novo_cfg = json.loads((TMP / "cfg.json").read_text(encoding="utf-8"))
    checar(r.json()["ok"] and server.ELEVEN_VOZ == "voz_rafael" and server.ELEVEN_MODELO == "eleven_v3", "trocou na hora para o modelo expressivo")
    checar(novo_cfg["elevenlabs_voice_id"] == "voz_rafael" and novo_cfg["elevenlabs_modelo"] == "eleven_v3", "gravou a voz e o modelo no config.json")
    checar({k: v for k, v in novo_cfg.items() if k not in ("elevenlabs_voice_id", "elevenlabs_modelo")} == {k: v for k, v in json.loads(antes_cfg).items() if k not in ("elevenlabs_voice_id", "elevenlabs_modelo")},
           "o resto do config.json (chaves incluídas) ficou idêntico")
    checar(cli.get("/api/vozes").json()["vozes"][1]["ativa"], "a lista passa a marcar a voz em uso")


try:
    asyncio.run(principal())
finally:
    shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULTADO:", "TUDO OK" if ok_geral else "HÁ FALHAS")
sys.exit(0 if ok_geral else 1)
