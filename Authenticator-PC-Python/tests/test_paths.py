import infrastructure.paths as paths


def test_source_data_directory_is_project_local(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    module_path = project_root / "infrastructure" / "paths.py"
    monkeypatch.setattr(paths, "__file__", str(module_path))
    monkeypatch.delattr(paths.sys, "frozen", raising=False)

    directory = paths.application_data_directory()

    assert directory == project_root / "data"
    assert directory.is_dir()


def test_frozen_data_directory_is_next_to_executable(monkeypatch, tmp_path):
    executable = tmp_path / "portable" / "AuthenticatorDesktop.exe"
    executable.parent.mkdir()
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(executable))

    directory = paths.application_data_directory()

    assert directory == executable.parent / "data"
    assert directory.is_dir()
