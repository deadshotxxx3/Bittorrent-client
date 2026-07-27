from core.bencode import decode 
from core.torrent import load_torrent, Torrent
from core.peer_parsing import parse_peers
from core.constants import TIMEOUT
from urllib.parse import quote 
import requests, os, socket, struct


class TrackerError(Exception):
    pass

def get_peers_http(announce_url: str,torrent: Torrent, peer_id: bytes) -> list[tuple[str,int]]:
    try:
        hash_info_encoded = quote(torrent.info_hash,safe="")
        peer_id_encoded = quote(peer_id,safe="")
        url = f"{announce_url}?info_hash={hash_info_encoded}&peer_id={peer_id_encoded}&port=6881&uploaded=0&downloaded=0&left={torrent.length}&compact=1"
        url_get = requests.get(url,timeout=TIMEOUT)
        try:
            url_decode = decode(url_get.content)[0]
        except IndexError as e:
            raise TrackerError("Ошибка про декодирование")

        if b"failure reason" in url_decode:
            raise TrackerError(url_decode[b"failure reason"].decode())

        return parse_peers(url_decode[b"peers"])

    except requests.exceptions.RequestException as e:
        raise TrackerError(f"Ошибка в обработке: {e}")

