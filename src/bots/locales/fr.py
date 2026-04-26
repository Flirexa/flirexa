"""
French locale for VPN Management Studio client Telegram bot.
"""

MESSAGES = {

    # =========================================================================
    # START / WELCOME
    # =========================================================================

    "welcome": (
        "*VPN Manager*\n\n"
        "Bienvenue dans notre service VPN !\n\n"
        "Vous avez *{client_count}* connexion(s) active(s).\n"
        "{sub_info}"
        "Choisissez une action :"
    ),

    "welcome_no_sub": (
        "*VPN Manager*\n\n"
        "Bienvenue dans notre service VPN !\n\n"
        "Vous n'avez pas encore d'abonnement actif.\n"
        "Choisissez un plan pour commencer :"
    ),

    "blocked": (
        "Votre compte a été bloqué. Veuillez contacter le support."
    ),

    # =========================================================================
    # HELP
    # =========================================================================

    "help_text": (
        "*VPN Manager — Aide*\n\n"
        "*Commandes principales :*\n"
        "/start — Menu principal\n"
        "/status — État de l'abonnement\n"
        "/traffic — Utilisation du trafic\n"
        "/config — Télécharger la configuration VPN\n\n"
        "*Abonnement :*\n"
        "/plans — Voir les plans disponibles\n"
        "/subscribe — Acheter un abonnement\n\n"
        "*Autre :*\n"
        "/support — Contacter le support\n"
        "/help — Ce message d'aide\n\n"
        "*Comment se connecter :*\n"
        "1. Achetez un abonnement avec /subscribe\n"
        "2. Sélectionnez un plan et effectuez le paiement\n"
        "3. Votre configuration est créée automatiquement après le paiement\n"
        "4. Téléchargez votre configuration avec /config\n"
        "5. Installez l’application recommandée pour votre protocole\n"
        "6. Importez la configuration ou scannez le QR code\n"
        "7. Connectez-vous et profitez !"
    ),

    # =========================================================================
    # STATUS
    # =========================================================================

    "status_title": "*État de l'Abonnement*",

    "status_tier": "Plan : *{tier}*",

    "status_expiry": "Expire le : {date}",

    "status_days_left": "Jours restants : *{days}*",

    "status_devices": "Appareils : {count}",

    "status_no_sub": (
        "Vous n'avez pas de connexions actives.\n"
        "{sub_info}\n\n"
        "Utilisez /subscribe pour obtenir un abonnement."
    ),

    "status_active": "Actif",

    "status_disabled": "Désactivé",

    "status_client": (
        "*{name}*\n"
        "Statut : {status}\n"
        "IP : `{ip}`\n"
        "Trafic : {traffic}\n"
        "Expire le : {expiry}"
    ),

    "status_no_expiry": "Pas d'expiration",

    # =========================================================================
    # TRAFFIC
    # =========================================================================

    "traffic_title": "*Statistiques de Trafic*",

    "traffic_used": "Utilisé : *{value}*",

    "traffic_limit": "Limite : *{limit}*",

    "traffic_unlimited": "Illimité",

    "traffic_percent": "Utilisé : *{percent}%*",

    "traffic_detail": (
        "*Statistiques de Trafic*\n\n"
        "{name}\n\n"
        "Téléchargement : {rx}\n"
        "Envoi : {tx}\n"
        "Total : {total}"
    ),

    "traffic_with_limit": (
        "\n\nLimite : {limit} Mo\n"
        "[{bar}] {percent}%"
    ),

    "traffic_no_sub": "Vous n'avez pas d'abonnements actifs.",

    # =========================================================================
    # CONFIG
    # =========================================================================

    "config_title": "*Configuration VPN*",

    "config_no_devices": (
        "Vous n'avez pas d'abonnements actifs.\n\n"
        "Utilisez /subscribe pour obtenir un abonnement."
    ),

    "config_download": (
        "*Fichier de Configuration*\n\n"
        "Protocole : *{protocol}*\n"
        "Application recommandée : *{app}*\n"
        "Importez le fichier joint ou scannez le QR code dans cette application."
    ),

    "config_qr_caption": "Code QR pour {name}\n\nProtocole : *{protocol}*\nScannez avec *{app}*",

    "config_file_caption": "*Fichier de configuration*",

    "config_error": "Impossible de récupérer la configuration.",

    # =========================================================================
    # PLANS
    # =========================================================================

    "plans_title": "*Plans Disponibles*\n\n",

    "plans_free": "Gratuit",

    "plans_price": "${price}/mois",

    "plans_features": "Fonctionnalités :",

    "plans_devices": "Appareils : *{count}*",

    "plans_traffic": "Trafic : *{value}*",

    "plans_bandwidth": "Vitesse : jusqu'à *{mbps} Mbps*",

    "plans_unlimited": "Illimité",

    "plans_max_speed": "Vitesse maximale",

    "plans_unavailable": (
        "Les plans sont temporairement indisponibles.\n"
        "Contactez le support : /support"
    ),

    "plans_subscribe_hint": "\nPour vous abonner utilisez /subscribe",

    "plans_select_hint": "\nSélectionnez un plan pour les détails :",

    # =========================================================================
    # SUBSCRIBE FLOW
    # =========================================================================

    "subscribe_select_plan": (
        "*S'abonner*\n\n"
        "Sélectionnez un plan :"
    ),

    "subscribe_select_duration": (
        "*{plan_name}*\n\n"
        "Prix : ${price}/mois\n"
        "Trafic : {traffic}\n"
        "Vitesse : {bandwidth}\n"
        "Appareils : {devices}\n"
        "{description}\n"
        "*Choisissez la période de facturation :*"
    ),

    "subscribe_select_currency": (
        "*Sélectionnez la devise de paiement*\n\n"
        "Période : {duration}\n\n"
        "Choisissez une cryptomonnaie :"
    ),

    "subscribe_payment_link": (
        "*Paiement*\n\n"
        "Plan : {plan}\n"
        "Montant : *${amount}*\n"
        "Devise : {currency}\n"
        "Période : {days} jours\n"
        "{promo_notice}"
        "{test_mode_notice}"
        "\n[Payer maintenant]({url})\n\n"
        "Cliquez sur le bouton ci-dessous après avoir effectué le paiement :"
    ),

    "subscribe_promo_discount": (
        "\nPromo *{code}* : -{discount}% → *${amount}*\n"
    ),

    "subscribe_referral_discount": (
        "\n🎁 Réduction parrainage (premier achat) : -{discount}% → *${amount}*\n"
    ),

    "subscribe_test_mode_notice": (
        "\n*Mode test :* le paiement sera confirmé par l'administrateur\n"
    ),

    "subscribe_check_payment": "Vérifier le paiement",

    "subscribe_plan_not_found": "Plan introuvable.",

    "subscribe_duration_monthly": "1 mois",
    "subscribe_duration_quarterly": "3 mois",
    "subscribe_duration_yearly": "12 mois",

    # =========================================================================
    # PAYMENT STATUSES
    # =========================================================================

    "payment_confirmed": (
        "*Paiement confirmé !*\n\n"
        "Plan : {plan}\n"
        "Période : {days} jours\n\n"
        "{config_ready}"
    ),

    "payment_confirmed_config_ready": "Votre configuration VPN est prête ! Utilisez /config pour la télécharger.",

    "payment_confirmed_creating": "Votre configuration est en cours de création...",

    "payment_pending": (
        "*En attente de paiement*\n\n"
        "Plan : {plan}\n"
        "Montant : ${amount}\n\n"
        "Le paiement n'a pas encore été confirmé.\n"
        "Cliquez sur le bouton ci-dessous après avoir payé :"
    ),

    "payment_expired": (
        "*Paiement expiré*\n\n"
        "La facture a expiré. Veuillez passer une nouvelle commande avec /subscribe."
    ),

    "payment_failed": (
        "*Paiement échoué*\n\n"
        "Une erreur s'est produite. Veuillez réessayer ou contacter /support."
    ),

    "payment_not_found": "Paiement introuvable.",

    # =========================================================================
    # SUPPORT
    # =========================================================================

    "support_text": (
        "*Support*\n\n"
        "Écrivez votre message ci-dessous et il sera envoyé à notre équipe de support.\n\n"
        "Écrivez simplement votre message et envoyez-le :"
    ),

    "support_sent": (
        "*Message envoyé !*\n\n"
        "Votre message a été reçu. Notre équipe de support l'examinera prochainement.\n\n"
        "Ticket #{ticket_id}"
    ),

    "login_enter_email": (
        "Entrez votre adresse e-mail du portail :"
    ),

    "login_enter_password": (
        "Entrez maintenant votre mot de passe :"
    ),

    "login_success": (
        "*Compte lié !*\n\n"
        "Votre Telegram est maintenant connecté au compte du portail *{email}*."
    ),

    "login_failed": (
        "E-mail ou mot de passe incorrect. Réessayez avec /start."
    ),

    "login_already_linked": (
        "Ce compte est déjà lié à un autre utilisateur Telegram."
    ),

    "account_credentials": (
        "*Votre compte du Portail VPN*\n\n"
        "E-mail : `{email}`\n"
        "Mot de passe : `{password}`\n"
        "Portail : {portal_url}\n\n"
        "Sauvegardez ces identifiants !"
    ),

    # =========================================================================
    # MAIN MENU BUTTONS
    # =========================================================================

    "menu_status": "Mon Statut",
    "menu_traffic": "Trafic",
    "menu_config": "Configuration",
    "menu_plans": "Plans",
    "menu_subscribe": "S'abonner",
    "menu_support": "Support",
    "menu_lang": "Langue",
    "menu_referral": "Parrainage",
    "menu_have_account": "J'ai un compte",
    "download_app_removed": "Utilisez /config pour récupérer votre configuration VPN. Le bot recommande désormais l’application standard selon votre protocole.",
    "app_links_title": "*Applications VPN recommandées*\n\nChoisissez l’application adaptée à votre protocole et à votre plateforme :\n\n",
    "app_links_entry": "• *{protocol}* → *{app}*\n",
    "menu_hint": "Utilisez les boutons ci-dessous pour naviguer.",
    "plans_devices_short": "app.",
    "menu_hide_keyboard": "Masquer le clavier",
    "keyboard_hidden": "Clavier masqué. Tapez /start pour l'afficher à nouveau.",

    # =========================================================================
    # COMMON BUTTONS
    # =========================================================================

    "btn_back": "Retour",
    "btn_back_to_plans": "Retour aux Plans",
    "btn_back_to_menu": "Menu Principal",
    "btn_refresh": "Actualiser",
    "btn_pay": "Payer Maintenant",
    "btn_check_payment": "Vérifier le Paiement",
    "btn_download_config": "Télécharger Config",
    "btn_delete_device": "Supprimer l'Appareil",
    "btn_confirm_delete": "Oui, supprimer",

    # =========================================================================
    # PROMO CODES
    # =========================================================================

    "promo_enter": "Utilisation : /promo CODE\n\nExemple : /promo SAVE20",

    "promo_invalid": "Code promo invalide. Veuillez vérifier et réessayer.",

    "promo_applied": (
        "*Code promo {code} appliqué !*\n\n"
        "Bonus : *{value}*"
    ),

    "promo_already_used": "Vous avez déjà utilisé ce code promo.",

    # =========================================================================
    # REFERRAL PROGRAM
    # =========================================================================

    "ref_title": "*Programme de Parrainage*",

    "ref_code": "Votre code de parrainage : `{code}`",

    "ref_link": "Votre lien de parrainage : {link}",

    "ref_count": "Amis parrainés : *{count}*",

    "ref_share": (
        "*Programme de Parrainage*\n\n"
        "Votre code de parrainage : `{code}`\n"
        "Votre lien de parrainage :\n{link}\n\n"
        "Amis parrainés : *{count}*\n\n"
        "Partagez le lien et gagnez des bonus pour chaque nouvel abonné !"
    ),

    # =========================================================================
    # LANGUAGE SELECTION
    # =========================================================================

    "lang_changed": "Langue changée en *Français*.",

    "lang_select": (
        "*Sélectionner la langue*\n\n"
        "Choisissez votre langue préférée :"
    ),

    # =========================================================================
    # DEVICE / CONFIG MANAGEMENT
    # =========================================================================

    "device_create": (
        "*Créer un nouvel appareil*\n\n"
        "Entrez un nom pour le nouvel appareil (ex. `Mon Téléphone`) :"
    ),

    "device_select_server": (
        "*Créer un nouvel appareil*\n\n"
        "Choisissez le serveur et le protocole pour le nouvel appareil :"
    ),

    "device_create_for_server": (
        "*Créer un nouvel appareil*\n\n"
        "Serveur : *{server}*\n"
        "Protocole : *{protocol}*\n\n"
        "Entrez maintenant un nom pour le nouvel appareil (ex. `Mon Téléphone`) :"
    ),

    "device_created": (
        "*Appareil créé !*\n\n"
        "Nom : `{name}`\n"
        "Serveur : *{server}*\n"
        "Protocole : *{protocol}*\n\n"
        "Utilisez /config pour télécharger la configuration."
    ),

    "device_limit_reached": (
        "*Limite d'appareils atteinte*\n\n"
        "Votre plan autorise un maximum de *{max}* appareil(s).\n"
        "Améliorez votre plan pour ajouter plus d'appareils."
    ),

    "menu_add_device": "Ajouter un Appareil",

    "device_create_failed": (
        "Impossible de créer l'appareil. Veuillez réessayer ou contacter /support."
    ),

    "device_no_servers": "Aucun serveur n’est disponible pour le moment. Réessayez plus tard ou contactez /support.",
    "device_server_not_found": "Le serveur sélectionné est introuvable. Recommencez la création de l’appareil.",

    "no_subscription_for_device": (
        "Vous avez besoin d'un abonnement actif pour créer un appareil.\n"
        "Utilisez /subscribe pour commencer."
    ),

    "device_delete_confirm": (
        "Supprimer l'appareil *{name}* ?\n\n"
        "Cela supprimera définitivement l'appareil et révoquera la clé WireGuard."
    ),

    "device_deleted": (
        "*Appareil supprimé*\n\n"
        "*{name}* a été retiré de votre compte."
    ),

    "device_delete_failed": "Impossible de supprimer l'appareil. Veuillez réessayer ou contacter /support.",

    "traffic_select_device": "*Sélectionnez l'appareil* pour voir le trafic :",

    "config_select_device": "*Sélectionnez l'appareil* pour télécharger la configuration :",

    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================

    "notify_expiry_warning": (
        "*Votre abonnement expire bientôt !*\n\n"
        "Votre plan *{tier}* expire dans *{days}* jour(s) "
        "(le {date}).\n\n"
        "Renouvelez maintenant pour éviter toute interruption : /subscribe"
    ),

    "notify_traffic_warning": (
        "*Limite de trafic presque atteinte !*\n\n"
        "Vous avez utilisé *{percent}%* de votre trafic mensuel.\n"
        "Restant : *{remaining}*\n\n"
        "Améliorez votre plan pour obtenir plus de trafic : /subscribe"
    ),

    "notify_payment_confirmed": (
        "*Paiement confirmé !*\n\n"
        "Votre abonnement *{tier}* a été activé.\n"
        "Période : *{days}* jours (jusqu'au {date}).\n\n"
        "Téléchargez votre configuration VPN : /config"
    ),
}
