# Client Management

A **client** in VPN Management Studio represents a single WireGuard peer — one device, one IP, one configuration file.

---

## Creating a Client

1. Go to **Clients → Add Client**
2. Fill in:
   - **Name** — a label to identify the client (e.g. `alice-laptop`)
   - **Server** — which WireGuard server to assign the client to
   - **Expiry date** (optional) — automatically disable the client after this date
   - **Traffic limit** (optional) — disable the client after N MB of traffic
   - **Bandwidth limit** (optional) — rate-limit to N Mbps via `tc`
3. Click **Create**

The system automatically:
- Assigns the next available IP from the server's address pool
- Generates a WireGuard key pair
- Adds the peer to the live WireGuard interface
- Stores the configuration in the database

---

## Downloading Client Configuration

After creating a client, click **Download Config** to get a `.conf` file. For mobile devices, click **QR Code** to display a QR code that can be scanned directly in the WireGuard app.

### WireGuard App

Use the official WireGuard client for most platforms:
- **Android / iOS** — WireGuard app from the store
- **Windows / macOS / Linux** — WireGuard client from [wireguard.com](https://www.wireguard.com/install/)

Import the `.conf` file or scan the QR code.

### AmneziaVPN App

If the client is on an **AmneziaWG** server, the config includes obfuscation parameters (Jc, Jmin, Jmax, S1, S2, H1–H4). These parameters are ignored by the standard WireGuard client. Clients connecting to AmneziaWG servers must use the **AmneziaVPN** app:

- Android: [Google Play](https://play.google.com/store/apps/details?id=org.amnezia.vpn) or direct APK
- iOS: App Store
- Windows / macOS / Linux: [amnezia.org](https://amnezia.org)

Import the downloaded `.conf` file into AmneziaVPN.

---

## Managing Clients

In the **Clients** list you can:

- **Enable / Disable** — toggle the peer in the live WireGuard interface without deleting it
- **Edit** — change the name, expiry, traffic limit, or bandwidth limit
- **Regenerate Keys** — issue a new key pair (the old config stops working immediately)
- **Delete** — remove from WireGuard and the database

### Bulk Operations

Select multiple clients with the checkboxes and use the bulk actions toolbar to enable, disable, or delete.

---

## Traffic Monitoring

The **Clients** table shows:
- **RX / TX** — cumulative bytes received and sent since last reset
- **Last Handshake** — when the peer last connected
- **Status** — active (connected recently), idle, disabled, or expired

Traffic counters are updated every monitoring cycle (default: 60 seconds).

To reset a client's traffic counter: open the client, click **Reset Traffic**.

---

## Expiry and Traffic Limits

When a client reaches its expiry date or traffic limit, it is automatically disabled by the background worker. Disabled clients are removed from the live WireGuard interface — their configs stop working — but the record remains in the database.

Re-enable a client manually or extend the expiry in the admin panel.

---

## Peer Visibility

Peer visibility allows devices belonging to the same user (same Telegram user ID) to see each other in the VPN network. This is an AmneziaWG-specific feature.

When enabled for a client:
- The server's WireGuard config lists the IPs of sibling devices as allowed IPs for each peer
- Devices can reach each other directly within the VPN subnet

**Requirements:**
- Server must be `amneziawg` type
- Server must have `supports_peer_visibility` enabled (default: true)
- Clients must have `peer_visibility` enabled

Configure on the client edit screen.

---

## Client Portal Self-Service

End users can manage their own VPN configs without admin involvement:

1. Open **Client Portal** at `http://YOUR_SERVER_IP:10090`
2. Register with email and password
3. Choose a subscription plan and pay
4. Download VPN config or scan QR code
5. View traffic usage

The client portal is configured via **Settings → Subscriptions** in the admin panel. Plans define price, duration, traffic quota, and number of allowed devices.

---

## Telegram Client Bot

Users who prefer Telegram over the web portal can use the client bot:

1. Start a chat with your client bot
2. The bot auto-registers them and creates a VPN client
3. Reply with commands:
   - View config
   - Get QR code
   - Check remaining traffic
   - Submit a support message

Set up the client bot token in **Settings → Bots** or in `.env` as `CLIENT_BOT_TOKEN`.

---

## Importing Existing Clients

If you have an existing WireGuard setup with clients already configured, use **Servers → Discover** to import them. The system reads the live `wg show dump` output, parses existing peers, and imports them into the database.

After discovery, each imported client is visible in the Clients list with its existing IP and public key.
