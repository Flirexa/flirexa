# Licensing

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

Your license is bound to the server's hardware identifier. This means:

- The license is valid only on the specific server where it was activated
- Moving to a different server requires a license transfer (see below)
- The hardware ID is generated automatically during activation

## Grace period

The software has a **72-hour offline tolerance**. If your server temporarily loses connectivity to the license server, the software will continue to operate normally for up to 72 hours. Normal operation resumes automatically once connectivity is restored.

## License verification

The software periodically contacts the license server at `flirexa.biz` to verify license validity. This check transmits only:

- Hostname and IP address
- Application version
- Instance identifier
- License status

No VPN traffic or user data is transmitted during verification.

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
