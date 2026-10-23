import time
from dataclasses import dataclass
from pathlib import Path

import libtorrent as lt

EXTRA_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://tracker.dler.org:6969/announce",
]

STATE_LABELS = {
    lt.torrent_status.checking_files: "checking",
    lt.torrent_status.downloading_metadata: "metadata",
    lt.torrent_status.downloading: "downloading",
    lt.torrent_status.finished: "completed",
    lt.torrent_status.seeding: "seeding",
    lt.torrent_status.checking_resume_data: "checking",
}


@dataclass
class TorrentInfo:
    key: str
    name: str
    size: int
    done: int
    progress: float
    down_rate: int
    up_rate: int
    peers: int
    seeds: int
    eta: int
    state: str
    paused: bool
    error: str
    save_path: str
    total_down: int
    total_up: int
    has_metadata: bool


@dataclass
class FileEntry:
    path: str
    size: int
    progress: float


def handle_key(handle) -> str:
    try:
        return str(handle.info_hashes().get_best())
    except AttributeError:
        return str(handle.info_hash())


class Engine:
    def __init__(self, state_dir: Path, port: int = 6881):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.handles = {}
        self.session = lt.session({
            "listen_interfaces": f"0.0.0.0:{port},[::]:{port}",
            "enable_dht": True,
            "enable_lsd": True,
            "enable_upnp": True,
            "enable_natpmp": True,
            "dht_bootstrap_nodes": (
                "router.bittorrent.com:6881,router.utorrent.com:6881,"
                "dht.transmissionbt.com:6881,dht.libtorrent.org:25401"
            ),
            "connections_limit": 500,
            "alert_mask": lt.alert.category_t.error_notification
            | lt.alert.category_t.status_notification,
        })
        self.errors = []
        self._load_saved()

    def set_limits(self, down_bytes: int, up_bytes: int) -> None:
        self.session.apply_settings({
            "download_rate_limit": int(down_bytes),
            "upload_rate_limit": int(up_bytes),
        })

    def _register(self, params) -> str:
        handle = self.session.add_torrent(params)
        key = handle_key(handle)
        self.handles[key] = handle
        for url in EXTRA_TRACKERS:
            try:
                handle.add_tracker({"url": url, "tier": 10})
            except Exception:
                pass
        return key

    def _load_saved(self) -> None:
        for file in sorted(self.state_dir.glob("*.resume")):
            try:
                params = lt.read_resume_data(file.read_bytes())
                self._register(params)
            except Exception as e:
                self.errors.append(f"{file.name}: {e}")

    def add(self, source: str, save_dir: str) -> str:
        Path(save_dir).mkdir(parents=True, exist_ok=True)
        if source.startswith("magnet:"):
            params = lt.parse_magnet_uri(source)
        else:
            params = lt.add_torrent_params()
            params.ti = lt.torrent_info(source)
        params.save_path = str(save_dir)
        key = self._register(params)
        self._save_one(key)
        return key

    def _save_one(self, key: str) -> None:
        handle = self.handles.get(key)
        if handle is not None and handle.is_valid():
            handle.save_resume_data(lt.torrent_handle.save_info_dict)

    def pause(self, key: str) -> None:
        handle = self.handles.get(key)
        if handle:
            handle.unset_flags(lt.torrent_flags.auto_managed)
            handle.pause()

    def resume(self, key: str) -> None:
        handle = self.handles.get(key)
        if handle:
            handle.set_flags(lt.torrent_flags.auto_managed)
            handle.resume()

    def remove(self, key: str, delete_files: bool = False) -> None:
        handle = self.handles.pop(key, None)
        if handle is None:
            return
        if delete_files:
            self.session.remove_torrent(handle, lt.session.delete_files)
        else:
            self.session.remove_torrent(handle)
        resume_file = self.state_dir / f"{key}.resume"
        if resume_file.exists():
            resume_file.unlink()

    def magnet(self, key: str) -> str:
        handle = self.handles.get(key)
        return lt.make_magnet_uri(handle) if handle else ""

    def files(self, key: str) -> list[FileEntry]:
        handle = self.handles.get(key)
        if handle is None:
            return []
        info = handle.torrent_file()
        if info is None:
            return []
        storage = info.files()
        progress = handle.file_progress()
        result = []
        for i in range(storage.num_files()):
            size = storage.file_size(i)
            done = progress[i] if i < len(progress) else 0
            result.append(FileEntry(storage.file_path(i), size, done / size if size else 1.0))
        return result

    def _process_alerts(self) -> None:
        for alert in self.session.pop_alerts():
            if isinstance(alert, lt.save_resume_data_alert):
                try:
                    key = str(alert.handle.info_hashes().get_best())
                except AttributeError:
                    key = str(alert.handle.info_hash())
                data = lt.write_resume_data_buf(alert.params)
                (self.state_dir / f"{key}.resume").write_bytes(data)
            elif isinstance(alert, (lt.torrent_error_alert, lt.file_error_alert)):
                self.errors.append(alert.message())

    def snapshot(self) -> list[TorrentInfo]:
        self._process_alerts()
        result = []
        for key, handle in list(self.handles.items()):
            if not handle.is_valid():
                continue
            s = handle.status()
            paused = bool(handle.flags() & lt.torrent_flags.paused)
            remaining = max(s.total_wanted - s.total_wanted_done, 0)
            eta = int(remaining / s.download_rate) if s.download_rate > 0 else -1
            if paused:
                state = "paused"
            elif s.errc.value() != 0:
                state = "error"
            else:
                state = STATE_LABELS.get(s.state, "downloading")
            result.append(TorrentInfo(
                key=key,
                name=s.name or "Fetching metadata…",
                size=s.total_wanted,
                done=s.total_wanted_done,
                progress=s.progress,
                down_rate=s.download_payload_rate,
                up_rate=s.upload_payload_rate,
                peers=s.num_peers,
                seeds=s.num_seeds,
                eta=eta,
                state=state,
                paused=paused,
                error=s.errc.message() if s.errc.value() != 0 else "",
                save_path=s.save_path,
                total_down=s.total_payload_download,
                total_up=s.total_payload_upload,
                has_metadata=s.has_metadata,
            ))
        return result

    def autosave(self) -> None:
        for key in list(self.handles):
            self._save_one(key)

    def shutdown(self) -> None:
        self.autosave()
        deadline = time.time() + 5
        pending = len(self.handles)
        saved = 0
        while saved < pending and time.time() < deadline:
            for alert in self.session.pop_alerts():
                if isinstance(alert, lt.save_resume_data_alert):
                    try:
                        key = str(alert.handle.info_hashes().get_best())
                    except AttributeError:
                        key = str(alert.handle.info_hash())
                    data = lt.write_resume_data_buf(alert.params)
                    (self.state_dir / f"{key}.resume").write_bytes(data)
                    saved += 1
                elif isinstance(alert, lt.save_resume_data_failed_alert):
                    saved += 1
            time.sleep(0.1)
        self.session.pause()
