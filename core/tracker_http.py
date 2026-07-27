from core.bencode import decode 
from core.torrent import load_torrent, Torrent
from urllib.parse import quote
import requests, os, socket, struct


class TrackerError(Exception):
    pass


def get_peers(torrent: Torrent, peer_id: bytes) -> list[tuple[str,int]]:
    try:
        hash_info_encoded = quote(torrent.info_hash,safe="")
        peer_id_encoded = quote(peer_id,safe="")
        url = f"{torrent.announce}?info_hash={hash_info_encoded}&peer_id={peer_id_encoded}&port=6881&uploaded=0&downloaded=0&left={torrent.length}&compact=1"
        url_get = requests.get(url,timeout=10)
        try:
            url_decode = decode(url_get.content)[0]
        except IndexError as e:
            raise TrackerError("Ошибка про декодирование")

        if b"failure reason" in url_decode:
            raise TrackerError(url_decode[b"failure reason"].decode())

        return parse_peers(url_decode[b"peers"])

    except requests.exceptions.RequestException as e:
        raise TrackerError(f"Ошибка в обработке: {e}")


def parse_peers(peers: bytes) -> list[tuple[str,int]]:
    chunks = [peers[i:i+6] for i in range(0,len(peers),6)]
    list_peer = []
        
    for chunk in chunks:
        if len(chunk) != 6: continue

        ip = socket.inet_ntoa(chunk[:4])
        port = struct.unpack(">H",chunk[4:])[0]
        list_peer.append((ip,port))
        
    return list_peer