import logging
import os
from logging.handlers import RotatingFileHandler

# Diretório onde os logs serão salvos (raiz do projeto)
_BASE_DIR = os.path.join(os.path.dirname(__file__), '..')
LOGS_DIR = os.path.join(_BASE_DIR, 'logs')

# Formato padrão das mensagens
LOG_FORMAT = '[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def setup_logging(level: int = logging.DEBUG) -> None:
    """
    Configura o sistema de logging global do projeto.
    Deve ser chamado UMA vez no main.py antes de qualquer outra coisa.

    - Console: nível INFO  (mensagens limpas no terminal)
    - Arquivo : nível DEBUG (histórico completo em logs/bot.log)
    - Rotação : 5 MB por arquivo, mantém os 3 últimos
    """
    os.makedirs(LOGS_DIR, exist_ok=True)

    log_file = os.path.join(LOGS_DIR, 'bot.log')

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    # --- Handler de arquivo com rotação ---
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding='utf-8',
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # --- Handler de console ---
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # --- Logger raiz ---
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Silencia logs verbosos de bibliotecas externas e evita duplicados
    for name, lvl in [
        ('discord',         logging.WARNING),
        ('discord.http',    logging.WARNING),
        ('discord.gateway', logging.WARNING),
        ('discord.client',  logging.WARNING),
        ('werkzeug',        logging.ERROR),
        ('yt_dlp',          logging.WARNING),
    ]:
        lib_log = logging.getLogger(name)
        lib_log.setLevel(lvl)
        lib_log.propagate = False   # evita subir para o root (sem duplicados)


def get_logger(name: str) -> logging.Logger:
    """
    Retorna um logger nomeado para o módulo que chamou.
    Uso: logger = get_logger(__name__)
    """
    return logging.getLogger(name)
