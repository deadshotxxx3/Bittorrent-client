import socket, struct

def parse_peers(peers: bytes) -> list[tuple[str,int]]:
    chunks = [peers[i:i+6] for i in range(0,len(peers),6)]
    list_peer = []
        
    for chunk in chunks:
        if len(chunk) != 6: continue

        ip = socket.inet_ntoa(chunk[:4])
        port = struct.unpack(">H",chunk[4:])[0]
        list_peer.append((ip,port))
        
    return list_peer