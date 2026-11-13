import io
import json
import tarfile

import pytest
from pydantic import ValidationError
from siling_voice.backends import keyword_tokens
from siling_voice.config import Settings, load_settings, save_settings
from siling_voice.models import check_asset, safe_extract, sha256


@pytest.mark.parametrize("word", ["", "a;rm", "你好 司聆", "x" * 50, "你好\n坏词"])
def test_keyword_validation(word):
    with pytest.raises(ValidationError):
        Settings(wake_word=word)


def test_settings_atomic_roundtrip_and_bad_file(tmp_path):
    target = tmp_path / "settings.json"
    settings = Settings(device=2, wake_word="小爱同学")
    save_settings(settings, target)
    assert load_settings(target) == settings
    assert not target.with_suffix(".tmp").exists()
    target.write_text("{bad}")
    with pytest.raises(ValidationError):
        load_settings(target)


def test_invalid_timing():
    with pytest.raises(ValidationError):
        Settings(speech_wait_ms=10000, max_record_ms=9000)


def test_default_wake_tokens_are_phonetic_and_validated(tmp_path):
    tokens = tmp_path / "tokens.txt"
    parts = ["n", "ǐ", "h", "ǎo", "s", "ī", "l", "íng"]
    tokens.write_text("\n".join(f"{p} {i}" for i, p in enumerate(parts)), "utf-8")
    assert keyword_tokens("你好司聆", tokens) == "n ǐ h ǎo s ī l íng @你好司聆\n"
    with pytest.raises(ValueError):
        keyword_tokens("小爱同学", tokens)


@pytest.mark.parametrize(
    "name,link",
    [
        ("../outside", False),
        ("/absolute", False),
        ("model/../../outside", False),
        ("model/link", True),
        ("model\\..\\outside", False),
    ],
)
def test_untrusted_tar_cannot_escape(tmp_path, name, link):
    archive = tmp_path / "bad.tar.bz2"
    with tarfile.open(archive, "w:bz2") as tar:
        member = tarfile.TarInfo(name)
        if link:
            member.type, member.linkname = tarfile.SYMTYPE, "../../outside"
            tar.addfile(member)
        else:
            member.size = 1
            tar.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(ValueError):
        safe_extract(archive, tmp_path / "out", "model")
    assert not (tmp_path / "outside").exists()


def test_model_asset_hash_rejects_tampering(tmp_path):
    asset = tmp_path / "model"
    asset.write_bytes(b"model bytes")
    pinned = {"bytes": asset.stat().st_size, "sha256": sha256(asset), "filename": "model"}
    check_asset(asset, pinned)
    asset.write_bytes(b"MODEL bytes")
    with pytest.raises(ValueError):
        check_asset(asset, pinned)


def test_no_credentials_in_default_settings():
    encoded = json.dumps(Settings().model_dump())
    assert "api_key" not in encoded
    assert "cloud" not in encoded
