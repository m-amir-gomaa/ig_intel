"""Private local/Modal-volume storage. No customer-controlled paths or pickle."""

import hashlib, json, re
from pathlib import Path
from .errors import DomainError


def audio_name(seconds):
    return (
        "audio-"
        + hashlib.sha256(str(float(seconds)).encode()).hexdigest()[:16]
        + ".wav"
    )


class Storage:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def directory(self, uid):
        import uuid

        if str(uuid.UUID(uid)) != uid:
            raise DomainError("Invalid storage identifier.")
        return self.root / uid

    def execute(self, operation, args):
        root = self.directory(args["upload"])
        if operation == "put":
            root.mkdir(exist_ok=True)
            path = root / "source.media"
            if path.exists():
                return
            temporary = root / "source.tmp"
            temporary.write_bytes(args["data"])
            temporary.replace(path)
            return
        if operation == "result":
            jid = str(__import__("uuid").UUID(args["job"]))
            return json.loads((root / ("result-" + jid + ".json")).read_text())
        if operation == "audio":
            path = root / audio_name(args["seconds"])
            size = path.stat().st_size
            start, end = 0, size - 1
            status = 200
            if args.get("range"):
                match = re.fullmatch(r"bytes=([0-9]+)-([0-9]*)", args["range"])
                if not match:
                    raise DomainError("Unsupported audio range.")
                start = int(match[1])
                end = min(size - 1, int(match[2])) if match[2] else size - 1
                if not 0 <= start <= end < size:
                    raise DomainError("Audio range is outside the file.")
                status = 206
            with path.open("rb") as f:
                f.seek(start)
                data = f.read(end - start + 1)
            headers = {"Accept-Ranges": "bytes", "Content-Length": str(len(data))}
            if status == 206:
                headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            return {"data": data, "status": status, "headers": headers}
        raise DomainError("Unknown storage operation.")
