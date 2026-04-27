## What changed

<!-- Brief description. If it fixes an issue, link it. -->

## Why

<!-- The reasoning, not just the symptom. -->

## Checklist

- [ ] Tests pass locally: `pytest tests/`
- [ ] No personal data (real IPs, hostnames, customer names, real email addresses) in the diff
- [ ] No re-introduction of `src/modules/integrity/` or other code removed during the open-core split
- [ ] If this touches a plugin, the corresponding test in `tests/test_*_plugin.py` is updated
- [ ] If this touches a license gate or feature flag, both FREE and paid behavior are still verified by tests
