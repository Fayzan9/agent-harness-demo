"""Storage checks. The same contract is run against every backend, so a new one must behave identically.

Run from backend/:  PYTHONPATH=. uv run python tests/test_storage.py
"""
import tempfile

from app.storage import LocalStorage

failed = []


def check(name, ok, extra=""):
    print("PASS" if ok else "FAIL", name, extra)
    if not ok:
        failed.append(name)


def raises(exc, fn, *args):
    try:
        fn(*args)
    except exc:
        return True
    except Exception:
        return False
    return False


def contract(label, s):
    """What every Storage must do."""
    s.write("users/alice/a.txt", b"hello")
    check(f"{label}: write then read", s.read("users/alice/a.txt") == b"hello")
    s.write("users/alice/a.txt", b"changed")
    check(f"{label}: writing again replaces", s.read("users/alice/a.txt") == b"changed")
    s.write("users/bob/b.txt", "héllo 👋".encode())
    check(f"{label}: bytes round-trip exactly", s.read("users/bob/b.txt").decode() == "héllo 👋")
    check(f"{label}: list by prefix", s.list("users/alice/") == ["users/alice/a.txt"] and s.list("users/") == ["users/alice/a.txt", "users/bob/b.txt"])
    check(f"{label}: a prefix is not a folder-escape (alice vs alice2)", (s.write("users/alice2/x.txt", b"x"), s.list("users/alice/"))[1] == ["users/alice/a.txt"])
    check(f"{label}: reading a missing key", raises(FileNotFoundError, s.read, "users/alice/nope.txt"))
    s.delete("users/alice/a.txt")
    s.delete("users/alice/a.txt")
    check(f"{label}: delete, and deleting twice is fine", s.list("users/alice/") == [])
    for bad in ["../x", "users/../../x", "/etc/passwd", "users//a", "", "users/./a", "a\\b", "a\x00b"]:
        check(f"{label}: refuses key {bad!r}", raises(ValueError, s.write, bad, b"x") and raises(ValueError, s.read, bad))


if __name__ == "__main__":
    contract("local", LocalStorage(tempfile.mkdtemp()))
    print("\nALL PASSED" if not failed else f"\nFAILED: {failed}")
    raise SystemExit(1 if failed else 0)
