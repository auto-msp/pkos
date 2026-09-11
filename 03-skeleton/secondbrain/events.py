"""Event log (SOW 11) and audit log (SOW 35, 95).

Two different things, deliberately not merged:
  event      - how KNOWLEDGE changed (object-scoped, reproducible history)
  audit      - what the SYSTEM did (including actions touching no object)
"""
from . import ids
from .util import now_iso, jdump

OPERATIONS = {"ACQUIRED","IMPORTED","NORMALIZED","CLASSIFIED","ENRICHED","REVIEWED",
              "VALIDATED","MODIFIED","MERGED","SPLIT","SUPERSEDED","ARCHIVED",
              "RESTORED","DELETED"}


def record_event(conn, operation, object_id=None, actor="system", source=None,
                 previous_state=None, new_state=None, reason=None, job_id=None,
                 model_id=None, confidence=None):
    if operation not in OPERATIONS:
        raise ValueError("unknown operation %r (SOW 11 vocabulary)" % operation)
    eid = ids.scoped("EVT", 1)
    conn.execute(
        "INSERT INTO event(event_id,timestamp,object_id,actor,operation,source,"
        "previous_state,new_state,reason,job_id,model_id,confidence)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (eid, now_iso(), object_id, actor, operation, source, previous_state,
         new_state, reason, job_id, model_id, confidence))
    return eid


def audit(conn, category, action, outcome, actor="system", target=None,
          detail=None, job_id=None):
    aid = ids.scoped("AUD", 1)
    conn.execute(
        "INSERT INTO audit_event(audit_id,timestamp,actor,category,action,target,"
        "outcome,detail,job_id) VALUES(?,?,?,?,?,?,?,?,?)",
        (aid, now_iso(), actor, category, action, target, outcome,
         detail if isinstance(detail, str) or detail is None else jdump(detail),
         job_id))
    return aid
