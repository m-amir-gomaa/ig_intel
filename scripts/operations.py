"""Owner-only Modal SDK operations; never exposed through public HTTP."""

import argparse
import json
import os
from pathlib import Path

import modal
from cryptography.fernet import Fernet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["report", "pause", "resume", "caps", "backup"]
    )
    parser.add_argument("--day-units", type=int)
    parser.add_argument("--month-units", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    store = modal.Function.from_name("sonaweft", "store")
    if args.action == "report":
        result = store.remote("operations", {})
        print(json.dumps(result, indent=2))
        return int(result["invalid_balances"] != 0)
    if args.action in ("pause", "resume", "caps"):
        values = (
            {"paused": args.action == "pause"}
            if args.action != "caps"
            else {"day_units": args.day_units, "month_units": args.month_units}
        )
        if args.action == "caps" and all(v is None for v in values.values()):
            parser.error(
                "Choose at least one cap. 10,000 units = $1 estimated admission."
            )
        print(json.dumps(store.remote("control", values)))
        return 0
    if not args.output:
        parser.error(
            "backup requires --output PATH; no existing file will be overwritten"
        )
    path = args.output.expanduser()
    key_path = path.with_suffix(path.suffix + ".key")
    if path.exists() or key_path.exists():
        parser.error("Choose new paths for the backup and its separate key")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = Fernet.generate_key()
    cipher = Fernet(key)
    raw = store.remote("snapshot", {})
    encrypted = cipher.encrypt(raw)
    if cipher.decrypt(encrypted) != raw:
        raise RuntimeError("Backup encryption verification failed")
    for target, value in ((key_path, key), (path, encrypted)):
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(value)
    print(
        "Encrypted financial backup written. Move its .key file to separate safe storage."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
