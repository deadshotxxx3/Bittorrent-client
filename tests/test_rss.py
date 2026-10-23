import unittest

from core.rss import parse_feed

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Show S01E01 1080p</title><guid>g1</guid>
<enclosure url="http://example.com/a.torrent" type="application/x-bittorrent"/></item>
<item><title>Show S01E02 720p</title><guid>g2</guid>
<link>magnet:?xt=urn:btih:abcdef</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom item</title><id>a1</id>
<link href="http://example.com/b.torrent"/></entry>
</feed>"""


class ParseFeedTests(unittest.TestCase):
    def test_rss(self):
        entries = parse_feed(RSS)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["title"], "Show S01E01 1080p")
        self.assertEqual(entries[0]["guid"], "g1")
        self.assertTrue(entries[1]["source"].startswith("magnet:"))

    def test_atom(self):
        entries = parse_feed(ATOM)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["guid"], "a1")
        self.assertTrue(entries[0]["source"].endswith("b.torrent"))


if __name__ == "__main__":
    unittest.main()
