"""Object identity (SOW 8, 9).

object_id  = KB-00000001            stable for the life of the concept
version_id = KB-00000001:v01        one state of that concept

An id must never encode a path, filename, provider, rowid, vector id or URL,
so that identity survives migration between storage systems. Allocation is
transactional against id_sequence.

Every object also carries a uuid4. The KB- id is the human-facing, sortable,
citable handle; the uuid is what makes two machines' allocations safely
mergeable if the canonical store is ever forked and rejoined.
"""
import uuid

PREFIX = "KB"


def allocate(conn, prefix=PREFIX, count=1):
    """Reserve `count` ids atomically. Returns a list of id strings."""
    cur = conn.execute("SELECT next_val FROM id_sequence WHERE prefix=?", (prefix,))
    row = cur.fetchone()
    if row is None:
        start = 1
        conn.execute("INSERT INTO id_sequence(prefix,next_val) VALUES(?,?)",
                     (prefix, start + count))
    else:
        start = row[0]
        conn.execute("UPDATE id_sequence SET next_val=? WHERE prefix=?",
                     (start + count, prefix))
    return ["%s-%08d" % (prefix, n) for n in range(start, start + count)]


def one(conn, prefix=PREFIX):
    return allocate(conn, prefix, 1)[0]


def version_id(object_id, version_num):
    return "%s:v%02d" % (object_id, version_num)


def new_uuid():
    return str(uuid.uuid4())


def scoped(kind, n):
    """Ids for non-KB entities (jobs, events, relationships...)."""
    return "%s-%s" % (kind, uuid.uuid4().hex[:16])
