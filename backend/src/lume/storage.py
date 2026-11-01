import asyncio
import base64
import hashlib
import io
import ipaddress
import os
import socket
import warnings
from urllib.parse import urlparse

import httpx
from PIL import Image

from .security import DomainError


class ImageStore:
    def __init__(self, settings):
        self.settings = settings
        self.root = settings.data_dir.resolve() / "images"
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def put(self, data: bytes) -> dict:
        if len(data) > self.settings.max_image_bytes:
            raise DomainError("IMAGE_TOO_LARGE", "图片字节超限", 413)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    if image.width * image.height > self.settings.max_image_pixels:
                        raise ValueError("pixel limit")
                    if image.format not in {"PNG", "JPEG", "WEBP"}:
                        raise ValueError("unsupported image")
                    mime = Image.MIME[image.format]
                    image.verify()
        except (OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
            raise DomainError("INVALID_IMAGE", "图片无效或解码尺寸超限", 422) from None
        digest = hashlib.sha256(data).hexdigest()
        path = self.root / digest
        if not path.exists():
            # Content-addressed names are derived here, never supplied by the client.
            temporary = self.root / f".{digest}.{os.urandom(8).hex()}"
            try:
                temporary.write_bytes(data)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        return {"blob": digest, "digest": digest, "mime": mime}

    def decode(self, encoded: str) -> dict:
        try:
            data = base64.b64decode(encoded, validate=True)
        except ValueError:
            raise DomainError("INVALID_IMAGE", "图片编码无效", 422) from None
        return self.put(data)

    def path(self, blob: str):
        if len(blob) != 64 or any(c not in "0123456789abcdef" for c in blob):
            raise DomainError("NOT_FOUND", "图片不可用", 404)
        path = self.root / blob
        if not path.is_file():
            raise DomainError("NOT_FOUND", "图片不可用", 404)
        return path

    async def download(self, url: str) -> dict:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in self.settings.attachment_hosts
            or parsed.username
            or parsed.password
            or parsed.port not in {None, 443}
        ):
            raise DomainError("REMOTE_IMAGE_REJECTED", "附件来源未获准")
        addresses = await asyncio.get_running_loop().getaddrinfo(
            parsed.hostname, 443, type=socket.SOCK_STREAM
        )
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise DomainError("REMOTE_IMAGE_REJECTED", "附件来源未获准")
        # Exact trusted vendor hosts only; do not allow user-selected domains or redirects.
        data = bytearray()
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise DomainError("REMOTE_IMAGE_REJECTED", "附件下载失败")
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > self.settings.max_image_bytes:
                        raise DomainError("IMAGE_TOO_LARGE", "附件字节超限", 413)
        return self.put(bytes(data))


async def recognize(path, language: str) -> tuple[str, str | None]:
    try:
        process = await asyncio.create_subprocess_exec(
            "tesseract",
            str(path),
            "stdout",
            "-l",
            language,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return "", "OCR_NOT_INSTALLED"
    try:
        async with asyncio.timeout(15):
            output, _ = await process.communicate()
    except asyncio.CancelledError:
        process.kill()
        await process.communicate()
        raise
    except TimeoutError:
        process.kill()
        await process.communicate()
        return "", "OCR_TIMEOUT"
    if process.returncode:
        return "", "OCR_FAILED"
    return output.decode("utf-8", errors="replace")[:20_000], None
