# Loki Bot — Discord Music Bot

Bot do Discord para reprodução de áudio do YouTube diretamente em canais de voz, com gerenciamento de playlist persistente, modo aleatório e suporte a proxy.

## Funcionalidades

- Reprodução de áudio do YouTube em canais de voz via `yt-dlp` + FFmpeg
- Adição de vídeos por URL, ID ou termo de busca
- Importação de playlists e YouTube Mix completos
- Gerenciamento de fila: remover, promover, limpar, paginar
- Modo aleatório (`&aleatorio`) com flag de "já tocado" para evitar repetições no ciclo
- Recomeçar música do início (`&recomecar`)
- Controle de volume em tempo real
- Detecção automática de geo-bloqueio com remoção da playlist
- Cache local de áudio com limpeza automática após reprodução
- Suporte a proxy (`ytdlp_proxy` no `config.env`)
- Suporte a cookies (`config/cookies.txt`)
- PO Token via Node.js (`js_runtimes: node`) para contornar restrições do YouTube
- Logging estruturado em `logs/`
- Script `test_download.py` para diagnóstico de downloads

## Stack

- Python 3.12+
- discord.py (com suporte a voz)
- yt-dlp
- FFmpeg
- PyNaCl
- python-dotenv

## Estrutura do projeto

```
bot_discord/
├── main.py               # Entrypoint
├── config.env            # Token e configurações (não versionar)
├── requirements.txt
├── test_download.py      # Script de diagnóstico de download
├── data/
│   └── playlist.json     # Playlist persistida
├── cache/                # Áudios temporários (auto-gerenciado)
├── logs/                 # Logs da aplicação
└── src/
    ├── logger.py
    └── bot/
        └── bot.py        # Bot completo
```

## Requisitos

- Python 3.12+
- FFmpeg instalado e no PATH
- Node.js instalado e no PATH (para PO Token do YouTube)

```bash
# Verificar dependências
ffmpeg -version
node --version
```

## Como executar

```bash
git clone <URL_DO_REPOSITORIO>
cd bot_discord

python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
python main.py
```

### Configuração (`config.env`)

```env
token_discord=SEU_TOKEN_AQUI
ytdlp_proxy=              # opcional: socks5://127.0.0.1:1080
```

### Cookies (opcional)

Para vídeos com restrição de idade ou autenticação, coloque o arquivo de cookies exportado do navegador em:

```
config/cookies.txt
```

## Comandos

### 🎵 Playlist

| Comando | Descrição |
|---|---|
| `&add <url\|busca>` | Adiciona vídeo por URL, ID ou termo de busca |
| `&playlist <url>` | Importa playlist ou YouTube Mix inteiro |
| `&listar` | Lista os vídeos com paginação |
| `&remove <pos\|id>` | Remove um vídeo da fila |
| `&promover <pos\|id>` | Move um vídeo para ser o próximo |
| `&limpar` | Limpa toda a playlist |

### 🔊 Reprodução de Voz

| Comando | Descrição |
|---|---|
| `&entrar` | Entra no canal de voz do usuário |
| `&tocar` | Inicia a reprodução (auto-join se necessário) |
| `&pausar` | Pausa o áudio |
| `&retomar` | Retoma o áudio pausado |
| `&parar` | Para sem sair da call |
| `&sair` | Para e sai da call |
| `&skip` | Pula para o próximo vídeo |
| `&previous` | Volta ao vídeo anterior |
| `&recomecar` | Recomeça a música atual do início |
| `&aleatorio` | Liga/desliga modo aleatório 🔀 |
| `&volume <0-200>` | Ajusta o volume (padrão: 25%) |
| `&tocando` | Mostra o que está tocando |

### 🎲 Diversão

| Comando | Descrição |
|---|---|
| `&dado [lados]` | Lança um dado (padrão: d20) |

## Modo Aleatório

Ao ativar `&aleatorio`, o bot escolhe a próxima música aleatoriamente entre as que ainda **não foram tocadas** no ciclo atual. Quando todas as músicas do ciclo tiverem sido tocadas, as flags são resetadas automaticamente e um novo ciclo começa.

## Diagnóstico de Download

```bash
# Testar se um vídeo pode ser baixado
.venv/bin/python test_download.py https://www.youtube.com/watch?v=VIDEO_ID

# Com proxy
.venv/bin/python test_download.py --proxy socks5://127.0.0.1:1080 VIDEO_ID
```

## Status

**Em desenvolvimento ativo.** Base funcional completa com reprodução de voz, gerenciamento de fila e modo aleatório implementados.