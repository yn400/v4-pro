"""
远程 ZIP 读取器 — 通过 HTTP Range 请求读取 Zenodo 上的大 ZIP 的部分内容，
不必下载整个 10GB 制品。仅用于基准数据获取（不随包分发）。
"""

from __future__ import annotations

import io
import json
import struct
import urllib.request
from collections import OrderedDict

BLOCK = 1024 * 1024  # 1MB 块


class HTTPRangeFile(io.RawIOBase):
    """把支持 Range 的 HTTP 资源包装成可 seek 的文件对象（带 LRU 块缓存）。"""

    def __init__(self, url: str, block: int = BLOCK, cache_blocks: int = 128):
        self.url = url
        self.block = block
        self.pos = 0
        self._len: int | None = None
        self._cache: OrderedDict[int, bytes] = OrderedDict()
        self._cache_max = cache_blocks

    def _fetch_range(self, start: int, end: int) -> bytes:
        req = urllib.request.Request(self.url, headers={
            "User-Agent": "v4-pro",
            "Range": f"bytes={start}-{end - 1}",
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            if resp.status not in (200, 206):
                raise OSError(f"range request failed: {resp.status}")
            return resp.read()

    def _read_block(self, idx: int) -> bytes:
        if idx in self._cache:
            self._cache.move_to_end(idx)
            return self._cache[idx]
        data = self._fetch_range(idx * self.block, (idx + 1) * self.block)
        self._cache[idx] = data
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)
        return data

    # io API
    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self.pos = offset
        elif whence == io.SEEK_CUR:
            self.pos += offset
        elif whence == io.SEEK_END:
            self.pos = self.length + offset
        return self.pos

    def tell(self) -> int:
        return self.pos

    @property
    def length(self) -> int:
        if self._len is None:
            req = urllib.request.Request(self.url, method="HEAD",
                                         headers={"User-Agent": "v4-pro"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                self._len = int(resp.headers["Content-Length"])
        return self._len

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = self.length - self.pos
        out = bytearray()
        remaining = size
        while remaining > 0 and self.pos < self.length:
            idx, off = divmod(self.pos, self.block)
            block = self._read_block(idx)
            chunk = block[off:off + remaining]
            out += chunk
            self.pos += len(chunk)
            remaining -= len(chunk)
        return bytes(out)


def list_entries(url: str) -> list[dict]:
    """列出远程 ZIP 的全部条目（下载末尾的中央目录，通常只有几 MB）。"""
    f = HTTPRangeFile(url)
    total = f.length
    tail_size = min(1024 * 1024, total)
    f.seek(total - tail_size)
    tail = f.read(tail_size)

    # 找 EOCD (PK\x05\x06)，再找 ZIP64 EOCD 定位器 (PK\x06\x07)
    eocd_pos = tail.rfind(b"PK\x05\x06")
    if eocd_pos < 0:
        raise OSError("EOCD not found")
    cd_size, cd_offset = struct.unpack_from("<II", tail, eocd_pos + 12)
    if cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
        # ZIP64
        loc_pos = tail.rfind(b"PK\x06\x07")
        if loc_pos < 0:
            raise OSError("ZIP64 locator not found")
        z64_eocd_off = struct.unpack_from("<Q", tail, loc_pos + 8)[0]
        f.seek(z64_eocd_off)
        z64 = f.read(56)
        cd_size, cd_offset = struct.unpack_from("<QQ", z64, 40)

    # 下载整个中央目录
    f.seek(cd_offset)
    central = f.read(cd_size)

    entries = []
    pos = 0
    while pos < len(central) and central[pos:pos + 4] == b"PK\x01\x02":
        (sig, ver_made, ver_need, flags, method, mtime, mdate, crc,
         comp_size, uncomp_size, name_len, extra_len, comment_len,
         disk_start, int_attr, ext_attr, local_off) = struct.unpack_from(
            "<IHHHHHHIIIHHHHHII", central, pos)
        name = central[pos + 46:pos + 46 + name_len].decode("utf-8", errors="replace")
        entries.append({"name": name, "size": uncomp_size,
                        "compressed": comp_size, "offset": local_off})
        pos += 46 + name_len + extra_len + comment_len
    return entries


def fetch_entry(url: str, offset: int, block: int = BLOCK) -> bytes:
    """按中央目录给出的 local header offset 下载单个条目的解压内容。"""
    f = HTTPRangeFile(url, block=block, cache_blocks=8)
    f.seek(offset)
    return f.read()  # zipfile 会自己解析 local header 并读 compressed 数据


def open_remote_zip(url: str):
    """返回 (HTTPRangeFile, entries)。用 zipfile.ZipFile(file) 配 entries 读取具体文件。"""
    f = HTTPRangeFile(url)
    entries = list_entries(url)
    return f, entries


if __name__ == "__main__":
    url = "https://zenodo.org/api/records/14676377/files/Artifacts_Submission.zip/content"
    entries = list_entries(url)
    print("条目总数:", len(entries))
    with open("benchmarks/data/zenodo_entries.json", "w", encoding="utf-8") as fp:
        json.dump(entries, fp, ensure_ascii=False, indent=1)
    # 展示可能包含幻觉包名单的候选
    for e in entries:
        n = e["name"].lower()
        if any(k in n for k in ("halluc", "package", "result")) and e["size"] < 200 * 1024 * 1024:
            print(f"  {e['size']:>12,}  {e['name']}")
