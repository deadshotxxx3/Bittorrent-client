from core.torrent import Torrent
from core.peer_parsing import parse_peers
from core.constants import PROTOCOL_ID, TIMEOUT, CONNECT_RESPONSE_SIZE
from urllib.parse import urlparse
import socket, struct, random

class UdpTrackerError(Exception):
    pass

def build_connect_request(transaction_id: int) -> bytes:
    return struct.pack(">QII",PROTOCOL_ID,0,transaction_id)


def send_connect_request(host: str, port: int, transaction_id: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(TIMEOUT)
        sock.sendto(build_connect_request(transaction_id), (host, port))
        try:
            data, addr = sock.recvfrom(CONNECT_RESPONSE_SIZE)
        except socket.timeout as e:
            raise UdpTrackerError("Трекер не ответил вовремя")
            
        action_recv, transaction_id_recv, connect_id_recv = struct.unpack(">IIQ",data)
        if transaction_id != transaction_id_recv:
            raise UdpTrackerError("Transaction ID не совпадает")
        return connect_id_recv


def build_announce_request(connection_id: int, transaction_id: int, info_hash: bytes, peer_id: bytes, left: int) -> bytes:
    downloaded = uploaded = event = ip = 0
    num_want,port = -1, 6881
    key = random.getrandbits(32)
    return (struct.pack(">QII",connection_id,1,transaction_id) + info_hash + peer_id + 
            struct.pack(">QQQIIIiH",downloaded,left,uploaded,event,ip,key,num_want,port))


def send_announce_request(host: str, port: int, connection_id: int, 
                        transaction_id: int, torrent: Torrent, peer_id: bytes) -> list[tuple[int, int]]:
    info_hash = torrent.info_hash
    length = torrent.length
    announce = build_announce_request(connection_id,transaction_id,info_hash, peer_id, length)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.settimeout(TIMEOUT)
        sock.sendto(announce, (host, port))
        
        try:
            msg = sock.recvfrom(2048)[0]
        except socket.timeout as e:
            raise UdpTrackerError("Трекер не ответил вовремя")

        action, transaction_id_recv, interval, leechers, seeders = struct.unpack(">IIIII",msg[:20])
        if transaction_id != transaction_id_recv:
            raise UdpTrackerError("Transaction ID не совпадает")
        
        return parse_peers(msg[20:])


def get_peers_udp(announce_url: str,torrent: Torrent, peer_id: bytes) -> list[tuple[str, int]]:
    parsed = urlparse(announce_url)
    host, port = parsed.hostname, parsed.port
    transaction_id = random.getrandbits(32)
    connection_id = send_connect_request(host, port, transaction_id)
    transaction_id = random.getrandbits(32)
    return send_announce_request(host,port,connection_id,transaction_id,torrent,peer_id)

