# Webhook Security & Payment Pipeline

This document describes how VPN Management Studio receives, verifies and processes payment notifications from each provider — and what stops a customer from ever ending up in "I paid, my subscription didn't activate".

If you just want to set up a provider, see [payment-setup.md](payment-setup.md). This page is for understanding the safety guarantees.

---

## The pipeline at a glance

```
┌──────────────┐  1) Subscribe       ┌──────────────────┐
│  Customer    │ ───────────────────►│  Client Portal   │
└──────────────┘                     └──────────────────┘
                                              │ 2) create_invoice (provider API)
                                              ▼
                                     ┌──────────────────┐
                                     │   Provider       │
                                     │  (Stripe, …)     │
                                     └──────────────────┘
       3) pay  ▲                              │ 4) signed webhook
               │                              ▼
┌──────────────────┐               ┌────────────────────────┐
│  Provider        │ ◄─── 8) status check ─── │  spongebot-api  │
│  checkout page   │   (recovery poller)      │ /client-portal/  │
└──────────────────┘                          │  webhooks/X       │
                                              └────────────────────────┘
                                                     │ 5) verify signature
                                                     │ 6) complete_payment (idempotent, row-locked)
                                                     │ 7) upgrade_subscription + sync WG limits
```

### Why every step matters

1. **Subscribe** — the customer chooses a provider in the Billing page. Backend filters this list by license tier (free → only NOWPayments).
2. **create_invoice** — backend posts to the provider's API. Stores a row in `client_portal_payments` with `status='pending'`, our generated `invoice_id`, and the provider's external ID in `provider_invoice_id`.
3. **Customer pays** at the provider's hosted checkout.
4. **Webhook** — provider POSTs to `/client-portal/webhooks/<provider>` with a signed body.
5. **Signature verification** — see the per-provider scheme below. Bad signature → `401 Unauthorized`, no credit.
6. **complete_payment()** is idempotent. It uses `SELECT … FOR UPDATE` plus a `status == 'completed'` re-check inside the lock, so duplicate webhooks (providers retry) cannot double-credit.
7. **Subscription upgrade** — plan, expiry, device limit, traffic counters, WG client lifecycle — all applied atomically.
8. **Recovery poller** runs every 60 s in the monitoring loop and asks each provider "is this pending invoice paid?". Self-heals dropped webhooks.

---

## Signature schemes per provider

| Provider | Header | Algorithm | What's signed | Reference |
|---|---|---|---|---|
| **NOWPayments** | `x-nowpayments-sig` | HMAC-SHA512 | sorted JSON body | [docs](https://documenter.getpostman.com/view/7907941/S1a32n38#instant-payments-notifications) |
| **CryptoPay** | `crypto-pay-api-signature` | HMAC-SHA256 | raw body, key = SHA256(api_token) | [docs](https://help.crypt.bot/crypto-pay-api) |
| **PayPal** | `paypal-transmission-sig` + 4 more | RSA via PayPal API | full event JSON | [docs](https://developer.paypal.com/api/rest/webhooks/rest/) |
| **Stripe** | `Stripe-Signature` | HMAC-SHA256, prefix `t=ts,v1=` | `ts.body` | [docs](https://stripe.com/docs/webhooks/signatures) |
| **Razorpay** | `X-Razorpay-Signature` | HMAC-SHA256 | raw body | [docs](https://razorpay.com/docs/webhooks/validate-test/) |
| **Mollie** | (none — by design) | API call-back with payment ID | n/a | [docs](https://docs.mollie.com/payments/webhook) |
| **Payme** | `Authorization: Basic` | base64("Paycom":secret_key) | header only | [docs](https://developer.help.paycom.uz/protokol-merchant-api/) |

A few important properties of these schemes:

- **NOWPayments** signs the *sorted-keys* JSON, not the original body. We resort and recompute before comparing — exactly what their reference Python code does.
- **Stripe** has a built-in 5-minute timestamp tolerance. We use the official SDK's `Webhook.construct_event(body, sig_header, secret)` which both verifies the HMAC and rejects stale events.
- **PayPal** doesn't sign locally — verification means calling PayPal's `/v1/notifications/verify-webhook-signature` endpoint with all the original headers. This requires you to register a Webhook in the PayPal app and put the resulting Webhook ID into our admin panel.
- **Mollie** webhooks contain only the payment ID. Verification = we call Mollie's API back ("is this payment paid?"). A forged webhook can't fake a real Mollie payment ID.
- **Payme** uses HTTP Basic Auth as its sole verification — the merchant secret IS the credential.

If you ever need to add a new provider, mirror one of these patterns. Plugin contract is in `plugins/payments/_template.py`.

---

## Idempotency: why duplicate webhooks are safe

Providers retry webhooks until they get a 200. That means we'll often receive the same `payment_status=finished` event 2–5 times.

`complete_payment()` (in `src/modules/subscription/subscription_manager.py`) is built to handle this:

```python
def complete_payment(self, invoice_id, …):
    # 1) Acquire row-level lock (PostgreSQL SELECT FOR UPDATE)
    payment = db.query(ClientPortalPayment) \
        .filter(invoice_id == invoice_id) \
        .with_for_update() \
        .first()

    # 2) Re-check status INSIDE the lock — concurrent webhook will see "completed"
    if payment.status == "completed":
        return True   # idempotent no-op

    # 3) Mark completed, upgrade subscription, sync WG, commit
    …
```

The `with_for_update()` translates to `SELECT … FOR UPDATE` on PostgreSQL. The second webhook arriving in parallel waits until the first releases the lock, then sees `status='completed'` and exits cleanly. SQLite degrades gracefully — the in-process row check is enough for non-prod use.

Promo code usage counters are incremented with raw SQL (`UPDATE … SET used_count = COALESCE(used_count, 0) + 1`) instead of the ORM read-modify-write pattern, so concurrent webhooks can't lose increments.

---

## Recovery poller: dropped webhooks self-heal

Webhooks can be lost — provider had a hiccup, our service restarted between the HTTPS handshake and DB commit, the network blipped. Without a recovery, that customer's payment hangs in `pending` forever.

The monitoring loop (`src/api/scheduler.py:_try_recover_pending_payments`) runs every 60 s and:

1. Selects rows where `status='pending'` AND `created_at <= now − 15 s` (15 s is the head start we give to the live webhook path so we don't race normal completion).
2. For each row, calls the provider's `check_payment(provider_invoice_id)`.
3. If the provider returns `COMPLETED`, runs the same `complete_payment()` path the webhook would have. Idempotent — even if the original webhook arrives later, no double credit.

This catches the rare edge case where a webhook never lands. You'll see `Recovered dropped-webhook payment: invoice=… provider=… user=…` in the API logs.

---

## What's NOT covered automatically

These are the cases where the system can't help and a human (you) must act:

- **Provider sent a refund**. We log it and mark the payment as `refunded`, but we DON'T downgrade the subscription. Behaviour is your business call — if you want to revoke access on refund, you can wire that in `complete_payment` or use the admin panel manually.
- **Customer paid the wrong amount** (under-payment, NOWPayments `partially_paid`). We treat these as `FAILED` and DON'T credit. Customer needs to either pay again or contact support.
- **Provider keys rotated and you forgot to update one side**. Webhook signature verification will start returning 401, but the subscription create-invoice flow will fail differently. Run **Test** in the admin panel — it'll tell you which side is out of sync.
- **Long-tail provider downtime**. If the provider is down for 6+ hours, the `pending` payment is logged with a louder warning every monitoring cycle. You can manually mark `completed` from the admin panel after confirming with the provider.

---

## Logs to check

When something looks off, these are the most useful greps:

```bash
# All webhook traffic
journalctl -u spongebot-api -n 500 | grep -iE 'webhook|complete_payment|signature'

# Per-provider
journalctl -u spongebot-api -n 500 | grep -iE 'nowpayments|cryptopay|paypal|stripe|razorpay|mollie|payme'

# Recovery poller activity
journalctl -u spongebot-api -n 500 | grep -iE 'recover.*payment|stuck.*pending'

# Subscriptions activated in last hour
journalctl -u spongebot-api --since "1 hour ago" | grep -iE 'subscription.*upgraded|subscription.*activated'
```

---

## Tools shipped with the system

- **`tools/test_webhook_signatures.py`** — offline unit tests of every provider's signature verification with known-good and known-bad inputs. Runs in ~1 s. Use after upgrading the package or modifying a plugin.
- **`tools/simulate_payments.py`** — end-to-end integration test that POSTs signed webhook payloads to the live API. Verifies a real `pending → completed` transition. Runs against a configured environment (env vars must be set).
- The **Test** button in the admin panel runs the same logic as `test_webhook_signatures.py` for one provider, in-process. Output renders as a green/red checklist under the provider card.

All three tools test the same security-critical paths. The unit one is fastest, the simulator most realistic, the admin button most discoverable.

---

## Auditing your own deployment

Quick checklist before going live:

- [ ] Each provider you've enabled has its **Webhook URL registered** at the provider's dashboard (not just our admin panel)
- [ ] Each provider's **Webhook Secret** in admin matches what's set at the provider
- [ ] **Test** button in admin shows green for every active provider
- [ ] `tools/simulate_payments.py` passes (run it from the API host)
- [ ] You've made one real low-amount test transaction for each provider you enabled
- [ ] You've verified the recovery poller works: kill the API service, pay a test invoice, restart the API, wait 60s, see the payment auto-complete

If all six tick, you're safe to take real customer money.
