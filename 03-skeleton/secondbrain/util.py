import datetime, json, sys


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso(ts):
    """Epoch seconds -> ISO 8601 UTC. Returns None rather than guessing."""
    if ts is None:
        return None
    try:
        return datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc)\
                       .strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OSError, OverflowError):
        return None


def jdump(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, default=str)


def human(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or u == "TB":
            return "%.1f %s" % (n, u) if u != "B" else "%d B" % n
        n /= 1024


def err(msg):
    print(msg, file=sys.stderr)
