"""Streaming de entregas Iberinform (.zip) desde Cloudflare R2 (S3-compatible) SIN
materializar el zip ni su contenido descomprimido en disco.

Contexto (2026-06): el disco persistente del pod son 9,8 GB y las entregas reales de
Iberinform pesan ~9,8 GB (y crecerán a decenas de GB al cubrir hasta 2,5M empresas), así
que no caben ni por descarga-completa-y-extrae ni por un POST de navegador a través del
proxy. Daniel sube el .zip a R2 por su cuenta (rclone/aws-cli) y el backend lo LEE por
streaming desde el bucket.

Cómo funciona sin bajar el fichero entero:
- `S3RangeReader` es un objeto fichero SEEKABLE respaldado por peticiones HTTP Range
  (GetObject con cabecera Range) contra R2. `zipfile.ZipFile` necesita hacer `seek` para
  leer el directorio central (que está al FINAL del zip) y luego cada miembro; este lector
  sirve solo los rangos de bytes que pide, con una ventana en memoria acotada (8 MB) — el
  consumo de RAM/disco es O(ventana), no O(tamaño del zip).
- Cada `Datos_*.tab` interno se abre con `zf.open(member)` (descompresión al vuelo,
  miembro a miembro) y se envuelve en `TextIOWrapper` con la codificación detectada.

Credenciales por variables de entorno: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID,
R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME (ver backend/.env).
"""

import io
import os
import zipfile
import logging
from contextlib import contextmanager

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)

_WINDOW = 8 * 1024 * 1024  # 8 MB: ventana de lectura en memoria (acota RAM, reduce nº de GETs)


def r2_client():
    """Cliente boto3 apuntando al endpoint S3-compatible de Cloudflare R2. Falla rápido
    (KeyError) si falta cualquiera de las 4 variables — nunca usamos valores por defecto."""
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 5, "mode": "standard"}),
    )


def bucket_name() -> str:
    return os.environ["R2_BUCKET_NAME"]


def list_zip_deliveries(prefix: str = ""):
    """Lista los objetos .zip del bucket (paginado, sin límite de 1000). Devuelve
    [{key, size, last_modified}], más recientes primero."""
    client = r2_client()
    bucket = bucket_name()
    out = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(".zip"):
                lm = obj.get("LastModified")
                out.append({
                    "key": key,
                    "size": obj.get("Size"),
                    "last_modified": lm.isoformat() if lm else None,
                })
    out.sort(key=lambda o: o["last_modified"] or "", reverse=True)
    return out


class S3RangeReader(io.RawIOBase):
    """Fichero seekable respaldado por HTTP Range GETs contra R2. Memory-bounded."""

    def __init__(self, client, bucket, key, window=_WINDOW):
        self._c = client
        self._b = bucket
        self._k = key
        self._win = window
        head = client.head_object(Bucket=bucket, Key=key)
        self._size = head["ContentLength"]
        self._pos = 0
        self._buf = b""
        self._buf_start = 0
        self._buf_end = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self._pos

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            self._pos = offset
        elif whence == io.SEEK_CUR:
            self._pos += offset
        elif whence == io.SEEK_END:
            self._pos = self._size + offset
        else:
            raise ValueError(f"whence inválido: {whence}")
        return self._pos

    @property
    def size(self):
        return self._size

    def _fetch(self, start, length):
        if start >= self._size or length <= 0:
            return b""
        end = min(start + length, self._size) - 1
        resp = self._c.get_object(Bucket=self._b, Key=self._k, Range=f"bytes={start}-{end}")
        return resp["Body"].read()

    def _read_bytes(self, size):
        if self._pos >= self._size:
            return b""
        if size is None or size < 0:
            data = self._fetch(self._pos, self._size - self._pos)
            self._pos += len(data)
            return data
        end = self._pos + size
        # ¿el buffer actual cubre [_pos, end)? si no, recarga una ventana desde _pos.
        if not (self._buf_start <= self._pos and end <= self._buf_end):
            fetch_len = max(size, self._win)
            self._buf = self._fetch(self._pos, fetch_len)
            self._buf_start = self._pos
            self._buf_end = self._pos + len(self._buf)
        off = self._pos - self._buf_start
        data = self._buf[off:off + size]
        self._pos += len(data)
        return data

    def read(self, size=-1):
        return self._read_bytes(size)

    def readinto(self, b):
        data = self._read_bytes(len(b))
        n = len(data)
        b[:n] = data
        return n


class ZipDelivery:
    """Un .zip de entrega Iberinform en R2, abierto por streaming. Resuelve los miembros
    por nombre base (tolera que el zip los anide dentro de una subcarpeta, igual que
    `_find_data_dir` hacía en disco) y da acceso texto miembro a miembro."""

    def __init__(self, object_key):
        self.key = object_key
        self._client = r2_client()
        self._reader = S3RangeReader(self._client, bucket_name(), object_key)
        self._zf = zipfile.ZipFile(self._reader)
        self._by_base = {}
        for zi in self._zf.infolist():
            if zi.is_dir():
                continue
            base = os.path.basename(zi.filename)
            # primer gana: si el zip trae duplicados anidados, nos quedamos con el primero.
            self._by_base.setdefault(base, zi)
        self._enc_cache = {}

    def names(self):
        return set(self._by_base)

    def has(self, base) -> bool:
        return base in self._by_base

    def member_stats(self, base):
        """(checksum, bytes) SIN pasada extra: usa CRC-32 y file_size del directorio
        central del zip (ya calculados por Iberinform al empaquetar)."""
        zi = self._by_base[base]
        return format(zi.CRC & 0xFFFFFFFF, "08x"), zi.file_size

    def detect_encoding(self, base) -> str:
        if base in self._enc_cache:
            return self._enc_cache[base]
        zi = self._by_base[base]
        with self._zf.open(zi) as fh:
            sample = fh.read(65536)
        try:
            sample.decode("utf-8")
            enc = "utf-8"
        except UnicodeDecodeError:
            enc = "latin-1"
        self._enc_cache[base] = enc
        return enc

    @contextmanager
    def open_text(self, base, encoding=None):
        """Stream texto de un miembro (descompresión al vuelo). Uso SECUENCIAL: no abrir
        dos miembros del mismo ZipDelivery a la vez (comparten el lector seekable)."""
        enc = encoding or self.detect_encoding(base)
        zi = self._by_base[base]
        fh = self._zf.open(zi)
        wrapper = io.TextIOWrapper(fh, encoding=enc, errors="replace", newline="")
        try:
            yield wrapper
        finally:
            wrapper.detach()
            fh.close()

    def close(self):
        try:
            self._zf.close()
        finally:
            self._reader.close()
