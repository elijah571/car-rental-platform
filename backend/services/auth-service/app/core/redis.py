import asyncio
import ssl
from functools import lru_cache
from urllib.parse import unquote, urlsplit

from app.core.config import get_settings


class RedisError(Exception):
    """A Redis transport or command error."""


class RedisStore:
    """Small async RESP client for the auth service's Redis primitives."""

    def __init__(self, url: str):
        parsed = urlsplit(url)
        if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
            raise ValueError("REDIS_URL must be a redis:// or rediss:// URL.")
        self.host = parsed.hostname
        self.port = parsed.port or 6379
        self.username = unquote(parsed.username) if parsed.username else None
        self.password = unquote(parsed.password) if parsed.password else None
        self.database = parsed.path.strip("/") or "0"
        self.tls = parsed.scheme == "rediss"

    async def _read_response(self, reader: asyncio.StreamReader):
        prefix = await reader.readexactly(1)
        line = await reader.readline()
        if not line.endswith(b"\r\n"):
            raise RedisError("Invalid Redis response.")
        value = line[:-2]
        if prefix == b"+":
            return value.decode()
        if prefix == b"-":
            raise RedisError("Redis returned an error response.")
        if prefix == b":":
            return int(value)
        if prefix == b"$":
            length = int(value)
            if length < 0:
                return None
            data = await reader.readexactly(length + 2)
            return data[:-2].decode()
        if prefix == b"*":
            length = int(value)
            if length < 0:
                return None
            return [await self._read_response(reader) for _ in range(length)]
        raise RedisError("Unsupported Redis response type.")

    async def _execute(self, *parts: str):
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    self.host,
                    self.port,
                    ssl=ssl.create_default_context() if self.tls else None,
                    server_hostname=self.host if self.tls else None,
                ),
                timeout=5,
            )
            commands = []
            if self.password:
                commands.append(("AUTH", self.username, self.password) if self.username else ("AUTH", self.password))
            if self.database not in {"", "0"}:
                commands.append(("SELECT", self.database))
            commands.append(parts)
            result = None
            for command in commands:
                encoded = [str(item).encode() for item in command if item is not None]
                writer.write(b"*" + str(len(encoded)).encode() + b"\r\n")
                for item in encoded:
                    writer.write(b"$" + str(len(item)).encode() + b"\r\n" + item + b"\r\n")
                await writer.drain()
                result = await asyncio.wait_for(self._read_response(reader), timeout=5)
            return result
        except RedisError:
            raise
        except (OSError, asyncio.IncompleteReadError, asyncio.TimeoutError, ValueError) as exc:
            raise RedisError("Could not communicate with Redis.") from exc
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass

    async def ping(self):
        return await self._execute("PING")

    async def get(self, key: str):
        return await self._execute("GET", key)

    async def getdel(self, key: str):
        return await self._execute("GETDEL", key)

    async def incr(self, key: str):
        return await self._execute("INCR", key)

    async def expire(self, key: str, seconds: int):
        return await self._execute("EXPIRE", key, str(seconds))

    async def set(self, key: str, value: str, *, ex: int, nx: bool = False):
        command = ("SET", key, value, "EX", str(ex), "NX") if nx else ("SET", key, value, "EX", str(ex))
        return await self._execute(*command)

    async def delete(self, *keys: str):
        if not keys:
            return 0
        return await self._execute("DEL", *keys)

    async def sadd(self, key: str, value: str):
        return await self._execute("SADD", key, value)

    async def smembers(self, key: str):
        return await self._execute("SMEMBERS", key)

    async def srem(self, key: str, value: str):
        return await self._execute("SREM", key, value)

    async def aclose(self):
        return None


@lru_cache
def get_redis() -> RedisStore:
    return RedisStore(get_settings().redis_connection_url)


async def close_redis() -> None:
    get_redis.cache_clear()
