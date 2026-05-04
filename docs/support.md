# Support

## Contact

- **Email:** [support@flirexa.biz](mailto:support@flirexa.biz)
- **Website chat:** Support widget in the bottom-right corner at [flirexa.biz](https://flirexa.biz)

## Response time

- **Standard support** (Starter, Business): within 24 hours on business days
- **Priority support** (Enterprise): prioritized response queue

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
vpnmanager support-bundle
```

Attach the generated archive to your support email.

## Self-help resources

- **Documentation:** [github.com/Flirexa/flirexa/tree/main/docs](https://github.com/Flirexa/flirexa/tree/main/docs)
- **CLI reference:** See [cli-reference.md](cli-reference.md) for all available commands
- **Troubleshooting guide:** See [troubleshooting.md](troubleshooting.md) for common issues and solutions
