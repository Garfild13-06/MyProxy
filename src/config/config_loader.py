from pathlib import Path
import yaml
from typing import Dict, Any, List, Optional

class ConfigLoader:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации из файла"""
        config_file = Path(self.config_path)
        if not config_file.exists():
            return {}
        
        with open(config_file, encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    def get_server_config(self) -> Dict[str, Any]:
        """Получение настроек сервера"""
        return self.config.get("server", {
            "host": "0.0.0.0",
            "port": 3128,
            "timeout": 20,
            "buffer_size": 4096
        })

    def get_logging_config(self) -> Dict[str, Any]:
        """Получение настроек логирования"""
        return self.config.get("logging", {
            "path": "./logs/proxy.log",
            "level": "INFO",
            "rotate_size_mb": 5,
            "rotate_backups": 3
        })

    def get_log_fields(self) -> Dict[str, bool]:
        """Получение настроек полей логирования"""
        return self.config.get("log_fields", {
            "remote_ip": True,
            "method": True,
            "url": True,
            "status_code": True,
            "duration_ms": True,
            "headers": False,
            "body": False,
            "response_headers": False,
            "response_body": False
        })

    def get_limits_config(self) -> Dict[str, Any]:
        """Получение настроек лимитов"""
        return self.config.get("limits", {
            "max_body_size_kb": 2048
        })

    def get_access_control_config(self) -> Dict[str, Any]:
        """Получение настроек контроля доступа"""
        return self.config.get("access_control", {
            "default_action": "deny",
            "rules": []
        })

    def get_special_hosts_config(self) -> List[Dict[str, Any]]:
        """Получение настроек специальных хостов"""
        return self.config.get("special_hosts", [])

    def is_special_host(self, host: str) -> bool:
        """Проверка, является ли хост специальным"""
        special_hosts = self.get_special_hosts_config()
        return any(special_host["host"] == host for special_host in special_hosts)

    def get_special_host_config(self, host: str) -> Optional[Dict[str, Any]]:
        """Получение настроек для специального хоста"""
        special_hosts = self.get_special_hosts_config()
        for special_host in special_hosts:
            if special_host["host"] == host:
                return special_host
        return None 