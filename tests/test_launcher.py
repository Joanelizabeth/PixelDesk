from services.launcher_service import LauncherService, validate_entry


def test_missing_folder_reports_error(tmp_path):
    err = validate_entry("folder", str(tmp_path / "nope"))
    assert err and "no longer exists" in err


def test_file_given_as_folder(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    assert "not a folder" in validate_entry("folder", str(f))


def test_app_must_be_executable_or_shortcut(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("x")
    assert validate_entry("app", str(f)) is not None
    assert validate_entry("app", str(tmp_path)) is not None


def test_empty_and_nul_paths():
    assert validate_entry("folder", "") is not None
    assert validate_entry("folder", "C:/x\x00y") is not None


def test_launch_calls_opener_only_when_valid(tmp_path):
    calls = []
    svc = LauncherService(opener=lambda p, k: calls.append((p, k)))
    assert svc.launch("folder", str(tmp_path)).ok
    res = svc.launch("folder", str(tmp_path / "gone"))
    assert not res.ok and calls == [(str(tmp_path), "folder")]


def test_opener_error_is_reported(tmp_path):
    def boom(p, k):
        raise OSError(5, "Access is denied")
    res = LauncherService(opener=boom).launch("folder", str(tmp_path))
    assert not res.ok and "Access is denied" in res.message


def test_label_never_used_as_command(tmp_path):
    # A label full of shell metacharacters only ever reaches the opener as data.
    calls = []
    svc = LauncherService(opener=lambda p, k: calls.append(p))
    weird = tmp_path / "a & del *"
    weird.mkdir()
    assert svc.launch("folder", str(weird)).ok
    assert calls == [str(weird)]
