import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

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
    category: str = ""
    tags: tuple = ()
    sequential: bool = False
    tracker: str = ""
    added: int = 0
    ratio: float = 0.0


@dataclass
class FileEntry:
    path: str
    size: int
    progress: float
    priority: int = 4


@dataclass
class PeerEntry:
    address: str
    client: str
    down: int
    up: int
    progress: float


@dataclass
class TrackerEntry:
    url: str
    status: str
    message: str
    tier: int


def handle_key(handle) -> str:
    try:
        return str(handle.info_hashes().get_best())
    except AttributeError:
        return str(handle.info_hash())


class Engine:
    def __init__(self, state_dir: Path, port: int = 6881):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.meta_file = self.state_dir / "meta.json"
        self.meta = self._read_meta()
        self.handles = {}
        self.errors = []
        self.events = []
        self.exempt = set()
        self.ratio_limit = 0.0
        self.seed_minutes = 0
        self.filter_path = None
        self.move_done = ""
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
        self._load_saved()

    def _read_meta(self) -> dict:
        meta = {"categories": {}, "torrents": {}}
        if self.meta_file.exists():
            try:
                data = json.loads(self.meta_file.read_text(encoding="utf-8"))
                meta["categories"] = dict(data.get("categories", {}))
                meta["torrents"] = dict(data.get("torrents", {}))
            except Exception:
                pass
        return meta

    def _write_meta(self) -> None:
        self.meta_file.write_text(
            json.dumps(self.meta, ensure_ascii=False, indent=1), encoding="utf-8")

    @property
    def categories(self) -> dict:
        return dict(self.meta["categories"])

    def set_categories(self, categories: dict) -> None:
        self.meta["categories"] = dict(categories)
        for info in self.meta["torrents"].values():
            if info.get("category") and info["category"] not in categories:
                info["category"] = ""
        self._write_meta()

    def set_limits(self, down_bytes: int, up_bytes: int) -> None:
        self.session.apply_settings({
            "download_rate_limit": int(down_bytes),
            "upload_rate_limit": int(up_bytes),
        })

    def apply_config(self, cfg: dict) -> None:
        port = int(cfg.get("port", 6881))
        interface = str(cfg.get("interface", "")).strip()
        pack = {
            "listen_interfaces": f"{interface}:{port}" if interface else f"0.0.0.0:{port},[::]:{port}",
            "outgoing_interfaces": interface,
            "active_downloads": int(cfg.get("active_downloads", 0)) or -1,
            "active_seeds": int(cfg.get("active_seeds", 0)) or -1,
            "active_limit": 10000,
            "dont_count_slow_torrents": False,
        }
        proxy = str(cfg.get("proxy_type", "none"))
        proxy_codes = {"none": 0, "socks4": 1, "socks5": 2, "http": 4}
        code = proxy_codes.get(proxy, 0)
        has_auth = bool(cfg.get("proxy_user"))
        if has_auth and code == 2:
            code = 3
        elif has_auth and code == 4:
            code = 5
        pack["proxy_type"] = code
        pack["proxy_hostname"] = str(cfg.get("proxy_host", ""))
        pack["proxy_port"] = int(cfg.get("proxy_port", 1080))
        pack["proxy_username"] = str(cfg.get("proxy_user", ""))
        pack["proxy_password"] = str(cfg.get("proxy_pass", ""))
        pack["proxy_peer_connections"] = True
        pack["proxy_tracker_connections"] = True
        pack["proxy_hostnames"] = True
        encryption = str(cfg.get("encryption", "prefer"))
        policy = {"force": 0, "prefer": 1, "off": 2}.get(encryption, 1)
        pack["out_enc_policy"] = policy
        pack["in_enc_policy"] = policy
        pack["allowed_enc_level"] = 2 if encryption == "force" else 3
        try:
            self.session.apply_settings(pack)
        except Exception as e:
            self.errors.append(f"settings: {e}")
        self.ratio_limit = float(cfg.get("ratio_limit", 0) or 0)
        self.seed_minutes = int(cfg.get("seed_minutes", 0) or 0)
        self.move_done = str(cfg.get("move_done", "")).strip()
        path = str(cfg.get("ip_filter", "")).strip()
        if path != self.filter_path:
            self.filter_path = path
            self._load_ip_filter(path)

    def _load_ip_filter(self, path: str) -> None:
        ip_filter = lt.ip_filter()
        if path:
            try:
                text = Path(path).read_text(encoding="utf-8", errors="ignore")
                pattern = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s*-\s*(\d+\.\d+\.\d+\.\d+)")
                for match in pattern.finditer(text):
                    try:
                        ip_filter.add_rule(match.group(1), match.group(2), 1)
                    except Exception:
                        continue
            except Exception as e:
                self.errors.append(f"ip filter: {e}")
        self.session.set_ip_filter(ip_filter)

    def inspect(self, source: str) -> tuple[str, list]:
        info = lt.torrent_info(source)
        storage = info.files()
        files = [(storage.file_path(i), storage.file_size(i)) for i in range(storage.num_files())]
        return info.name(), files

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
                self._register(lt.read_resume_data(file.read_bytes()))
            except Exception as e:
                self.errors.append(f"{file.name}: {e}")

    def add(self, source: str, save_dir: str, category: str = "", priorities=None) -> str:
        target = self.meta["categories"].get(category) or save_dir
        Path(target).mkdir(parents=True, exist_ok=True)
        if source.startswith("magnet:"):
            params = lt.parse_magnet_uri(source)
        else:
            params = lt.add_torrent_params()
            params.ti = lt.torrent_info(source)
            if priorities:
                params.file_priorities = list(priorities)
        params.save_path = str(target)
        key = self._register(params)
        entry = self.meta["torrents"].setdefault(key, {"category": "", "tags": []})
        if category in self.meta["categories"]:
            entry["category"] = category
        self._write_meta()
        self._save_one(key)
        return key

    def set_category(self, key: str, category: str) -> None:
        entry = self.meta["torrents"].setdefault(key, {"category": "", "tags": []})
        entry["category"] = category if category in self.meta["categories"] else ""
        self._write_meta()
        path = self.meta["categories"].get(category)
        handle = self.handles.get(key)
        if path and handle is not None and handle.is_valid():
            Path(path).mkdir(parents=True, exist_ok=True)
            handle.move_storage(str(path))

    def set_tags(self, key: str, tags: list[str]) -> None:
        entry = self.meta["torrents"].setdefault(key, {"category": "", "tags": []})
        entry["tags"] = [t for t in (x.strip() for x in tags) if t]
        self._write_meta()

    def set_sequential(self, key: str, enabled: bool) -> None:
        handle = self.handles.get(key)
        if handle is None:
            return
        if enabled:
            handle.set_flags(lt.torrent_flags.sequential_download)
        else:
            handle.unset_flags(lt.torrent_flags.sequential_download)

    def set_file_priorities(self, key: str, priorities: list) -> None:
        handle = self.handles.get(key)
        if handle is not None and handle.is_valid():
            handle.prioritize_files(list(priorities))
            self._save_one(key)

    def set_torrent_limits(self, key: str, down_bytes: int, up_bytes: int) -> None:
        handle = self.handles.get(key)
        if handle is not None and handle.is_valid():
            handle.set_download_limit(int(down_bytes))
            handle.set_upload_limit(int(up_bytes))
            self._save_one(key)

    def torrent_limits(self, key: str) -> tuple:
        handle = self.handles.get(key)
        if handle is None or not handle.is_valid():
            return 0, 0
        return max(handle.download_limit(), 0), max(handle.upload_limit(), 0)

    def recheck(self, key: str) -> None:
        handle = self.handles.get(key)
        if handle is not None and handle.is_valid():
            handle.force_recheck()

    def reannounce(self, key: str) -> None:
        handle = self.handles.get(key)
        if handle is not None and handle.is_valid():
            try:
                handle.force_reannounce()
            except Exception:
                pass

    def queue_move(self, key: str, where: str) -> None:
        handle = self.handles.get(key)
        if handle is None or not handle.is_valid():
            return
        action = {
            "top": handle.queue_position_top,
            "up": handle.queue_position_up,
            "down": handle.queue_position_down,
            "bottom": handle.queue_position_bottom,
        }.get(where)
        if action:
            action()

    def pause_all(self) -> None:
        for key in list(self.handles):
            self.pause(key)

    def resume_all(self) -> None:
        for key in list(self.handles):
            self.resume(key)

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
            self.exempt.add(key)
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
        self.meta["torrents"].pop(key, None)
        self._write_meta()

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
        try:
            priorities = handle.get_file_priorities()
        except Exception:
            priorities = []
        result = []
        for i in range(storage.num_files()):
            size = storage.file_size(i)
            done = progress[i] if i < len(progress) else 0
            priority = priorities[i] if i < len(priorities) else 4
            result.append(FileEntry(storage.file_path(i), size, done / size if size else 1.0, priority))
        return result

    def peers(self, key: str, limit: int = 200) -> list[PeerEntry]:
        handle = self.handles.get(key)
        if handle is None:
            return []
        try:
            infos = handle.get_peer_info()
        except Exception:
            return []
        result = []
        for p in infos:
            try:
                ip, port = p.ip
                client = p.client.decode(errors="replace") if isinstance(p.client, bytes) \
                    else str(p.client)
                result.append(PeerEntry(f"{ip}:{port}", client, p.down_speed, p.up_speed, p.progress))
            except Exception:
                continue
        result.sort(key=lambda x: x.down + x.up, reverse=True)
        return result[:limit]

    def trackers(self, key: str) -> list[TrackerEntry]:
        handle = self.handles.get(key)
        if handle is None:
            return []
        result = []
        try:
            trackers = handle.trackers()
        except Exception:
            return []
        for t in trackers:
            message = ""
            fails = 0
            updating = False
            started = False
            for endpoint in t.get("endpoints", []):
                for ih in (endpoint.get("info_hashes") or [endpoint]):
                    if not isinstance(ih, dict):
                        continue
                    message = str(ih.get("message") or message)
                    fails = max(fails, int(ih.get("fails", 0) or 0))
                    updating = updating or bool(ih.get("updating", False))
                    started = started or bool(ih.get("start_sent", False))
            if fails > 0:
                status = "Ошибка"
            elif updating:
                status = "Обновление"
            elif message or started:
                status = "Работает"
            else:
                status = "Ожидание"
            result.append(TrackerEntry(t.get("url", ""), status, message, int(t.get("tier", 0))))
        return result

    def _store_resume(self, alert) -> None:
        try:
            key = str(alert.handle.info_hashes().get_best())
        except AttributeError:
            key = str(alert.handle.info_hash())
        data = lt.write_resume_data_buf(alert.params)
        (self.state_dir / f"{key}.resume").write_bytes(data)

    def _process_alerts(self) -> None:
        for alert in self.session.pop_alerts():
            if isinstance(alert, lt.save_resume_data_alert):
                self._store_resume(alert)
            elif isinstance(alert, lt.torrent_finished_alert):
                try:
                    handle = alert.handle
                    key = handle_key(handle)
                    self.events.append(("finished", handle.status().name, key))
                    entry = self.meta["torrents"].get(key, {})
                    if self.move_done and not entry.get("category"):
                        Path(self.move_done).mkdir(parents=True, exist_ok=True)
                        handle.move_storage(self.move_done)
                except Exception as e:
                    self.errors.append(f"finish: {e}")
            elif isinstance(alert, (lt.torrent_error_alert, lt.file_error_alert)):
                self.errors.append(alert.message())

    def snapshot(self) -> list[TorrentInfo]:
        self._process_alerts()
        result = []
        for key, handle in list(self.handles.items()):
            if not handle.is_valid():
                continue
            s = handle.status()
            flags = handle.flags()
            paused_flag = bool(flags & lt.torrent_flags.paused)
            managed = bool(flags & lt.torrent_flags.auto_managed)
            paused = paused_flag and not managed
            queued = paused_flag and managed
            remaining = max(s.total_wanted - s.total_wanted_done, 0)
            eta = int(remaining / s.download_rate) if s.download_rate > 0 else -1
            if paused:
                state = "paused"
            elif s.errc.value() != 0:
                state = "error"
            elif queued:
                state = "queued"
            else:
                state = STATE_LABELS.get(s.state, "downloading")
            downloaded = max(s.all_time_download, s.total_done)
            ratio = s.all_time_upload / downloaded if downloaded else 0.0
            if state in ("seeding", "completed") and key not in self.exempt \
                    and (self.ratio_limit > 0 or self.seed_minutes > 0):
                seconds = getattr(s, "seeding_duration", None)
                if seconds is None:
                    seconds = getattr(s, "seeding_time", 0)
                if (self.ratio_limit > 0 and ratio >= self.ratio_limit) or \
                        (self.seed_minutes > 0 and seconds >= self.seed_minutes * 60):
                    self.pause(key)
                    self.events.append(("stopped", s.name, key))
                    state = "paused"
                    paused = True
            meta = self.meta["torrents"].get(key, {})
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
                category=meta.get("category", ""),
                tags=tuple(meta.get("tags", [])),
                sequential=bool(flags & lt.torrent_flags.sequential_download),
                tracker=(urlparse(getattr(s, "current_tracker", "") or "").hostname or ""),
                added=int(getattr(s, "added_time", 0) or 0),
                ratio=ratio,
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
                    self._store_resume(alert)
                    saved += 1
                elif isinstance(alert, lt.save_resume_data_failed_alert):
                    saved += 1
            time.sleep(0.1)
        self.session.pause()
