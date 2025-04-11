from typing import Dict, Tuple, Optional
from urllib.parse import urlsplit

class HTTPUtils:
    @staticmethod
    def parse_headers(headers_raw: str) -> Dict[str, str]:
        """
        Парсинг HTTP заголовков
        
        Args:
            headers_raw: Сырые заголовки в виде строки
            
        Returns:
            Dict[str, str]: Словарь заголовков
        """
        headers = {}
        for line in headers_raw.split('\r\n'):
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.strip()] = v.strip()
        return headers

    @staticmethod
    def parse_request_line(request_line: str) -> Tuple[str, str, str]:
        """
        Парсинг первой строки HTTP запроса
        
        Args:
            request_line: Первая строка запроса (например, "GET http://example.com/ HTTP/1.1")
            
        Returns:
            Tuple[str, str, str]: Метод, URL и версия протокола
        """
        try:
            method, url, version = request_line.split()
            return method, url, version
        except ValueError:
            raise ValueError(f"Invalid request line: {request_line}")

    @staticmethod
    def parse_url(url: str) -> Tuple[str, int, str, str]:
        """
        Парсинг URL
        
        Args:
            url: URL для парсинга
            
        Returns:
            Tuple[str, int, str, str]: Хост, порт, путь и query
        """
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port or 80
        path = parsed.path or '/'
        query = parsed.query
        
        return host, port, path, query

    @staticmethod
    def format_response(status: int, reason: str, headers: Dict[str, str], body: bytes) -> bytes:
        """
        Форматирование HTTP ответа
        
        Args:
            status: Код статуса
            reason: Текст статуса
            headers: Заголовки ответа
            body: Тело ответа
            
        Returns:
            bytes: Отформатированный ответ
        """
        response = [f"HTTP/1.1 {status} {reason}"]
        
        # Добавляем заголовки
        for k, v in headers.items():
            response.append(f"{k}: {v}")
            
        # Добавляем Content-Length если есть тело
        if body:
            response.append(f"Content-Length: {len(body)}")
            
        # Добавляем пустую строку и тело
        response.append("")
        if body:
            response.append(body.decode('utf-8', errors='ignore'))
            
        return "\r\n".join(response).encode('utf-8') 