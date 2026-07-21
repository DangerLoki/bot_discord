[![Build](https://github.com/DangerLoki/bot_discord/actions/workflows/build.yml/badge.svg)](https://github.com/DangerLoki/bot_discord/actions/workflows/build.yml)

# Loki Bot — Discord Music Bot

Bot Discord para reprodução de áudio do YouTube em canais de voz, com gerenciamento de playlist, modo aleatório com seed, modo de repetição, integração Spotify e diagnóstico de performance.

---

## ⬇️ Download

Baixe o binário da última versão na página de [Releases](https://github.com/DangerLoki/bot_discord/releases):

| Plataforma | Arquivo |
|---|---|
| Linux (x86_64) | `bot-discord-linux` |
| Windows (x64) | `bot-discord-windows.exe` |

> **Requisito externo:** [ffmpeg](https://ffmpeg.org/download.html) deve estar instalado e disponível no PATH.

---

## 🎯 Funcionalidades

- ✅ Reprodução de áudio do YouTube em canais de voz (yt-dlp + FFmpeg)
- ✅ Comandos com prefixo `&` e slash commands (`/`) sincronizados automaticamente
- ✅ Adição por URL, ID ou busca de texto
- ✅ Importação de playlists completas do YouTube
- ✅ Links de YouTube Mix adicionam apenas o vídeo selecionado (não a fila gerada)
- ✅ Lives bloqueadas — não é possível adicionar transmissões ao vivo
- ✅ Integração Spotify — track, álbum e playlist (busca automaticamente no YouTube)
- ✅ Gerenciamento de fila: remover, promover, inverter, limpar, paginar
- ✅ Modo aleatório com `shuffle_id` único por sessão
- ✅ Modo repetir: música atual 🔂, playlist inteira 🔁 ou desligado
- ✅ Flag `tocado` para evitar repetição no mesmo ciclo
- ✅ Detecção automática da primeira música não tocada ao reiniciar
- ✅ Controle de volume em tempo real
- ✅ Detecção e remoção automática de vídeos com geo-bloqueio
- ✅ Detecção de bot-block do YouTube com parada automática e mensagem de erro
- ✅ Cache local com limpeza automática após reprodução
- ✅ Suporte a proxy e cookies personalizados
- ✅ Setup interativo do token via CLI na primeira execução
- ✅ Logging estruturado com métricas de performance (`[PERF]`)

---

## 🏗️ Arquitetura

O projeto adota a estrutura **Cogs + Services + Repository**, com injeção de dependência manual em `main.py`.

```
src/
├── cogs/
│   ├── music_cog.py            # Comandos de voz: entrar, tocar, skip, pausar, volume, repetir…
│   └── playlist_cog.py         # Comandos de fila: add, playlist, spotify, remove, promover, inverter, aleatorio, dado…
│
├── services/
│   ├── player_service.py       # Lógica de reprodução, presença e auto-next
│   ├── player_status.py        # Loop de status/presença herdado por PlayerService
│   ├── playlist_service.py     # Fachada da fila (compõe os mixins abaixo)
│   ├── playlist_add.py         # Adição: URL, busca, playlist YouTube
│   ├── playlist_add_bulk.py    # Adição em lote: Spotify (track/álbum/playlist) e playlist YouTube
│   ├── playlist_manage.py      # Remoção, promoção, inversão, limpeza
│   ├── playlist_nav.py         # Navegação sequencial e aleatória (pular/voltar)
│   ├── playlist_resolver.py    # Resolve entrada ambígua por título (remove/promover)
│   ├── youtube_service.py      # Download e extração de playlist (yt-dlp)
│   ├── youtube_search.py       # Metadados e busca textual herdados por YouTubeService
│   ├── spotify_service.py      # Track, álbum, playlist (consultas)
│   └── spotify_client.py       # Auth, requisições REST e fallback via embed HTML
│
├── models/
│   └── player_state.py         # Estado mutável do player (volume, índice, shuffle, repeat_mode…)
│
├── repositories/
│   └── playlist_repository.py  # load() / save() do playlist.json
│
├── ui/
│   └── pagination.py           # View de paginação da playlist
│
├── setup/
│   └── cli_setup.py            # Setup interativo do config.env e checagem do ffmpeg
│
├── utils/
│   ├── __init__.py             # Re-exporta todos os helpers
│   ├── embeds.py               # embed_erro, embed_aviso, embed_sucesso, embed_carregando
│   ├── formatters.py           # formatar_duracao, extrair_video_id, is_spotify_url…
│   └── errors.py               # GeoBlockedError, BotBlockedError e helpers de detecção
│
└── logger.py                   # Configuração de logging (rotação, console, arquivo)

main.py                         # Wiring: instancia infra, serviços e registra cogs
```

### Fluxo de Dependências

```
main.py
 ├── PlayerState            (estado mutável compartilhado)
 ├── PlaylistRepository     (persistência JSON)
 ├── YouTubeService         (yt-dlp)
 ├── SpotifyService         (API Spotify)
 ├── PlaylistService  ←── repo + yt + spotify + state
 ├── PlayerService    ←── state + repo + yt + playlist_svc
 ├── MusicCog         ←── bot + state + repo + player_svc + playlist_svc
 └── PlaylistCog      ←── bot + state + repo + playlist_svc
```

---

## 💾 Stack

| Camada | Tecnologia |
|---|---|
| Runtime | Python 3.11+ |
| Discord | discord.py (com suporte a voz e hybrid/slash commands) |
| Áudio | yt-dlp + FFmpeg |
| Voz | PyNaCl |
| Spotify | spotipy + requests |
| Config | python-dotenv |
| Container | Docker + Compose |

---

## 📦 Pré-requisitos

- Python 3.11+
- FFmpeg no PATH
- Node.js (para PO Token do YouTube via yt-dlp)

```bash
ffmpeg -version
node --version
```

---

## 🚀 Como executar

### Bootstrap inicial (Linux)

Para preparar o ambiente do zero (venv, dependências, pastas e setup interativo):

```bash
chmod +x bootstrap.sh
./bootstrap.sh
```

Se você usa Fish:

```fish
chmod +x bootstrap.fish
./bootstrap.fish
```

Ao final, o script pergunta se você quer iniciar o bot no mesmo terminal.
Se você abrir o `bootstrap.fish` por clique no gerenciador de arquivos, ele tenta abrir um terminal automaticamente e iniciar o bot.

Opções úteis:

```bash
# Usar uma versão específica do Python
PYTHON_BIN=python3.11 ./bootstrap.sh

# Pular setup interativo (útil em CI)
SKIP_SETUP=1 ./bootstrap.sh
```

No Fish, use:

```fish
env PYTHON_BIN=python3.11 ./bootstrap.fish
env SKIP_SETUP=1 ./bootstrap.fish
env RUN_BOT=1 ./bootstrap.fish
env RUN_BOT=1 RUN_BOT_BG=1 ./bootstrap.fish
```

Para finalizar o bot (especialmente quando estiver em segundo plano):

```fish
chmod +x stop_bot.fish
./stop_bot.fish
```

### Opção 1 — Python direto

```bash
git clone https://github.com/DangerLoki/bot_discord.git
cd bot_discord

python -m venv .venv
source .venv/bin/activate     # Linux/macOS
# .venv\Scripts\activate      # Windows

pip install -r requirements.txt
python main.py
```

Na primeira execução, o bot solicita interativamente o token do Discord (e cria o `config.env`) caso ele ainda não exista.

### Opção 2 — Docker

```bash
git clone https://github.com/DangerLoki/bot_discord.git
cd bot_discord

# configure o config.env antes de subir
docker compose up -d

docker compose logs -f        # acompanhar logs
docker compose down           # parar
```

### Opção 3 — Binário pré-compilado

Baixe o binário em [Releases](https://github.com/DangerLoki/bot_discord/releases), coloque o `config.env` no mesmo diretório e execute:

```bash
# Linux
chmod +x bot-discord-linux
./bot-discord-linux

# Windows
bot-discord-windows.exe
```

### ⚙️ Configuração (`config.env`)

```env
token_discord=SEU_TOKEN_AQUI

# Opcional
ytdlp_proxy=               # ex: socks5://127.0.0.1:1080
spotify_client_id=         # https://developer.spotify.com/dashboard
spotify_client_secret=
```

### 🔐 Cookies (recomendado)

O YouTube pode bloquear downloads exigindo autenticação. Para evitar isso, exporte os cookies do navegador onde você está logado e salve em:

```
config/cookies.txt
```

```bash
# Exportar direto via yt-dlp (requer Chrome/Firefox instalado)
yt-dlp --cookies-from-browser chrome --cookies config/cookies.txt \
  -o /dev/null "https://www.youtube.com"
```

---

## 📋 Comandos

Todos os comandos aceitam tanto o prefixo `&` quanto slash commands (`/`). Use `&help` para a lista completa dentro do Discord.

### 🎵 Playlist

| Comando | Aliases | Descrição |
|---|---|---|
| `&add <url\|busca>` | — | URL do YouTube, playlist, URL do Spotify ou texto de busca |
| `&playlist <url>` | `&pl` `&addplaylist` | Importa playlist/Mix do YouTube |
| `&spotify <url>` | `&sp` `&addspotify` | Adiciona track, álbum ou playlist do Spotify |
| `&listar` | — | Lista a fila com paginação |
| `&remove <pos\|id>` | `&rm` `&remover` `&delete` | Remove por posição, video_id ou título |
| `&promover <pos\|id\|nome>` | `&promote` `&proxima` `&boost` | Move para próxima posição |
| `&inverter` | `&reverse` `&invert` `&flip` | Inverte a ordem da playlist |
| `&limpar` | `&clear` `&clearall` `&limpartudo` | Limpa toda a playlist |

### 🔊 Reprodução de Voz

| Comando | Aliases | Descrição |
|---|---|---|
| `&entrar` | `&join` `&connect` `&entra` | Entra no canal de voz do usuário |
| `&tocar` | `&play` `&start` | Inicia reprodução (auto-join se necessário) |
| `&pausar` | `&pause` | Pausa o áudio |
| `&retomar` | `&resume` `&continuar` | Retoma o áudio pausado |
| `&parar` | `&stop` | Para sem sair da call |
| `&sair` | `&leave` `&disconnect` `&dc` | Para e sai da call |
| `&skip` | `&pular` `&next` | Pula para o próximo |
| `&previous` | `&voltar` `&anterior` | Volta ao vídeo anterior |
| `&recomecar` | `&restart` `&replay` `&reiniciar` | Recomeça a música atual |
| `&volume <0-200>` | `&vol` `&v` | Ajusta o volume (padrão: 25%) |
| `&tocando` | `&np` `&nowplaying` `&atual` | Mostra o que está tocando |
| `&help` | `&ajuda` `&comandos` `&cmds` | Lista todos os comandos |

### 🔁 Repetição

| Comando | Aliases | Descrição |
|---|---|---|
| `&repetir` | `&repeat` `&loop` | Alterna entre: desligado → 🔂 música → 🔁 playlist |
| `&repetir musica` | — | Repete a música atual indefinidamente |
| `&repetir playlist` | — | Repete a playlist inteira em loop |
| `&repetir off` | — | Desliga a repetição |

### 🔀 Shuffle

| Comando | Aliases | Descrição |
|---|---|---|
| `&aleatorio` | `&shuffle` `&random` `&embaralhar` | Liga/desliga modo aleatório com `shuffle_id` |

### 🎲 Diversão

| Comando | Descrição |
|---|---|
| `&dado [lados]` | Lança um dado (padrão: 20 lados) |

---

## 🎲 Sistema de Shuffle

1. **Ao ativar** `&aleatorio`:
   - Gera um `shuffle_id` único de 8 caracteres
   - Cria lista aleatória com os vídeos ainda não tocados

2. **Ao adicionar vídeos com shuffle ativo**:
   - O novo vídeo entra em posição aleatória, preservando os demais

3. **`&listar` em modo shuffle**:
   - Exibe a ordem aleatória com `posicao_shuffle` e `shuffle_id` no footer

4. **Dados salvos por vídeo**:

```json
{
  "video_id": "dFlDRhvM4L0",
  "titulo": "...",
  "tocado": true,
  "shuffle_id": "abc1def2",
  "posicao_shuffle": 3
}
```

---

## 📊 Estrutura do `playlist.json`

```json
[
  {
    "video_id": "dFlDRhvM4L0",
    "titulo": "チェンソーマン OP",
    "duracao": 90,
    "duracao_formatada": "01:30",
    "canal": "MAPPA CHANNEL",
    "embed_url": "https://www.youtube.com/watch?v=dFlDRhvM4L0",
    "thumbnail_url": "https://img.youtube.com/vi/dFlDRhvM4L0/hqdefault.jpg",
    "adicionado_por": "user#0000",
    "data_adicionado": "2026-04-04 16:59:54",
    "posicao": 1,
    "tocado": false,
    "fonte": "spotify",
    "spotify_titulo_original": "KICK BACK"
  }
]
```

---

## 📝 Logging e Diagnóstico

Logs completos em `logs/bot.log` (rotação: 5 MB × 3 arquivos).
Console mostra nível INFO; arquivo registra DEBUG completo.

### Tags de performance (`[PERF]`)

| Tag | O que mede |
|---|---|
| `[PERF][DOWNLOAD]` | Tempo e tamanho do download via yt-dlp |
| `[PERF][INFO]` | Tempo para obter metadados de um vídeo |
| `[PERF][BUSCA]` | Tempo de busca no YouTube |
| `[PERF][PLAYLIST]` | Tempo para extrair playlist/Mix completo |
| `[PERF][TOCAR]` | Tempo total do comando até início da reprodução |
| `[PERF][ADD_URL]` | Tempo total do fluxo `&add <url>` |
| `[PERF][SPOTIFY_TRACK]` | Tempo da chamada à API do Spotify |
| `[CACHE][HIT]` | Música servida do cache (sem download) |
| `[CACHE][MISS]` | Música ausente do cache, iniciou download |

### Exemplo de saída

```
[CACHE][HIT]       usando arquivo em cache: cache/dFlDRhvM4L0.opus
[PERF][DOWNLOAD]   video_id=abc123 tempo=8.42s tamanho=3.1MB
[PERF][BUSCA]      termo="chainsaw man op" resultados=5 tempo=2.17s
[PERF][TOCAR]      tempo total até início da reprodução: 9.03s
[SHUFFLE]          ON (abc1def2) por user#0000
[PROMOTE]          NORMAL abc123 ("Título") → posição 2
```

---

## 📄 Licença

Projeto pessoal. Use livremente.

## 👤 Autor

**Loki** — Desenvolvedor

---

**Status**: ✅ Em desenvolvimento ativo | Arquitetura Cogs + Services + Repository
