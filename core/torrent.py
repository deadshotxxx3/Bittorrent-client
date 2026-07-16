from dataclasses import dataclass
from core.bencode import decode, encode
import hashlib

@dataclass
class FileInfo:
    length: int
    path: list[str]


@dataclass
class Torrent:
    announce: str
    name: str
    piece_length: int
    pieces: list[bytes]
    length: int
    files : list[FileInfo]
    info_hash: bytes
    announce_list: list[bytes] | None


def load_torrent(data: bytes) -> Torrent:
    raw, _ = decode(data)
    info = raw[b"info"]
    info_hash = hashlib.sha1(encode(raw[b"info"])).digest()

    pieces_raw = info[b"pieces"]
    pieces = [pieces_raw[i:i+20] for i in range(0, len(pieces_raw), 20)]
    files = []
    total_length = 0
    if b"length" in info:
        total_length  += info[b"length"]
        files.append(FileInfo(
            length=info[b"length"],
            path=[info[b"name"].decode()]
        ))
    else:
        for item in info[b"files"]:
            total_length += item[b"length"]
            files.append(FileInfo(
                length=item[b"length"],
                path=[x.decode() for x in item[b"path"]]
            ))

    return Torrent(
        announce=raw[b"announce"].decode(),
        name=info[b"name"].decode(),
        piece_length=info[b"piece length"],
        pieces=pieces,
        length=total_length,
        files=files,
        info_hash=info_hash,
        announce_list=raw.get(b"announce-list")
    )