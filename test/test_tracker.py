import struct
import socket
from core.tracker import parse_peers

def test_parse_peers_empty():
    assert parse_peers(b"") == []

def test_parse_peers_single():
    ip = "192.168.1.1"
    port = 6881
    peer_bytes = socket.inet_aton(ip) + struct.pack(">H", port)
    
    result = parse_peers(peer_bytes)
    
    assert result == [(ip, port)]

def test_parse_peers_multiple():
    peers_data = [("10.0.0.1", 6881), ("10.0.0.2", 51413)]
    peer_bytes = b"".join(
        socket.inet_aton(ip) + struct.pack(">H", port)
        for ip, port in peers_data
    )
    
    result = parse_peers(peer_bytes)
    
    assert result == peers_data

def test_parse_peers_incomplete_chunk():
    good_peer = socket.inet_aton("10.0.0.1") + struct.pack(">H", 6881)
    garbage = b"\x01\x02\x03"
    peer_bytes = good_peer + garbage
    result = parse_peers(peer_bytes)    

    assert result == [("10.0.0.1", 6881)]