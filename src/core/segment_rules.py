"""Push a segment's non-null rule template onto a member client's own fields.
Goes through ManagementCore so live bandwidth limits actually enforce."""
from .management import ManagementCore

_RULE_FIELDS = ("bandwidth_limit", "traffic_limit_mb", "expiry_date", "auto_bandwidth_rule_id")

def _update_client(db, client_id, **fields):
    ManagementCore(db).clients.update_client(client_id, **fields)

def apply_segment_to_client(db, segment, client_id) -> dict:
    fields = {f: getattr(segment, f) for f in _RULE_FIELDS if getattr(segment, f) is not None}
    if fields:
        _update_client(db, client_id, **fields)
    return fields
