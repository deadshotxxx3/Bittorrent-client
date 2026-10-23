import os
import time
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

STATE_NAMES = {
    lt.torrent_status.checking_files: "проверка файлов",
    lt.torrent_status.downloading_metadata: "загрузка метаданных",
    lt.torrent_status.downloading: "скачивание",
    lt.torrent_status.finished: "завершён",
    lt.torrent_status.seeding: "раздача",
    lt.torrent_status.checking_resume_data: "проверка resume",
}

def create_session(listen_port: int = 6881, download_limit: int = 0,
                   upload_limit: int = 0) -> "lt.session":

    settings = {
        "listen_interfaces": f"0.0.0.0:{listen_port},[::]:{listen_port}",
        "enable_dht": True,
        "enable_lsd": True,
        "enable_upnp": True,
        "enable_natpmp": True,
        "dht_bootstrap_nodes": (
            "router.bittorrent.com:6881,router.utorrent.com:6881,"
            "dht.transmissionbt.com:6881,dht.libtorrent.org:25401"
        ),
        "connections_limit": 500,
        "download_rate_limit": download_limit,
        "upload_rate_limit": upload_limit,
        "alert_mask": lt.alert.category_t.error_notification
        | lt.alert.category_t.status_notification,
    }
    return lt.session(settings)

def add_source(ses: "lt.session", source: str, save_dir: str) -> "lt.torrent_handle":

    Path(save_dir).mkdir(parents=True, exist_ok=True)
    if source.startswith("magnet:"):
        params = lt.parse_magnet_uri(source)
    else:
        params = lt.add_torrent_params()
        params.ti = lt.torrent_info(source)
    params.save_path = save_dir
    handle = ses.add_torrent(params)
    for url in EXTRA_TRACKERS:
        try:
            handle.add_tracker({"url": url, "tier": 10})
        except Exception:
            pass
    return handle

def collect_sources(inputs: list[str]) -> list[str]:

    result = []
    for item in inputs:
        if item.startswith("magnet:"):
            result.append(item)
        elif os.path.isdir(item):
            result.extend(str(p) for p in sorted(Path(item).rglob("*.torrent")))
        elif os.path.isfile(item):
            result.append(item)
        else:
            print(f"Пропускаю (не найдено): {item}")
    return result

def _line(handle: "lt.torrent_handle") -> str:
    s = handle.status()
    name = (s.name or "получение метаданных...")[:40]
    state = STATE_NAMES.get(s.state, str(s.state))
    return (f"{name:<40} {s.progress * 100:5.1f}%  "
            f"↓{s.download_rate / 1024 / 1024:5.2f} МБ/с  "
            f"пиры:{s.num_peers:<4} {state}")

def download(inputs: list[str], save_dir: str, listen_port: int = 6881,
             download_limit: int = 0, upload_limit: int = 0,
             seed_after: bool = False, max_active: int = 0) -> None:
    sources = collect_sources(inputs)
    if not sources:
        print("Нечего качать.")
        return

    ses = create_session(listen_port, download_limit, upload_limit)
    handles = []
    for src in sources:
        try:
            handles.append(add_source(ses, src, save_dir))
        except Exception as e:
            print(f"Не удалось добавить {src[:60]}: {e}")

    if max_active:
        ses.apply_settings({"active_downloads": max_active, "active_limit": max_active * 2})

    try:
        while handles:
            for alert in ses.pop_alerts():
                if isinstance(alert, lt.torrent_error_alert) or \
                        isinstance(alert, lt.file_error_alert):
                    print(f"[ошибка] {alert.message()}")

            print("\033[2J\033[H" if os.name != "nt" else "", end="")
            for h in list(handles):
                print(_line(h))
                s = h.status()
                done = s.is_finished or s.state in (lt.torrent_status.finished,
                                                    lt.torrent_status.seeding)
                if done and not seed_after:
                    handles.remove(h)
                    ses.remove_torrent(h)
                    print(f"  ✔ готово: {s.name}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nОстановлено. При следующем запуске докачка продолжится с места остановки.")
    finally:

        ses.pause()
    print("Всё скачано." if not handles else "Скачивание не завершено.")
