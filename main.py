import threading
from bot.bot import MyBot
from web.app import iniciar_servidor

def main():
    flask_thread = threading.Thread(
        target=iniciar_servidor,
        kwargs={'host': '0.0.0.0', 'port': 5000, 'debug': False},
        daemon=True
        )
    
    flask_thread.start()
    print("Servidor web iniciado em http://0.0.0.0:5000.")
    
    bot = MyBot()
    bot.run()

if __name__ == "__main__":
    main()
    