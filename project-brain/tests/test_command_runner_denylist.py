import pytest

from executor.command_runner import CommandRunner, DestructiveCommandError


@pytest.mark.parametrize(
    "argv",
    [
        ["git", "reset", "--hard"],
        ["git", "reset", "--hard", "HEAD~1"],
        ["git", "clean", "-fd"],
        ["git", "clean", "-df"],
        ["git", "clean", "--force", "--dirs"],
        ["git", "push", "--force"],
        ["git", "push", "-f", "origin", "main"],
        ["rm", "-rf", "/"],
        ["mysql", "-e", "DROP DATABASE prod"],
        ["mysql", "-e", "DROP TABLE users"],
        ["mysql", "-e", "TRUNCATE users"],
        ["mysql", "-e", "DELETE FROM users"],
        ["npm", "run", "deploy"],
    ],
)
def test_destructive_commands_are_blocked(argv):
    runner = CommandRunner()
    with pytest.raises(DestructiveCommandError):
        runner.run(argv)


def test_safe_commands_are_not_blocked():
    runner = CommandRunner()
    result = runner.run(["git", "--version"])
    assert result.ok


def test_destructive_command_never_reaches_subprocess(monkeypatch):
    called = {"count": 0}

    def fake_run(*args, **kwargs):
        called["count"] += 1
        raise AssertionError("subprocess.run should never be called for a denied command")

    monkeypatch.setattr("executor.command_runner.subprocess.run", fake_run)
    runner = CommandRunner()
    with pytest.raises(DestructiveCommandError):
        runner.run(["git", "reset", "--hard"])
    assert called["count"] == 0


def test_commit_message_containing_word_drop_is_not_falsely_blocked():
    # A commit message mentioning "drop" in prose must not trigger the
    # DB-destructive-statement check, since that check only inspects args
    # passed to a DB CLI binary (mysql/psql/sqlite3/...), not git.
    runner = CommandRunner()
    # The point of this test is that no DestructiveCommandError is raised;
    # the actual git exit code doesn't matter (this may run outside a repo).
    result = runner.run(["git", "log", "--grep=drop the legacy table later", "-1"])
    assert result.returncode is not None
