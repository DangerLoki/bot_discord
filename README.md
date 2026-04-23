# Loki Bot — Discord Music Bot

Bot Discord para reprodução de áudio do YouTube em canais de voz, com gerenciamento de playlist, modo aleatório com seed, integração Spotify e diagnóstico de performance.

## 🎯 Funcionalidades

- ✅ Reprodução de áudio do YouTube em canais de voz (yt-dlp + FFmpeg)
- ✅ Adição por URL, ID ou busca de texto
- ✅ Importação de playlists completas do YouTube
- ✅ Links de YouTube Mix adicionam apenas o vídeo selecionado (não a fila gerada)
- ✅ Lives bloqueadas — não é possível adicionar transmissões ao vivo
- ✅ Integração Spotify — track, álbum e playlist (busca automaticamente no YouTube)
- ✅ Gerenciamento de fila: remover, promover, limpar, paginar
- ✅ Modo aleatório com `shuffle_id` único por sessão
- ✅ Flag `tocado` para evitar repetição no mesmo ciclo
- ✅ Detecção automática da primeira música não tocada ao reiniciar
- ✅ Controle de volume em tempo real
- ✅ Detecção e remoção automática de vídeos com geo-bloqueio
- ✅ Cache local com limpeza automática após reprodução
- ✅ Suporte a proxy e cookies personalizados
- ✅ Logging estruturado com métricas de performance (`[PERF]`)

---

## 🏗️ Arquitetura

O projeto adota a estrutura **Cogs + Services + Repository**, com injeção de dependência manual em `main.py`.

```
src/
├── cogs/
│   ├── music_cog.py            # Comandos de voz: play, skip, pause, resume, volume…
│   └── playlist_cog.py         # Comandos de fila: add, remove, promote, shuffle, listar…
│
├── services/
│   ├── player_service.py       # Lógica de reprodução, presença e auto-next
│   ├── player_status.py        # Loop de status/presença herdado por PlayerService
│   ├── playlist_service.py     # Shuffle, navegação e fachada da fila
│   ├── playlist_add.py         # Adição: URL, busca, Spotify, playlist YT
│   ├── playlist_manage.py      # Remoção, promoção, limpeza, pular/voltar
│   ├── youtube_service.py      # Download e extração de playlist (yt-dlp)
│   ├── youtube_search.py       # Metadados e busca textual herdados por YouTubeService
│   ├── spotify_service.py      # Track, álbum, playlist (consultas)
│   └── spotify_client.py       # Auth, requisições REST e fallback via embed HTML
│
├── models/
│   └── player_state.py         # Estado mutável do player (volume, índice, shuffle…)
│
├── repositories/
│   └── playlist_repository.py  # load() / save() do playlist.json
│
├── ui/
│   └── pagination.py           # View de paginação da playlist
│
├── utils/
│   ├── __init__.py             # Re-exporta todos os helpers
│   ├── embeds.py               # embed_erro, embed_aviso, embed_sucesso, embed_carregando
│   ├── formatters.py           # formatar_duracao, extrair_video_id, is_spotify_url…
│   └── errors.py               # GeoBlockedError, _is_geo_blocked
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
| Runtime | Python 3.12+ |
| Discord | discord.py (com suporte a voz) |
| Áudio | yt-dlp + FFmpeg |
| Voz | PyNaCl |
| Spotify | spotipy + requests |
| Config | python-dotenv |

---

## 📦 Pré-requisitos

- Python 3.12+
- FFmpeg no PATH
- Node.js (para PO Token do YouTube via yt-dlp)

```bash
ffmpeg -version
node --version
```

---

## 🚀 Como executar

```bash
git clone <URL_DO_REPOSITORIO>
cd bot_discord

python -m venv .venv
source .venv/bin/activate     # Linux/macOS
# .venv\Scripts\activate      # Windows

pip install -r requirements.txt
python main.py
```

### ⚙️ Configuração (`config.env`)

```env
token_discord=SEU_TOKEN_AQUI

# Opcional
ytdlp_proxy=               # ex: socks5://127.0.0.1:1080
spotify_client_id=         # https://developer.spotify.com/dashboard
spotify_client_secret=
```

### 🔐 Cookies (opcional)

Para vídeos com restrição de idade, exporte os cookies do navegador e salve em:

```
config/cookies.txt
```

---

## 📋 Comandos

### 🎵 Playlist

| Comando | Aliases | Descrição |
|---|---|---|
| `&add <url\|busca>` | — | URL do YouTube, playlist, URL do Spotify ou texto de busca |
| `&playlist <url>` | `&pl` | Importa playlist/Mix do YouTube |
| `&spotify <url>` | `&sp` | Adiciona track, álbum ou playlist do Spotify |
| `&listar` | — | Lista a fila com paginação |
| `&remove <pos\|id>` | `&rm` | Remove por posição ou video_id |
| `&promover <pos\|id\|nome>` | `&proxima` | Move para próxima posição |
| `&limpar` | `&clear` | Limpa toda a playlist |

### 🔊 Reprodução de Voz

| Comando | Aliases | Descrição |
|---|---|---|
| `&entrar` | `&join` | Entra no canal de voz do usuário |
| `&tocar` | `&play` | Inicia reprodução (auto-join se necessário) |
| `&pausar` | `&pause` | Pausa o áudio |
| `&retomar` | `&resume` | Retoma o áudio pausado |
| `&parar` | `&stop` | Para sem sair da call |
| `&sair` | `&leave` `&dc` | Para e sai da call |
| `&skip` | `&pular` `&next` | Pula para o próximo |
| `&previous` | `&voltar` `&anterior` | Volta ao vídeo anterior |
| `&recomecar` | `&restart` `&replay` | Recomeça a música atual |
| `&volume <0-200>` | `&vol` | Ajusta o volume (padrão: 25%) |
| `&tocando` | `&np` `&atual` | Mostra o que está tocando |

### 🔀 Shuffle

| Comando | Aliases | Descrição |
|---|---|---|
| `&aleatorio` | `&shuffle` `&random` | Liga/desliga modo aleatório com `shuffle_id` |

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
