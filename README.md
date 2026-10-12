[![CI](https://github.com/DangerLoki/bot_discord/actions/workflows/ci.yml/badge.svg)](https://github.com/DangerLoki/bot_discord/actions/workflows/ci.yml)
[![Build](https://github.com/DangerLoki/bot_discord/actions/workflows/build.yml/badge.svg)](https://github.com/DangerLoki/bot_discord/actions/workflows/build.yml)

# Loki Bot — Discord Music Bot

Bot de música para Discord com reprodução de áudio do YouTube, importação do Spotify, painel interativo e filas isoladas por servidor.

## Funcionalidades

- Reprodução de áudio do YouTube com yt-dlp e FFmpeg.
- Pesquisa por texto e adição por URL ou ID.
- Importação de playlists do YouTube e de faixas, álbuns e playlists do Spotify.
- Painel persistente com controles de reprodução, volume, shuffle e repetição.
- Fila paginada com botões para adicionar, inverter e limpar músicas.
- Modal para adicionar músicas sem digitar uma mensagem no canal.
- Estado, configurações e playlist independentes para cada servidor.
- Persistência do volume, posição, canal do painel, shuffle e modo de repetição.
- Detecção de lives, restrições geográficas e bloqueios do YouTube.
- Cache local de áudio com limpeza automática de arquivos órfãos.
- Suporte a cookies Netscape e proxy no yt-dlp.
- Healthcheck de FFmpeg, cache, cookies e Spotify.
- Proteção contra duas instâncias do bot no mesmo diretório.
- Logs rotativos e métricas de performance.

## Download

Os binários da versão mais recente ficam na página de [Releases](https://github.com/DangerLoki/bot_discord/releases):

| Plataforma | Arquivo |
|---|---|
| Linux x86_64 | `bot-discord-linux` |
| Windows x64 | `bot-discord-windows.exe` |

Os binários publicados pelo workflow de release já incluem o FFmpeg. Para executar pelo código-fonte, instale o FFmpeg separadamente.

## Pré-requisitos

### Execução pelo código-fonte

- Python 3.11 ou superior.
- FFmpeg disponível no `PATH`.
- Node.js disponível no `PATH` para o runtime JavaScript usado pelo yt-dlp.
- Um bot criado no [Discord Developer Portal](https://discord.com/developers/applications).

Valide as dependências locais:

```bash
python3 --version
ffmpeg -version
node --version
```

No Discord Developer Portal, habilite o **Message Content Intent**. Ao convidar o bot, use os escopos `bot` e `applications.commands` e conceda, no mínimo, permissões para ver canais, enviar mensagens, incorporar links, ler o histórico, conectar e falar. A permissão para gerenciar mensagens é necessária para a limpeza automática do canal do painel e para `&limparchat`.

## Instalação e execução

### Bootstrap no Linux

O script Bash cria o ambiente virtual, instala as dependências, prepara os diretórios e executa a configuração interativa:

```bash
git clone https://github.com/DangerLoki/bot_discord.git
cd bot_discord
chmod +x bootstrap.sh
./bootstrap.sh
.venv/bin/python main.py
```

Para usar uma versão específica do Python ou pular o assistente de configuração:

```bash
PYTHON_BIN=python3.11 ./bootstrap.sh
SKIP_SETUP=1 ./bootstrap.sh
```

Quem usa Fish pode executar:

```fish
chmod +x bootstrap.fish
./bootstrap.fish
```

O bootstrap Fish pergunta se deve iniciar o bot ao final. Também aceita execução automática em primeiro ou segundo plano:

```fish
env RUN_BOT=1 ./bootstrap.fish
env RUN_BOT=1 RUN_BOT_BG=1 ./bootstrap.fish
./stop_bot.fish
```

### Instalação manual com `venv`

```bash
git clone https://github.com/DangerLoki/bot_discord.git
cd bot_discord

python3 -m venv .venv
source .venv/bin/activate
# No Windows: .venv\Scripts\activate

python -m pip install -r requirements.txt
python main.py
```

Na primeira execução, o assistente solicita o token do Discord e cria o `config.env`.

### Docker Compose

Crie o `config.env` antes de iniciar o contêiner:

```bash
git clone https://github.com/DangerLoki/bot_discord.git
cd bot_discord

docker compose up -d --build
docker compose logs -f
```

Para encerrar:

```bash
docker compose down
```

Os diretórios `data/`, `cache/`, `config/` e `logs/` são montados como volumes para preservar os dados.

### Binário pré-compilado

Baixe o arquivo da sua plataforma e execute-o em um diretório com permissão de escrita:

```bash
# Linux
chmod +x bot-discord-linux
./bot-discord-linux

# Windows (PowerShell)
.\bot-discord-windows.exe
```

Mantenha `config.env` e a pasta `config/` junto do executável.

## Configuração

O arquivo `config.env` aceita estas variáveis:

```env
# Obrigatório
token_discord=SEU_TOKEN_AQUI

# Opcionais
ytdlp_proxy=
spotify_client_id=
spotify_client_secret=
```

As credenciais do Spotify podem ser criadas no [Spotify for Developers](https://developer.spotify.com/dashboard). Sem elas, somente a integração com Spotify fica indisponível.

Para refazer o assistente de configuração:

```bash
python -m src.setup.cli_setup --force
```

> Nunca envie `config.env` ou cookies para o repositório. Ambos podem conter credenciais de acesso.

### Cookies do YouTube

Se o YouTube exigir autenticação ou bloquear os downloads, exporte os cookies de uma sessão válida no formato Netscape para:

```text
config/cookies.txt
```

Há um modelo em `config/cookies.txt.example`. Também é possível exportar diretamente com o yt-dlp:

```bash
yt-dlp --cookies-from-browser chrome --cookies config/cookies.txt \
  -o /dev/null "https://www.youtube.com"
```

## Primeiros passos no Discord

1. Convide o bot para o servidor e inicie o processo.
2. No canal de texto que será usado como painel, execute `&definircanal`.
3. Entre em um canal de voz.
4. Use `&add <URL ou busca>` e depois `&tocar`.

Depois de definido, os comandos ficam restritos ao canal do painel. O bot restaura esse canal e recria os controles persistentes ao reiniciar.

## Comandos

Os comandos híbridos aceitam o prefixo `&` e também aparecem como slash commands (`/`). O comando `repetir` é a exceção atual e funciona apenas pelo prefixo. Use `&help` para consultar a lista dentro do Discord.

### Playlist

| Comando | Aliases | Descrição |
|---|---|---|
| `&add <url\|busca>` | — | Adiciona vídeo, playlist do YouTube, link do Spotify ou resultado de busca. |
| `&playlist <url>` | `&pl`, `&addplaylist` | Importa uma playlist do YouTube. |
| `&spotify <url>` | `&sp`, `&addspotify` | Adiciona faixa, álbum ou playlist do Spotify. |
| `&listar` | — | Exibe a fila com paginação. |
| `&remove <posição\|id\|nome>` | `&rm`, `&remover`, `&delete` | Remove uma música da fila. |
| `&promover <posição\|id\|nome>` | `&promote`, `&proxima`, `&boost` | Move uma música para a próxima posição. |
| `&inverter` | `&reverse`, `&invert`, `&flip` | Inverte a ordem da fila. |
| `&limpar` | `&clear`, `&clearall`, `&limpartudo` | Limpa a fila do servidor. |

### Reprodução

| Comando | Aliases | Descrição |
|---|---|---|
| `&entrar` | `&join`, `&connect`, `&entra` | Entra no canal de voz do usuário. |
| `&tocar` | `&play`, `&start` | Inicia a reprodução e entra automaticamente na call. |
| `&pausar` | `&pause` | Pausa o áudio. |
| `&retomar` | `&resume`, `&continuar` | Retoma o áudio pausado. |
| `&parar` | `&stop` | Para o áudio sem sair da call. |
| `&sair` | `&leave`, `&disconnect`, `&dc` | Para o áudio e sai da call. |
| `&skip` | `&pular`, `&next` | Avança para a próxima música. |
| `&previous` | `&voltar`, `&anterior` | Retorna à música anterior. |
| `&recomecar` | `&restart`, `&replay`, `&reiniciar` | Reinicia a música atual. |
| `&volume [0-200]` | `&vol`, `&v` | Consulta ou ajusta o volume; o padrão é 25%. |
| `&tocando` | `&np`, `&nowplaying`, `&atual` | Mostra a música atual. |
| `&help` | `&ajuda`, `&comandos`, `&cmds` | Lista os comandos disponíveis. |

### Modos de reprodução

| Comando | Aliases | Descrição |
|---|---|---|
| `&aleatorio` | `&shuffle`, `&random`, `&embaralhar` | Ativa ou desativa a ordem aleatória. |
| `&repetir` | `&repeat`, `&loop` | Alterna entre desligado, música atual e playlist. |
| `&repetir musica` | — | Repete a música atual. |
| `&repetir playlist` | — | Repete a playlist inteira. |
| `&repetir off` | — | Desativa a repetição. |

### Configuração e diagnóstico

| Comando | Aliases | Descrição |
|---|---|---|
| `&definircanal [#canal]` | `&setcanal`, `&canalbot` | Define o canal do painel; usa o canal atual se omitido. |
| `&limparchat [1-100]` | `&clearchat`, `&purge` | Limpa mensagens do canal; o padrão é 50. |
| `&healthcheck` | `&health`, `&diag`, `&status` | Verifica FFmpeg, cache, cookies e Spotify. |
| `&dado [lados]` | — | Lança um dado; o padrão é 20 lados. |

## Painel e shuffle

O painel possui controles persistentes para voltar, pausar/retomar, avançar, parar/sair, shuffle, repetição e volume. Na fila, o botão **Promover** abre um seletor paginado para escolher visualmente a próxima música ou pesquisá-la pelo nome, sem precisar digitar `&promover`. O botão de parada funciona como um toggle: ele pausa e sai da call; quando acionado novamente, reconecta ao canal do usuário e retoma a faixa.

Na mensagem da fila, os botões permitem navegar pelas páginas, inverter a ordem, promover uma faixa, abrir o modal de adição e limpar a playlist.

Ao ativar o shuffle, o bot cria um `shuffle_id` para a sessão e mantém uma ordem aleatória independente da posição original. Novas músicas entram em uma posição aleatória sem reordenar as demais. A propriedade `tocado` impede repetições no mesmo ciclo.

## Persistência por servidor

Cada guild possui seu próprio diretório:

```text
data/
└── guilds/
    └── <guild_id>/
        ├── config.json
        └── playlist.json
```

`config.json` armazena o canal do painel e o estado persistível do player. `playlist.json` contém a fila daquele servidor. Um item possui uma estrutura semelhante a:

```json
{
  "video_id": "dFlDRhvM4L0",
  "titulo": "Título da música",
  "duracao": 90,
  "duracao_formatada": "01:30",
  "canal": "Nome do canal",
  "embed_url": "https://www.youtube.com/watch?v=dFlDRhvM4L0",
  "thumbnail_url": "https://img.youtube.com/vi/dFlDRhvM4L0/hqdefault.jpg",
  "adicionado_por": "usuario",
  "data_adicionado": "2026-10-10 12:00:00",
  "posicao": 1,
  "tocado": false,
  "fonte": "youtube"
}
```

Itens originados do Spotify também podem conter `spotify_titulo_original`. Quando o shuffle está ativo, são usados `shuffle_id` e `posicao_shuffle`.

## Arquitetura

O projeto usa Cogs, Services e Repositories com injeção manual de dependências em `main.py`:

```text
main.py
└── src/
    ├── cogs/
    │   ├── cog_utils.py
    │   ├── diagnostic_cog.py
    │   ├── music_cog.py
    │   └── playlist_cog.py
    ├── models/
    │   └── player_state.py
    ├── repositories/
    │   ├── config_repository.py
    │   └── playlist_repository.py
    ├── services/
    │   ├── player_service.py
    │   ├── player_status.py
    │   ├── playlist_service.py
    │   ├── playlist_add.py
    │   ├── playlist_add_bulk.py
    │   ├── playlist_manage.py
    │   ├── playlist_nav.py
    │   ├── playlist_resolver.py
    │   ├── spotify_client.py
    │   ├── spotify_service.py
    │   ├── youtube_search.py
    │   └── youtube_service.py
    ├── setup/
    │   └── cli_setup.py
    ├── ui/
    │   ├── pagination.py
    │   └── player_controls.py
    └── utils/
        ├── cache_manager.py
        ├── embeds.py
        ├── errors.py
        ├── formatters.py
        ├── healthcheck.py
        └── retry.py
```

`main.py` mantém um `PlayerState`, um `PlaylistService` e um `PlayerService` para cada guild. Os clientes de YouTube e Spotify, os repositórios e o gerenciador de cache são compartilhados, sempre recebendo o `guild_id` nas operações que precisam de isolamento.

## Desenvolvimento

O projeto usa [uv](https://docs.astral.sh/uv/) no CI e mantém um `uv.lock`:

```bash
uv sync --group dev
uv run ruff check .
uv run pytest
uv run pytest --cov=src --cov-report=term-missing
```

Também é possível instalar as dependências de execução com `requirements.txt`, mas as ferramentas de lint, teste e build estão no grupo `dev` do `pyproject.toml`.

O CI executa Ruff, pytest com cobertura e um smoke test do binário Linux. Releases são geradas automaticamente ao enviar uma tag no formato `v*`.

## Logs e diagnóstico

O console exibe mensagens de nível INFO e o arquivo `logs/bot.log` registra DEBUG. A rotação mantém três backups de até 5 MB cada.

Tags úteis:

| Tag | Informação |
|---|---|
| `[PERF][DOWNLOAD]` | Tempo e tamanho do download. |
| `[PERF][INFO]` | Tempo para obter metadados. |
| `[PERF][BUSCA]` | Tempo e quantidade de resultados da busca. |
| `[PERF][PLAYLIST]` | Tempo para extrair uma playlist. |
| `[PERF][TOCAR]` | Tempo total até o início da reprodução. |
| `[CACHE][HIT]` | Arquivo atendido pelo cache. |
| `[CACHE][MISS]` | Download iniciado por ausência no cache. |
| `[GUILD:<id>]` | Operação associada a um servidor. |

Use `&healthcheck` no Discord para verificar rapidamente as dependências críticas.

## Licença

Projeto pessoal. Use livremente.

## Autor

**Loki** — Desenvolvedor
