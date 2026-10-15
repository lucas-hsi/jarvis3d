"""Fase 2: documentos (criar/ler/buscar), modos especialista, roteador por dificuldade, custos e a busca/leitura da pesquisa profunda (web real, sem modelo)."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="jarvis_f2_"))
os.environ["JARVIS_HOME"] = str(tmp)
os.environ["JARVIS_SEM_VOZ"] = "1"
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import custos  # noqa: E402
import documentos  # noqa: E402
import especialistas  # noqa: E402
import pesquisa  # noqa: E402

ok = True


def checar(c, t):
    global ok
    ok &= bool(c)
    print("  [%s] %s" % ("OK" if c else "FALHOU", t))


pasta = tmp / "Documentos"
pasta.mkdir()
cfg = {"pastas_liberadas": [str(pasta)]}

print("DOCUMENTOS")
r = documentos.criar({"tipo": "docx", "nome": "Proposta", "conteudo": "# Proposta Alfa\n- prazo de 30 dias\n- valor R$ 12.500,00\nTexto livre sobre o contrato com a Padaria Estrela.", "pasta": "documentos"}, cfg)
checar("Proposta.docx" in r, r)
r2 = documentos.criar({"tipo": "docx", "nome": "Proposta", "conteudo": "outra", "pasta": "documentos"}, cfg)
checar("Proposta (2).docx" in r2, "não sobrescreve: " + r2)
documentos.criar({"tipo": "xlsx", "nome": "Vendas", "conteudo": "produto;qtd;preco\nParafuso;10;2,50\nPorca;4;1,25", "pasta": "documentos"}, cfg)
documentos.criar({"tipo": "md", "nome": "ideias", "conteudo": "Ideia sobre painel de metas por voz e o cliente Mercearia Sol.", "pasta": "documentos"}, cfg)
t = documentos.ler({"arquivo": "Proposta.docx"}, cfg)
checar("30 dias" in t and "Padaria Estrela" in t, "lê Word")
t = documentos.ler({"arquivo": "Vendas.xlsx"}, cfg)
checar("Parafuso" in t and "2.5" in t, "lê Excel (e converte número com vírgula)")
try:
    documentos.ler({"arquivo": r"C:\Windows\System32\drivers\etc\hosts"}, cfg)
    checar(False, "fora das pastas liberadas deve recusar")
except Exception:
    checar(True, "arquivo fora das pastas liberadas é recusado")
b = documentos.buscar("contrato padaria", cfg)
checar("Proposta.docx" in b, "busca por conteúdo acha o Word")
b = documentos.buscar("metas voz mercearia", cfg)
checar("ideias.md" in b, "busca acha o markdown")
checar("Não achei" in documentos.buscar("xylofone inexistente", cfg), "consulta sem resultado diz que não achou")

print("ESPECIALISTAS E ROTEADOR")
class S: modo = "geral"
s = S()
checar(especialistas.aplicar(s, "financas").startswith("Modo") and "EDUCATIVO" in especialistas.bloco(s), "liga o modo e entra no contexto")
especialistas.aplicar(s, "geral")
checar(especialistas.bloco(s) == "", "voltar ao geral limpa o contexto")
for f in ("analisa para mim as vantagens de abrir uma filial agora em Curitiba", "compara essas duas propostas de fornecedor com calma e me diz qual vale a pena"):
    checar(especialistas.parece_dificil(f), f"difícil: {f[:50]}")
for f in ("abre a calculadora", "que horas são", "qual a capital da frança", "tchau"):
    checar(not especialistas.parece_dificil(f), f"simples: {f}")

print("CUSTOS")
custos.ARQ = tmp / "custos.jsonl"
class U: input_tokens = 10000; cache_read_input_tokens = 8000; output_tokens = 500
v = custos.registrar("deepseek-flash", U())
checar(0 < v < 0.01 and custos.hoje()["usd"] >= v - 0.0001, f"custo estimado de uma chamada: US$ {v:.5f}")
checar(custos.dentro_do_orcamento(0.5) and not custos.dentro_do_orcamento(0.0000001), "teto diário funciona")

print("PESQUISA (web real: busca + leitura das páginas, sem modelo)")
async def web():
    import httpx
    async with httpx.AsyncClient(headers=pesquisa.CAB, timeout=httpx.Timeout(12.0, connect=6.0), follow_redirects=True) as cli:
        res = await pesquisa._buscar_ddg(cli, "linguagem de programação Python história")
        checar(len(res) >= 3 and all(r["url"].startswith("http") for r in res), f"busca trouxe {len(res)} resultados (ex.: {res[0]['url'][:60] if res else None})")
        lidas = [p for p in await asyncio.gather(*[pesquisa._ler(cli, r) for r in res[:6]]) if p]
        checar(lidas and all(len(p["texto"]) > 300 for p in lidas), f"leu {len(lidas)} páginas com texto")
asyncio.run(web())

print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
sys.exit(0 if ok else 1)
