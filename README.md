# 🎵 YouTube Playlist Bot

Bot do Discord que captura links do YouTube e exibe em um site com autoplay.

## 📁 Estrutura do Projeto

```
nightbot discord/
├── config/
│   ├── __init__.py
│   └── settings.py          # Configurações globais
├── models/
│   ├── __init__.py
│   ├── video.py              # Modelo de vídeo
│   └── playlist.py           # Gerenciador da playlist
├── bot/
│   ├── __init__.py
│   ├── discord_bot.py        # Bot do Discord
│   └── youtube_extractor.py  # Extrator de URLs
├── web/
│   ├── __init__.py
│   ├── app.py                # Aplicação Flask
│   ├── templates/
│   │   └── player.html       # Template do player
│   └── static/
│       ├── css/
│       │   └── style.css     # Estilos
│       └── js/
│           └── player.js     # JavaScript do player
├── data/
│   └── playlist.json         # Dados persistentes
├── main.py                   # Ponto de entrada
├── requirements.txt          # Dependências
└── README.md
```

## 🚀 Instalação

1. **Clone ou baixe o projeto**

2. **Crie um ambiente virtual (opcional mas recomendado)**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   ```

3. **Instale as dependências**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure o token do Discord**
   
   Edite o arquivo `config/settings.py` e substitua:
   ```python
   DISCORD_TOKEN = "SEU_TOKEN_AQUI"
   ```

5. **Execute o bot**
   ```bash
   python main.py
   ```

## 🎮 Comandos do Discord

| Comando | Descrição |
|---------|-----------|
| `!add <url>` | Adiciona um vídeo à playlist |
| `!playlist` | Mostra os vídeos na fila |
| `!remove <id>` | Remove um vídeo |
| `!limpar` | Limpa toda a playlist |
| `!site` | Mostra o link do player |
| `!ajuda` | Lista todos os comandos |

### Captura Automática
Envie qualquer link do YouTube no chat e ele será adicionado automaticamente!

## 🌐 Player Web

Acesse `http://localhost:5000` para ver o player.

### Funcionalidades:
- ▶️ Autoplay automático
- ⏭️ Próximo/Anterior
- 🔀 Modo aleatório
- 🔄 Atualização automática
- 📱 Design responsivo

## ⚙️ Configurações

Edite `config/settings.py` para personalizar:

```python
DISCORD_PREFIX = "!"           # Prefixo dos comandos
WEB_PORT = 5000                # Porta do servidor web
MAX_VIDEOS_PLAYLIST = 100      # Máximo de vídeos
```

## 📝 Licença

MIT License
