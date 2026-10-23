from core.torrent import load_torrent, Torrent
from core.tracker_client import get_peers
from core.peer import connect_to_peer, recv_message, PeerError,send_message
from core.constants import UNCHOKE, INTERESTED, CHOKE
from core.downloader import *
import os, socket
from urllib.parse import urlparse

with open("t.torrent","rb") as file:
    data = file.read()
torrent = load_torrent(data)
peer_id = os.urandom(20)
peers = get_peers(torrent, peer_id)
print(len(peers), peers)
download_torrent_parallel(peers, torrent, peer_id, "/home/deadshot/Leetcode")
print("Скачивание завершено!")