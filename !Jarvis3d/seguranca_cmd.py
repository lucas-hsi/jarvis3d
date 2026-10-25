"""
Classificador de risco dos comandos do Jarvis (PowerShell/cmd e scripts). Puro e testável: não executa nada.

Níveis (do mais livre ao mais preso):
- "leitura":   só lê/consulta (Get-*, dir, git status, python --version...). Roda direto, na janela visível.
- "oficina":   cria/edita/roda coisas DENTRO da Oficina do Jarvis (a pasta-sandbox). Roda direto se o pedido não leu conteúdo de fora.
- "risco":     mexe fora da Oficina, instala, baixa, apaga, mata processo, mexe no registro, agenda tarefa... Pede confirmação
               (nível alto: só "confirmo" por voz ou o clique).
- "bloqueado": destrutivo ou típico de ataque (formatar, apagar o sistema, desligar o antivírus, comando codificado, baixar e executar,
               virar administrador, ler senhas). NUNCA roda, nem com confirmação: o Jarvis explica e pede para o usuário fazer à mão.

Princípio: errar para MAIS preso. Comando desconhecido = risco (pede confirmação), nunca leitura.
"""

import re
from pathlib import Path

# ------------------------------------------------------------------ bloqueado: nunca roda
BLOQUEADO = [
    (r"\b(format(-volume)?|diskpart|clear-disk|initialize-disk|remove-partition|bcdedit|bootrec|vssadmin|wbadmin|cipher\s+/w|fsutil\s+(file\s+setzerodata|behavior))\b",
     "mexe no disco, na partição ou no boot do Windows"),
    (r"(?i)-e(nc(odedcommand)?|c)?\s+[a-z0-9+/=]{16,}|frombase64string", "comando codificado/escondido (técnica comum de ataque)"),
    (r"\b(iex|invoke-expression)\b[^\n]*\b(iwr|irm|invoke-webrequest|invoke-restmethod|net\.webclient|downloadstring|curl|wget)\b|"
     r"\b(iwr|irm|invoke-webrequest|invoke-restmethod|curl|wget|downloadstring)\b[^\n]*\|\s*(iex|invoke-expression|powershell|pwsh|cmd|bash|sh)\b",
     "baixa da internet e executa na hora"),
    (r"-verb\s+runas|\brunas(\.exe)?\s|start-process[^\n]*-verb|\bgsudo\b|\bsudo\s", "tenta rodar como administrador"),
    (r"\b(set-mppreference|add-mppreference)\b|disable(realtime|ioav|behavior)monitoring|\bnetsh\s+advfirewall\s+set\b[^\n]*\boff\b|"
     r"set-netfirewallprofile[^\n]*-enabled\s+(\$?false|0)|\buac\b[^\n]*disable|enablelua", "desliga antivírus, firewall ou o controle de conta"),
    (r"\b(mimikatz|lsass|sekurlsa|procdump)\b|\bcmdkey\s+/list|get-credential|login data|\\cookies\b|vaultcmd|"
     r"\bsam\b[^\n]*\bsave\b|reg\s+save\s+hklm", "mexe em senhas ou credenciais"),
    (r"\breg(\.exe)?\s+(delete|add|import)\s+['\"]?hk(lm|cr|u\\s-1-5-18)|remove-item[^\n]*hklm:|set-itemproperty[^\n]*hklm:|new-itemproperty[^\n]*hklm:",
     "altera o registro do sistema (HKLM)"),
    (r"\bclear-recyclebin\b|\brd\s+/s\s+/q\s+[a-z]:\\\s*$|\bshadowcopy\b", "apaga de vez (sem volta)"),
    (r"\bnet\s+(user|localgroup)\b[^\n]*\s/(add|delete)|\b(new|remove|set)-localuser\b|add-localgroupmember", "cria/remove usuários do Windows"),
    (r"\bset-executionpolicy\b[^\n]*\b(unrestricted|bypass)\b[^\n]*(localmachine|currentuser)?", "afrouxa a política de scripts do Windows de forma permanente"),
]

# alvos de sistema: apagar/mover/sobrescrever aqui é bloqueado
CAMINHO_SISTEMA = re.compile(r"(?i)([a-z]:\\(windows|program files( \(x86\))?|programdata|system volume information|recovery|boot)\b|"
                             r"\$env:(windir|systemroot|programfiles|programdata)|%(windir|systemroot|programfiles)%|\\system32\b)")
APAGAR = re.compile(r"(?i)\b(remove-item|rm|ri|del|erase|rmdir|rd)\b")
RAIZ_DE_DISCO = re.compile(r"(?i)(^|[\s'\"=])[a-z]:\\?\*?['\"]?(\s|$)|(^|\s)[\\/]\*?(\s|$)|\$env:userprofile\\?['\"]?(\s|$)|~[\\/]?(\s|$)")

# ------------------------------------------------------------------ risco: pede confirmação
RISCO = [
    (r"\b(remove-item|rm|ri|del|erase|rmdir|rd)\b", "apaga arquivos ou pastas"),
    (r"\b(iwr|irm|invoke-webrequest|invoke-restmethod|curl|wget|start-bitstransfer|net\.webclient|downloadfile|bitsadmin)\b", "baixa coisas da internet"),
    (r"\b(winget|choco|scoop|msiexec)\b|\b(pip|pip3|py\s+-m\s+pip|python\s+-m\s+pip)\s+(install|uninstall)\b|\bnpm\s+(i|install|uninstall|ci)\b|\byarn\s+add\b|install-module|install-package",
     "instala ou remove programas/pacotes (roda código de terceiros)"),
    (r"\b(stop-process|kill|taskkill|spps)\b", "fecha à força um programa"),
    (r"\b(shutdown|restart-computer|stop-computer|logoff)\b", "desliga ou reinicia o computador"),
    (r"\b(reg(\.exe)?\s+(add|delete|import)|set-itemproperty|new-itemproperty|remove-itemproperty)\b|hkcu:", "altera o registro do Windows"),
    (r"\b(schtasks|register-scheduledtask|new-service|sc(\.exe)?\s+(create|config|delete|stop)|set-service|stop-service|restart-service)\b|currentversion\\run",
     "cria tarefa agendada, serviço ou programa que inicia sozinho"),
    (r"\b(start-process|saps|invoke-item|ii)\b|\bstart\s+[^\s]", "abre/inicia outro programa"),
    (r"\b(invoke-expression|iex|invoke-command|icm|add-type|new-object\s+-com)\b|\[system\.|\[reflection\.|\$\(|`", "monta e executa código dinâmico"),
    (r"\bgit\s+(push|reset\s+--hard|clean|checkout\s+--|rebase|filter-branch)\b", "altera o repositório git de forma difícil de desfazer"),
    (r"\b(netsh|route|set-netipaddress|new-netfirewallrule|set-dnsclient)\b", "mexe na rede do Windows"),
    (r"\b(takeown|icacls|attrib|set-acl|cacls)\b", "muda permissões de arquivos"),
    (r"\b(set-executionpolicy)\b", "muda a política de scripts"),
    (r"\b(send-mailmessage|out-printer)\b", "envia algo para fora"),
    (r"\.\s*(delete|moveto|copyto|kill|invoke\w*|start|create\w*|open\w*|write\w*|setvalue|setaccesscontrol|encrypt|decrypt)\s*\(", "chama um método que altera algo"),
    (r"\b(clear-content|clear-item|set-item|set-clipboard|set-date|set-timezone|disable-\w+|enable-\w+|uninstall-\w+|suspend-\w+|resume-\w+|reset-\w+|"
     r"unregister-\w+|remove-\w+|stop-\w+|restart-\w+|wmic|cscript|wscript|mshta|rundll32|regsvr32|certutil|bitsadmin|powershell|pwsh|cmd(\.exe)?\s+/c)\b",
     "comando que altera o sistema ou abre outro interpretador"),
    (r"\.ssh\b|\.env\b|segredos|config\.json|\.aws\b|id_rsa|\.git-credentials|\btokens?\.(json|txt)\b", "toca em arquivo de segredos"),
    (r"^\s*(python3?|py|node|npx|deno|bun|pytest)\s+(?!-{1,2}(version|v)\b)(?!-0p?\b)(?!-m\s+pip\s+(list|show|freeze)\b)\S|^\s*npm\s+(run|start|test|exec)\b",
     "roda código fora da guarda da Oficina"),
]

# comandos que só leem (primeira palavra de CADA trecho do comando)
LEITURA = {
    "get-childitem", "gci", "ls", "dir", "get-content", "gc", "cat", "type", "get-item", "gi", "get-itemproperty", "gp", "get-location", "pwd",
    "get-process", "gps", "ps", "get-service", "gsv", "get-date", "get-computerinfo", "get-volume", "get-psdrive", "get-disk", "get-ciminstance",
    "get-wmiobject", "gwmi", "get-netipaddress", "get-netadapter", "get-nettcpconnection", "test-connection", "test-netconnection", "test-path",
    "resolve-path", "measure-object", "measure", "select-object", "select", "where-object", "where", "?", "sort-object", "sort", "group-object",
    "format-table", "ft", "format-list", "fl", "format-wide", "out-string", "select-string", "sls", "get-command", "gcm", "get-help", "help",
    "get-hotfix", "get-uptime", "get-filehash", "get-acl", "get-host", "get-culture", "get-timezone", "get-history", "get-module", "get-package",
    "get-startapps", "get-appxpackage", "get-printer", "get-localuser", "get-eventlog", "get-winevent", "get-clipboard", "get-random",
    "write-output", "echo", "write-host", "convertto-json", "convertfrom-json", "convertto-csv", "convertto-html", "join-path", "split-path",
    "whoami", "hostname", "ipconfig", "systeminfo", "tasklist", "where.exe", "ver", "nvidia-smi", "foreach-object", "%", "tree", "findstr",
    "get-member", "gm", "get-variable", "get-alias", "measure-command", "get-unique", "compare-object", "out-host", "out-null",
    "exit", "return", "start-sleep", "sleep", "clear-host", "cls", "write-error", "write-warning", "write-verbose", "if", "else", "elseif",
}
# comandos que leem com subcomando seguro
LEITURA_COMPOSTA = re.compile(
    r"^(git\s+(status|log|diff|branch|show|remote(\s+-v)?|rev-parse|ls-files|blame|tag|describe|config\s+--(get|list))|"
    r"(python|python3|py|node|npm|pip|pip3|git|dotnet|java|go|rustc|cargo|code|winget|choco)\s+(--version|-v|-V|version)|"
    r"py\s+-0p?|pip\s+(list|show|freeze)|npm\s+(ls|list|view|outdated)|node\s+-e\s+['\"]?console\.log|winget\s+(list|search|show)|"
    r"python\s+-c\s+['\"]?print\()", re.IGNORECASE)
# criam ou rodam coisas: liberados só se TUDO apontar para dentro da Oficina
CRIACAO = {"new-item", "ni", "mkdir", "md", "set-content", "sc", "add-content", "ac", "out-file", "copy-item", "cp", "copy", "cpi",
           "move-item", "mv", "move", "mi", "rename-item", "ren", "rni", "set-location", "cd", "sl", "push-location", "pop-location",
           "expand-archive", "compress-archive", "tee-object", "tee"}

_SEPARA = re.compile(r";|\|\||&&|\||\r?\n|[{}()]")      # blocos { } e ( ) também: o que vai dentro de um ForEach precisa ser seguro
_CAMINHO_ABS = re.compile(r"(?i)(?<![\w$])([a-z]:[\\/][^\s'\";|<>]*|\\\\[^\s'\";|<>]+|\$env:[a-z]+[^\s'\";|<>]*|%[a-z]+%[^\s'\";|<>]*|~[\\/][^\s'\";|<>]*)")
_REDIRECIONA = re.compile(r"\d?>>?\s*['\"]?([^\s'\";|]+)")


def _dentro(caminho: str, oficina: Path) -> bool:
    try:
        alvo = Path(caminho.strip("'\"")).expanduser().resolve()
        base = oficina.resolve()
        return alvo == base or base in alvo.parents
    except (OSError, ValueError):
        return False


def _primeira(trecho: str) -> str:
    t = trecho.strip().lstrip("&.( ").strip()
    return (t.split(None, 1)[0] if t else "").lower().strip("'\"")


def _sem_strings(comando: str) -> str:
    """Tira o conteúdo entre aspas (o texto de um Write-Output não deve parecer comando). Mantém as aspas vazias."""
    return re.sub(r"'[^']*'|\"[^\"]*\"", "''", comando)


def classificar(comando: str, pasta: Path | str, oficina: Path | str) -> tuple[str, list[str]]:
    """(nivel, motivos). `pasta` = onde vai rodar; `oficina` = a pasta-sandbox."""
    pasta, oficina = Path(pasta), Path(oficina)
    texto = comando.strip()
    baixo = texto.lower()
    nucleo = _sem_strings(baixo)                     # para não confundir texto entre aspas com comando
    motivos: list[str] = []

    for rx, porque in BLOQUEADO:
        if re.search(rx, baixo if "base64" in rx or "login data" in rx else nucleo, re.IGNORECASE):
            motivos.append(porque)
    if APAGAR.search(nucleo) and (CAMINHO_SISTEMA.search(baixo) or RAIZ_DE_DISCO.search(baixo)):
        motivos.append("apaga uma pasta do sistema, a raiz do disco ou a pasta do usuário inteira")
    if re.search(r"(?i)\b(move-item|mv|move|rename-item|ren|set-content|out-file|copy-item)\b", nucleo) and CAMINHO_SISTEMA.search(baixo):
        motivos.append("mexe em arquivos do Windows ou de Programas")
    if motivos:
        return "bloqueado", sorted(set(motivos))

    for rx, porque in RISCO:
        if re.search(rx, baixo if "ssh" in rx else nucleo, re.IGNORECASE):
            motivos.append(porque)
    for destino in _REDIRECIONA.findall(baixo):
        if destino.lower() not in ("$null", "null", "nul", "&1", "&2") and not _dentro(str(pasta / destino) if not re.match(r"(?i)[a-z]:", destino) else destino, oficina):
            motivos.append("grava um arquivo fora da Oficina")
    if motivos:
        return "risco", sorted(set(motivos))

    trechos = [t for t in _SEPARA.split(nucleo) if t.strip() and t.strip() not in ("''", ",")]
    palavras = set(re.findall(r"[a-z][a-z0-9.-]*", nucleo))
    # trecho de leitura: comando conhecido, ou só expressão ($_.Length -gt 1, .Year, 1..10, '' para texto)
    le = lambda t: (_primeira(t) in LEITURA or bool(LEITURA_COMPOSTA.match(t.strip())) or re.match(r"\s*(\$|\.[a-z]|\d|''|-[a-z]|,)", t) is not None)
    grava = any(d.lower() not in ("$null", "null", "nul", "&1", "&2") for d in _REDIRECIONA.findall(baixo))
    if trechos and not grava and not (palavras & (CRIACAO - LEITURA)) and all(le(t) for t in trechos):
        sensiveis = [c for c in _CAMINHO_ABS.findall(baixo) if re.search(r"\.ssh|segredos|appdata\\roaming\\jarvis|\.env", c)]
        if sensiveis:
            return "risco", ["lê uma pasta de segredos"]
        return "leitura", []

    cria = all(_primeira(t) in CRIACAO or le(t) for t in trechos)
    na_oficina = _dentro(str(pasta), oficina)
    caminhos_fora = [c for c in _CAMINHO_ABS.findall(texto) if not _dentro(c, oficina)]
    if cria and na_oficina and not caminhos_fora and ".." not in texto:
        return "oficina", []
    if not cria:
        return "risco", ["comando fora da lista dos que eu conheço como seguros"]
    if not na_oficina:
        return "risco", ["cria ou altera arquivos fora da Oficina"]
    return "risco", ["aponta para fora da Oficina: " + ", ".join(caminhos_fora[:3]) if caminhos_fora else "usa '..' para sair da Oficina"]


# ------------------------------------------------------------------ scripts Python (só como aviso: quem impõe é a guarda)
SINAIS_PYTHON = [
    (r"\bsubprocess\b|\bos\.(system|popen|startfile|exec\w*|spawn\w*)\b", "abre outros programas"),
    (r"\b(shutil\.rmtree|os\.(remove|unlink|rmdir)|Path\([^)]*\)\.unlink|send2trash)\b", "apaga arquivos"),
    (r"\b(requests|urllib|httpx|aiohttp|socket|http\.client|ftplib|smtplib|websocket)\b", "acessa a rede"),
    (r"\b(ctypes|winreg|_winapi|win32api|pywin32|comtypes)\b", "chama o Windows por baixo (registro, DLLs)"),
    (r"\b(eval|exec|__import__|compile)\s*\(", "monta e executa código dinâmico"),
]


def sinais_python(codigo: str) -> list[str]:
    return sorted({porque for rx, porque in SINAIS_PYTHON if re.search(rx, codigo)})


def classificar_script(codigo: str, extensao: str, pasta: Path | str, oficina: Path | str) -> tuple[str, list[str]]:
    """Script PowerShell/cmd: cada linha é classificada; o pior nível vence."""
    ordem = ["leitura", "oficina", "risco", "bloqueado"]
    pior, motivos = "leitura", []
    linhas = [l for l in codigo.splitlines() if l.strip() and not l.strip().startswith(("#", "rem ", "REM ", "::", "@echo"))]
    if extensao in (".bat", ".cmd"):
        motivos.append("script do cmd (não sei analisar tão bem quanto PowerShell)")
        pior = "risco"
    for l in linhas[:400]:
        nivel, m = classificar(l, pasta, oficina)
        if ordem.index(nivel) > ordem.index(pior):
            pior = nivel
        if nivel in ("risco", "bloqueado"):
            motivos += m
    if len(linhas) > 400:
        pior = max(pior, "risco", key=ordem.index)
        motivos.append("script grande demais para conferir linha a linha")
    return pior, sorted(set(motivos))
