"""DNS protection commercial plugin descriptor."""
from src.modules.plugin_loader import Plugin

class DnsProtectionPlugin(Plugin):
    def get_features(self):
        return ["dns_protection"]

PLUGIN = DnsProtectionPlugin({
    "name": "dns-protection", "version": "1.0.0",
    "display_name": "Per-device DNS Protection",
    "requires_license_feature": "dns_protection",
})
