import asyncio
import logging
from ..config.config_loader import ConfigLoader
from ..logutils.logger import ProxyLogger
from ..security.access_control import AccessControl
from .client_handler import ClientHandler

class ProxyServer:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_loader = ConfigLoader(config_path)
        self.logger = ProxyLogger(self.config_loader)
        self.access_control = AccessControl(self.config_loader)
        self.client_handler = ClientHandler(self.config_loader, self.logger, self.access_control)
        self.server_config = self.config_loader.get_server_config()

    async def start(self):
        """Запуск прокси-сервера"""
        host = self.server_config.get("host", "0.0.0.0")
        port = self.server_config.get("port", 3128)

        server = await asyncio.start_server(
            self.client_handler.handle_client,
            host,
            port
        )

        logging.info(f"🚀 Proxy server listening on {host}:{port}")

        async with server:
            await server.serve_forever()

    def run(self):
        """Запуск сервера в основном потоке"""
        try:
            asyncio.run(self.start())
        except KeyboardInterrupt:
            logging.info("🛑 Proxy server stopped") 