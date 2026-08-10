import subprocess

import pytest

from git.git_service import GitService


def _run(args, cwd):
    subprocess.run(args, cwd=str(cwd), check=True, capture_output=True, encoding="utf-8")


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-m", "initial commit"], repo)
    return repo


@pytest.mark.skipif(not GitService.is_git_available(), reason="git not available in PATH")
def test_status_on_clean_repo(git_repo):
    status = GitService(git_repo).status()
    assert status.is_repo is True
    assert status.dirty is False
    assert status.has_pre_existing_changes is False
    assert status.commit is not None


@pytest.mark.skipif(not GitService.is_git_available(), reason="git not available in PATH")
def test_status_detects_pre_existing_change(git_repo):
    (git_repo / "README.md").write_text("changed content\n", encoding="utf-8")
    status = GitService(git_repo).status()
    assert status.dirty is True
    assert status.has_pre_existing_changes is True
    assert "README.md" in status.changed_files


@pytest.mark.skipif(not GitService.is_git_available(), reason="git not available in PATH")
def test_status_detects_untracked_file(git_repo):
    (git_repo / "new_file.txt").write_text("new\n", encoding="utf-8")
    status = GitService(git_repo).status()
    assert status.has_pre_existing_changes is True
    assert "new_file.txt" in status.untracked_files


def test_status_on_non_git_directory(tmp_path):
    not_a_repo = tmp_path / "not_a_repo"
    not_a_repo.mkdir()
    status = GitService(not_a_repo).status()
    assert status.is_repo is False
    assert status.error is not None
