import pytest
from core.bencode import encode
from core.torrent import load_torrent, Torrent, FileInfo


def test_load_torrent_single_file():
    fake = encode({
        b"announce": b"http://tracker.example.com",
        b"info": {
            b"name": b"test.txt",
            b"length": 100,
            b"piece length": 50,
            b"pieces": b"\x00" * 40,
        }
    })
    torrent = load_torrent(fake)
    assert torrent.name == "test.txt"
    assert torrent.length == 100
    assert len(torrent.pieces) == 2
    assert len(torrent.info_hash) == 20

def test_load_torrent_multi_file():
    fake = encode({
        b"announce": b"http://tracker.example.com",
        b"info": {
            b"name": b"folder",
            b"piece length": 50,
            b"pieces": b"\x00" * 20,
            b"files": [
                {b"length": 30, b"path": [b"a.txt"]},
                {b"length": 70, b"path": [b"sub", b"b.txt"]},
            ]
        }
    })
    torrent = load_torrent(fake)
    assert torrent.length == 100
    assert len(torrent.files) == 2
    assert torrent.files[1].path == ["sub", "b.txt"]


@pytest.fixture
def fnaf_torrent_bytes():
    with open("test/fixtures/fnaf.torrent", "rb") as f:
        return f.read()

def test_load_real_torrent_sanity(fnaf_torrent_bytes):
    torrent = load_torrent(fnaf_torrent_bytes)
    assert isinstance(torrent, Torrent)
    assert torrent.length > 0
    assert len(torrent.info_hash) == 20