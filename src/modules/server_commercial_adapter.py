"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `multi_server` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "multi_server"
_UPGRADE_HINT = (
    "This component requires the multi_server commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


def is_remote_server(server) -> bool:
    return bool(getattr(server, 'ssh_host', None) or (getattr(server, 'agent_mode', None) or '') in {'agent', 'mikrotik'})

def get_remote_wg_manager(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)

def cleanup_server_runtime(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)

def install_agent(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)

def uninstall_agent(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)

def switch_to_agent_mode(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)

def switch_to_ssh_mode(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)
