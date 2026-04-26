# Security Policy

## Reporting a vulnerability

**Do not open a public issue for security problems.** Please email `support@flirexa.biz` with:

- A description of the vulnerability and its impact.
- Steps to reproduce, preferably as a minimal test case.
- The Flirexa version (`cat VERSION`) and OS version.
- Whether you've shared this with anyone else, and any disclosure timeline you have in mind.

You should expect an acknowledgment within **3 working days**. We aim to release a patch within **30 days** for high-severity issues; lower-severity issues are scheduled into the regular release cadence.

## Scope

In scope:
- The Flirexa core (this repository), including the plugin loader and the bundled plugin shells.
- The default `install.sh` and `update_apply.sh` flows.
- The Vue admin panel and client portal (`src/web/`).

Out of scope:
- Third-party dependencies — please report those upstream (Python packages, FastAPI, Vue, WireGuard tools, Hysteria2 / TUIC binaries). We will of course track CVEs and bump versions.
- Issues that require physical access or full root on the server already.
- Theoretical attacks against unconfigured installs (the FREE tier is intentionally permissive about local access by design).

## What we treat as a vulnerability

- Auth bypass on the admin panel or client portal.
- Privilege escalation between admin / manager / portal-user roles.
- Bypassing license-feature gates without modifying the source code.
- SQL injection, RCE, SSRF, path traversal in any HTTP route.
- Hardcoded credentials or secrets shipped in this repository.
- Data leaks in logs, error messages, or support bundles.

## What we don't treat as a vulnerability

- Removing license gates from a forked copy of the source code is **expected** — the gates protect users on the official distribution, not against motivated attackers with source access. This is the open-core trade-off.
- Misconfigurations that expose the admin panel to the public internet without TLS / a firewall.
- Self-XSS / social engineering against an already-logged-in admin.

## Acknowledgment

We're happy to credit researchers in release notes once a patch ships. If you'd prefer to stay anonymous, just say so in your report.
