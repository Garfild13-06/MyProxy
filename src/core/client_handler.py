import asyncio
import uuid
import time
from typing import Dict, Any, Optional
from aiohttp import ClientSession, ClientTimeout
from ..config.config_loader import ConfigLoader
from ..logutils.logger import ProxyLogger
from ..security.access_control import AccessControl
from ..utils.http_utils import HTTPUtils
from urllib.parse import urlsplit

class ClientHandler:
    def __init__(self, config_loader: ConfigLoader, logger: ProxyLogger, access_control: AccessControl):
        self.config_loader = config_loader
        self.logger = logger
        self.access_control = access_control
        self.http_utils = HTTPUtils()
        self.limits = config_loader.get_limits_config()
        self.max_body_size = self.limits.get("max_body_size_kb", 1024) * 1024

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """
        Обработка клиентского подключения
        
        Args:
            reader: StreamReader для чтения данных
            writer: StreamWriter для записи данных
        """
        request_id = uuid.uuid4().hex[:8]
        peer = writer.get_extra_info("peername")
        start_time = time.time()

        self.logger.log_event('info', request_id, peer=peer)

        try:
            # Читаем заголовки запроса
            try:
                data = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
            except asyncio.TimeoutError:
                self.logger.log_event('warning', request_id, message="Timeout reading headers")
                writer.write(b"HTTP/1.1 408 Request Timeout\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            except Exception as e:
                self.logger.log_event('error', request_id, message=f"Failed to read headers: {e}")
                writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return

            # Парсим первую строку запроса
            header_lines = data.decode(errors='ignore').split('\r\n')
            if not header_lines:
                return

            # Обработка HTTPS CONNECT
            if header_lines[0].startswith("CONNECT"):
                await self._handle_connect(reader, writer, header_lines[0], request_id, peer)
                return

            # Обработка обычного HTTP запроса
            await self._handle_http_request(reader, writer, header_lines, request_id, peer, start_time)

        except Exception as e:
            self.logger.log_event('error', request_id, message=f"[FATAL] {e}")
        finally:
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()

    async def _handle_connect(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                            connect_line: str, request_id: str, peer: tuple) -> None:
        """Обработка HTTPS CONNECT запроса"""
        target = connect_line.split()[1]
        host, port = target.split(":")
        port = int(port)

        client_ip = peer[0]
        if not self.access_control.check_access(client_ip, host):
            self.logger.log_event('warning', request_id, peer=client_ip, url=host,
                                message="Access denied (HTTPS) by ACL")
            writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
            return

        self.logger.log_event('info', request_id, url=f"https://{host}:{port}")

        try:
            remote_reader, remote_writer = await asyncio.open_connection(host, port)
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()

            await asyncio.gather(
                self._tunnel_data(reader, remote_writer),
                self._tunnel_data(remote_reader, writer)
            )
        except Exception as e:
            self.logger.log_event('error', request_id, message=f"[HTTPS] CONNECT failed: {e}")
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await writer.drain()

    async def _handle_http_request(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                                 header_lines: list, request_id: str, peer: tuple, start_time: float) -> None:
        """Обработка обычного HTTP запроса"""
        try:
            method, url, version = self.http_utils.parse_request_line(header_lines[0])
        except ValueError as e:
            self.logger.log_event('error', request_id, message=str(e))
            writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await writer.drain()
            return

        # Парсим заголовки
        headers = self.http_utils.parse_headers('\r\n'.join(header_lines[1:-2]))

        # Парсим URL
        host, port, path, query = self.http_utils.parse_url(url)

        # Проверяем доступ
        client_ip = peer[0]
        if not self.access_control.check_access(client_ip, host):
            self.logger.log_event('warning', request_id, peer=client_ip, url=host,
                                message="Access denied by ACL")
            writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
            return

        # Читаем тело запроса если есть
        content = b''
        if 'Content-Length' in headers:
            try:
                content_length = int(headers['Content-Length'])
                if content_length > self.max_body_size:
                    self.logger.log_event('warning', request_id, message="Request body too large")
                    writer.write(b"HTTP/1.1 413 Request Entity Too Large\r\n\r\n")
                    await writer.drain()
                    return
                content = await reader.readexactly(content_length)
            except Exception as e:
                self.logger.log_event('warning', request_id, message=f"Failed to read body: {e}")

        # Логируем детали запроса
        if self.logger.log_fields.get("body"):
            self.logger.log_event('info', request_id, body=content.decode(errors='ignore'))
        if self.logger.log_fields.get("headers"):
            self.logger.log_event('info', request_id, headers=headers)

        # Специальная обработка для IP 172.16.10.30
        if host == "172.16.10.30":
            await self._handle_special_host(reader, writer, method, url, headers, content, host, port)
            return

        # Логируем время выполнения
        if self.logger.log_fields.get("duration_ms"):
            duration = round((time.time() - start_time) * 1000)
            self.logger.log_event('info', request_id, duration=duration)

        # Обычная обработка через aiohttp
        url = f"http://{host}{path}"
        if query:
            url += f"?{query}"

        # Проверяем порт в заголовке Host
        host_header = headers.get("Host", "")
        if ":" in host_header:
            host_name, host_port = host_header.split(":", 1)
            try:
                port = int(host_port)
                # Обновляем URL с правильным портом
                url = f"http://{host}:{port}{path}"
                if query:
                    url += f"?{query}"
            except ValueError:
                pass  # Игнорируем некорректный порт

        # Устанавливаем заголовки для поддержки JavaScript
        headers["Connection"] = "close"
        
        # Добавляем заголовки для поддержки JavaScript-приложений
        if "Accept" not in headers:
            headers["Accept"] = "*/*"
        if "Accept-Language" not in headers:
            headers["Accept-Language"] = "en-US,en;q=0.9"
        if "Accept-Encoding" not in headers:
            headers["Accept-Encoding"] = "gzip, deflate"
        if "User-Agent" not in headers:
            headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        
        # Получаем настройки таймаута из конфигурации
        server_config = self.config_loader.get_server_config()
        timeout = ClientTimeout(total=server_config.get("timeout", 20))

        try:
            async with ClientSession(timeout=timeout) as session:
                async with session.request(method, url, headers=headers, data=content) as resp:
                    body = await resp.read()
                    writer.write(f"HTTP/1.1 {resp.status} {resp.reason}\r\n".encode())
                    for k, v in resp.headers.items():
                        writer.write(f"{k}: {v}\r\n".encode())
                    writer.write(b"Connection: close\r\n\r\n")
                    writer.write(body)
                    await writer.drain()

                    # Логируем ответ
                    if self.logger.log_fields.get("response_headers"):
                        self.logger.log_event('info', request_id, response_headers=dict(resp.headers))
                    if self.logger.log_fields.get("response_body"):
                        self.logger.log_event('info', request_id, response_body=body.decode(errors='ignore'))

        except Exception as e:
            self.logger.log_event('error', request_id, message=f"[AIOHTTP ERROR] {e}")
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await writer.drain()

    async def _handle_special_host(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                                 method: str, url: str, headers: Dict[str, str], content: bytes,
                                 host: str, port: int) -> None:
        """Специальная обработка для хоста 172.16.10.30"""
        request_id = uuid.uuid4().hex[:8]
        start_time = time.time()
        
        # Проверяем порт в заголовке Host
        host_header = headers.get("Host", "")
        if ":" in host_header:
            host_name, host_port = host_header.split(":", 1)
            try:
                port = int(host_port)
            except ValueError:
                pass  # Игнорируем некорректный порт
        
        self.logger.log_event('info', request_id, method=method, url=url)
        
        if self.logger.log_fields.get("headers"):
            self.logger.log_event('info', request_id, headers=headers)
            
        if self.logger.log_fields.get("body") and content:
            self.logger.log_event('info', request_id, body=content.decode(errors='ignore'))
            
        try:
            remote_reader, remote_writer = await asyncio.open_connection(host, port)

            # Получаем размер буфера из конфигурации
            server_config = self.config_loader.get_server_config()
            buffer_size = server_config.get("buffer_size", 4096)

            # Формируем запрос с принудительным закрытием соединения
            request_lines = [
                f"{method} {url} HTTP/1.1",
                "Connection: close"
            ]
            
            # Добавляем остальные заголовки
            for k, v in headers.items():
                if k.lower() != "connection":  # Пропускаем существующий Connection
                    request_lines.append(f"{k}: {v}")

            # Отправляем запрос
            raw_request = "\r\n".join(request_lines).encode() + b"\r\n\r\n" + content
            remote_writer.write(raw_request)
            await remote_writer.drain()

            # Читаем и передаем ответ
            response_body = b""
            while not remote_reader.at_eof():
                chunk = await remote_reader.read(buffer_size)
                if not chunk:
                    break
                response_body += chunk
                writer.write(chunk)
                await writer.drain()
                
            # Логируем ответ
            if self.logger.log_fields.get("response_body") and response_body:
                self.logger.log_event('info', request_id, response_body=response_body.decode(errors='ignore'))
                
            # Логируем время выполнения
            if self.logger.log_fields.get("duration_ms"):
                duration = round((time.time() - start_time) * 1000)
                self.logger.log_event('info', request_id, duration=duration)

            remote_writer.close()
            await remote_writer.wait_closed()
        except Exception as e:
            self.logger.log_event('error', request_id, message=f"[SPECIAL HOST ERROR] {e}")
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _tunnel_data(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Туннелирование данных между клиентом и сервером"""
        try:
            while not reader.at_eof():
                chunk = await reader.read(4096)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed() 