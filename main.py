import argparse

from core.lt_downloader import download


def main() -> None:
    p = argparse.ArgumentParser(description="Торрент-клиент на libtorrent")
    p.add_argument("sources", nargs="+",
                   help=".torrent файлы, папки с ними или magnet-ссылки")
    p.add_argument("-o", "--output", required=True, help="папка для загрузки")
    p.add_argument("--port", type=int, default=6881)
    p.add_argument("--down-limit", type=float, default=0, help="МБ/с, 0 = без лимита")
    p.add_argument("--up-limit", type=float, default=0, help="МБ/с, 0 = без лимита")
    p.add_argument("--seed", action="store_true", help="раздавать после скачивания")
    args = p.parse_args()

    download(args.sources, args.output, args.port,
             int(args.down_limit * 1024 * 1024), int(args.up_limit * 1024 * 1024),
             seed_after=args.seed)

if __name__ == "__main__":
    main()
