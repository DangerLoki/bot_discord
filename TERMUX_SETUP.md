# Rodando o Bot no Android com Termux

## Passo 1 — Instalar os apps

> ⚠️ Use o **F-Droid**, não a Play Store (versões desatualizadas lá).

- [Termux](https://f-droid.org/packages/com.termux/)
- [Termux:Widget](https://f-droid.org/packages/com.termux.widget/) *(botões na tela inicial)*
- [Termux:Boot](https://f-droid.org/packages/com.termux.boot/) *(opcional — subir bot ao ligar o celular)*

Após instalar, abra o Termux e dê permissão de armazenamento:

```sh
termux-setup-storage
```

---

## Passo 2 — Instalar dependências do sistema

```sh
pkg update && pkg upgrade -y
pkg install -y python git ffmpeg clang libffi openssl
```

---

## Passo 3 — Copiar o projeto para o celular

**Opção A — via Git** (se tiver repositório):

```sh
cd ~
git clone https://github.com/seu-usuario/bot_discord.git
```

**Opção B — via cabo USB:**

1. Conecta o celular no PC
2. Copia a pasta `bot_discord` para o armazenamento interno
3. No Termux:

```sh
cp -r ~/storage/shared/bot_discord ~/bot_discord
```

---

## Passo 4 — Criar ambiente virtual e instalar pacotes

```sh
cd ~/bot_discord
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> Se o **PyNaCl** falhar durante a instalação:
> ```sh
> pip install --no-binary :all: PyNaCl
> ```

---

## Passo 5 — Configurar o config.env

```sh
nano ~/bot_discord/config.env
```

Preencha com o token do Discord e as credenciais do Spotify normalmente.

---

## Passo 6 — Testar se funciona

```sh
cd ~/bot_discord
source .venv/bin/activate
python main.py
```

Se o bot aparecer online no Discord, tudo certo. Encerra com `Ctrl+C`.

---

## Passo 7 — Criar os botões de Start e Stop

```sh
mkdir -p ~/.shortcuts

# Botão Start
cat > ~/.shortcuts/Bot\ Start.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/bash
cd ~/bot_discord
source .venv/bin/activate
pkill -f "python main.py" 2>/dev/null
mkdir -p logs
python main.py >> logs/termux.log 2>&1 &
EOF

# Botão Stop
cat > ~/.shortcuts/Bot\ Stop.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/bash
pkill -f "python main.py" && echo "Bot parado." || echo "Bot não estava rodando."
EOF

chmod +x ~/.shortcuts/Bot\ Start.sh ~/.shortcuts/Bot\ Stop.sh
```

---

## Passo 8 — Adicionar widget na tela inicial

1. Segura a tela inicial → **Widgets**
2. Procura **Termux:Widget**
3. Arrasta para a tela inicial
4. Os botões `Bot Start` e `Bot Stop` aparecerão disponíveis

---

## Passo 9 (opcional) — Subir o bot automaticamente ao ligar o celular

Requer o app **Termux:Boot** instalado (F-Droid). Após instalar, abra-o ao menos uma vez e então:

```sh
mkdir -p ~/.termux/boot

cat > ~/.termux/boot/start-bot.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
cd ~/bot_discord
source .venv/bin/activate
mkdir -p logs
python main.py >> logs/termux.log 2>&1 &
EOF

chmod +x ~/.termux/boot/start-bot.sh
```

---

## Manter rodando com a tela bloqueada

Na notificação do Termux, toque em **Acquire Wakelock** — impede o Android de encerrar o processo em background.

---

## Verificar logs

Para ver o que o bot está fazendo enquanto roda em background:

```sh
tail -f ~/bot_discord/logs/termux.log
```
