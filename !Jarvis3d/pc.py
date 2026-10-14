"""
Ferramentas de controle do notebook: arquivos, janelas/volume e mouse/teclado.

Segurança (tudo imposto aqui no código, não pelo modelo):
- Arquivos: só nas pastas de "pastas_liberadas"; nunca apaga (vai para _Jarvis-lixo);
  tudo que muda algo passa por sessao.confirmar() e dá para desfazer.
- Mouse/teclado: só depois de iniciar_controle ser autorizado; limite de ações por pedido;
  freio de emergência (mouse no canto superior esquerdo); telas sensíveis e atalhos perigosos
  pedem confirmação extra.
"""

import asyncio
import os
import re
from pathlib import Path

import arquivos
import uia
import windows_ctl
from navegador import RISCO_ACAO


def _def(nome, descricao, props, req):
    return {"name": nome, "description": descricao,
            "input_schema": {"type": "object", "properties": props, "required": req}}


def definicoes() -> list[dict]:
    return [
        _def("listar_pasta", "Lista o conteúdo de uma pasta liberada (Downloads, Área de Trabalho, Documentos ou um caminho dentro delas).",
             {"pasta": {"type": "string"}}, ["pasta"]),
        _def("organizar_pasta", "Organiza os arquivos soltos de uma pasta liberada em subpastas por tipo (Imagens, PDFs, Documentos...). Mostra o plano e PEDE CONFIRMAÇÃO ao usuário antes de mover. Nunca apaga nada e dá para desfazer.",
             {"pasta": {"type": "string"}}, ["pasta"]),
        _def("mover_itens", "Move arquivos ou pastas específicos para outra pasta (dentro das liberadas). Pede confirmação.",
             {"pasta_origem": {"type": "string"},
              "itens": {"type": "array", "items": {"type": "string"}, "description": "Nomes dos itens dentro da pasta de origem."},
              "destino": {"type": "string", "description": "Pasta de destino; se for só um nome, vira subpasta da origem."}},
             ["pasta_origem", "itens", "destino"]),
        _def("renomear_item", "Renomeia um arquivo ou pasta. Pede confirmação.",
             {"pasta": {"type": "string"}, "nome_atual": {"type": "string"}, "novo_nome": {"type": "string"}},
             ["pasta", "nome_atual", "novo_nome"]),
        _def("criar_pasta", "Cria uma pasta nova dentro de uma pasta liberada.",
             {"pasta_pai": {"type": "string"}, "nome": {"type": "string"}}, ["pasta_pai", "nome"]),
        _def("mover_para_lixo", "'Apaga' itens movendo-os para a pasta _Jarvis-lixo (recuperável). Pede confirmação. É a única forma de se livrar de arquivos; não existe apagar de vez.",
             {"pasta_origem": {"type": "string"}, "itens": {"type": "array", "items": {"type": "string"}}},
             ["pasta_origem", "itens"]),
        _def("desfazer_organizacao", "Desfaz a última movimentação ou renomeação feita pelo Jarvis, devolvendo os arquivos aos lugares originais. Pede confirmação.", {}, []),
        _def("abrir_pasta", "Abre uma pasta liberada no Explorador de Arquivos.", {"pasta": {"type": "string"}}, ["pasta"]),
        _def("controlar_volume", "Ajusta o volume do notebook.",
             {"acao": {"type": "string", "enum": ["subir", "descer", "mudo", "definir"]},
              "valor": {"type": "integer", "description": "Para 'definir': 0 a 100. Para subir/descer: quantos pontos percentuais (padrão 10)."}},
             ["acao"]),
        _def("controlar_midia", "Controla a música ou vídeo que estiver tocando.",
             {"acao": {"type": "string", "enum": ["play_pause", "proxima", "anterior", "parar"]}}, ["acao"]),
        _def("listar_janelas", "Lista os títulos das janelas abertas.", {}, []),
        _def("gerenciar_janela", "Foca, minimiza, maximiza, restaura ou fecha uma janela pelo trecho do título. Fechar pede confirmação.",
             {"titulo": {"type": "string", "description": "Trecho do título da janela."},
              "acao": {"type": "string", "enum": ["focar", "minimizar", "maximizar", "restaurar", "fechar"]}},
             ["titulo", "acao"]),
        _def("mostrar_area_de_trabalho", "Minimiza tudo e mostra a área de trabalho (de novo, restaura).", {}, []),
        _def("bloquear_tela", "Bloqueia o Windows (pede a senha para voltar).", {}, []),
        _def("iniciar_controle", "OBRIGATÓRIO antes de clicar, digitar, pressionar_teclas ou rolar: pede ao usuário autorização para você controlar o mouse e o teclado neste pedido. Descreva o objetivo em uma frase. Se ele recusar, desista.",
             {"objetivo": {"type": "string"}}, ["objetivo"]),
        _def("janela_ver", "PREFERIDA para operar programas do Windows: lista os controles da janela em foco (ou da janela cujo título contém 'titulo') NUMERADOS, com nome, tipo e estado (botões, campos, caixas, menus, abas, itens). Só leitura, não exige iniciar_controle. Use antes de janela_acao; os números valem só para a última lista. Se a lista vier vazia, o programa não expõe acessibilidade: use ver_tela e clicar.",
             {"titulo": {"type": "string", "description": "Trecho do título da janela; vazio = a janela em foco."}}, []),
        _def("janela_acao", "Age num controle pelo NÚMERO de janela_ver (exige iniciar_controle). Ações: clicar (aciona o botão sem mexer o mouse), duplo_clique, clique_direito, digitar (campo; use 'enter' para confirmar), alternar (caixa de seleção), expandir, recolher, selecionar, focar. Devolve a lista nova de controles. Mais confiável que clicar por coordenadas; nunca preenche senha.",
             {"numero": {"type": "integer"},
              "acao": {"type": "string", "enum": ["clicar", "duplo_clique", "clique_direito", "digitar", "alternar", "expandir", "recolher", "selecionar", "focar"]},
              "texto": {"type": "string", "description": "Para 'digitar'."}, "enter": {"type": "boolean", "description": "Apertar Enter depois de digitar."}},
             ["numero", "acao"]),
        _def("clicar", "Último recurso para programas que não expõem acessibilidade: clica numa posição da tela, em coordenadas da imagem devolvida por ver_tela (chame ver_tela antes). Devolve um print novo depois do clique.",
             {"x": {"type": "integer"}, "y": {"type": "integer"},
              "botao": {"type": "string", "enum": ["esquerdo", "direito", "meio"]}, "duplo": {"type": "boolean"}},
             ["x", "y"]),
        _def("digitar", "Digita texto no campo em foco. Devolve um print novo da tela.", {"texto": {"type": "string"}}, ["texto"]),
        _def("pressionar_teclas", "Aperta uma tecla ou combinação, ex.: 'enter', 'ctrl+c', 'alt+tab', 'ctrl+l'. Devolve um print novo da tela.",
             {"combinacao": {"type": "string"}}, ["combinacao"]),
        _def("rolar", "Rola a roda do mouse na posição atual. Positivo sobe, negativo desce (1 = ~3 linhas). Devolve um print novo da tela.",
             {"passos": {"type": "integer"}}, ["passos"]),
    ]


ROTULOS = {
    **{n: "ARQUIVOS" for n in ("listar_pasta", "organizar_pasta", "mover_itens", "renomear_item", "criar_pasta",
                               "mover_para_lixo", "desfazer_organizacao", "abrir_pasta")},
    **{n: "WINDOWS" for n in ("controlar_volume", "controlar_midia", "listar_janelas", "gerenciar_janela",
                              "mostrar_area_de_trabalho", "bloquear_tela")},
    **{n: "CONTROLE" for n in ("iniciar_controle", "clicar", "digitar", "pressionar_teclas", "rolar", "janela_acao")},
    "janela_ver": "JANELA",
}
NOMES = set(ROTULOS)
CONTROLE = {"iniciar_controle", "clicar", "digitar", "pressionar_teclas", "rolar", "janela_acao"}
LIMITE_ACOES = 20


def _texto(entrada: dict, campo: str) -> str:
    valor = entrada.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"Faltou o campo '{campo}'.")
    return valor.strip()


async def executar(nome: str, entrada: dict, config: dict, sessao, ver_tela) -> tuple[list | str, bool]:
    """Devolve (conteúdo, deu_erro). `ver_tela` é injetado para não haver import circular."""
    try:
        if nome == "janela_ver":
            return await uia.ver(str(entrada.get("titulo") or "")), False
        if nome in CONTROLE:
            return await _controle(nome, entrada, sessao, ver_tela), False
        return await _arquivos_e_janelas(nome, entrada, config, sessao), False
    except arquivos.ErroArquivos as e:
        raise ValueError(str(e))


# ================================================================== arquivos e janelas

def _itens(entrada: dict) -> list[str]:
    itens = entrada.get("itens")
    if not isinstance(itens, list) or not itens or not all(isinstance(i, str) and i.strip() for i in itens):
        raise ValueError("Faltou a lista 'itens'.")
    return [i.strip() for i in itens][:200]


def _resolver_itens(origem: Path, nomes: list[str], rs: list[Path]) -> list[Path]:
    saida = []
    for n in nomes:
        if "/" in n or "\\" in n or n.startswith(".."):
            raise ValueError(f"Use só o nome do item, sem caminho: {n}")
        saida.append(arquivos.resolver(str(origem / n), rs, permitir_raiz=False))
    return saida


def _linhas_de_movimentos(movs, limite=10) -> list[str]:
    linhas = [f"{o.name}  →  {d.parent.name}\\" for o, d in movs[:limite]]
    if len(movs) > limite:
        linhas.append(f"... e mais {len(movs) - limite}")
    return linhas


def _falhas(r: dict) -> str:
    return f" Falhas: {r['falhas'][:5]}" if r["falhas"] else ""


async def _arquivos_e_janelas(nome: str, entrada: dict, config: dict, sessao) -> str:
    rs = arquivos.raizes(config)

    if nome == "listar_pasta":
        return arquivos.listar(arquivos.resolver(_texto(entrada, "pasta"), rs))

    if nome == "abrir_pasta":
        pasta = arquivos.resolver(_texto(entrada, "pasta"), rs)
        os.startfile(str(pasta))
        return f"Pasta aberta: {pasta}"

    if nome == "criar_pasta":
        pai = arquivos.resolver(_texto(entrada, "pasta_pai"), rs)
        nome_pasta = _texto(entrada, "nome")
        if any(c in nome_pasta for c in '\\/:*?"<>|'):
            raise ValueError("Nome de pasta inválido.")
        novo = arquivos.resolver(str(pai / nome_pasta), rs, permitir_raiz=False)
        novo.mkdir(parents=True, exist_ok=True)
        return f"Pasta criada: {novo}"

    if nome == "organizar_pasta":
        pasta = arquivos.resolver(_texto(entrada, "pasta"), rs)
        plano = await asyncio.to_thread(arquivos.plano_organizar, pasta)
        if not plano["mover"]:
            return (f"Nada para organizar em {pasta.name} "
                    f"({plano['ignorados']} itens ignorados por serem atalhos, recentes ou do sistema).")
        detalhes = [f"{n} arquivo(s)  →  {cat}\\" for cat, n in sorted(plano["resumo"].items())]
        detalhes += ["", f"Pasta: {pasta}", f"Ignorados (atalhos, em uso, recentes): {plano['ignorados']}",
                     "Nada será apagado. Dá para desfazer depois."]
        if not await sessao.confirmar(
                f"Organizar {pasta.name}: mover {len(plano['mover'])} arquivos para subpastas por tipo", detalhes):
            return "O usuário cancelou. Nada foi alterado."
        r = await asyncio.to_thread(arquivos.executar, plano["mover"], rs, f"organizar {pasta.name}")
        return f"Movidos {r['feitos']} arquivos." + _falhas(r)

    if nome == "mover_itens":
        origem = arquivos.resolver(_texto(entrada, "pasta_origem"), rs)
        alvos = _resolver_itens(origem, _itens(entrada), rs)
        destino_txt = _texto(entrada, "destino")
        try:
            destino = arquivos.resolver(destino_txt, rs)
        except arquivos.ErroArquivos:
            destino = arquivos.resolver(str(origem / destino_txt), rs)
        movs = arquivos.plano_mover(alvos, destino)
        if not await sessao.confirmar(f"Mover {len(movs)} item(ns) para {destino.name}", _linhas_de_movimentos(movs)):
            return "O usuário cancelou. Nada foi alterado."
        r = await asyncio.to_thread(arquivos.executar, movs, rs, f"mover para {destino.name}")
        return f"Movidos {r['feitos']} item(ns)." + _falhas(r)

    if nome == "mover_para_lixo":
        origem = arquivos.resolver(_texto(entrada, "pasta_origem"), rs)
        alvos = _resolver_itens(origem, _itens(entrada), rs)
        movs = arquivos.plano_lixo(alvos, rs)
        detalhes = _linhas_de_movimentos(movs) + ["", "Vão para a pasta _Jarvis-lixo (não são apagados de vez)."]
        if not await sessao.confirmar(f"Mandar {len(movs)} item(ns) para o lixo do Jarvis", detalhes):
            return "O usuário cancelou. Nada foi alterado."
        r = await asyncio.to_thread(arquivos.executar, movs, rs, "mover para o lixo")
        return f"{r['feitos']} item(ns) no lixo do Jarvis (recuperáveis)." + _falhas(r)

    if nome == "renomear_item":
        pasta = arquivos.resolver(_texto(entrada, "pasta"), rs)
        alvo = _resolver_itens(pasta, [_texto(entrada, "nome_atual")], rs)[0]
        novo = _texto(entrada, "novo_nome")
        if not await sessao.confirmar(f"Renomear {alvo.name} para {novo}", [f"Pasta: {pasta}"]):
            return "O usuário cancelou. Nada foi alterado."
        final = await asyncio.to_thread(arquivos.renomear, alvo, novo, rs)
        return f"Renomeado para {final.name}."

    if nome == "desfazer_organizacao":
        rotulo, qtd = arquivos.descricao_do_desfazer()
        if not await sessao.confirmar(f"Desfazer: {rotulo} ({qtd} itens voltam ao lugar de origem)", []):
            return "O usuário cancelou. Nada foi alterado."
        r = await asyncio.to_thread(arquivos.desfazer, rs)
        return f"{r['voltaram']} item(ns) devolvidos." + _falhas(r)

    # ---- Windows
    if nome == "controlar_volume":
        await asyncio.to_thread(windows_ctl.volume, _texto(entrada, "acao"), int(entrada.get("valor") or 0))
        return "Volume ajustado."
    if nome == "controlar_midia":
        await asyncio.to_thread(windows_ctl.midia, _texto(entrada, "acao"))
        return "Feito."
    if nome == "listar_janelas":
        return "\n".join(t for _, t in windows_ctl.listar_janelas()) or "Nenhuma janela."
    if nome == "mostrar_area_de_trabalho":
        await asyncio.to_thread(windows_ctl.mostrar_area_de_trabalho)
        return "Feito."
    if nome == "bloquear_tela":
        await asyncio.to_thread(windows_ctl.bloquear_tela)
        return "Tela bloqueada."
    if nome == "gerenciar_janela":
        acao, trecho = _texto(entrada, "acao"), _texto(entrada, "titulo")
        if acao == "fechar":
            titulo = next((t for _, t in windows_ctl.listar_janelas() if trecho.lower() in t.lower()), trecho)
            if not await sessao.confirmar(f"Fechar a janela: {titulo}", ["O programa pode perguntar se você quer salvar."]):
                return "O usuário cancelou. Nada foi alterado."
        titulo = await asyncio.to_thread(windows_ctl.acao_na_janela, trecho, acao)
        return f"{acao}: {titulo}"

    raise ValueError(f"Ferramenta desconhecida: {nome}")


# ================================================================== mouse e teclado

SENSIVEL_TITULO = re.compile(
    r"banco|bank|\bpix\b|senha|password|paypal|nubank|ita[uú]|bradesco|santander|caixa econ|gov\.br|carteira|wallet|binance|cart[aã]o|cvv",
    re.IGNORECASE)
COMBO_SENSIVEL = re.compile(
    r"(^|\+)(win|windows)(\+|$)|alt\+f4|ctrl\+alt|ctrl\+shift\+(del|delete|esc)|shift\+delete", re.IGNORECASE)


async def _liberar_acao(sessao, descricao: str, combo: str = "") -> bool:
    """Confere autorização, limite, freio de emergência e telas sensíveis. False = o usuário negou esta ação."""
    c = sessao.controle
    if not c["ativo"]:
        raise ValueError("Controle não autorizado. Chame iniciar_controle primeiro.")
    if await asyncio.to_thread(windows_ctl.mouse_no_canto):
        c["ativo"] = False
        await sessao.enviar({"tipo": "controle", "ativo": False})
        raise ValueError("FREIO DE EMERGÊNCIA: o usuário jogou o mouse no canto para você parar. Pare agora e avise que parou.")
    if c["acoes"] >= LIMITE_ACOES:
        c["ativo"] = False
        await sessao.enviar({"tipo": "controle", "ativo": False})
        raise ValueError("Limite de ações atingido. Se ainda precisar continuar, chame iniciar_controle de novo.")
    foco = await asyncio.to_thread(windows_ctl.janela_em_foco)
    if SENSIVEL_TITULO.search(foco) or (combo and COMBO_SENSIVEL.search(combo)):
        if not await sessao.confirmar(
                f"Ação sensível: {descricao}",
                [f"Janela em foco: {foco}", "Pode envolver dinheiro, senha ou o sistema."]):
            return False
    c["acoes"] += 1
    return True


async def _agir(fn, *args):
    windows_ctl.EM_ACAO["v"] = True
    try:
        await asyncio.to_thread(fn, *args)
    finally:
        await asyncio.sleep(0.2)   # as teclas simuladas ainda "contam" por um instante
        windows_ctl.EM_ACAO["v"] = False


async def _controle(nome: str, entrada: dict, sessao, ver_tela) -> list | str:
    c = sessao.controle
    if nome == "iniciar_controle":
        objetivo = _texto(entrada, "objetivo")
        if c["ativo"]:
            return "O controle já está autorizado neste pedido."
        ok = getattr(sessao, "liberado", lambda _o: False)("controle") or await sessao.confirmar(
            f"Controlar mouse e teclado: {objetivo}",
            [f"Até {LIMITE_ACOES} ações neste pedido.",
             "Para parar na hora: ESC, ESPAÇO, ou jogue o mouse no canto superior esquerdo da tela.",
             "Em telas de banco/senha e atalhos perigosos, peço confirmação de novo."])
        if not ok:
            return "O usuário NÃO autorizou o controle. Não insista; diga que respeita a decisão."
        c.update(ativo=True, acoes=0)
        await sessao.enviar({"tipo": "controle", "ativo": True})
        return "Controle autorizado. Comece com janela_ver (lista numerada dos controles); use ver_tela só se a janela não expuser acessibilidade."

    if nome == "janela_acao":
        acao = _texto(entrada, "acao")
        numero, texto = entrada.get("numero"), str(entrada.get("texto") or "")
        alvo = await uia.alvo(numero)
        descricao = f"{acao} em '{alvo}'" + (f": {texto[:40]}" if acao == "digitar" and texto else "")
        if RISCO_ACAO.search(alvo):
            if not await sessao.confirmar(f"Ação de risco: {descricao}",
                                          ["O controle parece comprar, pagar, enviar, apagar ou publicar.", "Pode ser difícil de desfazer."]):
                return "O usuário negou esta ação."
        if not await _liberar_acao(sessao, descricao):
            return "O usuário negou esta ação."
        windows_ctl.EM_ACAO["v"] = True
        try:
            feito = await uia.acao(numero, acao, texto[:2000], bool(entrada.get("enter")))
        finally:
            await asyncio.sleep(0.2)
            windows_ctl.EM_ACAO["v"] = False
        await asyncio.sleep(0.6)
        try:
            lista = await uia.ver("")
        except ValueError as e:
            lista = f"(não consegui reler a janela: {e})"
        return f"{feito} ({c['acoes']}/{LIMITE_ACOES} ações)\n\n{lista}"

    if nome == "clicar":
        ox, oy = windows_ctl.TELA["orig"]
        ex, ey = windows_ctl.TELA["env"]
        if not ex:
            raise ValueError("Chame ver_tela antes de clicar, para eu saber as coordenadas.")
        x, y = int(entrada["x"]), int(entrada["y"])
        if not (0 <= x <= ex and 0 <= y <= ey):
            raise ValueError(f"Coordenada fora da imagem ({ex}x{ey}).")
        if not await _liberar_acao(sessao, f"clicar em ({x}, {y})"):
            return "O usuário negou este clique."
        await _agir(windows_ctl.clicar, round(x * ox / ex), round(y * oy / ey),
                                entrada.get("botao") or "esquerdo", bool(entrada.get("duplo")))
    elif nome == "digitar":
        texto = entrada.get("texto")
        if not isinstance(texto, str) or not texto:
            raise ValueError("Faltou o campo 'texto'.")
        if not await _liberar_acao(sessao, f"digitar: {texto[:60]}"):
            return "O usuário negou esta digitação."
        await _agir(windows_ctl.digitar, texto[:2000])
    elif nome == "pressionar_teclas":
        combo = _texto(entrada, "combinacao")
        windows_ctl.combo_para_teclas(combo)  # valida os nomes antes de pedir qualquer coisa
        if not await _liberar_acao(sessao, f"apertar {combo}", combo):
            return "O usuário negou esta ação."
        await _agir(windows_ctl.pressionar, combo)
    elif nome == "rolar":
        if not await _liberar_acao(sessao, "rolar a tela"):
            return "O usuário negou esta ação."
        await _agir(windows_ctl.rolar, max(-30, min(30, int(entrada.get("passos") or 0))))

    await asyncio.sleep(0.7)
    return await asyncio.to_thread(ver_tela, f"Ação feita ({c['acoes']}/{LIMITE_ACOES}). Tela agora:")
