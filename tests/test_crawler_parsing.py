from crawlers.tiktok import TikTokCrawler
from crawlers.facebook import FacebookCrawler

def test_tiktok_id_extraction():
    crawler = TikTokCrawler()
    url = "https://www.tiktok.com/@username.123/video/7412345678901234567"
    item_id = crawler._extract_item_id(url)
    assert item_id == "tt_7412345678901234567"

    # Photo post must be skipped (return None)
    photo_url = "https://www.tiktok.com/@username.123/photo/7412345678901234567"
    assert crawler._extract_item_id(photo_url) is None
    assert crawler.crawl_url(photo_url) is None

def test_facebook_id_extraction():
    crawler = FacebookCrawler()
    reel_url = "https://www.facebook.com/reel/123456789012345"
    item_id, kind = crawler._extract_item_id(reel_url)
    assert item_id == "fb_123456789012345"
    assert kind == "reel"

    video_url = "https://www.facebook.com/watch/?v=987654321098765"
    item_id_v, kind_v = crawler._extract_item_id(video_url)
    assert item_id_v == "fb_987654321098765"
