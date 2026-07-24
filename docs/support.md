# Support

_Last verified: 2026-07-24._

## Contact

- **Email:** [support@flirexa.biz](mailto:support@flirexa.biz)
- **Website chat:** Support widget in the bottom-right corner at [flirexa.biz](https://flirexa.biz)

## Response handling

Enterprise requests receive priority handling. Current support terms and any
response-time commitments are the ones shown with the selected plan or support
contract on [flirexa.biz](https://flirexa.biz).

## What to include in a support request

To help us resolve your issue quickly, include the following:

1. **License tier** (Starter / Business / Enterprise)
2. **Product version** (run `vpnmanager status` to check)
3. **Description of the issue** with steps to reproduce
4. **Error messages** or screenshots, if applicable
5. **Support bundle** (see below)

## Generating a support bundle

The `support-bundle` command collects diagnostic information including logs, system status, and configuration (with secrets automatically redacted):

```bash
sudo vpnmanager support-bundle --output /tmp --redact-strict
```

Inspect the generated archive before attaching it. Never attach a backup,
database dump, `.env`, licence/activation key, VPN configuration, or unredacted
log unless a secure transfer has been agreed separately.

## Self-help resources

- **Documentation:** [github.com/Flirexa/flirexa/tree/main/docs](https://github.com/Flirexa/flirexa/tree/main/docs)
- **CLI reference:** See [cli.md](cli.md) for all available commands
- **Troubleshooting guide:** See [troubleshooting.md](troubleshooting.md) for common issues and solutions
