#!/usr/bin/env python
"""
Скрипт для запуска прокси-сервера
"""
from src.core.proxy_server import ProxyServer

def main():
    server = ProxyServer()
    server.run()

if __name__ == "__main__":
    main() 