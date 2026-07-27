from core.torrent import Torrent
from core.tracker_http import get_peers_http, TrackerError
from core.tracker_udp import get_peers_udp
from urllib.parse import urlparse

def get_peers(torrent: Torrent, peer_id: bytes) -> list[tuple[str,int]]:
    list_peers = []
    list_announce = []
    if torrent.announce_list:
        list_announce = torrent.announce_list
    else: list_announce = [[torrent.announce]]

    for tier in list_announce:
        for url in tier:
            try:
                url = url.decode()
                scheme = urlparse(url).scheme
                peers = get_peers_http(url,torrent, peer_id) if scheme != "udp" else get_peers_udp(url,torrent,peer_id)
                if peers: list_peers += peers
            except Exception as e:
                print(f"Трекер {url} не ответил: {e}")
                continue

    if len(list_peers) != 0:
        return list_peers
    raise TrackerError("Не найдено ни одного пира")