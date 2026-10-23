from core.peer import download_piece, PeerError, connect_to_peer, recv_message, send_message, download_piece_pipelined
from core.torrent import Torrent
from core.constants import UNCHOKE, INTERESTED
from hashlib import sha1
from math import ceil
import socket, os, queue, threading, time
from pathlib import Path

class PieceHashError(Exception):
    pass


def prepare_files(torrent: Torrent, output_dir: str) -> list[tuple[int, int, str]]:
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    list_files = []
    offset = 0

    for file_info in torrent.files:
        full_path = Path(output_dir).joinpath(*file_info.path)
        full_path.parent.mkdir(parents=True,exist_ok=True)
        if not (os.path.exists(full_path) and os.path.getsize(full_path) == file_info.length):
            with open(full_path,"wb") as file:
                file.truncate(file_info.length)
        list_files.append((offset,file_info.length,full_path))
        offset += file_info.length
    
    return list_files


def write_piece_to_files(piece_data: bytes, piece_offset: int, list_files: list[tuple[int, int, str]]) -> None:
    for files in list_files:
        file_offset, file_length, full_path = files
        if piece_offset < file_offset + file_length and piece_offset + len(piece_data) > file_offset:
            overlap_start = max(piece_offset, file_offset)
            overlap_end = min(piece_offset + len(piece_data), file_offset + file_length)
            piece_start = overlap_start - piece_offset
            piece_end = overlap_end - piece_offset
            file_write_offset = overlap_start - file_offset
            
            with open(full_path,"r+b") as file:
                file.seek(file_write_offset)
                file.write(piece_data[piece_start:piece_end])


def read_piece_from_files(piece_length: int,piece_offset: int, list_files: list[tuple[int, int, str]]) -> bytes:
    buffer = bytearray(piece_length)
    for files in list_files:
        file_offset, file_length, full_path = files
        if piece_offset < file_offset + file_length and piece_offset + piece_length > file_offset:
            overlap_start = max(piece_offset, file_offset)
            overlap_end = min(piece_offset + piece_length, file_offset + file_length)
            piece_start = overlap_start - piece_offset
            piece_end = overlap_end - piece_offset
            file_read_offset = overlap_start - file_offset
            
            with open(full_path,"rb") as file:
                file.seek(file_read_offset)
                buffer[piece_start:piece_end] = file.read(piece_end - piece_start)
    return bytes(buffer)
            

def download_torrent(sock: socket, torrent: Torrent, output_dir: str) -> None:
    cnt_piece = ceil(torrent.length / torrent.piece_length)
    list_files = prepare_files(torrent,output_dir)
    for index in range(cnt_piece):
        print(f"Скачиваю piece {index}")
        piece_length = torrent.piece_length if index != cnt_piece - 1 else torrent.length - torrent.piece_length * (cnt_piece - 1)

        existing_data = read_piece_from_files(piece_length, index * torrent.piece_length, list_files)
        if torrent.pieces[index] == sha1(existing_data).digest():
            print(f"Piece {index} уже скачан, пропускаем")
            continue

        check_download = False
        for attempt in range(5):
            buffer = download_piece(sock, index, piece_length)
            actual_hash = sha1(buffer).digest()
            expected_hash = torrent.pieces[index]
            if torrent.pieces[index] == sha1(buffer).digest():
                write_piece_to_files(buffer, index * torrent.piece_length, list_files) 
                check_download = True
                break
        if not check_download:
            raise PieceHashError("Не удалось скачать кусок")

def download_worker(peer: tuple[str, int], torrent: Torrent, peer_id: bytes, 
                     piece_queue: queue.Queue, list_files: list[tuple[int, int, str]], 
                     file_lock: threading.Lock, completed_pieces: list[int], cnt_piece: int,
                     total_bytes_downloaded: list[int], start_time: float) -> None:
    try:
        sock = connect_to_peer(peer[0],peer[1],torrent.info_hash,peer_id)
    except (PeerError, OSError) as e:
        print(f"Ошибка: {e}")
        return
    
    send_message(sock,INTERESTED)
    choked = False
    while True:
        try:
            msg = recv_message(sock)
            print(msg)
            if msg is None:
                continue
            if msg[0] == UNCHOKE:
                print("Пир готов передавать данные")
                while True:
                    try:
                        index = piece_queue.get(block=False)
                    except queue.Empty: break
                    piece_length = torrent.piece_length if index != cnt_piece - 1 else torrent.length - torrent.piece_length * (cnt_piece - 1)
                    check_download = False
                    for attempt in range(2):
                        try:
                            buffer = download_piece_pipelined(sock, index, piece_length)
                        except PeerError as e:
                            print(f"Ошибка пира: {e}")
                            piece_queue.put(index)
                            return
                        actual_hash = sha1(buffer).digest()
                        expected_hash = torrent.pieces[index]
                        if torrent.pieces[index] == sha1(buffer).digest():
                            with file_lock:
                                write_piece_to_files(buffer, index * torrent.piece_length, list_files)
                                completed_pieces[0] += 1
                                percent = completed_pieces[0] / cnt_piece * 100
                                print(f"Прогресс: {percent:.1f}% ({completed_pieces[0]}/{cnt_piece})")
                                total_bytes_downloaded[0] += len(buffer)
                                elapsed = time.time() - start_time
                                speed_bytes_per_sec = total_bytes_downloaded[0] / elapsed if elapsed > 0 else 0
                                speed_mb_per_sec = speed_bytes_per_sec / (1024 * 1024)
                                print(f"Скорость скачивания в мб: {speed_mb_per_sec}",)
                            check_download = True
                            break
                    if not check_download:
                        piece_queue.put(index)
                        return
        except PeerError as e:
            print("Ошибка соединения с пиром")
            return
        except socket.timeout:
            print("Превышено время ожидания пира")
            return 


def download_torrent_parallel(peers: list[tuple[str, int]], torrent: Torrent, 
                                peer_id: bytes, output_dir: str, num_threads: int = 30) -> None:
    cnt_piece = ceil(torrent.length / torrent.piece_length)
    piece_queue = queue.Queue()
    list_files = prepare_files(torrent, output_dir)
    for index in range(cnt_piece):
        piece_length = torrent.piece_length if index != cnt_piece - 1 else torrent.length - torrent.piece_length * (cnt_piece - 1)
        existing_data = read_piece_from_files(piece_length, index * torrent.piece_length, list_files)
        if torrent.pieces[index] == sha1(existing_data).digest(): continue
        piece_queue.put(index)
    start_time = time.time()
    total_bytes = [0]   
    completed_pieces = [0]
    file_lock = threading.Lock()
    threads = []
    for peer in peers[:num_threads + 15 ]:
        T = threading.Thread(target=download_worker, args=(peer, torrent, peer_id, piece_queue, list_files, file_lock,completed_pieces,cnt_piece,
                            total_bytes,start_time))
        threads.append(T)
        T.start()
    for T in threads:
        T.join()


