from pathlib import Path

import libtorrent as lt


def make_torrent(source: str, out_file: str, trackers: list, comment: str = "",
                 private: bool = False, progress=None) -> str:
    source_path = Path(source)
    storage = lt.file_storage()
    lt.add_files(storage, str(source_path))
    if storage.num_files() == 0:
        raise ValueError("нет файлов для раздачи")
    creator = lt.create_torrent(storage)
    for index, url in enumerate(trackers):
        creator.add_tracker(url, index)
    if comment:
        creator.set_comment(comment)
    creator.set_creator("BitClient")
    creator.set_priv(private)
    total = max(creator.num_pieces(), 1)
    parent = str(source_path.parent)
    try:
        lt.set_piece_hashes(creator, parent, lambda i: progress(i / total) if progress else None)
    except TypeError:
        lt.set_piece_hashes(creator, parent)
    data = lt.bencode(creator.generate())
    Path(out_file).write_bytes(data)
    return out_file
