from src.bot.bot import MyBot
from src.logger import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

def main():
    bot = MyBot()
    bot.run()

if __name__ == "__main__":
    main()