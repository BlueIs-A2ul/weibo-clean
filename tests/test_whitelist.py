import json

import pytest

from app.whitelist import (
    WhitelistEntry,
    WhitelistError,
    WhitelistStore,
    parse_uid_input,
)


def entry(uid: str, name: str = "n") -> WhitelistEntry:
    return WhitelistEntry(uid=uid, name=name, avatar="http://img/a.jpg")


def test_parse_uid_input_accepts_digits():
    assert parse_uid_input(" 123456 ") == "123456"


@pytest.mark.parametrize("text", [
    "https://weibo.com/u/123456",
    "weibo.com/u/123456?from=page",
    "https://m.weibo.cn/u/123456",
    "https://weibo.com/123456",
])
def test_parse_uid_input_accepts_links(text):
    assert parse_uid_input(text) == "123456"


@pytest.mark.parametrize("text", ["", "昵称", "https://weibo.com/n/somebody"])
def test_parse_uid_input_rejects(text):
    with pytest.raises(ValueError):
        parse_uid_input(text)


def test_add_persists_and_removes_from_removed(tmp_path):
    path = tmp_path / "wl.json"
    store = WhitelistStore(path)
    store.hide(entry("1"))
    store.add(entry("1", "新名字"))
    reloaded = WhitelistStore(path)
    assert reloaded.is_added("1") is True
    assert reloaded.is_removed("1") is False
    assert reloaded.added_entries()[0].name == "新名字"


def test_add_stamps_time_when_missing(tmp_path):
    store = WhitelistStore(tmp_path / "wl.json")
    store.add(WhitelistEntry(uid="1"))
    assert store.added_entries()[0].at


def test_hide_moves_added_to_removed(tmp_path):
    store = WhitelistStore(tmp_path / "wl.json")
    store.add(entry("1"))
    store.hide(entry("1"))
    assert store.is_added("1") is False
    assert store.is_removed("1") is True


def test_remove_added_and_restore(tmp_path):
    store = WhitelistStore(tmp_path / "wl.json")
    store.add(entry("1"))
    store.hide(entry("2"))
    store.remove_added("1")
    store.restore("2")
    assert store.added_entries() == []
    assert store.removed_entries() == []


def test_missing_file_starts_empty(tmp_path):
    store = WhitelistStore(tmp_path / "nope.json")
    assert store.added_entries() == []
    assert store.is_added("1") is False


def test_corrupt_file_raises(tmp_path):
    path = tmp_path / "wl.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(WhitelistError):
        WhitelistStore(path).is_added("1")


def test_entries_without_uid_are_skipped(tmp_path):
    path = tmp_path / "wl.json"
    payload = {"version": 1, "added": [{"name": "x"}, vars(entry("1"))]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert [e.uid for e in WhitelistStore(path).added_entries()] == ["1"]


def test_saved_file_is_valid_and_tmp_cleaned(tmp_path):
    path = tmp_path / "wl.json"
    store = WhitelistStore(path)
    store.add(entry("1"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1 and payload["added"][0]["uid"] == "1"
    assert not (tmp_path / "wl.json.tmp").exists()
