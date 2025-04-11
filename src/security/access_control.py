import ipaddress
import fnmatch
from pathlib import Path
from typing import Set, Dict, Any
from ..config.config_loader import ConfigLoader

class AccessControl:
    def __init__(self, config_loader: ConfigLoader):
        self.config_loader = config_loader
        self.access_config = config_loader.get_access_control_config()
        self.default_action = self.access_config.get("default_action", "deny").lower()

    def load_domain_list(self, file_path: str) -> Set[str]:
        """
        Загрузка списка доменов из файла
        
        Args:
            file_path: Путь к файлу со списком доменов
            
        Returns:
            Set[str]: Множество доменов
        """
        try:
            with open(file_path, encoding='utf-8') as f:
                return set(
                    line.split("#", 1)[0].strip()
                    for line in f
                    if line.strip() and not line.strip().startswith("#")
                )
        except FileNotFoundError:
            return set()

    def match_hostname(self, hostname: str, pattern_set: Set[str]) -> bool:
        """
        Проверка соответствия хоста шаблону
        
        Args:
            hostname: Имя хоста для проверки
            pattern_set: Множество шаблонов
            
        Returns:
            bool: True если хост соответствует хотя бы одному шаблону
        """
        for pattern in pattern_set:
            if fnmatch.fnmatch(hostname, pattern):
                return True
            # Дополнительно: если паттерн начинается с *, и hostname == остатку — засчитываем
            if pattern.startswith("*") and hostname == pattern.lstrip("*"):
                return True
        return False

    def check_access(self, client_ip: str, hostname: str) -> bool:
        """
        Проверка доступа клиента к хосту
        
        Args:
            client_ip: IP-адрес клиента
            hostname: Имя хоста для доступа
            
        Returns:
            bool: True если доступ разрешен
        """
        ip = ipaddress.ip_address(client_ip)
        
        for rule in self.access_config.get("rules", []):
            networks = rule.get("networks", [])
            for net in networks:
                try:
                    if ip in ipaddress.ip_network(net):
                        action = rule.get("action", "deny").lower()
                        
                        # Загружаем списки доменов если они указаны
                        whitelist = self.load_domain_list(rule.get("whitelist_file", "")) if "whitelist_file" in rule else set()
                        blacklist = self.load_domain_list(rule.get("blacklist_file", "")) if "blacklist_file" in rule else set()

                        if action == "deny":
                            # Для deny: разрешаем только если домен в белом списке
                            if whitelist and not self.match_hostname(hostname, whitelist):
                                return False
                            return True
                        elif action == "allow":
                            # Для allow: запрещаем если домен в черном списке
                            if blacklist and self.match_hostname(hostname, blacklist):
                                return False
                            return True
                except ValueError:
                    continue

        # Если не совпало ни одно правило — применяем default_action
        return self.default_action == "allow" 