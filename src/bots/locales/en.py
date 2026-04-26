"""
English locale for VPN Management Studio client Telegram bot.

Usage:
    from src.bots.locales.en import MESSAGES
    text = MESSAGES["welcome"].format(name="Alice")
"""

MESSAGES = {

    # =========================================================================
    # START / WELCOME
    # =========================================================================

    "welcome": (
        "*VPN Manager*\n\n"
        "Welcome to our VPN service!\n\n"
        "You have *{client_count}* active connection(s).\n"
        "{sub_info}"
        "Choose an action:"
    ),

    "welcome_no_sub": (
        "*VPN Manager*\n\n"
        "Welcome to our VPN service!\n\n"
        "You don't have an active subscription yet.\n"
        "Pick a plan to get started:"
    ),

    "blocked": (
        "Your account has been blocked. Please contact support."
    ),

    # =========================================================================
    # HELP
    # =========================================================================

    "help_text": (
        "*VPN Manager — Help*\n\n"
        "*Main commands:*\n"
        "/start — Main menu\n"
        "/status — Subscription status\n"
        "/traffic — Traffic usage\n"
        "/config — Download VPN config\n\n"
        "*Subscription:*\n"
        "/plans — View available plans\n"
        "/subscribe — Purchase a subscription\n\n"
        "*Other:*\n"
        "/support — Contact support\n"
        "/help — This help message\n\n"
        "*How to connect:*\n"
        "1. Purchase a subscription with /subscribe\n"
        "2. Select a plan and complete payment\n"
        "3. Your config is created automatically after payment\n"
        "4. Download your config with /config\n"
        "5. Install the recommended client app for your protocol\n"
        "6. Import or scan the configuration\n"
        "7. Connect and enjoy!"
    ),

    # =========================================================================
    # STATUS
    # =========================================================================

    "status_title": "*Subscription Status*",

    "status_tier": "Plan: *{tier}*",

    "status_expiry": "Expires: {date}",

    "status_days_left": "Days left: *{days}*",

    "status_devices": "Devices: {count}",

    "status_no_sub": (
        "You have no active connections.\n"
        "{sub_info}\n\n"
        "Use /subscribe to get a subscription."
    ),

    "status_active": "Active",

    "status_disabled": "Disabled",

    "status_client": (
        "*{name}*\n"
        "Status: {status}\n"
        "IP: `{ip}`\n"
        "Traffic: {traffic}\n"
        "Expires: {expiry}"
    ),

    "status_no_expiry": "No expiry",

    # =========================================================================
    # TRAFFIC
    # =========================================================================

    "traffic_title": "*Traffic Statistics*",

    "traffic_used": "Used: *{value}*",

    "traffic_limit": "Limit: *{limit}*",

    "traffic_unlimited": "Unlimited",

    "traffic_percent": "Used: *{percent}%*",

    "traffic_detail": (
        "*Traffic Statistics*\n\n"
        "{name}\n\n"
        "Download: {rx}\n"
        "Upload: {tx}\n"
        "Total: {total}"
    ),

    "traffic_with_limit": (
        "\n\nLimit: {limit} MB\n"
        "[{bar}] {percent}%"
    ),

    "traffic_no_sub": "You have no active subscriptions.",

    # =========================================================================
    # CONFIG
    # =========================================================================

    "config_title": "*VPN Configuration*",

    "config_no_devices": (
        "You have no active subscriptions.\n\n"
        "Use /subscribe to get a subscription."
    ),

    "config_download": (
        "*Configuration File*\n\n"
        "Protocol: *{protocol}*\n"
        "Recommended client: *{app}*\n"
        "Import the attached file or scan the QR code in that app."
    ),

    "config_qr_caption": "QR code for {name}\n\nProtocol: *{protocol}*\nScan with *{app}*",

    "config_file_caption": "*Configuration file*",

    "config_error": "Could not retrieve the configuration.",

    # =========================================================================
    # PLANS
    # =========================================================================

    "plans_title": "*Available Plans*\n\n",

    "plans_free": "Free",

    "plans_price": "${price}/mo",

    "plans_features": "Features:",

    "plans_devices": "Devices: *{count}*",

    "plans_traffic": "Traffic: *{value}*",

    "plans_bandwidth": "Speed: up to *{mbps} Mbps*",

    "plans_unlimited": "Unlimited",

    "plans_max_speed": "Maximum speed",

    "plans_unavailable": (
        "Plans are temporarily unavailable.\n"
        "Contact support: /support"
    ),

    "plans_subscribe_hint": "\nTo subscribe use /subscribe",

    "plans_select_hint": "\nSelect a plan for details:",

    # =========================================================================
    # SUBSCRIBE FLOW
    # =========================================================================

    "subscribe_select_plan": (
        "*Subscribe*\n\n"
        "Select a plan:"
    ),

    "subscribe_select_duration": (
        "*{plan_name}*\n\n"
        "Price: ${price}/mo\n"
        "Traffic: {traffic}\n"
        "Speed: {bandwidth}\n"
        "Devices: {devices}\n"
        "{description}\n"
        "*Choose billing period:*"
    ),

    "subscribe_select_currency": (
        "*Select payment currency*\n\n"
        "Period: {duration}\n\n"
        "Choose cryptocurrency:"
    ),

    "subscribe_payment_link": (
        "*Payment*\n\n"
        "Plan: {plan}\n"
        "Amount: *${amount}*\n"
        "Currency: {currency}\n"
        "Period: {days} days\n"
        "{promo_notice}"
        "{test_mode_notice}"
        "\n[Pay now]({url})\n\n"
        "Click the button below after completing payment:"
    ),

    "subscribe_promo_discount": (
        "\nPromo *{code}*: -{discount}% → *${amount}*\n"
    ),

    "subscribe_referral_discount": (
        "\n🎁 Referral discount (first purchase): -{discount}% → *${amount}*\n"
    ),

    "subscribe_test_mode_notice": (
        "\n*Test mode:* payment will be confirmed by the administrator\n"
    ),

    "subscribe_check_payment": "Check payment",

    "subscribe_plan_not_found": "Plan not found.",

    "subscribe_duration_monthly": "1 month",
    "subscribe_duration_quarterly": "3 months",
    "subscribe_duration_yearly": "12 months",

    # =========================================================================
    # PAYMENT STATUSES
    # =========================================================================

    "payment_confirmed": (
        "*Payment confirmed!*\n\n"
        "Plan: {plan}\n"
        "Period: {days} days\n\n"
        "{config_ready}"
    ),

    "payment_confirmed_config_ready": "Your VPN config is ready! Use /config to download it.",

    "payment_confirmed_creating": "Your configuration is being created...",

    "payment_pending": (
        "*Waiting for payment*\n\n"
        "Plan: {plan}\n"
        "Amount: ${amount}\n\n"
        "Payment has not been confirmed yet.\n"
        "Click the button below after paying:"
    ),

    "payment_expired": (
        "*Payment expired*\n\n"
        "The invoice has expired. Please start a new order with /subscribe."
    ),

    "payment_failed": (
        "*Payment failed*\n\n"
        "Something went wrong. Please try again or contact /support."
    ),

    "payment_not_found": "Payment not found.",

    # =========================================================================
    # SUPPORT
    # =========================================================================

    "support_text": (
        "*Support*\n\n"
        "Write your message below and it will be sent to our support team for review.\n\n"
        "Simply type your message and send it:"
    ),

    "support_sent": (
        "*Message sent!*\n\n"
        "Your message has been received. Our support team will review it shortly.\n\n"
        "Ticket #{ticket_id}"
    ),

    "login_enter_email": (
        "Enter your portal email address:"
    ),

    "login_enter_password": (
        "Now enter your password:"
    ),

    "login_success": (
        "*Account linked!*\n\n"
        "Your Telegram is now connected to the portal account *{email}*."
    ),

    "login_failed": (
        "Wrong email or password. Try again with /start."
    ),

    "login_already_linked": (
        "This account is already linked to another Telegram user."
    ),

    "account_credentials": (
        "*Your VPN Portal account*\n\n"
        "Email: `{email}`\n"
        "Password: `{password}`\n"
        "Portal: {portal_url}\n\n"
        "Save these credentials!"
    ),

    # =========================================================================
    # MAIN MENU BUTTONS
    # =========================================================================

    "menu_status": "My Status",
    "menu_traffic": "Traffic",
    "menu_config": "Config",
    "menu_plans": "Plans",
    "menu_subscribe": "Subscribe",
    "menu_support": "Support",
    "menu_lang": "Language",
    "menu_referral": "Referral",
    "menu_have_account": "I have an account",
    "download_app_removed": "Use /config to get your VPN config. The bot now recommends the standard client app for your protocol.",
    "app_links_title": "*Recommended VPN apps*\n\nChoose the correct app for your protocol and platform:\n\n",
    "app_links_entry": "• *{protocol}* → *{app}*\n",
    "menu_hint": "Use the buttons below to navigate.",
    "plans_devices_short": "dev.",
    "menu_hide_keyboard": "Hide keyboard",
    "keyboard_hidden": "Keyboard hidden. Type /start to show it again.",

    # =========================================================================
    # COMMON BUTTONS
    # =========================================================================

    "btn_back": "Back",
    "btn_back_to_plans": "Back to Plans",
    "btn_back_to_menu": "Main Menu",
    "btn_refresh": "Refresh",
    "btn_pay": "Pay Now",
    "btn_check_payment": "Check Payment",
    "btn_download_config": "Download Config",
    "btn_delete_device": "Delete Device",
    "btn_confirm_delete": "Yes, delete",

    # =========================================================================
    # PROMO CODES
    # =========================================================================

    "promo_enter": "Usage: /promo CODE\n\nExample: /promo SAVE20",

    "promo_invalid": "Invalid promo code. Please check and try again.",

    "promo_applied": (
        "*Promo code {code} applied!*\n\n"
        "Bonus: *{value}*"
    ),

    "promo_already_used": "You have already used this promo code.",

    # =========================================================================
    # REFERRAL PROGRAM
    # =========================================================================

    "ref_title": "*Referral Program*",

    "ref_code": "Your referral code: `{code}`",

    "ref_link": "Your referral link: {link}",

    "ref_count": "Friends referred: *{count}*",

    "ref_share": (
        "*Referral Program*\n\n"
        "Your referral code: `{code}`\n"
        "Your referral link:\n{link}\n\n"
        "Friends referred: *{count}*\n\n"
        "Share the link and earn bonuses for each new subscriber!"
    ),

    # =========================================================================
    # LANGUAGE SELECTION
    # =========================================================================

    "lang_changed": "Language changed to *English*.",

    "lang_select": (
        "*Select language*\n\n"
        "Choose your preferred language:"
    ),

    # =========================================================================
    # DEVICE / CONFIG MANAGEMENT
    # =========================================================================

    "device_create": (
        "*Create new device*\n\n"
        "Enter a name for the new device (e.g. `My Phone`):"
    ),

    "device_select_server": (
        "*Create new device*\n\n"
        "Select the server and protocol for the new device:"
    ),

    "device_create_for_server": (
        "*Create new device*\n\n"
        "Server: *{server}*\n"
        "Protocol: *{protocol}*\n\n"
        "Now enter a name for the new device (e.g. `My Phone`):"
    ),

    "device_created": (
        "*Device created!*\n\n"
        "Name: `{name}`\n"
        "Server: *{server}*\n"
        "Protocol: *{protocol}*\n\n"
        "Use /config to download the configuration."
    ),

    "device_limit_reached": (
        "*Device limit reached*\n\n"
        "Your plan allows a maximum of *{max}* device(s).\n"
        "Upgrade your plan to add more devices."
    ),

    "menu_add_device": "Add Device",

    "device_create_failed": (
        "Failed to create the device. Please try again or contact /support."
    ),

    "device_no_servers": "No servers are available right now. Please try again later or contact /support.",
    "device_server_not_found": "The selected server was not found. Please start the device creation again.",

    "no_subscription_for_device": (
        "You need an active subscription to create a device.\n"
        "Use /subscribe to get started."
    ),

    "device_delete_confirm": (
        "Delete device *{name}*?\n\n"
        "This will permanently remove the device and revoke the WireGuard key."
    ),

    "device_deleted": (
        "*Device deleted*\n\n"
        "*{name}* has been removed from your account."
    ),

    "device_delete_failed": "Failed to delete the device. Please try again or contact /support.",

    "traffic_select_device": "*Select device* to view traffic:",

    "config_select_device": "*Select device* to download config:",

    # =========================================================================
    # NOTIFICATIONS  (sent proactively to the user)
    # =========================================================================

    "notify_expiry_warning": (
        "*Your subscription is expiring soon!*\n\n"
        "Your *{tier}* plan expires in *{days}* day(s) "
        "(on {date}).\n\n"
        "Renew now to avoid interruption: /subscribe"
    ),

    "notify_traffic_warning": (
        "*Traffic limit almost reached!*\n\n"
        "You have used *{percent}%* of your monthly traffic.\n"
        "Remaining: *{remaining}*\n\n"
        "Upgrade your plan to get more traffic: /subscribe"
    ),

    "notify_payment_confirmed": (
        "*Payment confirmed!*\n\n"
        "Your *{tier}* subscription has been activated.\n"
        "Period: *{days}* days (until {date}).\n\n"
        "Download your VPN config: /config"
    ),
}
