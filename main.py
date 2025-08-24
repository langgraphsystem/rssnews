import argparse

from sheets_client import SheetClient
from discovery import ensure_feed
from poller import poll_active_feeds
from worker import process_pending

def main():
    ap = argparse.ArgumentParser("NewsPipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ensure", help="Создать/проверить таблицу и вкладки")

    p_dis = sub.add_parser("discovery", help="Добавить RSS (EN и свежее 7 дней)")
    p_dis.add_argument("--feed", action="append", help="RSS URL. Можно указать несколько.", default=[])

    sub.add_parser("poll", help="Опрос активных RSS и запись новых pending строк")
    p_work = sub.add_parser("work", help="Обработка pending строк (парсинг статей)")
    p_work.add_argument("--worker-id", default="worker-1")

    args = ap.parse_args()
    client = SheetClient()
    client.ensure_worksheets()

    if args.cmd == "ensure":
        print("OK: worksheets ensured"); return

    if args.cmd == "discovery":
        if not args.feed:
            print("Укажи хотя бы один --feed <rss_url>")
            return
        for f in args.feed:
            ensure_feed(client, f)
        print("OK: discovery finished")
        return

    if args.cmd == "poll":
        poll_active_feeds(client)
        print("OK: poll finished")
        return

    if args.cmd == "work":
        process_pending(client, worker_id=args.worker_id)
        print("OK: work finished")
        return

if __name__ == "__main__":
    main()
