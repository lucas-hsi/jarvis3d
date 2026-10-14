# Jarvis 3D

Assistente de voz para Windows com painel 3D, voz natural e controle do computador por voz.
O programa fica na pasta [`!Jarvis3d`](./%21Jarvis3d). Quem só quer **instalar** não precisa de nada além do instalador.

## Instalar

1. Abra a página de [**Releases**](../../releases/latest) e baixe o `JarvisSetup-X.Y.Z.exe`.
2. Execute. O instalador é por usuário (não pede administrador). Como o programa ainda não é assinado digitalmente, o Windows pode mostrar
   "O Windows protegeu o computador": clique em **Mais informações → Executar assim mesmo**.
3. Na primeira abertura o Jarvis mostra uma tela de configuração: sua **chave da Anthropic** (obrigatória), a da **ElevenLabs** (opcional, para a voz natural),
   seu nome e tratamento, e os downloads da voz (reconhecimento de fala que roda no seu próprio computador).

Requisitos: Windows 10/11 de 64 bits, microfone, ~3 GB livres (mais ~1,1 GB se quiser aceleração por placa NVIDIA) e internet.

## Atualizações

O Jarvis instalado confere as Releases deste repositório 30 segundos depois de abrir e a cada 6 horas, baixa a versão nova em segundo plano e a instala
quando você fecha o programa (ou pelo menu da bandeja: **Reiniciar para atualizar**). Suas chaves, memória e configurações ficam em
`%APPDATA%\Jarvis` e nunca são tocadas por uma atualização.

## Privacidade

- O reconhecimento de voz roda **no seu computador** (Whisper). Só o texto da conversa vai para a Anthropic, e o texto das respostas para a ElevenLabs (se você usar a voz natural).
- Suas chaves ficam só na sua pasta de dados. Nada pessoal faz parte deste repositório.
- A câmera só acende quando você pede uma foto ou liga os gestos; nada é gravado em disco.

## Publicar uma versão nova (para quem mantém o projeto)

1. Em `!Jarvis3d/desktop/package.json`, suba o número de `version` (ex.: `0.2.1`) e faça commit.
2. Crie e envie a tag: `git tag v0.2.1 && git push origin v0.2.1`.
3. A ação **Release do Jarvis** (GitHub Actions) gera o instalador e publica na Release. Quem já tem o Jarvis instalado recebe sozinho.

Para gerar o instalador na própria máquina: `!Jarvis3d/empacotar/construir.cmd`.

## Licença

Ainda não definida pelo autor: até lá, todos os direitos reservados.
