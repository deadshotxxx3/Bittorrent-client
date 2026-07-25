from core.peer import download_piece 
from core.torrent import Torrent
from hashlib import sha1
from math import ceil
import socket, os
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
            

def download_torrent(sock: socket, torrent: Torrent, output_dir: str) -> None:
    cnt_piece = ceil(torrent.length / torrent.piece_length)
    list_files = prepare_files(torrent,output_dir)
    for index in range(cnt_piece):
        print(f"Скачиваю piece {index}")
        piece_length = torrent.piece_length if index != cnt_piece - 1 else torrent.length - torrent.piece_length * (cnt_piece - 1)
        check_download = False
        for attempt in range(5):
            buffer = download_piece(sock, index, piece_length)
            if torrent.pieces[index*20:(index + 1) * 20] == sha1(buffer).digest():
                write_piece_to_files(buffer, index * torrent.piece_length, list_files) 
                check_download = True
                break
        if not check_download:
            raise PieceHashError("Не удалось скачать кусок")