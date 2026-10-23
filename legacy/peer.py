import socket, struct
from legacy.constants import *


class PeerError(Exception):
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
    sock.settimeout(5)
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


def build_block_list(piece_length: int) -> list[tuple[int, int]]:
    blocks = []
    begin = 0
    while begin < piece_length:
        block_size = min(16384, piece_length - begin)
        blocks.append((begin, block_size))
        begin += block_size
    return blocks


def download_piece_pipelined(sock: socket.socket, index: int, piece_length: int, pipeline_depth: int = 10) -> bytes:
    blocks = build_block_list(piece_length)
    buffer = bytearray(piece_length)
    next_to_send = 0
    received_count = 0
    for i in range(min(pipeline_depth, len(blocks))):
        begin, block_size = blocks[next_to_send]
        payload = build_request_payload(index, begin, block_size)
        send_message(sock, REQUEST, payload)
        next_to_send += 1
    while received_count < len(blocks):
        msg = recv_message(sock) 
        if msg is None: continue
        elif msg[0] == PIECE:
            recv_index, recv_begin, block_data = parse_piece(msg[1])
            buffer[recv_begin:recv_begin+len(block_data)] = block_data
            received_count += 1
            if next_to_send < len(blocks):
                begin, block_size = blocks[next_to_send]
                payload = build_request_payload(index, begin, block_size)
                send_message(sock, REQUEST, payload)
                next_to_send += 1

    return bytes(buffer)

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