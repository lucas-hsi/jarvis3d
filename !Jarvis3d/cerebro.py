"""
O "cérebro" do Jarvis: memória (banco local) + conhecimento (cofre do Obsidian = cérebro central).

- Banco (memoria.py): o que o Jarvis aprende SOBRE VOCÊ, rápido de buscar. É espelhado no cofre em Pessoal\\Memórias do Jarvis.md
  (gerada, por categoria) para o Obsidian ser a visão completa. Memória sobre assunto jurídico NÃO é espelhada.
- Cofre: lido por inteiro (índice de busca). O Jarvis só escreve nele de forma aditiva, no modelo do cofre, com link no índice:
  notas novas (ideia, aprendizado, decisão de projeto, pessoal, nota livre) e trechos acrescentados em "## Anotações do Jarvis"
  de notas existentes. Nunca reescreve nem apaga texto existente. Assunto jurídico só entra com confirmação.
"""

import re
import time
from pathlib import Path

import memoria

ESPELHO = "Memórias do Jarvis.md"
INTOCAVEIS = {"Templates", "Ferramentas", ".obsidian", ".trash", ".git"}
PASTAS_COMUNS = {"Ideias", "Aprendizados", "Pessoal", "Notas", "Templates", "Ferramentas"}
CAT_ROTULOS = {"perfil": "Perfil", "preferencia": "Preferências", "rotina": "Rotina", "pessoas": "Pessoas", "trabalho": "Trabalho", "projetos": "Projetos",
               "interesses": "Interesses", "objetivos": "Objetivos", "saude": "Saúde", "financas": "Finanças", "historia": "História",
               "opiniao": "Opiniões", "lugares": "Lugares", "outros": "Outros"}
SENSIVEL = re.compile(r"(?i)\b(processos?|advogad[oa]s?|ju[ií]z(?:a|es)?|tribunal|audi[eê]ncia|boletim de ocorr[eê]ncia|delegacia|inqu[eé]rito|criminal|queixa-crime|a[cç][aã]o judicial)\b")
SEGREDO = re.compile(r"sk-[A-Za-z0-9_\-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{12,}|(?i:password|senha|api[_-]?key|token)\s*[:=]\s*\S+")


def _def(nome, descricao, props, req):
    return {"name": nome, "description": descricao,
            "input_schema": {"type": "object", "properties": props, "required": req}}


def definicoes(tem_cofre: bool) -> list[dict]:
    ferr = [
        _def("lembrar", "Guarda na memória permanente um fato durável sobre o usuário (quem ele é, gostos, rotina, pessoas, planos, objetivos, opiniões, como prefere ser atendido). Use quando ele pedir para lembrar de algo ou contar algo importante sobre si. Uma frase completa e autônoma, ex.: 'Lucas prefere reuniões curtas pela manhã.'. Isso também é feito automaticamente depois das conversas; use esta ferramenta quando ele pedir explicitamente.",
             {"texto": {"type": "string"}, "categoria": {"type": "string", "enum": list(memoria.CATEGORIAS)},
              "importancia": {"type": "integer", "description": "3 = essencial (identidade, valores, relações, objetivos centrais), 2 = útil, 1 = detalhe."}},
             ["texto"]),
        _def("buscar_memoria", "Procura na memória permanente o que você sabe sobre o usuário. Devolve as memórias com seus ids.",
             {"consulta": {"type": "string"}}, ["consulta"]),
        _def("esquecer_memoria", "Apaga uma memória pelo id (use buscar_memoria antes para achar o id). Pede confirmação ao usuário.",
             {"id": {"type": "integer"}}, ["id"]),
    ]
    if tem_cofre:
        ferr.append(_def(
            "anotar_no_cofre",
            "Cria uma nota NOVA no Obsidian do usuário (o cérebro central dele). Tipos: 'ideia' (ideia de negócio/produto), 'aprendizado' (lição técnica ou de mercado), "
            "'decisao' (decisão de um projeto; informe 'projeto' = nome da pasta, ex.: MeuProjeto), 'pessoal' (assunto pessoal dele: pessoas, rotina, gostos, objetivos, saúde, planos; use 'categoria'), "
            "'nota' (anotação livre: reunião, conversa, pesquisa, diário). Use quando ele pedir para anotar/guardar no Obsidian, ou quando a ideia/decisão for clara. "
            "Nunca inclua senhas ou chaves. Nunca altera nota existente (para isso use acrescentar_no_cofre). Assunto jurídico pede confirmação dele. Depois diga em uma frase o que anotou e onde.",
            {"tipo": {"type": "string", "enum": ["ideia", "aprendizado", "decisao", "pessoal", "nota"]},
             "titulo": {"type": "string", "description": "Título claro em português, sem prefixos numéricos."},
             "texto": {"type": "string", "description": "Ideia: o que é e para quem (2-3 frases). Aprendizado: o que foi aprendido. Decisão: o que foi decidido. Pessoal/nota: o conteúdo."},
             "projeto": {"type": "string", "description": "Só decisão: pasta do projeto (ex.: MeuProjeto)."},
             "categoria": {"type": "string", "enum": list(memoria.CATEGORIAS), "description": "Só pessoal."},
             "contexto": {"type": "string", "description": "Decisão: o que levou a ela. Pessoal: de onde veio."},
             "alternativas": {"type": "string", "description": "Só decisão: alternativas descartadas."},
             "consequencias": {"type": "string", "description": "Só decisão: o que muda a partir de agora."},
             "por_que": {"type": "string", "description": "Só ideia: por que pode funcionar."},
             "duvidas": {"type": "string", "description": "Só ideia: dúvidas e restrições reais."},
             "como_validar": {"type": "string", "description": "Só ideia: como validar sem construir nada."},
             "origem": {"type": "string", "description": "Só aprendizado: de onde veio."},
             "como_aplicar": {"type": "string", "description": "Só aprendizado: quando lembrar e o que fazer."},
             "links": {"type": "array", "items": {"type": "string"}, "description": "Títulos de notas existentes para ligar (aparecem no grafo)."},
             "tags": {"type": "array", "items": {"type": "string"}}},
            ["tipo", "titulo", "texto"]))
        ferr.append(_def(
            "acrescentar_no_cofre",
            "Acrescenta uma linha datada ao fim de uma nota JÁ EXISTENTE do Obsidian (numa seção '## Anotações do Jarvis'), sem mexer no texto que existe. "
            "Use para atualizar uma nota de projeto, pessoa ou assunto com algo novo. Informe o título da nota. Nunca inclua senhas ou chaves.",
            {"nota": {"type": "string", "description": "Título da nota existente (use consultar_cofre para achar)."},
             "texto": {"type": "string", "description": "O que acrescentar (curto)."}}, ["nota", "texto"]))
    return ferr


ROTULOS = {"lembrar": "MEMÓRIA", "buscar_memoria": "MEMÓRIA", "esquecer_memoria": "MEMÓRIA", "anotar_no_cofre": "OBSIDIAN", "acrescentar_no_cofre": "OBSIDIAN"}
PEDEM_CONFIRMACAO = {"esquecer_memoria", "anotar_no_cofre", "acrescentar_no_cofre"}      # esperam o usuário (assunto jurídico)
NOMES = set(ROTULOS)


def _texto(entrada: dict, campo: str) -> str:
    v = entrada.get(campo)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"Faltou o campo '{campo}'.")
    return v.strip()


async def executar(nome: str, entrada: dict, ctx) -> str:
    """ctx: .mem, .sessao, .cofre (Path|None), .nome, .ao_memorizar(item) (async), .reindexar() (callable)."""
    if nome == "lembrar":
        texto = _texto(entrada, "texto")
        if SEGREDO.search(texto):
            raise ValueError("Isso parece conter uma senha ou chave; não guardo segredos na memória.")
        id_, nova = ctx.mem.salvar(texto, entrada.get("categoria") or "outros", entrada.get("importancia") or 2, fonte="pedido")
        await ctx.ao_memorizar({"id": id_, "texto": texto, "nova": nova})
        return f"Memória {'guardada' if nova else 'já existia; reforçada'} (id {id_})."

    if nome == "buscar_memoria":
        achadas = ctx.mem.buscar(_texto(entrada, "consulta"), 8)
        if not achadas:
            return "Nada na memória sobre isso."
        return "\n".join(f"[id {r['id']}] ({r['categoria']}) {r['texto']}" for r in achadas)

    if nome == "esquecer_memoria":
        id_ = int(entrada.get("id") or 0)
        linha = ctx.mem.db.execute("SELECT texto FROM memorias WHERE id=?", (id_,)).fetchone()
        if not linha:
            raise ValueError("Não existe memória com esse id.")
        if not await ctx.sessao.confirmar("Esquecer esta memória", [linha["texto"], "", "Isso apaga de vez do banco."]):
            return "O usuário cancelou. Nada foi apagado."
        ctx.mem.esquecer(id_)
        await ctx.ao_memorizar({"id": id_, "texto": None, "nova": False})
        return "Memória apagada."

    if nome in ("anotar_no_cofre", "acrescentar_no_cofre"):
        if not ctx.cofre:
            raise ValueError("O cofre do Obsidian não está configurado.")
        if SENSIVEL.search(" ".join(str(v) for v in entrada.values())):
            if not await ctx.sessao.confirmar("Anotar assunto jurídico no Obsidian", [f"Nota: {str(entrada.get('titulo') or entrada.get('nota') or '')[:80]}",
                                                                                     "Você decidiu manter o caso jurídico fora do cofre (vault separado).",
                                                                                     "Só anoto aqui se você confirmar."]):
                return "O usuário cancelou. Nada foi anotado."
        if nome == "acrescentar_no_cofre":
            caminho = acrescentar(ctx.cofre, entrada)
            ctx.reindexar()
            return f"Acrescentado em {caminho.relative_to(ctx.cofre).as_posix()} (seção Anotações do Jarvis)."
        caminho = anotar(ctx.cofre, entrada)
        ctx.reindexar()
        return f"Nota criada: {caminho.relative_to(ctx.cofre).as_posix()} (e ligada no índice/hub)."

    raise ValueError(f"Ferramenta desconhecida: {nome}")


# ================================================================== escrita aditiva no Obsidian

def _titulo_seguro(titulo: str) -> str:
    t = re.sub(r'[\\/:*?"<>|#^\[\]]', " ", titulo)
    t = " ".join(t.split()).strip(" .")[:90]
    if len(t) < 6:
        raise ValueError("Título curto demais.")
    return t


def _secao(texto: str | None, padrao: str = "_A preencher._") -> str:
    texto = (texto or "").strip()
    if SEGREDO.search(texto):
        raise ValueError("A nota pareceu conter senha ou chave; não anotei.")
    return texto or padrao


def _inserir_no_indice(indice: Path, cabecalho: str, linha: str):
    """Acrescenta `linha` ao fim da lista que fica sob `cabecalho`. Não mexe em mais nada."""
    linhas = indice.read_text(encoding="utf-8").split("\n")
    try:
        i = next(k for k, l in enumerate(linhas) if l.strip() == cabecalho)
    except StopIteration:
        raise ValueError(f"O índice {indice.name} não tem a seção '{cabecalho}'.")
    fim, ultimo_item = len(linhas), None
    for k in range(i + 1, len(linhas)):
        if linhas[k].startswith("## "):
            fim = k
            break
        if linhas[k].startswith("- "):
            ultimo_item = k
    if ultimo_item is not None:
        linhas.insert(ultimo_item + 1, linha)
    else:
        linhas[i + 1:i + 1] = ["", linha]
    indice.write_text("\n".join(linhas), encoding="utf-8")


def _notas_existentes(raiz: Path) -> dict[str, Path]:
    return {c.stem.lower(): c for c in raiz.rglob("*.md") if not any(x in INTOCAVEIS for x in c.relative_to(raiz).parts)}


def _relacionados(raiz: Path, base: list[str], pedidos) -> str:
    """Lista '- [[x]]' com os links fixos + os títulos pedidos que existem de verdade no cofre (os outros são ignorados)."""
    existentes = _notas_existentes(raiz)
    nomes = list(base)
    for t in (pedidos or [])[:8]:
        c = existentes.get(str(t).strip().removesuffix(".md").lower())
        if c and c.stem not in nomes:
            nomes.append(c.stem)
    return "\n".join(f"- [[{n}]]" for n in nomes)


def _indice_garantido(indice: Path, titulo: str, descricao: str):
    if not indice.exists():
        indice.parent.mkdir(parents=True, exist_ok=True)
        indice.write_text(f"---\ntipo: projeto\nstatus: ativo\ncriado: {time.strftime('%Y-%m-%d')}\ntags: [jarvis]\n---\n\n# {titulo}\n\n{descricao}\n\n"
                          "Voltar para [[Bem-vindo]].\n\n## Notas\n\n_Nenhuma ainda._\n", encoding="utf-8", newline="\n")


def anotar(raiz: Path, dados: dict) -> Path:
    raiz = Path(raiz).resolve()
    tipo = _texto(dados, "tipo")
    titulo = _titulo_seguro(_texto(dados, "titulo"))
    hoje = time.strftime("%Y-%m-%d")
    tags = [re.sub(r"[^a-z0-9\-áéíóúâêôãõç]", "", str(t).lower().replace(" ", "-")) for t in (dados.get("tags") or [])[:6]]
    tags = [t for t in tags if t]
    corpo_tags = "[" + ", ".join(tags) + "]"
    ligacoes = dados.get("links")
    hub_projeto = None

    if tipo == "ideia":
        pasta, indice, cabecalho = raiz / "Ideias", raiz / "Ideias" / "Ideias.md", "## Em validação"
        texto = f"""---
tipo: ideia
status: em validação
criado: {hoje}
tags: {corpo_tags}
---

# {titulo}

## A ideia

{_secao(dados.get("texto"))}

## Por que pode funcionar

{_secao(dados.get("por_que"))}

## Dúvidas e riscos

{_secao(dados.get("duvidas"))}

## Como validar

{_secao(dados.get("como_validar"))}

## Relacionado

{_relacionados(raiz, ["Ideias"], ligacoes)}
"""
        linha_indice = f"- [[{titulo}]] ({hoje})"
    elif tipo == "aprendizado":
        pasta, indice, cabecalho = raiz / "Aprendizados", raiz / "Aprendizados" / "Aprendizados.md", "## Notas"
        texto = f"""---
tipo: aprendizado
status: ativo
criado: {hoje}
tags: {corpo_tags}
---

# {titulo}

## O que aprendi

{_secao(dados.get("texto"))}

## De onde veio

{_secao(dados.get("origem"), "Conversa com o Jarvis.")}

## Como aplicar

{_secao(dados.get("como_aplicar"))}

## Relacionado

{_relacionados(raiz, ["Aprendizados"], ligacoes)}
"""
        linha_indice = f"- [[{titulo}]] ({hoje})"
    elif tipo == "decisao":
        projeto = _texto(dados, "projeto")
        projetos = sorted(d.name for d in raiz.iterdir() if d.is_dir() and d.name not in PASTAS_COMUNS and not d.name.startswith(".") and (d / f"{d.name}.md").exists())
        achado = next((n for n in projetos if n.lower() == projeto.lower()), None)
        if not achado:
            raise ValueError(f"Não existe o projeto '{projeto}' no cofre. Projetos: {', '.join(projetos) or '(nenhum)'}.")
        hub_projeto = raiz / achado / f"{achado}.md"
        pasta, indice, cabecalho = raiz / achado / "Decisões", None, None
        texto = f"""---
tipo: decisão
status: decidido
criado: {hoje}
projeto: "[[{achado}]]"
tags: {corpo_tags}
---

# {titulo}

## Contexto

{_secao(dados.get("contexto"))}

## Decisão

{_secao(dados.get("texto"))}

## Alternativas descartadas

{_secao(dados.get("alternativas"))}

## Consequências

{_secao(dados.get("consequencias"))}

## Relacionado

{_relacionados(raiz, [achado], ligacoes)}
"""
        linha_indice = None
    elif tipo == "pessoal":
        categoria = dados.get("categoria") if dados.get("categoria") in memoria.CATEGORIAS else "outros"
        pasta, indice, cabecalho = raiz / "Pessoal", raiz / "Pessoal" / "Pessoal.md", "## Notas"
        _indice_garantido(indice, "Pessoal", "Tudo sobre o Lucas que o Jarvis aprende ou que ele pede para anotar.")
        texto = f"""---
tipo: pessoal
categoria: {categoria}
status: ativo
criado: {hoje}
tags: {corpo_tags}
---

# {titulo}

## O que é

{_secao(dados.get("texto"))}

## Contexto

{_secao(dados.get("contexto"), f"Conversa com o Jarvis em {hoje}.")}

## Relacionado

{_relacionados(raiz, ["Pessoal"], ligacoes)}
"""
        linha_indice = f"- [[{titulo}]] ({CAT_ROTULOS[categoria].lower()}, {hoje})"
    elif tipo == "nota":
        pasta, indice, cabecalho = raiz / "Notas", raiz / "Notas" / "Notas.md", "## Notas"
        _indice_garantido(indice, "Notas", "Anotações livres pedidas ao Jarvis: reuniões, conversas, pesquisas, diário.")
        texto = f"""---
tipo: nota
status: ativo
criado: {hoje}
tags: {corpo_tags}
---

# {titulo}

## Anotação

{_secao(dados.get("texto"))}

## Relacionado

{_relacionados(raiz, ["Notas"], ligacoes)}
"""
        linha_indice = f"- [[{titulo}]] ({hoje})"
    else:
        raise ValueError("Tipo deve ser ideia, aprendizado, decisao, pessoal ou nota.")

    pasta.mkdir(parents=True, exist_ok=True)
    destino = (pasta / f"{titulo}.md").resolve()
    if raiz not in destino.parents:
        raise ValueError("Caminho inválido.")
    if destino.exists() or titulo.lower() in _notas_existentes(raiz):
        raise ValueError("Já existe uma nota com esse título. Escolha outro (não sobrescrevo notas); para acrescentar algo nela, use acrescentar_no_cofre.")
    if indice is not None and not indice.exists():
        raise ValueError(f"Não achei o índice {indice.name}.")
    destino.write_text(texto, encoding="utf-8", newline="\n")
    if indice is not None:
        _inserir_no_indice(indice, cabecalho, linha_indice)
        if tipo in ("pessoal", "nota"):
            _tirar_placeholder(indice)
    if hub_projeto is not None:
        _anexar_decisao_no_hub(hub_projeto, titulo, hoje)
    return destino


def _tirar_placeholder(indice: Path):
    """Quando entra a primeira nota, sai o '_Nenhuma ainda._' dos índices criados pelo Jarvis."""
    txt = indice.read_text(encoding="utf-8")
    if "\n_Nenhuma ainda._\n" in txt and "\n- [[" in txt.split("## Notas", 1)[-1]:
        indice.write_text(txt.replace("\n_Nenhuma ainda._\n", "\n", 1), encoding="utf-8", newline="\n")


def _anexar_decisao_no_hub(hub: Path, titulo: str, hoje: str):
    """Se o hub tem a linha '- Decisões: [[..]], ...', acrescenta a nova no fim dela. Senão, só o backlink da própria nota liga."""
    linhas = hub.read_text(encoding="utf-8").split("\n")
    for k, l in enumerate(linhas):
        if l.startswith("- Decisões:"):
            linhas[k] = f"{l}, [[{titulo}]] ({hoje})"
            hub.write_text("\n".join(linhas), encoding="utf-8", newline="\n")
            return


def _achar_nota(raiz: Path, nome: str) -> Path:
    n = nome.strip().removesuffix(".md").lower()
    cand = [c for c in raiz.rglob("*.md") if not any(x in INTOCAVEIS for x in c.relative_to(raiz).parts) and c.name not in ("CLAUDE.md", ESPELHO)]
    exatas = [c for c in cand if c.stem.lower() == n]
    if len(exatas) == 1:
        return exatas[0]
    escolhas = exatas or [c for c in cand if n and n in c.stem.lower()]
    if len(escolhas) == 1:
        return escolhas[0]
    if not escolhas:
        raise ValueError(f"Não achei nenhuma nota chamada '{nome}'. Use consultar_cofre para ver os títulos.")
    raise ValueError("Mais de uma nota combina: " + "; ".join(c.relative_to(raiz).as_posix() for c in escolhas[:6]) + ". Diga o título exato.")


def acrescentar(raiz: Path, dados: dict) -> Path:
    raiz = Path(raiz).resolve()
    destino = _achar_nota(raiz, _texto(dados, "nota")).resolve()
    if raiz not in destino.parents:
        raise ValueError("Caminho inválido.")
    texto = _secao(dados.get("texto")).replace("\n", "\n  ")
    if len(texto) > 1500:
        raise ValueError("Texto grande demais para acrescentar (máx. 1500 caracteres). Crie uma nota nova.")
    entrada = f"- {time.strftime('%Y-%m-%d')}: {texto}"
    cab = "## Anotações do Jarvis"
    linhas = destino.read_text(encoding="utf-8").rstrip("\n").split("\n")
    if cab in linhas:
        i = linhas.index(cab)
        fim = next((k for k in range(i + 1, len(linhas)) if linhas[k].startswith("## ")), len(linhas))
        while fim - 1 > i and not linhas[fim - 1].strip():
            fim -= 1
        linhas[fim:fim] = [entrada]
    else:
        linhas += ["", cab, "", entrada]
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8", newline="\n")
    return destino


def espelhar_memorias(raiz: Path, mem) -> int:
    """Gera Pessoal\\Memórias do Jarvis.md a partir do banco (por categoria). Só reescreve se mudou. Devolve quantas memórias entraram."""
    raiz = Path(raiz).resolve()
    por_cat: dict[str, list[str]] = {}
    fora = 0
    for r in mem.todas():
        if SENSIVEL.search(r["texto"]):
            fora += 1
            continue
        marca = "⭐ " if r["importancia"] >= 3 else ""
        por_cat.setdefault(r["categoria"] if r["categoria"] in CAT_ROTULOS else "outros", []).append(f"- {marca}{r['texto']} (id {r['id']})")
    n = sum(len(v) for v in por_cat.values())
    partes = [f"---\ntipo: referência\nstatus: ativo\ngerado_por: jarvis\natualizado: {time.strftime('%Y-%m-%d')}\ntags: [jarvis, memória]\n---\n",
              "# Memórias do Jarvis\n",
              f"Gerada sozinha a partir do banco do Jarvis ({n} memórias). **Não edite aqui**: peça ao Jarvis para lembrar, corrigir ou esquecer. "
              "⭐ = essencial. Veja também [[Pessoal]].\n"]
    for cat in CAT_ROTULOS:
        if cat in por_cat:
            partes += [f"## {CAT_ROTULOS[cat]}\n", "\n".join(por_cat[cat]) + "\n"]
    if fora:
        partes.append(f"_{fora} memória(s) sobre assuntos jurídicos ficam só no banco local, fora do cofre._\n")
    novo = "\n".join(partes)
    destino = raiz / "Pessoal" / ESPELHO
    atual = destino.read_text(encoding="utf-8") if destino.exists() else ""
    if novo.split("\n", 6)[-1] != atual.split("\n", 6)[-1] or not destino.exists():       # ignora só a data do cabeçalho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(novo, encoding="utf-8", newline="\n")
    return n


# ================================================================== aprendizado automático

FERRAMENTA_REGISTRO = {
    "name": "registrar_memorias",
    "description": "Registra o que vale lembrar sobre o usuário a partir desta troca. Lista vazia se nada vale.",
    "input_schema": {"type": "object", "properties": {"operacoes": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "acao": {"type": "string", "enum": ["adicionar", "atualizar"]},
            "id": {"type": "integer", "description": "Só para 'atualizar': id da memória existente."},
            "texto": {"type": "string", "description": "Uma frase completa e autônoma, em português, na terceira pessoa."},
            "categoria": {"type": "string", "enum": list(memoria.CATEGORIAS)},
            "importancia": {"type": "integer", "description": "3 essencial, 2 útil, 1 detalhe."},
        },
        "required": ["acao", "texto"]}}},
        "required": ["operacoes"]},
}

PROMPT_APRENDIZ = """Você é o módulo de memória do Jarvis, o assistente pessoal de {nome}. Leia a troca abaixo e registre só fatos DURÁVEIS e úteis sobre {nome}: quem ele é, gostos, rotina, pessoas importantes, planos, objetivos, opiniões, valores, interesses, decisões, como prefere ser atendido, histórias que ele contou.

Regras:
- Só vale o que {nome} disse ou deixou claro. Nunca registre algo que só o assistente afirmou.
- Ignore o passageiro e o trivial (pedir volume, perguntar as horas, comandos). Ignore perguntas gerais sobre o mundo, a menos que revelem um interesse ou objetivo dele.
- Não repita o que já existe na lista de memórias. Se for correção ou atualização de uma existente, use 'atualizar' com o id dela.
- Cada memória: uma frase completa e autônoma, na terceira pessoa ("{nome} prefere...", "A irmã de {nome} se chama...").
- Nunca registre senhas, chaves, números de documentos ou de cartão.
- Importância: 3 = essencial (identidade, valores, relações próximas, objetivos centrais, preferências de atendimento); 2 = útil; 1 = detalhe.
- Se nada vale a pena (acontece na maioria das trocas), devolva a lista vazia. No máximo 4 operações."""


async def aprender(ai, modelo: str, mem, nome: str, fala_usuario: str, resposta: str) -> list[dict]:
    """Extrai memórias novas da troca. Devolve [{id, texto, nova}] do que mudou. Nunca levanta erro para quem chama."""
    if len(fala_usuario.strip()) < 15:
        return []
    existentes = mem.buscar(fala_usuario + " " + resposta, 10, marcar_uso=False)
    lista = "\n".join(f"[{r['id']}] {r['texto']}" for r in existentes) or "(nenhuma ainda)"
    conteudo = (f"Memórias já existentes:\n{lista}\n\n--- TROCA ---\n{nome} disse: {fala_usuario}\nJarvis respondeu: {resposta}")
    try:
        r = await ai.messages.create(
            model=modelo, max_tokens=900, system=PROMPT_APRENDIZ.replace("{nome}", nome),
            messages=[{"role": "user", "content": conteudo}],
            tools=[FERRAMENTA_REGISTRO], tool_choice={"type": "tool", "name": "registrar_memorias"},
            output_config={"effort": "low"})
    except Exception as e:
        print(f"[jarvis] aprendizado falhou: {type(e).__name__}: {e}", flush=True)
        return []
    bloco = next((b for b in r.content if b.type == "tool_use"), None)
    operacoes = (bloco.input or {}).get("operacoes") if bloco else None
    if not isinstance(operacoes, list):
        return []
    mudou = []
    for op in operacoes[:4]:
        try:
            texto = str(op["texto"])
            if SEGREDO.search(texto):
                continue
            if op.get("acao") == "atualizar" and op.get("id"):
                if mem.atualizar(int(op["id"]), texto, op.get("categoria"), op.get("importancia")):
                    mudou.append({"id": int(op["id"]), "texto": texto, "nova": False})
            else:
                id_, nova = mem.salvar(texto, op.get("categoria") or "outros", op.get("importancia") or 2, fonte="aprendido")
                if nova:
                    mudou.append({"id": id_, "texto": texto, "nova": True})
        except (KeyError, ValueError, TypeError):
            continue
    return mudou
