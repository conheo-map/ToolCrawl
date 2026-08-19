import json
from pathlib import Path
from storage.metadata_writer import MetadataWriter

def test_metadata_and_summary_writer(tmp_path: Path):
    meta_file = tmp_path / "metadata.json"
    summary_file = tmp_path / "summary.json"

    writer = MetadataWriter(metadata_file=meta_file, summary_file=summary_file)

    record1 = {
        "item_id": "tt_7412345678901234567",
        "platform": "tiktok",
        "platform_video_id": "7412345678901234567",
        "video_url": "https://www.tiktok.com/@user/video/7412345678901234567",
        "title": "Review quán ăn Hà Nội",
        "description": "Test caption",
        "posted_at": "2026-08-10T13:22:05+07:00",
        "language_raw": "vi",
        "audio_path": "audio/tt_7412345678901234567.wav",
        "duration_seconds": 120.0,
        "crawl_batch": "tt_20260819_01",
        "crawled_at": "2026-08-19T09:14:00+07:00",
        "platform_meta": {
            "music_is_original": True,
            "is_duet": False,
            "is_stitch": False,
            "has_platform_captions": True
        }
    }

    writer.add_record(record1)
    assert meta_file.exists()

    data = json.loads(meta_file.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["item_id"] == "tt_7412345678901234567"

    # Write summary
    writer.write_summary(platform="tiktok", batch_count=1)
    assert summary_file.exists()

    summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
    assert summary_data["platform"] == "tiktok"
    assert summary_data["items_delivered"] == 1
    assert summary_data["unique_item_ids"] == 1
    assert summary_data["total_hours"] == round(120.0 / 3600, 2)
    assert summary_data["audio_spec"]["sample_rate"] == 16000
    assert summary_data["audio_spec"]["channels"] == 1
