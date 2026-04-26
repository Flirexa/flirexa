"""
German locale for VPN Management Studio client Telegram bot.
"""

MESSAGES = {

    # =========================================================================
    # START / WELCOME
    # =========================================================================

    "welcome": (
        "*VPN Manager*\n\n"
        "Willkommen bei unserem VPN-Dienst!\n\n"
        "Sie haben *{client_count}* aktive Verbindung(en).\n"
        "{sub_info}"
        "Wählen Sie eine Aktion:"
    ),

    "welcome_no_sub": (
        "*VPN Manager*\n\n"
        "Willkommen bei unserem VPN-Dienst!\n\n"
        "Sie haben noch kein aktives Abonnement.\n"
        "Wählen Sie einen Plan, um zu beginnen:"
    ),

    "blocked": (
        "Ihr Konto wurde gesperrt. Bitte kontaktieren Sie den Support."
    ),

    # =========================================================================
    # HELP
    # =========================================================================

    "help_text": (
        "*VPN Manager — Hilfe*\n\n"
        "*Hauptbefehle:*\n"
        "/start — Hauptmenü\n"
        "/status — Abonnementstatus\n"
        "/traffic — Datenverbrauch\n"
        "/config — VPN-Konfiguration herunterladen\n\n"
        "*Abonnement:*\n"
        "/plans — Verfügbare Pläne anzeigen\n"
        "/subscribe — Abonnement kaufen\n\n"
        "*Sonstiges:*\n"
        "/support — Support kontaktieren\n"
        "/help — Diese Hilfe\n\n"
        "*So verbinden Sie sich:*\n"
        "1. Kaufen Sie ein Abonnement mit /subscribe\n"
        "2. Wählen Sie einen Plan und schließen Sie die Zahlung ab\n"
        "3. Ihre Konfiguration wird automatisch nach der Zahlung erstellt\n"
        "4. Laden Sie Ihre Konfiguration mit /config herunter\n"
        "5. Installieren Sie die empfohlene App für Ihr Protokoll\n"
        "6. Importieren oder scannen Sie die Konfiguration\n"
        "7. Verbinden und genießen!"
    ),

    # =========================================================================
    # STATUS
    # =========================================================================

    "status_title": "*Abonnementstatus*",

    "status_tier": "Plan: *{tier}*",

    "status_expiry": "Läuft ab: {date}",

    "status_days_left": "Verbleibende Tage: *{days}*",

    "status_devices": "Geräte: {count}",

    "status_no_sub": (
        "Sie haben keine aktiven Verbindungen.\n"
        "{sub_info}\n\n"
        "Verwenden Sie /subscribe, um ein Abonnement zu erhalten."
    ),

    "status_active": "Aktiv",

    "status_disabled": "Deaktiviert",

    "status_client": (
        "*{name}*\n"
        "Status: {status}\n"
        "IP: `{ip}`\n"
        "Traffic: {traffic}\n"
        "Läuft ab: {expiry}"
    ),

    "status_no_expiry": "Kein Ablaufdatum",

    # =========================================================================
    # TRAFFIC
    # =========================================================================

    "traffic_title": "*Traffic-Statistiken*",

    "traffic_used": "Verwendet: *{value}*",

    "traffic_limit": "Limit: *{limit}*",

    "traffic_unlimited": "Unbegrenzt",

    "traffic_percent": "Verwendet: *{percent}%*",

    "traffic_detail": (
        "*Traffic-Statistiken*\n\n"
        "{name}\n\n"
        "Download: {rx}\n"
        "Upload: {tx}\n"
        "Gesamt: {total}"
    ),

    "traffic_with_limit": (
        "\n\nLimit: {limit} MB\n"
        "[{bar}] {percent}%"
    ),

    "traffic_no_sub": "Sie haben keine aktiven Abonnements.",

    # =========================================================================
    # CONFIG
    # =========================================================================

    "config_title": "*VPN-Konfiguration*",

    "config_no_devices": (
        "Sie haben keine aktiven Abonnements.\n\n"
        "Verwenden Sie /subscribe, um ein Abonnement zu erhalten."
    ),

    "config_download": (
        "*Konfigurationsdatei*\n\n"
        "Protokoll: *{protocol}*\n"
        "Empfohlene App: *{app}*\n"
        "Importieren Sie die Datei oder scannen Sie den QR-Code in dieser App."
    ),

    "config_qr_caption": "QR-Code für {name}\n\nProtokoll: *{protocol}*\nMit *{app}* scannen",

    "config_file_caption": "*Konfigurationsdatei*",

    "config_error": "Konfiguration konnte nicht abgerufen werden.",

    # =========================================================================
    # PLANS
    # =========================================================================

    "plans_title": "*Verfügbare Pläne*\n\n",

    "plans_free": "Kostenlos",

    "plans_price": "${price}/Mo.",

    "plans_features": "Funktionen:",

    "plans_devices": "Geräte: *{count}*",

    "plans_traffic": "Traffic: *{value}*",

    "plans_bandwidth": "Geschwindigkeit: bis zu *{mbps} Mbps*",

    "plans_unlimited": "Unbegrenzt",

    "plans_max_speed": "Maximale Geschwindigkeit",

    "plans_unavailable": (
        "Pläne sind vorübergehend nicht verfügbar.\n"
        "Kontakt Support: /support"
    ),

    "plans_subscribe_hint": "\nZum Abonnieren verwenden Sie /subscribe",

    "plans_select_hint": "\nWählen Sie einen Plan für Details:",

    # =========================================================================
    # SUBSCRIBE FLOW
    # =========================================================================

    "subscribe_select_plan": (
        "*Abonnieren*\n\n"
        "Wählen Sie einen Plan:"
    ),

    "subscribe_select_duration": (
        "*{plan_name}*\n\n"
        "Preis: ${price}/Mo.\n"
        "Traffic: {traffic}\n"
        "Geschwindigkeit: {bandwidth}\n"
        "Geräte: {devices}\n"
        "{description}\n"
        "*Abrechnungszeitraum wählen:*"
    ),

    "subscribe_select_currency": (
        "*Zahlungswährung wählen*\n\n"
        "Zeitraum: {duration}\n\n"
        "Kryptowährung wählen:"
    ),

    "subscribe_payment_link": (
        "*Zahlung*\n\n"
        "Plan: {plan}\n"
        "Betrag: *${amount}*\n"
        "Währung: {currency}\n"
        "Zeitraum: {days} Tage\n"
        "{promo_notice}"
        "{test_mode_notice}"
        "\n[Jetzt bezahlen]({url})\n\n"
        "Klicken Sie nach der Zahlung auf die Schaltfläche unten:"
    ),

    "subscribe_promo_discount": (
        "\nPromo *{code}*: -{discount}% → *${amount}*\n"
    ),

    "subscribe_referral_discount": (
        "\n🎁 Empfehlungsrabatt (erster Kauf): -{discount}% → *${amount}*\n"
    ),

    "subscribe_test_mode_notice": (
        "\n*Testmodus:* Zahlung wird vom Administrator bestätigt\n"
    ),

    "subscribe_check_payment": "Zahlung prüfen",

    "subscribe_plan_not_found": "Plan nicht gefunden.",

    "subscribe_duration_monthly": "1 Monat",
    "subscribe_duration_quarterly": "3 Monate",
    "subscribe_duration_yearly": "12 Monate",

    # =========================================================================
    # PAYMENT STATUSES
    # =========================================================================

    "payment_confirmed": (
        "*Zahlung bestätigt!*\n\n"
        "Plan: {plan}\n"
        "Zeitraum: {days} Tage\n\n"
        "{config_ready}"
    ),

    "payment_confirmed_config_ready": "Ihre VPN-Konfiguration ist bereit! Verwenden Sie /config zum Herunterladen.",

    "payment_confirmed_creating": "Ihre Konfiguration wird erstellt...",

    "payment_pending": (
        "*Warten auf Zahlung*\n\n"
        "Plan: {plan}\n"
        "Betrag: ${amount}\n\n"
        "Zahlung wurde noch nicht bestätigt.\n"
        "Klicken Sie nach der Zahlung auf die Schaltfläche unten:"
    ),

    "payment_expired": (
        "*Zahlung abgelaufen*\n\n"
        "Die Rechnung ist abgelaufen. Bitte starten Sie eine neue Bestellung mit /subscribe."
    ),

    "payment_failed": (
        "*Zahlung fehlgeschlagen*\n\n"
        "Etwas ist schiefgelaufen. Bitte versuchen Sie es erneut oder kontaktieren Sie /support."
    ),

    "payment_not_found": "Zahlung nicht gefunden.",

    # =========================================================================
    # SUPPORT
    # =========================================================================

    "support_text": (
        "*Support*\n\n"
        "Schreiben Sie Ihre Nachricht unten und sie wird an unser Support-Team gesendet.\n\n"
        "Schreiben Sie einfach Ihre Nachricht und senden Sie sie:"
    ),

    "support_sent": (
        "*Nachricht gesendet!*\n\n"
        "Ihre Nachricht wurde empfangen. Unser Support-Team wird sie in Kürze überprüfen.\n\n"
        "Ticket #{ticket_id}"
    ),

    "login_enter_email": (
        "Geben Sie Ihre Portal-E-Mail-Adresse ein:"
    ),

    "login_enter_password": (
        "Geben Sie jetzt Ihr Passwort ein:"
    ),

    "login_success": (
        "*Konto verknüpft!*\n\n"
        "Ihr Telegram ist jetzt mit dem Portal-Konto *{email}* verbunden."
    ),

    "login_failed": (
        "Falsche E-Mail oder Passwort. Versuchen Sie es erneut mit /start."
    ),

    "login_already_linked": (
        "Dieses Konto ist bereits mit einem anderen Telegram-Benutzer verknüpft."
    ),

    "account_credentials": (
        "*Ihr VPN-Portal-Konto*\n\n"
        "E-Mail: `{email}`\n"
        "Passwort: `{password}`\n"
        "Portal: {portal_url}\n\n"
        "Speichern Sie diese Zugangsdaten!"
    ),

    # =========================================================================
    # MAIN MENU BUTTONS
    # =========================================================================

    "menu_status": "Mein Status",
    "menu_traffic": "Traffic",
    "menu_config": "Konfiguration",
    "menu_plans": "Pläne",
    "menu_subscribe": "Abonnieren",
    "menu_support": "Support",
    "menu_lang": "Sprache",
    "menu_referral": "Empfehlung",
    "menu_have_account": "Ich habe ein Konto",
    "download_app_removed": "Verwenden Sie /config, um Ihre VPN-Konfiguration zu erhalten. Der Bot empfiehlt jetzt die Standard-App für Ihr Protokoll.",
    "app_links_title": "*Empfohlene VPN-Apps*\n\nWählen Sie die passende App für Ihr Protokoll und Ihre Plattform:\n\n",
    "app_links_entry": "• *{protocol}* → *{app}*\n",
    "menu_hint": "Verwenden Sie die Schaltflächen unten zur Navigation.",
    "plans_devices_short": "Ger.",
    "menu_hide_keyboard": "Tastatur ausblenden",
    "keyboard_hidden": "Tastatur ausgeblendet. Geben Sie /start ein, um sie wieder anzuzeigen.",

    # =========================================================================
    # COMMON BUTTONS
    # =========================================================================

    "btn_back": "Zurück",
    "btn_back_to_plans": "Zurück zu den Plänen",
    "btn_back_to_menu": "Hauptmenü",
    "btn_refresh": "Aktualisieren",
    "btn_pay": "Jetzt bezahlen",
    "btn_check_payment": "Zahlung prüfen",
    "btn_download_config": "Konfiguration herunterladen",
    "btn_delete_device": "Gerät löschen",
    "btn_confirm_delete": "Ja, löschen",

    # =========================================================================
    # PROMO CODES
    # =========================================================================

    "promo_enter": "Verwendung: /promo CODE\n\nBeispiel: /promo SAVE20",

    "promo_invalid": "Ungültiger Promo-Code. Bitte prüfen und erneut versuchen.",

    "promo_applied": (
        "*Promo-Code {code} angewendet!*\n\n"
        "Bonus: *{value}*"
    ),

    "promo_already_used": "Sie haben diesen Promo-Code bereits verwendet.",

    # =========================================================================
    # REFERRAL PROGRAM
    # =========================================================================

    "ref_title": "*Empfehlungsprogramm*",

    "ref_code": "Ihr Empfehlungscode: `{code}`",

    "ref_link": "Ihr Empfehlungslink: {link}",

    "ref_count": "Geworbene Freunde: *{count}*",

    "ref_share": (
        "*Empfehlungsprogramm*\n\n"
        "Ihr Empfehlungscode: `{code}`\n"
        "Ihr Empfehlungslink:\n{link}\n\n"
        "Geworbene Freunde: *{count}*\n\n"
        "Teilen Sie den Link und verdienen Sie Boni für jeden neuen Abonnenten!"
    ),

    # =========================================================================
    # LANGUAGE SELECTION
    # =========================================================================

    "lang_changed": "Sprache auf *Deutsch* geändert.",

    "lang_select": (
        "*Sprache wählen*\n\n"
        "Wählen Sie Ihre bevorzugte Sprache:"
    ),

    # =========================================================================
    # DEVICE / CONFIG MANAGEMENT
    # =========================================================================

    "device_create": (
        "*Neues Gerät erstellen*\n\n"
        "Geben Sie einen Namen für das neue Gerät ein (z.B. `Mein Telefon`):"
    ),

    "device_select_server": (
        "*Neues Gerät erstellen*\n\n"
        "Wählen Sie Server und Protokoll für das neue Gerät:"
    ),

    "device_create_for_server": (
        "*Neues Gerät erstellen*\n\n"
        "Server: *{server}*\n"
        "Protokoll: *{protocol}*\n\n"
        "Geben Sie jetzt einen Namen für das neue Gerät ein (z.B. `Mein Telefon`):"
    ),

    "device_created": (
        "*Gerät erstellt!*\n\n"
        "Name: `{name}`\n"
        "Server: *{server}*\n"
        "Protokoll: *{protocol}*\n\n"
        "Verwenden Sie /config, um die Konfiguration herunterzuladen."
    ),

    "device_limit_reached": (
        "*Gerätelimit erreicht*\n\n"
        "Ihr Plan erlaubt maximal *{max}* Gerät(e).\n"
        "Upgraden Sie Ihren Plan, um mehr Geräte hinzuzufügen."
    ),

    "menu_add_device": "Gerät hinzufügen",

    "device_create_failed": (
        "Gerät konnte nicht erstellt werden. Bitte erneut versuchen oder /support kontaktieren."
    ),

    "device_no_servers": "Derzeit sind keine Server verfügbar. Bitte später erneut versuchen oder /support kontaktieren.",
    "device_server_not_found": "Der ausgewählte Server wurde nicht gefunden. Bitte starten Sie die Geräteerstellung erneut.",

    "no_subscription_for_device": (
        "Sie benötigen ein aktives Abonnement, um ein Gerät zu erstellen.\n"
        "Verwenden Sie /subscribe, um zu beginnen."
    ),

    "device_delete_confirm": (
        "Gerät *{name}* löschen?\n\n"
        "Dadurch wird das Gerät dauerhaft entfernt und der WireGuard-Schlüssel widerrufen."
    ),

    "device_deleted": (
        "*Gerät gelöscht*\n\n"
        "*{name}* wurde von Ihrem Konto entfernt."
    ),

    "device_delete_failed": "Gerät konnte nicht gelöscht werden. Bitte erneut versuchen oder /support kontaktieren.",

    "traffic_select_device": "*Gerät auswählen* um Traffic anzuzeigen:",

    "config_select_device": "*Gerät auswählen* um Konfiguration herunterzuladen:",

    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================

    "notify_expiry_warning": (
        "*Ihr Abonnement läuft bald ab!*\n\n"
        "Ihr *{tier}*-Plan läuft in *{days}* Tag(en) ab "
        "(am {date}).\n\n"
        "Verlängern Sie jetzt, um Unterbrechungen zu vermeiden: /subscribe"
    ),

    "notify_traffic_warning": (
        "*Traffic-Limit fast erreicht!*\n\n"
        "Sie haben *{percent}%* Ihres monatlichen Traffics verbraucht.\n"
        "Verbleibend: *{remaining}*\n\n"
        "Upgraden Sie Ihren Plan für mehr Traffic: /subscribe"
    ),

    "notify_payment_confirmed": (
        "*Zahlung bestätigt!*\n\n"
        "Ihr *{tier}*-Abonnement wurde aktiviert.\n"
        "Zeitraum: *{days}* Tage (bis {date}).\n\n"
        "Laden Sie Ihre VPN-Konfiguration herunter: /config"
    ),
}
