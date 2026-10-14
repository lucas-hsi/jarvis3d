# Conectar o Jarvis ao Google (Agenda + Gmail + Drive)

São ~10 minutos, **uma vez só**. A sua senha do Google nunca passa pelo Jarvis: você aprova no site do Google.
O Jarvis fica com um "token" guardado no **Cofre de Credenciais do Windows**.

## 1. Criar o projeto no Google Cloud
1. Abra <https://console.cloud.google.com> e entre com a conta que quer conectar.
2. No topo, **Selecionar projeto → Novo projeto**. Nome: `Jarvis`. Criar.

## 2. Ligar as três APIs
Com o projeto `Jarvis` selecionado, abra cada link e clique em **Ativar**:
- Gmail API: <https://console.cloud.google.com/apis/library/gmail.googleapis.com>
- Google Calendar API: <https://console.cloud.google.com/apis/library/calendar-json.googleapis.com>
- Google Drive API: <https://console.cloud.google.com/apis/library/drive.googleapis.com>

## 3. Tela de consentimento (Google Auth Platform)
1. Menu ☰ → **APIs e serviços → Tela de permissão OAuth** (ou "Google Auth Platform") → **Começar**.
2. Nome do app: `Jarvis`. E-mail de suporte: o seu. Avançar.
3. Público: **Externo**. Avançar. E-mail de contato: o seu. Concluir.
4. **Importante — evita o acesso cair a cada 7 dias:** em **Público-alvo** (Audience), clique em **Publicar app / Em produção**.
   Aparece um aviso sobre verificação: **não precisa verificar**, é uso pessoal (só você usa).
5. (Opcional) Em **Acesso a dados**, adicione estas permissões: `gmail.readonly`, `gmail.compose`, `gmail.modify`, `calendar.events`, `calendar.readonly`, `drive`.

## 4. Criar a credencial e baixar o arquivo
1. **Clientes → Criar cliente** (ou *Credenciais → Criar credenciais → ID do cliente OAuth*).
2. Tipo de aplicativo: **App para computador** (Desktop app). Nome: `Jarvis`. Criar.
3. Clique em **Baixar JSON** e salve o arquivo como:

   `C:\Jarvis\segredos\google_client.json`

   (A pasta `segredos` já existe e está protegida do git. Esse arquivo é secreto: não envie a ninguém.)

## 5. Conectar
Dê dois cliques em **`Conectar-Google.cmd`** (ou diga *"Jarvis, conecta meu Google"*). No navegador:
1. Escolha a sua conta.
2. Vai aparecer **"O Google não verificou este app"**. Clique em **Avançado → Acessar Jarvis (não seguro)**. É normal: o app é seu.
3. **Marque TODAS as caixas** de permissão e clique em **Continuar**.
4. Quando aparecer "Jarvis conectado", pode fechar. O painel **Agenda & e-mail** da tela passa a mostrar os seus dados.

> **Sem página de privacidade?** Para publicar o app o Google exige links reais de página inicial e de Política de Privacidade. Sem eles, deixe o app em **Teste** (adicione sua conta em *Usuários de teste*) e **reconecte a cada 7 dias** (dois cliques em `Conectar-Google.cmd`): o Jarvis avisa quando o acesso expirar.

## 6. Testar
- "Jarvis, o que tenho na agenda amanhã?"
- "Tenho e-mails não lidos?"
- "Me lembra amanhã às 9 de ligar para o contador." → vira notificação no celular (app **Google Agenda**).
- "Marca reunião com a Ana sexta às 15h." → cria o evento.
- "Marca como lidos os e-mails da loja X." / "Joga na lixeira as promoções antigas." → mostra o plano e pede confirmação. "Desfaz" volta atrás.
- "Acha o contrato do João no Drive." / "Cria a pasta Faturas e move as notas fiscais."
- "Manda um e-mail para ana@exemplo.com avisando que atraso 10 minutos." → mostra o texto na tela e **só envia se você confirmar**.

## Segurança
- **E-mail só sai com a sua confirmação** (clique ou "confirmo"), com texto completo na tela. Limite de 5 destinatários e 8 e-mails por hora.
- Evento com convidados, alteração e exclusão de evento também pedem confirmação. Lembrete e evento sem convidados são criados direto e dá para desfazer ("apaga esse lembrete").
- **Nada é apagado de vez:** e-mail e arquivo vão para a lixeira (30 dias). Lixeira e lotes grandes pedem confirmação; "desfaz" volta atrás. Só rascunhos apagados somem de vez (com confirmação). Nenhum compartilhamento de arquivos.
- Remetentes protegidos: `"google_protegidos": ["meubanco.com.br"]` no `config.json`.
- O conteúdo dos seus e-mails e arquivos é tratado como **dado**: o Jarvis não obedece ordens escritas dentro de e-mails.
- Para **revogar** o acesso a qualquer hora: <https://myaccount.google.com/permissions>, ou diga "desconecta o Google".
- Tudo que o Jarvis escreve no Google fica registrado em `memoria\google_atividade.jsonl`.

## Problemas comuns
| Mensagem | O que fazer |
|---|---|
| "Falta o arquivo segredos\google_client.json" | Refaça o passo 4 e confira o nome/pasta. |
| "Acesso bloqueado / app em teste" | No passo 3, adicione a sua conta em **Usuários de teste**, ou publique o app (passo 3.4). |
| "A autorização expirou ou foi revogada" | O app ficou em modo *Teste* (expira em 7 dias). Publique em produção e conecte de novo. |
| "Falta a permissão para..." | Conecte de novo e marque **todas** as caixas. |
