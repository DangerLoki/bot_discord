import threading
from src.bot.bot import MyBot
from src.web.app import iniciar_servidor
from src.logger import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

def main():
    flask_thread = threading.Thread(
        target=iniciar_servidor,
        kwargs={'host': '0.0.0.0', 'port': 5000, 'debug': False},
        daemon=True
        )
    
    flask_thread.start()
    logger.info('Servidor web iniciado em http://0.0.0.0:5000.')
    
    bot = MyBot()
    bot.run()

if __name__ == "__main__":
    main()
    