# Discord Bot + Web Player

Projeto em desenvolvimento voltado à automação de captura de links do YouTube enviados no Discord, com organização da fila e reprodução em uma interface web local.

## Resumo

A aplicação integra um bot do Discord com um player web local para centralizar vídeos compartilhados em servidores e evitar controle manual de playlists no chat.

## Principais funcionalidades

- Captura de links do YouTube enviados no Discord
- Adição manual de vídeos por comando
- Listagem e remoção de itens da playlist
- Limpeza completa da fila
- Persistência local dos dados em JSON
- Interface web para reprodução e navegação entre vídeos

## Stack

- Python
- discord.py
- Flask
- HTML, CSS e JavaScript
- JSON

## Habilidades demonstradas

- Integração com API
- Automação com Python
- Execução concorrente com `threading`
- Fluxo assíncrono com `asyncio`
- Organização modular de código
- Manipulação de arquivos JSON
- Separação entre backend e interface web
- Estruturação de aplicação para evolução futura

## Estrutura do projeto

```bash
bot_discord/
├── bot/
├── web/
├── main.py
├── playlist.json
├── requirements.txt
└── README.md
````

## Como executar

```bash
git clone <URL_DO_REPOSITORIO>
cd bot_discord
python -m venv .venv
source .venv/bin/activate  # Linux
pip install -r requirements.txt
python main.py
```

No Windows:

```bash
.venv\Scripts\activate
```

## Arquitetura resumida

1. O usuário envia um link ou comando no Discord
2. O bot processa a entrada e atualiza a playlist
3. Os dados são persistidos localmente
4. A aplicação web lê a playlist e exibe os vídeos no navegador

## Status

**Projeto em desenvolvimento**

O projeto já possui base funcional, mas ainda está em evolução. Melhorias previstas incluem uso de variáveis de ambiente, tratamento de erros, testes automatizados, banco de dados e containerização.

## Objetivo no portfólio

Este projeto faz parte do meu portfólio para demonstrar competências em automação, integração com API, backend em Python e organização de aplicações modulares.