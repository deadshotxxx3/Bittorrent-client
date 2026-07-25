import socket, struct
from core.constants import *
from hashlib import sha1
from math import ceil


class PeerError(Exception):
    pass


class PieceHashError(Exception):
    pass


def build_handshake(info_hash: bytes, peer_id: bytes) -> bytes:
    return bytes([PSTRLEN]) + PSTR + bytes(8) + info_hash + peer_id


def recv_exact(sock: socket.socket, size: int) -> bytes:
    answer = b""

    while len(answer) != size:
        p = sock.recv(size - len(answer))
        if len(p) == 0:
            raise PeerError("Соединение с пиром завершено")

        answer += p
    
    return answer


def connect_to_peer(ip: str, port: int, info_hash: bytes, peer_id: bytes) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(60)
    sock.connect((ip,port))
    sock.sendall(build_handshake(info_hash,peer_id))

    message = recv_exact(sock,HANDSHAKE_LENGTH)

    if message[0] == PSTRLEN and message[1 + PSTRLEN + 8:1 + PSTRLEN + 8 + INFO_HASH_LEN] == info_hash:
        return sock
    raise PeerError("Неправильное сообщение от пира")


def recv_message(sock: socket.socket) -> tuple[int, bytes] | None:
    length_prefix = recv_exact(sock,4)
    length = struct.unpack(">I", length_prefix)[0]
    if length == 0: return None
    all_message = recv_exact(sock,length)

    return (all_message[0], all_message[1:])
    

def send_message(sock: socket.socket, message_id: int, payload: bytes = b"") -> None: 
    length = 1 + len(payload)
    message_id_bytes = struct.pack("B",message_id)
    length_prefix = struct.pack(">I",length)
    sock.sendall(length_prefix + message_id_bytes + payload)


def build_request_payload(index: int, begin: int, length: int) -> bytes:
    return struct.pack(">III",index,begin,length)


def parse_piece(payload: bytes) -> tuple[int, int, bytes]:
    index, begin = struct.unpack(">II",payload[:8])
    return (index,begin, payload[8:])


def download_piece(sock: socket, index: int, piece_length: int) -> bytes:
    begin = 0
    buffer = bytearray(piece_length)
    while begin < piece_length:
        block_size = min(16384, piece_length - begin)
        payload = build_request_payload(index,begin,block_size)
        send_message(sock, REQUEST, payload)
        
        while True:
            answer = recv_message(sock)
            if answer is None or answer[0] == HAVE:
                continue
            elif answer[0] == PIECE:
                recv_index, recv_begin, block_data = parse_piece(answer[1])
                if recv_index == index and begin == recv_begin:
                    buffer[begin:begin+len(block_data)] = block_data
                    begin += len(block_data)
                    break
                else: print("Индекс и начало запроса не совпадают с оригиналом")
    return bytes(buffer)