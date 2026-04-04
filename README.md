# Loki Bot — Discord Music Bot

Bot Discord avançado para reprodução de áudio do YouTube em canais de voz, com gerenciamento inteligente de playlist, sistema de shuffle baseado em seeds e suporte a proxy.

## 🎯 Funcionalidades

- ✅ Reprodução de áudio do YouTube em canais de voz (yt-dlp + FFmpeg)
- ✅ Adição de vídeos: URL, ID ou busca no YouTube
- ✅ Importação de playlists e YouTube Mix completos
- ✅ Gerenciamento de fila: remover, promover, limpar, paginar
- ✅ **Modo aleatório com shuffle_id**: Sistema de seed que mantém ordem relativa mas insere novos vídeos aleatoriamente
- ✅ Flag `tocado` para evitar repetição no mesmo ciclo
- ✅ Rastreamento de `posicao_shuffle` e `shuffle_id` na playlist
- ✅ Detecção automática de primeira música não tocada ao reiniciar
- ✅ Recomeçar música do início
- ✅ Controle de volume em tempo real
- ✅ Detecção e remoção automática de vídeos com geo-bloqueio
- ✅ Cache local com limpeza automática
- ✅ Suporte a proxy e cookies personalizados
- ✅ PO Token via Node.js para contornar restrições
- ✅ Logging estruturado

## 🏗️ Arquitetura

Projeto refatorado com separação de responsabilidades:

```
src/bot/
├── services/              # Lógica de negócio
│   ├── youtube_service.py      # Busca e metadados de vídeos
│   ├── playlist_service.py      # CRUD e gerenciamento de playlist
│   └── player_service.py        # Reprodução e cache
├── commands/              # Handlers de comandos (em desenvolvimento)
├── ui/
│   └── pagination.py      # Componentes de interface
├── bot.py                # Classe MyBot e registros de handlers
├── playlist_mixin.py      # Métodos de playlist
├── player_mixin.py        # Métodos de reprodução
├── youtube_mixin.py       # Métodos de YouTube
├── utils.py              # Funções auxiliares
└── logger.py             # Configuração de logging
```

## 💾 Stack

- Python 3.12+
- discord.py (suporte a voz)
- yt-dlp
- FFmpeg
- PyNaCl
- python-dotenv

## 📦 Requisitos

- Python 3.12+
- FFmpeg (instalado e no PATH)
- Node.js (para PO Token do YouTube)

```bash
ffmpeg -version
node --version
```

## 🚀 Como executar

```bash
git clone <URL_DO_REPOSITORIO>
cd bot_discord

python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
python main.py
```

### ⚙️ Configuração (`config.env`)

```env
token_discord=SEU_TOKEN_AQUI
ytdlp_proxy=              # Opcional: socks5://127.0.0.1:1080
```

### 🔐 Cookies (Opcional)

Para vídeos com restrição de idade, exporte os cookies do navegador e salve em:

```
config/cookies.txt
```

## 📋 Comandos

### 🎵 Playlist

| Comando | Descrição |
|---|---|
| `&add <url\|busca>` | Adiciona vídeo por URL, ID ou termo de busca |
| `&playlist <url>` | Importa playlist ou YouTube Mix inteiro |
| `&listar` | Lista vídeos com paginação (mostra shuffle_id se ativo) |
| `&remove <pos\|id>` | Remove vídeo (respeita posição em modo shuffle) |
| `&promover <pos\|id>` | Move vídeo para próximo (reodenação no shuffle) |
| `&limpar` | Limpa toda a playlist |

### 🔊 Reprodução e Controle

| Comando | Descrição |
|---|---|
| `&entrar` | Entra no canal de voz do usuário |
| `&tocar` | Inicia reprodução (auto-join se necessário) |
| `&pausar` | Pausa o áudio |
| `&retomar` | Retoma o áudio pausado |
| `&parar` | Para sem sair da call |
| `&sair` | Para e sai da call |
| `&skip` | Pula para próximo vídeo |
| `&previous` | Volta ao vídeo anterior |
| `&recomecar` | Recomeça música atual do início |
| `&volume <0-200>` | Ajusta volume (padrão: 25%) |
| `&tocando` | Mostra o que está tocando na call |

### 🔀 Modo Aleatório

| Comando | Descrição |
|---|---|
| `&aleatorio` / `&shuffle` | Ativa/desativa modo aleatório com shuffle_id único |

## 🎲 Sistema de Shuffle Avançado

### Como Funciona

1. **Ao ativar** `&aleatorio`:
   - Gera `shuffle_id` único (UUID de 8 caracteres)
   - Cria lista aleatória com vídeos não tocados
   - Exibe: `🔀 Modo aleatório **ativado**! (ID: abc1def2) Lista criada com X músicas.`

2. **Ao adicionar vídeos com shuffle ativo**:
   - Novos vídeos são inseridos em posição aleatória
   - Mantém `shuffle_id` da geração atual
   - Preserva ordem relativa dos vídeos existentes

3. **Comando `&listar` em modo shuffle**:
   - Mostra posição na lista aleatória (`posicao_shuffle`)
   - Exibe `shuffle_id` no footer
   - Título: `🔀 Playlist Aleatória (ID: abc1def2)`

4. **Ao desativar**:
   - Volta para ordem normal da playlist
   - Preserva flags `tocado` para evitar repetição

### Dados Salvos em Cada Vídeo

```json
{
  "video_id": "dFlDRhvM4L0",
  "titulo": "Vídeo...",
  "tocado": true,
  "shuffle_id": "abc1def2",        // ID do shuffle que tocou este vídeo
  "posicao_shuffle": 3              // Posição naquele shuffle
}
```

## 🔍 Diagnóstico

### Testar Download de Vídeo

```bash
.venv/bin/python test_download.py https://www.youtube.com/watch?v=VIDEO_ID

# Com proxy
.venv/bin/python test_download.py --proxy socks5://127.0.0.1:1080 VIDEO_ID
```

## 📊 Estrutura de Dados

### playlist.json

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
    "adicionado_por": "boy42",
    "data_adicionado": "2026-04-04 16:59:54",
    "posicao": 1,
    "tocado": false,
    "shuffle_id": "abc1def2",
    "posicao_shuffle": 3
  }
]
```

## 📝 Logging

Logs estruturados em `logs/`:

```
[INIT] Continuando de: Título da música (posição 1)
[ADD] "Título" (video_id) por user — pos 5
[SHUFFLE] ON (abc1def2) por user
[PROMOTE] SHUFFLE video_id ("Título") → posição 2
[VOZ] Tocando: Título da música
```

## 🛠️ Desenvolvimento

### Próximas Refatorações

- [ ] Separar comandos em `src/bot/commands/`
- [ ] Criar `CommandHandler` centralizado
- [ ] Extrair estado para classe separada
- [ ] Usar services diretamente em place dos mixins

### Testes de Diagnóstico

Execute `test_download.py` para verificar se vídeos podem ser baixados corretamente.

## 📄 Licença

Projeto pessoal. Use livremente.

## 👤 Autor

**Loki** - Desenvolvedor

---

**Status**: ✅ Em desenvolvimento ativo | Base funcional completa