"""
Spanish locale for VPN Management Studio client Telegram bot.
"""

MESSAGES = {

    # =========================================================================
    # START / WELCOME
    # =========================================================================

    "welcome": (
        "*VPN Manager*\n\n"
        "¡Bienvenido a nuestro servicio VPN!\n\n"
        "Tienes *{client_count}* conexión(es) activa(s).\n"
        "{sub_info}"
        "Elige una acción:"
    ),

    "welcome_no_sub": (
        "*VPN Manager*\n\n"
        "¡Bienvenido a nuestro servicio VPN!\n\n"
        "Todavía no tienes una suscripción activa.\n"
        "Elige un plan para comenzar:"
    ),

    "blocked": (
        "Tu cuenta ha sido bloqueada. Por favor, contacta con el soporte."
    ),

    # =========================================================================
    # HELP
    # =========================================================================

    "help_text": (
        "*VPN Manager — Ayuda*\n\n"
        "*Comandos principales:*\n"
        "/start — Menú principal\n"
        "/status — Estado de suscripción\n"
        "/traffic — Uso de tráfico\n"
        "/config — Descargar configuración VPN\n\n"
        "*Suscripción:*\n"
        "/plans — Ver planes disponibles\n"
        "/subscribe — Comprar suscripción\n\n"
        "*Otros:*\n"
        "/support — Contactar soporte\n"
        "/help — Este mensaje de ayuda\n\n"
        "*Cómo conectarse:*\n"
        "1. Compra una suscripción con /subscribe\n"
        "2. Selecciona un plan y completa el pago\n"
        "3. Tu configuración se crea automáticamente tras el pago\n"
        "4. Descarga tu configuración con /config\n"
        "5. Instala la app recomendada para tu protocolo\n"
        "6. Importa la configuración o escanea el QR\n"
        "7. ¡Conéctate y disfruta!"
    ),

    # =========================================================================
    # STATUS
    # =========================================================================

    "status_title": "*Estado de Suscripción*",

    "status_tier": "Plan: *{tier}*",

    "status_expiry": "Expira: {date}",

    "status_days_left": "Días restantes: *{days}*",

    "status_devices": "Dispositivos: {count}",

    "status_no_sub": (
        "No tienes conexiones activas.\n"
        "{sub_info}\n\n"
        "Usa /subscribe para obtener una suscripción."
    ),

    "status_active": "Activo",

    "status_disabled": "Desactivado",

    "status_client": (
        "*{name}*\n"
        "Estado: {status}\n"
        "IP: `{ip}`\n"
        "Tráfico: {traffic}\n"
        "Expira: {expiry}"
    ),

    "status_no_expiry": "Sin expiración",

    # =========================================================================
    # TRAFFIC
    # =========================================================================

    "traffic_title": "*Estadísticas de Tráfico*",

    "traffic_used": "Usado: *{value}*",

    "traffic_limit": "Límite: *{limit}*",

    "traffic_unlimited": "Ilimitado",

    "traffic_percent": "Usado: *{percent}%*",

    "traffic_detail": (
        "*Estadísticas de Tráfico*\n\n"
        "{name}\n\n"
        "Descarga: {rx}\n"
        "Subida: {tx}\n"
        "Total: {total}"
    ),

    "traffic_with_limit": (
        "\n\nLímite: {limit} MB\n"
        "[{bar}] {percent}%"
    ),

    "traffic_no_sub": "No tienes suscripciones activas.",

    # =========================================================================
    # CONFIG
    # =========================================================================

    "config_title": "*Configuración VPN*",

    "config_no_devices": (
        "No tienes suscripciones activas.\n\n"
        "Usa /subscribe para obtener una suscripción."
    ),

    "config_download": (
        "*Archivo de Configuración*\n\n"
        "Protocolo: *{protocol}*\n"
        "App recomendada: *{app}*\n"
        "Importa el archivo adjunto o escanea el QR en esa app."
    ),

    "config_qr_caption": "Código QR para {name}\n\nProtocolo: *{protocol}*\nEscanea con *{app}*",

    "config_file_caption": "*Archivo de configuración*",

    "config_error": "No se pudo obtener la configuración.",

    # =========================================================================
    # PLANS
    # =========================================================================

    "plans_title": "*Planes Disponibles*\n\n",

    "plans_free": "Gratis",

    "plans_price": "${price}/mes",

    "plans_features": "Características:",

    "plans_devices": "Dispositivos: *{count}*",

    "plans_traffic": "Tráfico: *{value}*",

    "plans_bandwidth": "Velocidad: hasta *{mbps} Mbps*",

    "plans_unlimited": "Ilimitado",

    "plans_max_speed": "Velocidad máxima",

    "plans_unavailable": (
        "Los planes no están disponibles temporalmente.\n"
        "Contacta soporte: /support"
    ),

    "plans_subscribe_hint": "\nPara suscribirte usa /subscribe",

    "plans_select_hint": "\nSelecciona un plan para ver detalles:",

    # =========================================================================
    # SUBSCRIBE FLOW
    # =========================================================================

    "subscribe_select_plan": (
        "*Suscribirse*\n\n"
        "Selecciona un plan:"
    ),

    "subscribe_select_duration": (
        "*{plan_name}*\n\n"
        "Precio: ${price}/mes\n"
        "Tráfico: {traffic}\n"
        "Velocidad: {bandwidth}\n"
        "Dispositivos: {devices}\n"
        "{description}\n"
        "*Elige el período de facturación:*"
    ),

    "subscribe_select_currency": (
        "*Selecciona la moneda de pago*\n\n"
        "Período: {duration}\n\n"
        "Elige criptomoneda:"
    ),

    "subscribe_payment_link": (
        "*Pago*\n\n"
        "Plan: {plan}\n"
        "Monto: *${amount}*\n"
        "Moneda: {currency}\n"
        "Período: {days} días\n"
        "{promo_notice}"
        "{test_mode_notice}"
        "\n[Pagar ahora]({url})\n\n"
        "Haz clic en el botón de abajo después de completar el pago:"
    ),

    "subscribe_promo_discount": (
        "\nPromo *{code}*: -{discount}% → *${amount}*\n"
    ),

    "subscribe_referral_discount": (
        "\n🎁 Descuento por referido (primera compra): -{discount}% → *${amount}*\n"
    ),

    "subscribe_test_mode_notice": (
        "\n*Modo de prueba:* el pago será confirmado por el administrador\n"
    ),

    "subscribe_check_payment": "Verificar pago",

    "subscribe_plan_not_found": "Plan no encontrado.",

    "subscribe_duration_monthly": "1 mes",
    "subscribe_duration_quarterly": "3 meses",
    "subscribe_duration_yearly": "12 meses",

    # =========================================================================
    # PAYMENT STATUSES
    # =========================================================================

    "payment_confirmed": (
        "*¡Pago confirmado!*\n\n"
        "Plan: {plan}\n"
        "Período: {days} días\n\n"
        "{config_ready}"
    ),

    "payment_confirmed_config_ready": "¡Tu configuración VPN está lista! Usa /config para descargarla.",

    "payment_confirmed_creating": "Tu configuración se está creando...",

    "payment_pending": (
        "*Esperando pago*\n\n"
        "Plan: {plan}\n"
        "Monto: ${amount}\n\n"
        "El pago aún no ha sido confirmado.\n"
        "Haz clic en el botón de abajo después de pagar:"
    ),

    "payment_expired": (
        "*Pago expirado*\n\n"
        "La factura ha expirado. Por favor inicia un nuevo pedido con /subscribe."
    ),

    "payment_failed": (
        "*Pago fallido*\n\n"
        "Algo salió mal. Por favor intenta de nuevo o contacta /support."
    ),

    "payment_not_found": "Pago no encontrado.",

    # =========================================================================
    # SUPPORT
    # =========================================================================

    "support_text": (
        "*Soporte*\n\n"
        "Escribe tu mensaje abajo y será enviado a nuestro equipo de soporte.\n\n"
        "Simplemente escribe tu mensaje y envíalo:"
    ),

    "support_sent": (
        "*¡Mensaje enviado!*\n\n"
        "Tu mensaje ha sido recibido. Nuestro equipo de soporte lo revisará pronto.\n\n"
        "Ticket #{ticket_id}"
    ),

    "login_enter_email": (
        "Ingresa tu dirección de correo del portal:"
    ),

    "login_enter_password": (
        "Ahora ingresa tu contraseña:"
    ),

    "login_success": (
        "*¡Cuenta vinculada!*\n\n"
        "Tu Telegram ahora está conectado a la cuenta del portal *{email}*."
    ),

    "login_failed": (
        "Correo o contraseña incorrectos. Intenta de nuevo con /start."
    ),

    "login_already_linked": (
        "Esta cuenta ya está vinculada a otro usuario de Telegram."
    ),

    "account_credentials": (
        "*Tu cuenta del Portal VPN*\n\n"
        "Correo: `{email}`\n"
        "Contraseña: `{password}`\n"
        "Portal: {portal_url}\n\n"
        "¡Guarda estas credenciales!"
    ),

    # =========================================================================
    # MAIN MENU BUTTONS
    # =========================================================================

    "menu_status": "Mi Estado",
    "menu_traffic": "Tráfico",
    "menu_config": "Configuración",
    "menu_plans": "Planes",
    "menu_subscribe": "Suscribirse",
    "menu_support": "Soporte",
    "menu_lang": "Idioma",
    "menu_referral": "Referidos",
    "menu_have_account": "Tengo una cuenta",
    "download_app_removed": "Usa /config para obtener tu configuración VPN. El bot ahora recomienda la app estándar según tu protocolo.",
    "app_links_title": "*Aplicaciones VPN recomendadas*\n\nElige la aplicación correcta para tu protocolo y tu plataforma:\n\n",
    "app_links_entry": "• *{protocol}* → *{app}*\n",
    "menu_hint": "Usa los botones de abajo para navegar.",
    "plans_devices_short": "disp.",
    "menu_hide_keyboard": "Ocultar teclado",
    "keyboard_hidden": "Teclado oculto. Escribe /start para mostrarlo de nuevo.",

    # =========================================================================
    # COMMON BUTTONS
    # =========================================================================

    "btn_back": "Atrás",
    "btn_back_to_plans": "Volver a Planes",
    "btn_back_to_menu": "Menú Principal",
    "btn_refresh": "Actualizar",
    "btn_pay": "Pagar Ahora",
    "btn_check_payment": "Verificar Pago",
    "btn_download_config": "Descargar Config",
    "btn_delete_device": "Eliminar Dispositivo",
    "btn_confirm_delete": "Sí, eliminar",

    # =========================================================================
    # PROMO CODES
    # =========================================================================

    "promo_enter": "Uso: /promo CÓDIGO\n\nEjemplo: /promo SAVE20",

    "promo_invalid": "Código promocional inválido. Por favor verifica e intenta de nuevo.",

    "promo_applied": (
        "*¡Código promocional {code} aplicado!*\n\n"
        "Bono: *{value}*"
    ),

    "promo_already_used": "Ya has usado este código promocional.",

    # =========================================================================
    # REFERRAL PROGRAM
    # =========================================================================

    "ref_title": "*Programa de Referidos*",

    "ref_code": "Tu código de referido: `{code}`",

    "ref_link": "Tu enlace de referido: {link}",

    "ref_count": "Amigos referidos: *{count}*",

    "ref_share": (
        "*Programa de Referidos*\n\n"
        "Tu código de referido: `{code}`\n"
        "Tu enlace de referido:\n{link}\n\n"
        "Amigos referidos: *{count}*\n\n"
        "¡Comparte el enlace y gana bonos por cada nuevo suscriptor!"
    ),

    # =========================================================================
    # LANGUAGE SELECTION
    # =========================================================================

    "lang_changed": "Idioma cambiado a *Español*.",

    "lang_select": (
        "*Seleccionar idioma*\n\n"
        "Elige tu idioma preferido:"
    ),

    # =========================================================================
    # DEVICE / CONFIG MANAGEMENT
    # =========================================================================

    "device_create": (
        "*Crear nuevo dispositivo*\n\n"
        "Ingresa un nombre para el nuevo dispositivo (ej. `Mi Teléfono`):"
    ),

    "device_select_server": (
        "*Crear nuevo dispositivo*\n\n"
        "Selecciona el servidor y protocolo para el nuevo dispositivo:"
    ),

    "device_create_for_server": (
        "*Crear nuevo dispositivo*\n\n"
        "Servidor: *{server}*\n"
        "Protocolo: *{protocol}*\n\n"
        "Ahora ingresa un nombre para el nuevo dispositivo (ej. `Mi Teléfono`):"
    ),

    "device_created": (
        "*¡Dispositivo creado!*\n\n"
        "Nombre: `{name}`\n"
        "Servidor: *{server}*\n"
        "Protocolo: *{protocol}*\n\n"
        "Usa /config para descargar la configuración."
    ),

    "device_limit_reached": (
        "*Límite de dispositivos alcanzado*\n\n"
        "Tu plan permite un máximo de *{max}* dispositivo(s).\n"
        "Mejora tu plan para agregar más dispositivos."
    ),

    "menu_add_device": "Agregar Dispositivo",

    "device_create_failed": (
        "No se pudo crear el dispositivo. Por favor intenta de nuevo o contacta /support."
    ),

    "device_no_servers": "No hay servidores disponibles en este momento. Inténtalo más tarde o contacta /support.",
    "device_server_not_found": "No se encontró el servidor seleccionado. Inicia de nuevo la creación del dispositivo.",

    "no_subscription_for_device": (
        "Necesitas una suscripción activa para crear un dispositivo.\n"
        "Usa /subscribe para comenzar."
    ),

    "device_delete_confirm": (
        "¿Eliminar dispositivo *{name}*?\n\n"
        "Esto eliminará permanentemente el dispositivo y revocará la clave WireGuard."
    ),

    "device_deleted": (
        "*Dispositivo eliminado*\n\n"
        "*{name}* ha sido eliminado de tu cuenta."
    ),

    "device_delete_failed": "No se pudo eliminar el dispositivo. Por favor intenta de nuevo o contacta /support.",

    "traffic_select_device": "*Selecciona dispositivo* para ver el tráfico:",

    "config_select_device": "*Selecciona dispositivo* para descargar la configuración:",

    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================

    "notify_expiry_warning": (
        "*¡Tu suscripción expira pronto!*\n\n"
        "Tu plan *{tier}* expira en *{days}* día(s) "
        "(el {date}).\n\n"
        "Renueva ahora para evitar interrupciones: /subscribe"
    ),

    "notify_traffic_warning": (
        "*¡Límite de tráfico casi alcanzado!*\n\n"
        "Has usado *{percent}%* de tu tráfico mensual.\n"
        "Restante: *{remaining}*\n\n"
        "Mejora tu plan para obtener más tráfico: /subscribe"
    ),

    "notify_payment_confirmed": (
        "*¡Pago confirmado!*\n\n"
        "Tu suscripción *{tier}* ha sido activada.\n"
        "Período: *{days}* días (hasta {date}).\n\n"
        "Descarga tu configuración VPN: /config"
    ),
}
