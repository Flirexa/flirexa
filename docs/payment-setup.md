# Payment Setup

VPN Management Studio supports **7 payment providers** for the client portal. Customers can pay for subscriptions in crypto, cards, bank rails, or local methods. You enable as many as you want from a single admin page.

> **Free tier:** only NOWPayments is available to your customers. All other providers (CryptoPay, PayPal, Stripe, Mollie, Razorpay, Payme) require a paid VPN Management Studio license. The gating is enforced on both the API and the UI.

---

## Supported Providers

| Provider | Type | Currencies | Best for | Tier |
|---|---|---|---|---|
| [**NOWPayments**](#nowpayments) | Crypto (100+) | BTC, ETH, USDT, USDC, LTC, XMR, TON, SOL… | Most flexible crypto rail | Free |
| [**CryptoPay**](#cryptopay-telegram) | Crypto (Telegram bot) | BTC, TON, USDT, USDC, BUSD, ETH | Telegram-centric VPN brands | Paid |
| [**PayPal**](#paypal) | PayPal + cards | USD, EUR, GBP | International cards & PayPal balance | Paid |
| [**Stripe**](#stripe) | Cards + Apple/Google Pay | USD, EUR, GBP, CAD, AUD, JPY | EU/US card payments | Paid |
| [**Mollie**](#mollie) | Cards + iDEAL + SEPA + Klarna | EUR, USD, GBP | Europe-focused | Paid |
| [**Razorpay**](#razorpay) | UPI, NetBanking, cards | INR, USD, EUR | India | Paid |
| [**Payme**](#payme) | UzCard, Humo, Visa, Mastercard | UZS | Uzbekistan | Paid |

You configure all of them from a single page in the admin panel:

> **Settings → Payment Providers → Configure**

Each provider has its own card with:
- the required fields (API key, secrets, etc. — what to paste comes from the provider dashboard);
- the exact **webhook URL** to register at the provider's side (auto-generated from your `CLIENT_PORTAL_DOMAIN`, with a one-click Copy button);
- **Save & Connect**, **Test** (runs a self-check without real charges), **Disconnect**.

> **About webhook URLs in this guide:** every section below lists `https://YOUR_HOST/client-portal/webhooks/<provider>` for documentation purposes. **Don't copy that template manually.** Open the provider's card in your admin panel — the actual URL with your real domain is shown there with a Copy button. That's the one you paste into the provider's dashboard.

---

## NOWPayments

Universal crypto provider — your customer picks any of 100+ tokens.

### What you need

| Field | Where to get it |
|---|---|
| **API Key** | <https://account.nowpayments.io/store-settings/api-keys> → click **Add new key** |
| **IPN Secret** | Same dashboard → **Store Settings** → **IPN Settings** → generate IPN Secret |
| **Sandbox** | Toggle ON if you used the [sandbox](https://account-sandbox.nowpayments.io) keys above |

### Webhook URL to register

In the NOWPayments dashboard → **Store Settings** → **IPN Settings** → set **IPN callback URL**:

```
https://YOUR_HOST/client-portal/webhooks/nowpayments
```

No event selection — NOWPayments sends an IPN for every status change. We only credit on `finished` (per the [official IPN spec](https://documenter.getpostman.com/view/7907941/S1a32n38#instant-payments-notifications)).

### Steps

1. Settings → Payment Providers → Configure → expand **NOWPayments**
2. Paste API Key + IPN Secret, leave Sandbox OFF for production
3. **Save & Connect** — badge turns to *Active*
4. Click **Test** — should return all green checks
5. Register the webhook URL above in NOWPayments dashboard
6. Done — customers see NOWPayments on the Billing page

### Reference

- API docs: <https://documenter.getpostman.com/view/7907941/S1a32n38>
- Sandbox dashboard: <https://account-sandbox.nowpayments.io>

---

## CryptoPay (Telegram)

Crypto payments via [@CryptoBot](https://t.me/CryptoBot). Customer pays straight from their Telegram wallet — no exchange, no on-chain wait.

### What you need

| Field | Where to get it |
|---|---|
| **API Token** | [@CryptoBot](https://t.me/CryptoBot) (or [@CryptoTestnetBot](https://t.me/CryptoTestnetBot) for testing) → **Crypto Pay** → **Create App** → copy token |
| **Testnet** | Toggle ON if you used `@CryptoTestnetBot` instead of `@CryptoBot` |

### Webhook URL to register

In the bot: **Crypto Pay** → **My Apps** → choose your app → **Webhooks** → set:

```
https://YOUR_HOST/client-portal/webhooks/cryptopay
```

### Reference

- API docs: <https://help.crypt.bot/crypto-pay-api>
- Test bot: <https://t.me/CryptoTestnetBot>

---

## PayPal

PayPal balance and major card networks (Visa, Mastercard, Discover, Amex).

### What you need

| Field | Where to get it |
|---|---|
| **Client ID** | <https://developer.paypal.com/dashboard/applications> → create or open an app |
| **Client Secret** | Same app page (click **Show**) |
| **Webhook ID** | Same app page → **Webhooks** → create webhook → copy ID |
| **Sandbox** | Toggle ON if the credentials above are from the *Sandbox* mode of the PayPal Developer Dashboard |

### Webhook URL to register

In your PayPal app → **Webhooks** → **Add Webhook**:

- URL: `https://YOUR_HOST/client-portal/webhooks/paypal`
- **Events to subscribe:**
  - `Checkout order approved` (`CHECKOUT.ORDER.APPROVED`)
  - `Payment capture completed` (`PAYMENT.CAPTURE.COMPLETED`)

After saving, copy the webhook **ID** (looks like `8YR1A6781E6543210`) and paste it into the Webhook ID field in the admin panel.

### Sandbox vs Production

PayPal has two completely separate worlds:
- **Sandbox** at <https://developer.paypal.com/dashboard/applications/sandbox> — fake money, fake test accounts
- **Live** at <https://developer.paypal.com/dashboard/applications/live> — real money

Each has its own Client ID + Client Secret + Webhook ID. **You cannot mix them.**

### Reference

- Orders API: <https://developer.paypal.com/docs/api/orders/v2/>
- Webhook setup: <https://developer.paypal.com/api/rest/webhooks/>

---

## Stripe

Cards (Visa, Mastercard, Amex, Discover, JCB), Apple Pay, Google Pay, plus regional methods. Best for EU/US.

### What you need

| Field | Where to get it |
|---|---|
| **Secret Key** | <https://dashboard.stripe.com/apikeys> → **Standard keys** → reveal Secret key (`sk_live_…`) |
| **Webhook Secret** | <https://dashboard.stripe.com/webhooks> → create endpoint → reveal **Signing secret** (`whsec_…`) |

### Webhook URL to register

In Stripe Dashboard → **Developers → Webhooks → Add endpoint**:

- URL: `https://YOUR_HOST/client-portal/webhooks/stripe`
- **Events to listen to:**
  - `checkout.session.completed` (single event is enough — that's when we credit)

After saving, click **Reveal signing secret** and paste into the Webhook Secret field in admin.

### Test mode

Stripe has Test mode (toggle in top-left of Dashboard). Test keys start with `sk_test_…` and `whsec_…` (test webhooks have their own signing secret). Use the same admin form, just paste test keys.

Stripe provides [official test card numbers](https://stripe.com/docs/testing#cards) — `4242 4242 4242 4242` for successful charge.

### Reference

- API: <https://stripe.com/docs/api>
- Webhook signatures: <https://stripe.com/docs/webhooks/signatures>

---

## Mollie

European-favorite — iDEAL, Bancontact, SEPA, Klarna, plus international cards.

### What you need

| Field | Where to get it |
|---|---|
| **API Key** | <https://www.mollie.com/dashboard/developers/api-keys> → copy **Live API key** (`live_…`) or **Test API key** (`test_…`) |

### Webhook URL

Mollie webhooks are passed *per-payment* (we set them when creating the invoice) — no global webhook URL to register at the Mollie dashboard. Just enter the API key, it works.

### Test mode

Mollie test keys (`test_…`) work in Test mode where you can pay with [test method picker](https://docs.mollie.com/overview/testing). No real money.

### Reference

- API: <https://docs.mollie.com/>
- Webhook spec: <https://docs.mollie.com/payments/webhook>

---

## Razorpay

India-focused: UPI, NetBanking, cards (Visa, Mastercard, RuPay, Amex), wallets. Also supports international cards in USD/EUR.

### What you need

| Field | Where to get it |
|---|---|
| **Key ID** | <https://dashboard.razorpay.com/app/keys> → **Generate Key** → copy Key ID (`rzp_live_…`) |
| **Key Secret** | Same page — shown only at creation, save it immediately |
| **Webhook Secret** | <https://dashboard.razorpay.com/app/webhooks> → create webhook → set a secret |

### Webhook URL to register

In Razorpay Dashboard → **Settings → Webhooks → Add Webhook**:

- URL: `https://YOUR_HOST/client-portal/webhooks/razorpay`
- **Active Events:**
  - `payment.captured`
  - `payment_link.paid`
- Set **Secret** to a random string — paste the same string into the **Webhook Secret** field in admin

### Test mode

Razorpay has a Test mode toggle. Test keys start with `rzp_test_…`. Use the same admin form. Razorpay test cards: `4111 1111 1111 1111`.

### Reference

- API: <https://razorpay.com/docs/api/>
- Webhook validation: <https://razorpay.com/docs/webhooks/validate-test/>

---

## Payme

Uzbekistan local payment system — UzCard, Humo, plus Visa/Mastercard for UZS.

### What you need

| Field | Where to get it |
|---|---|
| **Merchant ID** | Payme merchant cabinet → **Settings → Merchant info** |
| **Secret Key** | Payme merchant cabinet → **Settings → Test Cabinet / Production** → API Key |

### Webhook URL to register

Set in Payme merchant cabinet → **Settings → Notifications**:

```
https://YOUR_HOST/client-portal/webhooks/payme
```

Currency: **UZS only** for the actual charge. Customers paying in UZS see the right amount.

### Reference

- Merchant API: <https://developer.help.paycom.uz/protokol-merchant-api/>

---

## The "Test" button

Every provider card in admin has a **Test** button next to **Save & Connect**. It's an offline self-check that:

1. Verifies the provider is loaded into memory (env vars set)
2. Pings the provider's API (`test_connection`)
3. Generates a webhook with a valid signature → expects `verified=true`
4. Generates a webhook with a forged signature → expects rejection
5. Extracts the order ID from the test payload — proves the lookup will work

It does **not** make any real charge. Run it after each Save and after each provider key change.

A green panel under the card means everything's wired correctly. Red means something's missing — the per-row detail tells you what (e.g., "STRIPE_WEBHOOK_SECRET not configured").

---

## What happens when a customer pays

Same flow for all providers:

1. Customer clicks **Subscribe** → invoice is created on the provider's side, customer is redirected to the provider's checkout page
2. Customer pays
3. Provider sends a signed webhook to `https://YOUR_HOST/client-portal/webhooks/<provider>`
4. We verify the signature using the secret you configured
5. If valid → subscription is upgraded, WG limits are applied, customer gets email/Telegram notification
6. If signature is invalid → 401 returned, no credit

If a webhook is dropped (rare — providers retry), the **monitoring loop** runs every 60 s and asks the provider directly via `check_payment(invoice_id)`. If the provider says "paid", we credit the subscription anyway. The customer never gets stuck in "I paid but my plan didn't activate".

See [webhook-security.md](webhook-security.md) for the full pipeline + how the recovery poller works.

---

## Common gotchas

**"Provider doesn't show up for my customers"**
- They're on the free tier — only NOWPayments is visible. [Upgrade your VPN Management Studio license](https://flirexa.biz/#pricing) to unlock all providers.
- The provider isn't activated — check **Settings → Payment Providers** and look for an "Active" badge.

**"Customer paid but subscription isn't active"**
- First check the webhook arrived: `journalctl -u spongebot-api -n 200 | grep -iE 'webhook|<provider>'`
- If no webhook line: provider's webhook URL is misconfigured — re-check that you registered our exact URL
- If webhook arrived but rejected (401): signature secret in admin doesn't match what's set at the provider — regenerate at the provider, paste the new value, Save
- The recovery poller will catch it within ~60 s if `check_payment` works for that provider

**"Wrong currency on checkout"**
- NOWPayments takes the price in USD/EUR but charges any crypto — exchange happens on their side
- PayPal/Stripe/Mollie respect what you send (USD, EUR, GBP)
- Razorpay → INR for India, USD/EUR for international cards
- Payme → UZS only

**"My webhook URL changed (different domain)"**
- Update it on the provider's side too — providers don't auto-detect
- Re-register in the provider dashboard

---

## Disconnecting a provider

Click **Disconnect** in the provider's card — keys are wiped from `.env`, the in-memory provider object is cleared, and customers lose that option immediately. Existing subscriptions are not affected.

---

## See also

- [webhook-security.md](webhook-security.md) — webhook pipeline, signature schemes, recovery loop
- [licensing.md](licensing.md) — which providers are unlocked at which license tier
- [troubleshooting.md](troubleshooting.md) — common payment failures and how to debug them
- [Support](mailto:support@flirexa.biz) — if you're stuck after the troubleshooting guide
