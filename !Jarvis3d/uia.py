"""
Controle de programas do Windows pela ÁRVORE DE ACESSIBILIDADE (Microsoft UI Automation), não por pixels.

Antes: o Jarvis via um print, "adivinhava" coordenadas e clicava no pixel (errava com DPI, janela movida, tema...).
Agora: janela_ver lista os controles NUMERADOS (botão, campo, caixa, menu...) com o nome que o programa expõe, e
janela_acao age no controle pelo número: aciona o botão pelo padrão Invoke (sem mover o mouse), escreve no campo
pelo padrão Value, marca/desmarca, expande, seleciona. Só cai no clique de mouse quando o controle não oferece
nenhum padrão. É o mesmo modelo que o navegador.py já usa nas páginas (elementos numerados).

Segurança (a autorização, o limite de ações, o freio e as telas sensíveis ficam em pc.py, igual ao mouse/teclado):
- campos de senha NUNCA são preenchidos; ver a árvore é só leitura;
- o número vale para o último janela_ver; se o controle sumiu ou mudou de nome, a ação é recusada (peça janela_ver de novo).

Todas as chamadas COM rodam numa única thread dedicada (UI Automation exige a mesma thread de ponta a ponta).
Sem a biblioteca `uiautomation` instalada, as ferramentas respondem com uma mensagem clara e o resto do Jarvis segue.
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

try:
    import uiautomation as auto
    DISPONIVEL = True
except Exception:          # biblioteca ausente (ou COM indisponível): as ferramentas avisam, nada quebra
    auto = None
    DISPONIVEL = False

AVISO_INSTALAR = ("O controle por UI Automation precisa da biblioteca 'uiautomation'. "
                  "Peça ao Lucas para rodar no terminal: C:\\Jarvis\\.venv\\Scripts\\pip install uiautomation")

LIMITE_ITENS = 90          # controles interativos listados por janela
LIMITE_VISITAS = 3000      # controles examinados no máximo
ORCAMENTO_SEG = 5.0        # tempo máximo percorrendo a árvore
PROFUNDIDADE = 16

_INIT = None


def _iniciar_thread():
    global _INIT
    if DISPONIVEL:
        _INIT = auto.UIAutomationInitializerInThread(debug=False)   # mantém o COM vivo enquanto a thread existir


EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia", initializer=_iniciar_thread)

# tipo do UIA -> nome falado; só estes entram na lista numerada
TIPOS = {
    "ButtonControl": "botão", "SplitButtonControl": "botão", "HyperlinkControl": "link",
    "EditControl": "campo", "ComboBoxControl": "lista", "CheckBoxControl": "caixa", "RadioButtonControl": "opção",
    "MenuItemControl": "menu", "TabItemControl": "aba", "ListItemControl": "item", "TreeItemControl": "item",
    "SliderControl": "controle", "SpinnerControl": "controle", "DataItemControl": "item",
}
CONTAINERS_IGNORADOS = {"ScrollBarControl", "ThumbControl", "TitleBarControl"}

SNAPSHOT: dict = {"janela": "", "controles": {}, "meta": {}, "quando": 0.0}


class ErroUIA(ValueError):
    pass


def _exigir():
    if not DISPONIVEL:
        raise ErroUIA(AVISO_INSTALAR)


# ------------------------------------------------------------------ janelas

def _janelas_topo():
    return [c for c in auto.GetRootControl().GetChildren() if c.ControlTypeName == "WindowControl" or c.Name]


def _achar_janela(titulo: str = ""):
    """Janela em foco, ou a primeira cujo título contém `titulo` (sem diferenciar maiúsculas)."""
    titulo = (titulo or "").strip().lower()
    if not titulo:
        foco = auto.GetForegroundControl()
        if foco is None:
            raise ErroUIA("Não há janela em foco.")
        return foco.GetTopLevelControl() or foco
    for j in _janelas_topo():
        try:
            if titulo in (j.Name or "").lower():
                return j
        except Exception:
            continue
    raise ErroUIA(f"Não achei nenhuma janela com '{titulo}'. Use listar_janelas para ver os títulos.")


def _programa(janela) -> str:
    try:
        import psutil
        return psutil.Process(janela.ProcessId).name()
    except Exception:
        return ""


def _padrao(c, nome: str):
    """Padrão de acessibilidade do controle ('Invoke', 'Value', 'Toggle'...) ou None se ele não oferece."""
    f = getattr(c, f"Get{nome}Pattern", None)
    try:
        if f is not None:
            return f()
        pid = getattr(auto.PatternId, f"{nome}Pattern", None)
        return c.GetPattern(pid) if pid is not None else None
    except Exception:
        return None


# ------------------------------------------------------------------ ler a árvore

def _rect_ok(c) -> bool:
    try:
        r = c.BoundingRectangle
        return r.width() > 2 and r.height() > 2
    except Exception:
        return False


def _valor(c) -> str:
    try:
        p = _padrao(c, "Value")
        return (p.Value or "") if p else ""
    except Exception:
        return ""


def _estado_alternancia(c) -> str:
    try:
        p = _padrao(c, "Toggle")
        if p:
            return {0: "desmarcada", 1: "marcada", 2: "indeterminada"}.get(int(p.ToggleState), "")
    except Exception:
        pass
    return ""


def _selecionado(c) -> bool:
    try:
        p = _padrao(c, "SelectionItem")
        return bool(p and p.IsSelected)
    except Exception:
        return False


def ver_janela(titulo: str = "") -> str:
    """Texto com a janela e seus controles numerados. Roda na thread do UIA."""
    _exigir()
    janela = _achar_janela(titulo)
    nome_janela = janela.Name or "(sem título)"
    controles, meta, linhas, textos = {}, {}, [], []
    visitas, inicio, cortou = 0, time.perf_counter(), False
    vistos = set()
    for c, _prof in auto.WalkControl(janela, includeTop=False, maxDepth=PROFUNDIDADE):
        visitas += 1
        if visitas > LIMITE_VISITAS or time.perf_counter() - inicio > ORCAMENTO_SEG:
            cortou = True
            break
        try:
            tipo = c.ControlTypeName
            if tipo == "TextControl":
                if len(textos) < 14 and not c.IsOffscreen and (c.Name or "").strip():
                    textos.append(" ".join(c.Name.split())[:90])
                continue
            falado = TIPOS.get(tipo)
            if not falado or c.IsOffscreen or not _rect_ok(c):
                continue
            nome = " ".join((c.Name or c.AutomationId or "").split())[:90]
            if not nome and tipo != "EditControl":
                continue
            r = c.BoundingRectangle
            chave = (tipo, nome, r.left // 20, r.top // 20)
            if chave in vistos:
                continue
            vistos.add(chave)
            senha = bool(getattr(c, "IsPassword", False))
            extra = []
            if tipo == "EditControl":
                extra.append("SENHA, não preencho" if senha else (f'= "{_valor(c)[:50]}"' if _valor(c) else "vazio"))
            alt = _estado_alternancia(c) if tipo in ("CheckBoxControl", "ButtonControl", "MenuItemControl") else ""
            if alt:
                extra.append(alt)
            if tipo in ("RadioButtonControl", "ListItemControl", "TabItemControl", "TreeItemControl") and _selecionado(c):
                extra.append("selecionado")
            if not c.IsEnabled:
                extra.append("desativado")
            n = len(controles) + 1
            controles[n] = c
            meta[n] = {"nome": nome, "tipo": tipo, "senha": senha}
            linhas.append(f"[{n}] {falado}: {nome or '(sem nome)'}" + (f"  ({'; '.join(extra)})" if extra else ""))
            if len(controles) >= LIMITE_ITENS:
                cortou = True
                break
        except Exception:
            continue          # um controle problemático não derruba a lista
    SNAPSHOT.update(janela=nome_janela, controles=controles, meta=meta, quando=time.time())
    programa = _programa(janela)
    cab = f"Janela: {nome_janela}" + (f" ({programa})" if programa else "")
    corpo = "\n".join(linhas) if linhas else "(nenhum controle interativo encontrado; este programa pode não expor acessibilidade. Use ver_tela.)"
    rodape = ("\n(lista cortada: janela grande; use janela_ver com outro título ou role/abra o menu desejado)" if cortou else "")
    texto = ("\nTexto na janela: " + " | ".join(textos)) if textos else ""
    return f"{cab}\nControles:\n{corpo}{rodape}{texto}"[:9000]


# ------------------------------------------------------------------ agir

def _controle(numero) -> tuple:
    try:
        n = int(numero)
    except (TypeError, ValueError):
        raise ErroUIA("Informe o número do controle (de janela_ver).")
    c = SNAPSHOT["controles"].get(n)
    if c is None:
        raise ErroUIA("Esse número não existe. Chame janela_ver para ver a lista atual.")
    m = SNAPSHOT["meta"][n]
    try:
        vivo = c.Exists(0, 0)
        mudou = vivo and " ".join((c.Name or c.AutomationId or "").split())[:90] != m["nome"]
    except Exception:
        vivo, mudou = False, True
    if not vivo or mudou:
        raise ErroUIA("A janela mudou desde a última lista (o controle sumiu ou trocou de nome). Chame janela_ver de novo.")
    return n, c, m


def descrever_alvo(numero) -> str:
    """Nome do controle (para a confirmação e a checagem de ação de risco), sem agir."""
    _exigir()
    _, _c, m = _controle(numero)
    return m["nome"] or m["tipo"]


def agir(numero, acao: str, texto: str = "", enter: bool = False) -> str:
    """Executa a ação no controle numerado. Devolve uma frase do que foi feito. Roda na thread do UIA."""
    _exigir()
    n, c, m = _controle(numero)
    nome = m["nome"] or m["tipo"]
    if acao == "digitar":
        if m["senha"]:
            raise ErroUIA("Esse é um campo de senha: não digito senhas. Peça para o usuário preencher.")
        if m["tipo"] not in ("EditControl", "ComboBoxControl"):
            raise ErroUIA(f"'{nome}' não é um campo de texto.")
        feito = False
        try:
            p = _padrao(c, "Value")
            if p and not p.IsReadOnly:
                p.SetValue(texto)
                feito = True
        except Exception:
            feito = False
        if not feito:
            import windows_ctl
            c.SetFocus()
            time.sleep(0.15)
            windows_ctl.pressionar("ctrl+a")
            windows_ctl.digitar(texto)
        if enter:
            import windows_ctl
            c.SetFocus()
            windows_ctl.pressionar("enter")
        return f"Escrevi no campo '{nome}'" + (" e apertei Enter." if enter else ".")
    if acao == "focar":
        c.SetFocus()
        return f"Foco em '{nome}'."
    if acao == "alternar":
        p = _padrao(c, "Toggle")
        if not p:
            raise ErroUIA(f"'{nome}' não alterna (não é caixa de seleção).")
        p.Toggle()
        return f"Alternei '{nome}' (agora {_estado_alternancia(c) or 'alterado'})."
    if acao == "expandir":
        p = _padrao(c, "ExpandCollapse")
        if not p:
            raise ErroUIA(f"'{nome}' não expande.")
        p.Expand()
        return f"Expandi '{nome}'."
    if acao == "recolher":
        p = _padrao(c, "ExpandCollapse")
        if not p:
            raise ErroUIA(f"'{nome}' não recolhe.")
        p.Collapse()
        return f"Recolhi '{nome}'."
    if acao == "selecionar":
        p = _padrao(c, "SelectionItem")
        if not p:
            raise ErroUIA(f"'{nome}' não é selecionável.")
        p.Select()
        return f"Selecionei '{nome}'."
    if acao in ("clicar", "duplo_clique", "clique_direito"):
        if acao == "clicar":
            for nome_padrao, usar in (("Invoke", lambda p: p.Invoke()),
                                      ("SelectionItem", lambda p: p.Select()),
                                      ("Toggle", lambda p: p.Toggle())):
                try:
                    p = _padrao(c, nome_padrao)
                    if p:
                        usar(p)
                        return f"Acionei '{nome}'."
                except Exception:
                    continue
        # sem padrão acionável (ou duplo/direito): clique de mouse no centro do controle
        if not _rect_ok(c):
            raise ErroUIA(f"'{nome}' não está visível para clicar.")
        if acao == "duplo_clique":
            c.DoubleClick(simulateMove=False, waitTime=0.05)
        elif acao == "clique_direito":
            c.RightClick(simulateMove=False, waitTime=0.05)
        else:
            c.Click(simulateMove=False, waitTime=0.05)
        return f"Cliquei em '{nome}' (por posição, o controle não oferece acionamento direto)."
    raise ErroUIA(f"Ação desconhecida: {acao}")


# ------------------------------------------------------------------ pontes assíncronas (o resto do Jarvis é asyncio)

async def ver(titulo: str = "") -> str:
    _exigir()
    return await asyncio.get_running_loop().run_in_executor(EXEC, ver_janela, titulo)


async def alvo(numero) -> str:
    _exigir()
    return await asyncio.get_running_loop().run_in_executor(EXEC, descrever_alvo, numero)


async def acao(numero, acao_: str, texto: str = "", enter: bool = False) -> str:
    _exigir()
    return await asyncio.get_running_loop().run_in_executor(EXEC, agir, numero, acao_, texto, enter)
