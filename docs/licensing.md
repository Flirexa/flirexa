# Licensing

_Last verified: 2026-07-24._

## Obtaining your activation code

After completing your purchase, you will receive your activation code:

1. On the **thank-you page** immediately after payment confirmation
2. Via **email** to the address you provided at checkout

Keep your activation code safe. It is your proof of purchase and is required for installation.

## Activation code format

```
XXXX-XXXX-XXXX-XXXX
```

16 alphanumeric characters separated by dashes.

## Activating your license

1. Open the admin panel
2. Navigate to **Settings > License**
3. Paste your activation code
4. Click **Activate**

The license is activated immediately upon successful verification.

## Hardware binding

Most paid licences are bound to a derived server hardware identifier. This means:

- The license is valid only on the specific server where it was activated
- Moving to a different server requires a license transfer (see below)
- The hardware ID is generated automatically during activation

## Grace period

Subscription licences normally have a **72-hour offline tolerance** backed by a
locally cached signed status. Exact enforcement and heartbeat cadence depend on
the licence type: protected lifetime licences use a slower clone-detection
heartbeat, while pure offline lifetime licences do not heartbeat.

## License verification

Activated subscription/protected licences periodically contact the official
licence service. Validation and heartbeat requests can include:

- the licence key or a one-way licence identifier, plus a masked activation-code prefix;
- derived hardware and persistent instance identifiers;
- hostname, application version, licence status, uptime, and timestamps;
- migration receipts when a licensed installation is being moved;
- normal HTTP request metadata, including source IP.

These requests do **not** include the VPN client list, VPN keys/configurations,
traffic contents, traffic counters, payment records, or portal user data. An
unactivated FREE runtime has no licence heartbeat. Installer diagnostics and
update checks are separate and documented in [installation.md](installation.md)
and [updates.md](updates.md).

## License transfer

If you need to move your installation to a different server, contact [support@flirexa.biz](mailto:support@flirexa.biz) to request a hardware rebinding. Include your activation code and the reason for the transfer.

## Internal development mode

The software includes a development mode intended for internal testing only. This mode is **not licensed for production use** and must not be used to serve real clients.

## Troubleshooting

| Issue | Resolution |
|-------|------------|
| "License invalid" after server migration | Contact support for hardware rebinding |
| Activation code not accepted | Verify the code format (XXXX-XXXX-XXXX-XXXX) and check for typos |
| License deactivated | Ensure the server can reach `flirexa.biz` and that the license is not active on another server |
