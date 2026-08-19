from bot import URL_REGEX

def test_url_regex_extraction():
    sample_text = """
    Xem video này hay quá: https://www.tiktok.com/@kienthuckinhte28/video/7675666420574735634
    Còn video này nữa:
    https://www.facebook.com/reel/1410384157640503
    Và link fb watch: https://fb.watch/abcd1234ef/
    """
    matches = URL_REGEX.findall(sample_text)
    assert len(matches) == 3
    assert "https://www.tiktok.com/@kienthuckinhte28/video/7675666420574735634" in matches
    assert "https://www.facebook.com/reel/1410384157640503" in matches
