"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `proxy_protocols` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "proxy_protocols"
_UPGRADE_HINT = (
    "This component requires the proxy_protocols commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


_PROXY_TYPES = {'hysteria2', 'tuic', 'vless-reality'}

def is_proxy_server(server) -> bool:
    return (getattr(server, 'server_category', None) == 'proxy' or getattr(server, 'server_type', '') in _PROXY_TYPES)

def normalize_create_options(*, server_type, server_category, config_path, proxy_config_path, interface):
    if server_type in _PROXY_TYPES:
        raise RuntimeError(_UPGRADE_HINT)
    if config_path is None:
        config_path = (f'/etc/amnezia/amneziawg/{interface}.conf' if server_type == 'amneziawg' else f'/etc/wireguard/{interface}.conf')
    return False, server_category or 'vpn', config_path

def get_proxy_manager(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)

def cleanup_server_runtime(server, *, force=False) -> bool:
    try:
        manager = get_proxy_manager(server)
    except Exception:
        return True
    try:
        manager.purge_service()
    except Exception:
        pass
    finally:
        try:
            manager.close()
        except Exception:
            pass
    return True

def status(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)

def start(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)

def stop(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)

def restart(*args, **kwargs):
    raise RuntimeError(_UPGRADE_HINT)
