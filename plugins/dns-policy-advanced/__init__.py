"""Advanced DNS policy commercial plugin descriptor."""
from src.modules.plugin_loader import Plugin

class DnsPolicyAdvancedPlugin(Plugin):
    def get_features(self):
        return ["dns_policy_advanced"]

PLUGIN = DnsPolicyAdvancedPlugin({
    "name": "dns-policy-advanced", "version": "1.0.0",
    "display_name": "Advanced DNS Policies",
    "requires_license_feature": "dns_policy_advanced",
})
