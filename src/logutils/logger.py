import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Any, Optional
from ..config.config_loader import ConfigLoader

class ProxyLogger:
    def __init__(self, config_loader: ConfigLoader):
        self.config_loader = config_loader
        self.log_fields = config_loader.get_log_fields()
        self.setup_logging()

    def setup_logging(self) -> None:
        """Настройка системы логирования"""
        log_config = self.config_loader.get_logging_config()
        
        # Параметры логирования
        log_path = log_config.get("path", "./logs/proxy.log")
        log_level = log_config.get("level", "INFO").upper()
        rotate_size = log_config.get("rotate_size_mb", 5) * 1024 * 1024
        rotate_count = log_config.get("rotate_backups", 3)

        # Создаем директорию для логов если её нет
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)

        # Настройка обработчика с ротацией
        handler = RotatingFileHandler(
            log_path,
            maxBytes=rotate_size,
            backupCount=rotate_count,
            encoding='utf-8'
        )
        
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        handler.setFormatter(formatter)

        # Настройка корневого логгера
        logging.basicConfig(
            level=getattr(logging, log_level),
            handlers=[handler]
        )

    def log_event(self, level: str, request_id: str, **kwargs) -> None:
        """
        Логирование события с учетом настроек полей логирования
        
        Args:
            level: Уровень логирования (info, warning, error)
            request_id: Уникальный идентификатор запроса
            **kwargs: Дополнительные поля для логирования
        """
        pieces = []

        # Формируем сообщение на основе настроенных полей
        if self.log_fields.get("remote_ip") and kwargs.get("peer"):
            pieces.append(f"IP={kwargs['peer']}")
        if self.log_fields.get("method") and kwargs.get("method"):
            pieces.append(f"METHOD={kwargs['method']}")
        if self.log_fields.get("url") and kwargs.get("url"):
            pieces.append(f"URL={kwargs['url']}")
        if self.log_fields.get("status_code") and kwargs.get("status_code") is not None:
            pieces.append(f"STATUS={kwargs['status_code']}")
        if self.log_fields.get("duration_ms") and kwargs.get("duration") is not None:
            pieces.append(f"TIME={kwargs['duration']}ms")
        if self.log_fields.get("headers") and kwargs.get("headers"):
            pieces.append(f"HEADERS={kwargs['headers']}")
        if self.log_fields.get("body") and kwargs.get("body") is not None:
            pieces.append(f"BODY={kwargs['body']}")
        if self.log_fields.get("response_headers") and kwargs.get("response_headers"):
            pieces.append(f"RESP_HEADERS={kwargs['response_headers']}")
        if self.log_fields.get("response_body") and kwargs.get("response_body") is not None:
            pieces.append(f"RESP_BODY={kwargs['response_body']}")
        if kwargs.get("message"):
            pieces.append(str(kwargs["message"]))

        msg = f"[{request_id}] " + " | ".join(pieces)

        # Выбираем функцию логирования в зависимости от уровня
        log_func = {
            "info": logging.info,
            "warning": logging.warning,
            "error": logging.error,
            "debug": logging.debug
        }.get(level.lower(), logging.info)

        log_func(msg) 