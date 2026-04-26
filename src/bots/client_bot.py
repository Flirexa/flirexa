#!/usr/bin/env python3
"""
VPN Management Studio Client Bot
Telegram bot for VPN users - self-service portal

Uses SubscriptionManager for subscriptions and payments (same as web portal).
Bridges TelegramUser -> ClientUser via telegram_id field.
Full i18n support via locale files (en, ru).
"""

import os
import io
import secrets
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timezone, timedelta

import qrcode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from loguru import logger

from ..database.connection import SessionLocal
from ..database.models import TelegramUser, Client, Server
from ..core.management import ManagementCore
from ..modules.subscription.subscription_models import (
    ClientUser, ClientUserClients, SubscriptionPlan,
    ClientPortalSubscription, PaymentMethod,
)
from ..modules.subscription.subscription_manager import SubscriptionManager
from ..modules.subscription.subscription_models import PromoCode, SupportMessage


# i18n loader
_SUPPORTED_LANGS = {"en", "ru", "de", "es", "fr"}

def _load_locale(lang: str) -> dict:
    """Load locale messages for given language"""
    try:
        if lang == "ru":
            from .locales.ru import MESSAGES
        elif lang == "de":
            from .locales.de import MESSAGES
        elif lang == "es":
            from .locales.es import MESSAGES
        elif lang == "fr":
            from .locales.fr import MESSAGES
        else:
            from .locales.en import MESSAGES
        return MESSAGES
    except ImportError:
        from .locales.en import MESSAGES
        return MESSAGES


class ClientBot:
    """
    Client-facing Telegram Bot

    Allows users to:
    - View their subscription status
    - Download VPN configuration
    - Check traffic usage
    - View available plans and subscribe
    - Pay via CryptoPay or test mode
    - Contact support
    """

    def __init__(self, token: str):
        self.token = token
        self.app: Optional[Application] = None
        self._locale_cache = {}
        self._email_domain = os.getenv("AUTO_EMAIL_DOMAIN", "vpnmanager.local")

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def t(self, key: str, lang: str = "en", **kwargs) -> str:
        """Get translated message"""
        if lang not in self._locale_cache:
            self._locale_cache[lang] = _load_locale(lang)
        msgs = self._locale_cache[lang]
        text = msgs.get(key, self._locale_cache.get("en", {}).get(key, key))
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, IndexError):
                pass
        return text

    def get_user_lang(self, core, telegram_user) -> str:
        """Get user's preferred language"""
        client_user = core.db.query(ClientUser).filter(
            ClientUser.telegram_id == str(telegram_user.id)
        ).first()
        if client_user and client_user.language and client_user.language in _SUPPORTED_LANGS:
            return client_user.language
        # Auto-detect from Telegram language_code (e.g. "ru", "de-DE", "fr", "es-ES")
        tg_lang = getattr(telegram_user, 'language_code', None)
        if tg_lang:
            prefix = tg_lang[:2].lower()
            if prefix in _SUPPORTED_LANGS:
                return prefix
        return 'en'

    def get_core(self) -> ManagementCore:
        """Get a new ManagementCore instance with fresh DB session"""
        db = SessionLocal()
        return ManagementCore(db)

    def close_core(self, core: ManagementCore) -> None:
        """Close the database session"""
        core.db.close()

    def get_or_create_user(self, core: ManagementCore, telegram_user) -> TelegramUser:
        """Get or create a TelegramUser record"""
        user = core.db.query(TelegramUser).filter(
            TelegramUser.telegram_id == telegram_user.id
        ).first()

        if not user:
            user = TelegramUser(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                is_admin=False,
                is_blocked=False,
            )
            core.db.add(user)
            core.db.commit()
            core.db.refresh(user)
            logger.info(f"Created new TelegramUser: {telegram_user.id}")

        # Update last activity
        user.last_activity = datetime.now(timezone.utc)
        core.db.commit()

        return user

    def get_or_create_client_user(self, core: ManagementCore, telegram_user) -> Optional[ClientUser]:
        """Get or create ClientUser linked to Telegram user.
        Bridges Telegram users to the client portal subscription system."""
        tg_id = str(telegram_user.id)

        client_user = core.db.query(ClientUser).filter(
            ClientUser.telegram_id == tg_id
        ).first()

        if not client_user:
            username = telegram_user.username or f"tg_{telegram_user.id}"
            full_name = f"{telegram_user.first_name or ''} {telegram_user.last_name or ''}".strip()

            # Ensure unique username
            base_username = username
            counter = 1
            while core.db.query(ClientUser).filter(ClientUser.username == username).first():
                username = f"{base_username}_{counter}"
                counter += 1

            # Ensure unique email
            email = f"{base_username}@{self._email_domain}"
            counter = 1
            while core.db.query(ClientUser).filter(ClientUser.email == email).first():
                email = f"{base_username}_{counter}@{self._email_domain}"
                counter += 1

            import string, random
            ref_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

            client_user = ClientUser(
                email=email,
                password_hash="telegram-auth-no-password",
                telegram_id=tg_id,
                username=username,
                full_name=full_name or username,
                is_active=True,
                email_verified=True,
                referral_code=ref_code,
                language=getattr(telegram_user, 'language_code', 'en')[:2] if getattr(telegram_user, 'language_code', None) else 'en',
            )
            core.db.add(client_user)
            core.db.commit()
            core.db.refresh(client_user)

            # Create free subscription
            try:
                manager = SubscriptionManager(core.db)
                manager.create_subscription(client_user.id, "free")
            except Exception as e:
                logger.warning(f"Could not create free subscription for tg user {tg_id}: {e}")

            logger.info(f"Created ClientUser for telegram user {tg_id}: {username}")

        return client_user

    def get_user_clients(self, core: ManagementCore, telegram_user_id: int) -> List[Client]:
        """Get all WG clients for a Telegram user (legacy + portal links)"""
        # Legacy: Client.telegram_user_id
        legacy = core.db.query(Client).filter(
            Client.telegram_user_id == telegram_user_id
        ).all()

        # New: via ClientUserClients
        client_user = core.db.query(ClientUser).filter(
            ClientUser.telegram_id == str(telegram_user_id)
        ).first()

        portal_clients = []
        if client_user:
            manager = SubscriptionManager(core.db)
            portal_clients = manager.get_user_wireguard_clients(client_user.id)

        # Merge, deduplicate by ID
        seen_ids = set()
        result = []
        for c in legacy + portal_clients:
            if c.id not in seen_ids:
                seen_ids.add(c.id)
                result.append(c)
        return result

    @staticmethod
    def create_qr_code(config_text: str) -> io.BytesIO:
        """Create QR code image from config text"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(config_text)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        bio = io.BytesIO()
        img.save(bio, format='PNG')
        bio.seek(0)
        return bio

    @staticmethod
    def _client_protocol(server_type: Optional[str]) -> str:
        return (server_type or "wireguard").lower()

    def _recommended_client_app(self, server_type: Optional[str]) -> str:
        protocol = self._client_protocol(server_type)
        if protocol == "amneziawg":
            return "AmneziaWG"
        if protocol == "hysteria2":
            return "Hiddify / NekoBox"
        if protocol == "tuic":
            return "Hiddify / NekoBox"
        return "WireGuard"

    def _protocol_display_name(self, server_type: Optional[str]) -> str:
        protocol = self._client_protocol(server_type)
        if protocol == "amneziawg":
            return "AmneziaWG"
        if protocol == "hysteria2":
            return "Hysteria2"
        if protocol == "tuic":
            return "TUIC"
        return "WireGuard"

    def _client_app_links(self, server_type: Optional[str]) -> List[Tuple[str, str]]:
        protocol = self._client_protocol(server_type)
        if protocol == "amneziawg":
            return [
                ("🍎 iPhone / iPad · AmneziaWG", "https://apps.apple.com/app/amneziawg/id6478942365"),
                ("🤖 Android · AmneziaWG", "https://play.google.com/store/apps/details?id=org.amnezia.awg"),
                ("💻 Desktop · Docs", "https://docs.amnezia.org/documentation/alternative-clients/"),
            ]
        if protocol == "hysteria2":
            return [
                ("🍎 iPhone / iPad · Hiddify", "https://app.hiddify.com/"),
                ("🤖 Android · Hiddify", "https://app.hiddify.com/"),
                ("🤖 Android · NekoBox", "https://github.com/MatsuriDayo/NekoBoxForAndroid/releases"),
                ("💻 Desktop · Hiddify", "https://app.hiddify.com/"),
            ]
        if protocol == "tuic":
            return [
                ("🤖 Android · NekoBox", "https://github.com/MatsuriDayo/NekoBoxForAndroid/releases"),
                ("🤖 Android · Hiddify", "https://app.hiddify.com/"),
                ("🍎 iPhone / iPad · Hiddify", "https://app.hiddify.com/"),
                ("💻 Desktop · Hiddify", "https://app.hiddify.com/"),
            ]
        return [
            ("🍎 iPhone / iPad · WireGuard", "https://www.wireguard.com/install/"),
            ("🤖 Android · WireGuard", "https://www.wireguard.com/install/"),
            ("💻 Desktop · WireGuard", "https://www.wireguard.com/install/"),
        ]

    def _client_app_links_markup(self, server_type: Optional[str]) -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(label, url=url)] for label, url in self._client_app_links(server_type)]
        return InlineKeyboardMarkup(rows)

    def _get_available_servers(self, core: ManagementCore) -> List[Server]:
        return core.db.query(Server).order_by(Server.display_name.asc().nulls_last(), Server.name.asc()).all()

    def _client_config_extension(self, server_type: Optional[str]) -> str:
        protocol = self._client_protocol(server_type)
        if protocol == "hysteria2":
            return "yaml"
        if protocol == "tuic":
            return "json"
        return "conf"

    def _build_client_delivery(self, core: ManagementCore, client: Client) -> Optional[dict]:
        client = core.get_client(client.id) or client
        server_type = self._client_protocol(
            getattr(client.server, "server_type", None) if getattr(client, "server", None) else None
        )

        if server_type in {"hysteria2", "tuic"}:
            access = core.clients.get_proxy_client_access(client.id)
            if not access:
                return None
            config_text = access.get("config_yaml") or access.get("config_json") or access.get("config")
            qr_text = access.get("uri") or config_text
        else:
            config_text = core.get_client_config(client.id)
            qr_text = config_text

        if not config_text or not qr_text:
            return None

        return {
            "client_name": client.name,
            "protocol": self._protocol_display_name(server_type),
            "server_type": server_type,
            "app": self._recommended_client_app(server_type),
            "extension": self._client_config_extension(server_type),
            "config_text": config_text,
            "qr_text": qr_text,
        }

    async def _send_client_delivery(self, target, payload: dict, lang: str) -> None:
        qr_image = self.create_qr_code(payload["qr_text"])
        await target.reply_photo(
            photo=qr_image,
            caption=self.t(
                "config_qr_caption",
                lang,
                name=payload["client_name"],
                app=payload["app"],
                protocol=payload["protocol"],
            ),
        )

        config_bio = io.BytesIO(payload["config_text"].encode())
        config_bio.name = f"{payload['client_name']}.{payload['extension']}"
        await target.reply_document(
            document=config_bio,
            filename=f"{payload['client_name']}.{payload['extension']}",
            caption=self.t(
                "config_download",
                lang,
                app=payload["app"],
                protocol=payload["protocol"],
            ),
            reply_markup=self._client_app_links_markup(payload["server_type"]),
        )

    async def _show_protocol_app_links(self, query, core: ManagementCore, client_user: ClientUser, lang: str) -> None:
        clients = self.get_user_clients(core, int(client_user.telegram_id)) if client_user.telegram_id else []
        protocols: Dict[str, Dict[str, str]] = {}
        for client in clients:
            payload = self._build_client_delivery(core, client)
            if not payload:
                continue
            key = payload["server_type"]
            if key not in protocols:
                protocols[key] = {
                    "protocol": payload["protocol"],
                    "app": payload["app"],
                }

        if not protocols:
            await query.edit_message_text(
                self.t("config_no_devices", lang),
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data='menu')
                ]]),
            )
            return

        text = self.t("app_links_title", lang)
        buttons: List[List[InlineKeyboardButton]] = []
        for server_type, info in protocols.items():
            text += self.t("app_links_entry", lang, protocol=info["protocol"], app=info["app"])
            for label, url in self._client_app_links(server_type):
                buttons.append([InlineKeyboardButton(label, url=url)])

        buttons.append([InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data='menu')])
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True,
        )

    def _get_subscription_info(self, core: ManagementCore, telegram_user_id: int) -> Optional[ClientPortalSubscription]:
        """Get subscription for a Telegram user via ClientUser bridge"""
        client_user = core.db.query(ClientUser).filter(
            ClientUser.telegram_id == str(telegram_user_id)
        ).first()
        if not client_user:
            return None
        manager = SubscriptionManager(core.db)
        return manager.get_subscription(client_user.id)

    def _send_notification(self, core: ManagementCore, user_id: int, tier: str, days: int, expiry_date_str: str):
        """Send payment confirmed notification via NotificationService"""
        try:
            from ..modules.notifications import NotificationService
            ns = NotificationService(core.db)
            ns.notify_user_payment_confirmed(user_id, tier, days, expiry_date_str)
        except Exception as e:
            logger.error(f"Failed to send payment notification: {e}")

    def _send_admin_payment_notification(self, core: ManagementCore, username: str, amount: float, tier: str, method: str):
        """Send payment notification to admin"""
        try:
            from ..modules.notifications import NotificationService
            ns = NotificationService(core.db)
            ns.notify_admin_new_payment(username, amount, tier, method)
        except Exception as e:
            logger.error(f"Failed to send admin payment notification: {e}")

    # ========================================================================
    # KEYBOARDS (all i18n-aware)
    # ========================================================================

    def get_reply_keyboard(self, lang: str, has_subscription: bool = False,
                           can_add_device: bool = False,
                           show_link_account: bool = False) -> ReplyKeyboardMarkup:
        """Persistent bottom keyboard — main navigation, always visible"""
        rows = []

        if has_subscription:
            rows.append([
                KeyboardButton(f"📊 {self.t('menu_status', lang)}"),
                KeyboardButton(f"📈 {self.t('menu_traffic', lang)}"),
                KeyboardButton(f"📥 {self.t('menu_config', lang)}"),
            ])
            if can_add_device:
                rows.append([KeyboardButton(f"➕ {self.t('menu_add_device', lang)}")])

        rows.append([
            KeyboardButton(f"💳 {self.t('menu_subscribe', lang)}"),
            KeyboardButton(f"📋 {self.t('menu_plans', lang)}"),
        ])
        rows.append([
            KeyboardButton(f"🎁 {self.t('menu_referral', lang)}"),
            KeyboardButton(f"💬 {self.t('menu_support', lang)}"),
        ])
        if show_link_account:
            rows.append([KeyboardButton(f"🔗 {self.t('menu_have_account', lang)}")])

        rows.append([KeyboardButton(f"⌨️ {self.t('menu_hide_keyboard', lang)}")])

        return ReplyKeyboardMarkup(rows, resize_keyboard=True)

    def get_plans_keyboard(self, core: ManagementCore, lang: str) -> InlineKeyboardMarkup:
        """Plans selection keyboard using SubscriptionPlan"""
        plans = core.db.query(SubscriptionPlan).filter(
            SubscriptionPlan.is_active == True,
            SubscriptionPlan.is_visible == True,
        ).order_by(SubscriptionPlan.display_order).all()

        keyboard = []
        for plan in plans:
            if plan.tier.lower() == "free":
                continue  # Skip free tier in subscribe flow
            price_text = f"${plan.price_monthly_usd:.2f}/{self.t('subscribe_duration_monthly', lang)}"
            keyboard.append([InlineKeyboardButton(
                f"{plan.name} - {price_text}",
                callback_data=f'plan_{plan.tier}'
            )])

        keyboard.append([InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data='menu')])
        return InlineKeyboardMarkup(keyboard)

    def get_duration_keyboard(self, plan: SubscriptionPlan, lang: str) -> InlineKeyboardMarkup:
        """Duration selection keyboard for a plan"""
        keyboard = []

        # Monthly (always available)
        keyboard.append([InlineKeyboardButton(
            f"📅 {self.t('subscribe_duration_monthly', lang)} - ${plan.price_monthly_usd:.2f}",
            callback_data=f'dur_{plan.tier}_monthly'
        )])

        # Quarterly
        if plan.price_quarterly_usd:
            keyboard.append([InlineKeyboardButton(
                f"📅 {self.t('subscribe_duration_quarterly', lang)} - ${plan.price_quarterly_usd:.2f}",
                callback_data=f'dur_{plan.tier}_quarterly'
            )])

        # Yearly
        if plan.price_yearly_usd:
            keyboard.append([InlineKeyboardButton(
                f"📅 {self.t('subscribe_duration_yearly', lang)} - ${plan.price_yearly_usd:.2f}",
                callback_data=f'dur_{plan.tier}_yearly'
            )])

        keyboard.append([InlineKeyboardButton(f"⬅️ {self.t('btn_back_to_plans', lang)}", callback_data='subscribe')])
        return InlineKeyboardMarkup(keyboard)

    def get_currency_keyboard(self, tier: str, duration: str, lang: str) -> InlineKeyboardMarkup:
        """Currency selection keyboard"""
        currencies = [
            ("BTC", "btc"),
            ("USDT", "usdt"),
            ("TON", "ton"),
            ("ETH", "eth"),
        ]
        keyboard = []
        for label, code in currencies:
            keyboard.append([InlineKeyboardButton(
                f"💰 {label}",
                callback_data=f'pay_{tier}_{duration}_{code}'
            )])
        keyboard.append([InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data=f'plan_{tier}')])
        return InlineKeyboardMarkup(keyboard)

    def get_client_select_keyboard(self, clients: List[Client], lang: str) -> InlineKeyboardMarkup:
        """Client selection keyboard for users with multiple configs (status view)"""
        keyboard = []
        for client in clients:
            status = "✅" if client.enabled else "❌"
            keyboard.append([InlineKeyboardButton(
                f"{status} {client.name}",
                callback_data=f'client_{client.id}'
            )])
        keyboard.append([InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data='menu')])
        return InlineKeyboardMarkup(keyboard)

    def get_traffic_select_keyboard(self, clients: List[Client], lang: str) -> InlineKeyboardMarkup:
        """Device selection keyboard for traffic view"""
        keyboard = []
        for client in clients:
            status = "✅" if client.enabled else "❌"
            keyboard.append([InlineKeyboardButton(
                f"{status} {client.name}",
                callback_data=f'traffic_{client.id}'
            )])
        keyboard.append([InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data='menu')])
        return InlineKeyboardMarkup(keyboard)

    def get_config_select_keyboard(self, clients: List[Client], lang: str) -> InlineKeyboardMarkup:
        """Device selection keyboard for config download"""
        keyboard = []
        for client in clients:
            status = "✅" if client.enabled else "❌"
            keyboard.append([InlineKeyboardButton(
                f"{status} {client.name}",
                callback_data=f'config_{client.id}'
            )])
        keyboard.append([InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data='menu')])
        return InlineKeyboardMarkup(keyboard)

    def get_server_select_keyboard(self, servers: List[Server], lang: str) -> InlineKeyboardMarkup:
        keyboard = []
        for server in servers:
            protocol = self._protocol_display_name(getattr(server, "server_type", None))
            display_name = getattr(server, "display_name", None) or server.name
            keyboard.append([InlineKeyboardButton(
                f"{display_name} [{protocol}]",
                callback_data=f'add_device_server_{server.id}'
            )])
        keyboard.append([InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data='menu')])
        return InlineKeyboardMarkup(keyboard)

    # ========================================================================
    # COMMAND HANDLERS
    # ========================================================================

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command"""
        core = self.get_core()
        try:
            user = self.get_or_create_user(core, update.effective_user)
            lang = self.get_user_lang(core, update.effective_user)

            # Clear any pending state
            context.user_data.pop('awaiting', None)

            # Check if this TG user already has a ClientUser
            tg_id = str(update.effective_user.id)
            client_user = core.db.query(ClientUser).filter(
                ClientUser.telegram_id == tg_id
            ).first()

            # Handle referral: /start ref_CODE
            if context.args and context.args[0].startswith("ref_"):
                ref_code = context.args[0][4:]
                if not client_user:
                    client_user = self.get_or_create_client_user(core, update.effective_user)
                if client_user and not client_user.referred_by_id:
                    referrer = core.db.query(ClientUser).filter(
                        ClientUser.referral_code == ref_code,
                        ClientUser.id != client_user.id,
                    ).first()
                    if referrer:
                        client_user.referred_by_id = referrer.id
                        core.db.commit()
                        logger.info(f"User {client_user.username} referred by {referrer.username}")

            if user.is_blocked:
                await update.message.reply_text(self.t("blocked", lang))
                return

            # Auto-create ClientUser if not exists (free account, no portal password)
            if not client_user:
                client_user = self.get_or_create_client_user(core, update.effective_user)

            # Show main menu
            await self._show_main_menu(update.message, core, user, client_user, lang)

        finally:
            self.close_core(core)

    def _has_portal_password(self, client_user: ClientUser) -> bool:
        """Check if user has a real portal password (not TG-only account)"""
        if not client_user or not client_user.password_hash:
            return False
        return client_user.password_hash != "telegram-auth-no-password"

    async def _show_main_menu(self, message, core, user, client_user, lang):
        """Show the main menu — persistent ReplyKeyboard at bottom"""
        clients = self.get_user_clients(core, user.telegram_id)
        has_subscription = len(clients) > 0
        show_link_account = not self._has_portal_password(client_user)

        subscription = self._get_subscription_info(core, user.telegram_id)
        sub_info = ""
        can_add_device = False
        if subscription and subscription.tier and subscription.tier.lower() != "free":
            sub_info = f"\n*{subscription.tier.upper()}*"
            if subscription.expiry_date:
                sub_info += f" — {subscription.expiry_date.strftime('%d.%m.%Y')}"
            sub_info += "\n"
            max_dev = subscription.max_devices or 1
            if len(clients) < max_dev:
                can_add_device = True

        if has_subscription:
            text = self.t("welcome", lang, client_count=len(clients), sub_info=sub_info)
        else:
            text = self.t("welcome_no_sub", lang)

        await message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=self.get_reply_keyboard(lang, has_subscription, can_add_device, show_link_account),
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command"""
        core = self.get_core()
        try:
            user = self.get_or_create_user(core, update.effective_user)
            lang = self.get_user_lang(core, update.effective_user)
            clients = self.get_user_clients(core, user.telegram_id)
            subscription = self._get_subscription_info(core, user.telegram_id)

            if not clients:
                sub_info = ""
                if subscription:
                    sub_info = f"\n{self.t('status_tier', lang, tier=subscription.tier)}"
                await update.message.reply_text(
                    self.t("status_no_sub", lang, sub_info=sub_info),
                    parse_mode='Markdown'
                )
                return

            # Show subscription info
            if subscription and subscription.tier.lower() != "free":
                days_left = ""
                if subscription.expiry_date:
                    expiry = subscription.expiry_date
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=timezone.utc)
                    dl = (expiry - datetime.now(timezone.utc)).days
                    days_left = f"\n{self.t('status_days_left', lang, days=dl)}"
                text = (
                    f"{self.t('status_title', lang)}\n\n"
                    f"{self.t('status_tier', lang, tier=subscription.tier.upper())}"
                    f"{days_left}\n"
                )
                await update.message.reply_text(text, parse_mode='Markdown')

            for client in clients:
                info = core.get_client_full_info(client.id)
                if not info:
                    continue

                status = self.t("status_active", lang) if info['enabled'] else self.t("status_disabled", lang)
                traffic = info['traffic']
                traffic_text = f"↓{traffic['rx_formatted']} ↑{traffic['tx_formatted']}"
                if traffic['limit_mb']:
                    traffic_text += f" ({int(traffic['percent_used'])}%)"

                expiry = info['expiry']
                expiry_text = expiry['display_text'] if expiry else self.t("status_no_expiry", lang)

                text = self.t("status_client", lang,
                    name=info['name'],
                    status=status,
                    ip=info['ipv4'],
                    traffic=traffic_text,
                    expiry=expiry_text,
                )

                await update.message.reply_text(text, parse_mode='Markdown')

        finally:
            self.close_core(core)

    async def traffic_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /traffic command"""
        core = self.get_core()
        try:
            user = self.get_or_create_user(core, update.effective_user)
            lang = self.get_user_lang(core, update.effective_user)
            clients = self.get_user_clients(core, user.telegram_id)

            if not clients:
                await update.message.reply_text(self.t("traffic_no_sub", lang))
                return

            for client in clients:
                info = core.get_client_full_info(client.id)
                if not info:
                    continue

                traffic = info['traffic']

                text = self.t("traffic_detail", lang,
                    name=info['name'],
                    rx=traffic['rx_formatted'],
                    tx=traffic['tx_formatted'],
                    total=traffic['total_formatted'],
                )

                if traffic['limit_mb']:
                    filled = int(traffic['percent_used'] / 10)
                    bar = "█" * filled + "░" * (10 - filled)
                    text += self.t("traffic_with_limit", lang,
                        limit=traffic['limit_mb'],
                        bar=bar,
                        percent=int(traffic['percent_used']),
                    )

                await update.message.reply_text(text, parse_mode='Markdown')

        finally:
            self.close_core(core)

    async def config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /config command - download configuration"""
        core = self.get_core()
        try:
            user = self.get_or_create_user(core, update.effective_user)
            lang = self.get_user_lang(core, update.effective_user)
            clients = self.get_user_clients(core, user.telegram_id)

            if not clients:
                await update.message.reply_text(
                    self.t("config_no_devices", lang),
                    parse_mode='Markdown'
                )
                return

            for client in clients:
                payload = self._build_client_delivery(core, client)
                if not payload:
                    continue
                await self._send_client_delivery(update.message, payload, lang)

        finally:
            self.close_core(core)

    async def plans_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /plans command - show available subscription plans"""
        core = self.get_core()
        try:
            lang = self.get_user_lang(core, update.effective_user)
            plans = core.db.query(SubscriptionPlan).filter(
                SubscriptionPlan.is_active == True,
                SubscriptionPlan.is_visible == True,
            ).order_by(SubscriptionPlan.display_order).all()

            if not plans:
                await update.message.reply_text(
                    self.t("plans_unavailable", lang),
                    parse_mode='Markdown'
                )
                return

            text = self.t("plans_title", lang)

            for plan in plans:
                if plan.tier.lower() == "free":
                    continue

                text += f"*{plan.name}*\n"
                text += f"💰 ${plan.price_monthly_usd:.2f}/{self.t('subscribe_duration_monthly', lang)}"
                if plan.price_quarterly_usd:
                    text += f" | ${plan.price_quarterly_usd:.2f}/{self.t('subscribe_duration_quarterly', lang)}"
                if plan.price_yearly_usd:
                    text += f" | ${plan.price_yearly_usd:.2f}/{self.t('subscribe_duration_yearly', lang)}"
                text += "\n"

                traffic_val = f"{plan.traffic_limit_gb} GB" if plan.traffic_limit_gb else self.t("plans_unlimited", lang)
                text += f"📊 {self.t('plans_traffic', lang, value=traffic_val)}\n"

                if plan.bandwidth_limit_mbps:
                    text += f"⚡ {self.t('plans_bandwidth', lang, mbps=plan.bandwidth_limit_mbps)}\n"
                else:
                    text += f"⚡ {self.t('plans_max_speed', lang)}\n"

                text += f"📱 {self.t('plans_devices', lang, count=plan.max_devices)}\n"

                if plan.description:
                    text += f"ℹ️ {plan.description}\n"

                text += "\n"

            text += self.t("plans_subscribe_hint", lang)

            await update.message.reply_text(text, parse_mode='Markdown')

        finally:
            self.close_core(core)

    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /subscribe command - start subscription flow"""
        core = self.get_core()
        try:
            self.get_or_create_client_user(core, update.effective_user)
            lang = self.get_user_lang(core, update.effective_user)

            await update.message.reply_text(
                self.t("subscribe_select_plan", lang),
                parse_mode='Markdown',
                reply_markup=self.get_plans_keyboard(core, lang)
            )
        finally:
            self.close_core(core)

    async def support_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /support command — ask user to write a message"""
        core = self.get_core()
        try:
            self.get_or_create_client_user(core, update.effective_user)
            lang = self.get_user_lang(core, update.effective_user)
            context.user_data['awaiting'] = 'support_message'
            await update.message.reply_text(
                self.t("support_text", lang),
                parse_mode='Markdown'
            )
        finally:
            self.close_core(core)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command"""
        core = self.get_core()
        try:
            lang = self.get_user_lang(core, update.effective_user)
            await update.message.reply_text(
                self.t("help_text", lang),
                parse_mode='Markdown'
            )
        finally:
            self.close_core(core)

    # ========================================================================
    # CALLBACK HANDLERS
    # ========================================================================

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle all callback queries"""
        query = update.callback_query
        await query.answer()

        data = query.data

        core = self.get_core()
        try:
            user = self.get_or_create_user(core, update.effective_user)
            client_user = self.get_or_create_client_user(core, update.effective_user)
            lang = self.get_user_lang(core, update.effective_user)

            if user.is_blocked:
                await query.edit_message_text(self.t("blocked", lang))
                return

            clients = self.get_user_clients(core, user.telegram_id)
            has_subscription = len(clients) > 0

            # Check if user can add more devices
            subscription = self._get_subscription_info(core, user.telegram_id)
            can_add_device = False
            if subscription and subscription.tier and subscription.tier.lower() != "free":
                max_dev = subscription.max_devices or 1
                if len(clients) < max_dev:
                    can_add_device = True

            show_link_account = not self._has_portal_password(client_user)

            if data == 'menu':
                # Back to main menu — just show a neutral message (ReplyKeyboard is already persistent)
                text = (
                    self.t("welcome", lang, client_count=len(clients), sub_info="")
                    if has_subscription else self.t("welcome_no_sub", lang)
                )
                await query.edit_message_text(text, parse_mode='Markdown')

            elif data == 'my_status':
                if not clients:
                    await query.edit_message_text(
                        self.t("status_no_sub", lang, sub_info=""),
                        parse_mode='Markdown',
                        reply_markup=self.get_main_menu_keyboard(lang, False)
                    )
                    return

                if len(clients) == 1:
                    await self._show_client_status(query, core, clients[0], lang)
                else:
                    await query.edit_message_text(
                        self.t("status_title", lang),
                        parse_mode='Markdown',
                        reply_markup=self.get_client_select_keyboard(clients, lang)
                    )

            elif data == 'my_traffic':
                if not clients:
                    await query.edit_message_text(self.t("traffic_no_sub", lang))
                elif len(clients) == 1:
                    await self._show_traffic(query, core, clients[0], lang)
                else:
                    await query.edit_message_text(
                        self.t("traffic_select_device", lang),
                        parse_mode='Markdown',
                        reply_markup=self.get_traffic_select_keyboard(clients, lang)
                    )

            elif data == 'my_config':
                if not clients:
                    await query.edit_message_text(self.t("config_no_devices", lang), parse_mode='Markdown')
                elif len(clients) == 1:
                    await self._send_config(query, core, clients[0], lang)
                else:
                    await query.edit_message_text(
                        self.t("config_select_device", lang),
                        parse_mode='Markdown',
                        reply_markup=self.get_config_select_keyboard(clients, lang)
                    )

            elif data == 'plans':
                await self._show_plans(query, core, lang)

            elif data == 'subscribe':
                await query.edit_message_text(
                    self.t("subscribe_select_plan", lang),
                    parse_mode='Markdown',
                    reply_markup=self.get_plans_keyboard(core, lang)
                )

            elif data.startswith('plan_'):
                tier = data[5:]
                await self._show_plan_details(query, core, tier, lang)

            elif data.startswith('dur_'):
                # dur_{tier}_{duration}
                parts = data.split('_', 2)
                if len(parts) >= 3:
                    tier = parts[1]
                    duration = parts[2]
                    await self._show_currency_selection(query, tier, duration, lang)

            elif data.startswith('pay_'):
                # pay_{tier}_{duration}_{currency}
                parts = data.split('_', 3)
                if len(parts) >= 4:
                    tier = parts[1]
                    duration = parts[2]
                    currency = parts[3]
                    await self._create_payment(query, core, client_user, tier, duration, currency, lang, context)

            elif data.startswith('check_'):
                # check_{invoice_id}
                invoice_id = data[6:]
                await self._check_payment_status(query, core, client_user, invoice_id, lang)

            elif data.startswith('client_'):
                client_id = int(data[7:])
                client = core.get_client(client_id)
                # Verify ownership
                client_ids = {c.id for c in clients}
                if client and client.id in client_ids:
                    await self._show_client_status(query, core, client, lang)

            elif data.startswith('config_'):
                client_id = int(data[7:])
                client = core.get_client(client_id)
                client_ids = {c.id for c in clients}
                if client and client.id in client_ids:
                    await self._send_config(query, core, client, lang)

            elif data.startswith('traffic_'):
                client_id = int(data[8:])
                client = core.get_client(client_id)
                client_ids = {c.id for c in clients}
                if client and client.id in client_ids:
                    await self._show_traffic(query, core, client, lang)

            elif data.startswith('del_confirm_'):
                client_id = int(data[12:])
                client = core.get_client(client_id)
                client_ids = {c.id for c in clients}
                if client and client.id in client_ids:
                    keyboard = [
                        [InlineKeyboardButton(f"✅ {self.t('btn_confirm_delete', lang)}", callback_data=f'del_{client_id}')],
                        [InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data=f'client_{client_id}')],
                    ]
                    await query.edit_message_text(
                        self.t("device_delete_confirm", lang, name=client.name),
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )

            elif data.startswith('del_'):
                client_id = int(data[4:])
                client = core.get_client(client_id)
                client_ids = {c.id for c in clients}
                if client and client.id in client_ids:
                    name = client.name
                    ok = core.delete_client(client_id)
                    if ok:
                        await query.edit_message_text(
                            self.t("device_deleted", lang, name=name),
                            parse_mode='Markdown',
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton(f"🏠 {self.t('btn_back_to_menu', lang)}", callback_data='menu')
                            ]])
                        )
                    else:
                        await query.edit_message_text(self.t("device_delete_failed", lang))

            elif data == 'show_ref':
                if client_user:
                    if not client_user.referral_code:
                        import string, random
                        client_user.referral_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                        core.db.commit()
                    ref_count = core.db.query(ClientUser).filter(
                        ClientUser.referred_by_id == client_user.id
                    ).count()
                    bot_info = await context.bot.get_me()
                    ref_link = f"https://t.me/{bot_info.username}?start=ref_{client_user.referral_code}"
                    # Escape underscores for Markdown
                    ref_link_escaped = ref_link.replace("_", "\\_")
                    text = self.t("ref_share", lang,
                        code=client_user.referral_code,
                        link=ref_link_escaped,
                        count=ref_count,
                    )
                    keyboard = [[InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data='menu')]]
                    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

            elif data == 'support':
                context.user_data['awaiting'] = 'support_message'
                await query.edit_message_text(
                    self.t("support_text", lang),
                    parse_mode='Markdown',
                )

            elif data.startswith('set_lang_'):
                lang_code = data[9:]  # "en" or "ru"
                await self._handle_lang_callback(query, lang_code)

            elif data == 'add_device':
                await self._handle_add_device(query, context, core, client_user, lang)

            elif data.startswith('add_device_server_'):
                server_id = int(data.rsplit('_', 1)[1])
                await self._handle_add_device_server(query, context, core, client_user, lang, server_id)

            elif data == 'download_app':
                await self._show_protocol_app_links(query, core, client_user, lang)

            elif data == 'link_account':
                # User wants to link existing portal account
                context.user_data['awaiting'] = 'login_email'
                await query.edit_message_text(
                    self.t("login_enter_email", lang),
                    parse_mode='Markdown',
                )

        finally:
            self.close_core(core)

    # ========================================================================
    # DISPLAY HELPERS
    # ========================================================================

    async def _show_client_status(self, query, core: ManagementCore, client: Client, lang: str) -> None:
        """Show detailed client status"""
        info = core.get_client_full_info(client.id)
        if not info:
            await query.edit_message_text(self.t("config_error", lang))
            return

        status = self.t("status_active", lang) if info['enabled'] else self.t("status_disabled", lang)
        traffic = info['traffic']
        traffic_text = f"↓{traffic['rx_formatted']} ↑{traffic['tx_formatted']}"
        expiry = info['expiry']
        expiry_text = expiry['display_text'] if expiry else self.t("status_no_expiry", lang)

        text = self.t("status_client", lang,
            name=info['name'],
            status=status,
            ip=info['ipv4'],
            traffic=traffic_text,
            expiry=expiry_text,
        )

        keyboard = [
            [InlineKeyboardButton(f"📥 {self.t('btn_download_config', lang)}", callback_data=f'config_{client.id}')],
            [InlineKeyboardButton(f"🗑️ {self.t('btn_delete_device', lang)}", callback_data=f'del_confirm_{client.id}')],
            [InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data='menu')]
        ]

        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_traffic(self, query, core: ManagementCore, client: Client, lang: str) -> None:
        """Show traffic statistics"""
        info = core.get_client_full_info(client.id)
        if not info:
            await query.edit_message_text(self.t("config_error", lang))
            return

        traffic = info['traffic']

        text = self.t("traffic_detail", lang,
            name=info['name'],
            rx=traffic['rx_formatted'],
            tx=traffic['tx_formatted'],
            total=traffic['total_formatted'],
        )

        if traffic['limit_mb']:
            filled = int(traffic['percent_used'] / 10)
            bar = "█" * filled + "░" * (10 - filled)
            text += self.t("traffic_with_limit", lang,
                limit=traffic['limit_mb'],
                bar=bar,
                percent=int(traffic['percent_used']),
            )

        keyboard = [[InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data='menu')]]
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    async def _send_config(self, query, core: ManagementCore, client: Client, lang: str) -> None:
        """Send config file and QR code"""
        payload = self._build_client_delivery(core, client)
        if not payload:
            await query.edit_message_text(self.t("config_error", lang))
            return
        await self._send_client_delivery(query.message, payload, lang)

    async def _show_plans(self, query, core: ManagementCore, lang: str) -> None:
        """Show available plans"""
        plans = core.db.query(SubscriptionPlan).filter(
            SubscriptionPlan.is_active == True,
            SubscriptionPlan.is_visible == True,
        ).order_by(SubscriptionPlan.display_order).all()

        if not plans:
            await query.edit_message_text(
                self.t("plans_unavailable", lang),
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data='menu')
                ]])
            )
            return

        text = self.t("plans_title", lang)

        for plan in plans:
            if plan.tier.lower() == "free":
                continue
            text += f"• *{plan.name}* - ${plan.price_monthly_usd:.2f}/{self.t('subscribe_duration_monthly', lang)}"
            if plan.max_devices > 1:
                text += f" ({plan.max_devices} dev.)"
            text += "\n"

        text += self.t("plans_select_hint", lang)

        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=self.get_plans_keyboard(core, lang)
        )

    # ------------------------------------------------------------------
    # Message-based variants (for ReplyKeyboard button presses)
    # ------------------------------------------------------------------

    async def _show_client_status_msg(self, message, core: ManagementCore, client: Client, lang: str) -> None:
        """Show client status in reply to a message (ReplyKeyboard)"""
        info = core.get_client_full_info(client.id)
        if not info:
            await message.reply_text(self.t("config_error", lang))
            return
        status = self.t("status_active", lang) if info['enabled'] else self.t("status_disabled", lang)
        traffic = info['traffic']
        traffic_text = f"↓{traffic['rx_formatted']} ↑{traffic['tx_formatted']}"
        expiry = info['expiry']
        expiry_text = expiry['display_text'] if expiry else self.t("status_no_expiry", lang)
        text = self.t("status_client", lang,
            name=info['name'], status=status, ip=info['ipv4'],
            traffic=traffic_text, expiry=expiry_text,
        )
        keyboard = [
            [InlineKeyboardButton(f"📥 {self.t('btn_download_config', lang)}", callback_data=f'config_{client.id}')],
            [InlineKeyboardButton(f"🗑️ {self.t('btn_delete_device', lang)}", callback_data=f'del_confirm_{client.id}')],
        ]
        await message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_traffic_msg(self, message, core: ManagementCore, client: Client, lang: str) -> None:
        """Show traffic stats in reply to a message (ReplyKeyboard)"""
        info = core.get_client_full_info(client.id)
        if not info:
            await message.reply_text(self.t("config_error", lang))
            return
        traffic = info['traffic']
        text = self.t("traffic_detail", lang,
            name=info['name'], rx=traffic['rx_formatted'],
            tx=traffic['tx_formatted'], total=traffic['total_formatted'],
        )
        if traffic['limit_mb']:
            filled = int(traffic['percent_used'] / 10)
            bar = "█" * filled + "░" * (10 - filled)
            text += self.t("traffic_with_limit", lang,
                limit=traffic['limit_mb'], bar=bar, percent=int(traffic['percent_used']),
            )
        await message.reply_text(text, parse_mode='Markdown')

    async def _send_config_msg(self, message, core: ManagementCore, client: Client, lang: str) -> None:
        """Send config file in reply to a message (ReplyKeyboard)"""
        payload = self._build_client_delivery(core, client)
        if not payload:
            await message.reply_text(self.t("config_error", lang))
            return
        await self._send_client_delivery(message, payload, lang)

    async def _show_plans_msg(self, message, core: ManagementCore, lang: str) -> None:
        """Show plans in reply to a message (ReplyKeyboard)"""
        plans = core.db.query(SubscriptionPlan).filter(
            SubscriptionPlan.is_active == True, SubscriptionPlan.is_visible == True,
        ).order_by(SubscriptionPlan.display_order).all()
        if not plans:
            await message.reply_text(self.t("plans_unavailable", lang), parse_mode='Markdown')
            return
        text = self.t("plans_title", lang)
        for plan in plans:
            if plan.tier.lower() == "free":
                continue
            text += f"• *{plan.name}* - ${plan.price_monthly_usd:.2f}/{self.t('subscribe_duration_monthly', lang)}"
            if plan.max_devices > 1:
                text += f" ({plan.max_devices} {self.t('plans_devices_short', lang)})"
            text += "\n"
        text += self.t("plans_select_hint", lang)
        await message.reply_text(text, parse_mode='Markdown',
                                 reply_markup=self.get_plans_keyboard(core, lang))

    async def _handle_add_device_msg(self, message, context, core, client_user, lang: str) -> None:
        """Handle add device from ReplyKeyboard — ask for server first."""
        mgr = SubscriptionManager(core.db)
        sub = mgr.get_subscription(client_user.id)
        if not sub or sub.tier == "free":
            await message.reply_text(self.t("no_subscription_for_device", lang))
            return
        existing = mgr.get_user_wireguard_clients(client_user.id)
        if len(existing) >= (sub.max_devices or 1):
            await message.reply_text(
                self.t("device_limit_reached", lang, max=sub.max_devices), parse_mode='Markdown'
            )
            return
        servers = self._get_available_servers(core)
        if not servers:
            await message.reply_text(self.t("device_no_servers", lang))
            return
        await message.reply_text(
            self.t("device_select_server", lang),
            parse_mode='Markdown',
            reply_markup=self.get_server_select_keyboard(servers, lang),
        )

    async def _show_plan_details(self, query, core: ManagementCore, tier: str, lang: str) -> None:
        """Show plan details with duration selection"""
        from sqlalchemy import func as _func
        plan = core.db.query(SubscriptionPlan).filter(
            _func.lower(SubscriptionPlan.tier) == tier.lower(),
            SubscriptionPlan.is_active == True,
        ).first()

        if not plan:
            await query.edit_message_text(self.t("subscribe_plan_not_found", lang))
            return

        traffic_val = f"{plan.traffic_limit_gb} GB" if plan.traffic_limit_gb else self.t("plans_unlimited", lang)
        bandwidth_val = f"{plan.bandwidth_limit_mbps} Mbps" if plan.bandwidth_limit_mbps else self.t("plans_max_speed", lang)
        desc = f"\nℹ️ {plan.description}" if plan.description else ""

        text = self.t("subscribe_select_duration", lang,
            plan_name=plan.name,
            price=f"{plan.price_monthly_usd:.2f}",
            traffic=traffic_val,
            bandwidth=bandwidth_val,
            devices=plan.max_devices,
            description=desc,
        )

        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=self.get_duration_keyboard(plan, lang)
        )

    async def _show_currency_selection(self, query, tier: str, duration: str, lang: str) -> None:
        """Show currency selection"""
        duration_labels = {
            "monthly": self.t("subscribe_duration_monthly", lang),
            "quarterly": self.t("subscribe_duration_quarterly", lang),
            "yearly": self.t("subscribe_duration_yearly", lang),
        }

        text = self.t("subscribe_select_currency", lang,
            duration=duration_labels.get(duration, duration),
        )

        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=self.get_currency_keyboard(tier, duration, lang)
        )

    async def _create_payment(self, query, core: ManagementCore, client_user: ClientUser,
                              tier: str, duration: str, currency: str, lang: str,
                              context=None) -> None:
        """Create payment invoice and show payment link"""
        from sqlalchemy import func as _func
        plan = core.db.query(SubscriptionPlan).filter(
            _func.lower(SubscriptionPlan.tier) == tier.lower(),
            SubscriptionPlan.is_active == True,
        ).first()

        if not plan:
            await query.edit_message_text(self.t("subscribe_plan_not_found", lang))
            return

        # Calculate price and duration days
        duration_map = {
            "monthly": (plan.price_monthly_usd, 30),
            "quarterly": (plan.price_quarterly_usd or plan.price_monthly_usd * 3, 90),
            "yearly": (plan.price_yearly_usd or plan.price_monthly_usd * 12, 365),
        }

        amount_usd, duration_days = duration_map.get(duration, (plan.price_monthly_usd, 30))

        # Apply percent promo code discount if stored
        promo_notice = ""
        active_promo = context.user_data.pop('active_promo', None) if context else None
        if active_promo:
            discount_pct = active_promo['discount']
            discounted = round(amount_usd * (1 - discount_pct / 100), 2)
            promo_notice = self.t("subscribe_promo_discount", lang,
                code=active_promo['code'],
                discount=int(discount_pct),
                amount=f"{discounted:.2f}",
            )
            amount_usd = discounted

        # Apply referral discount (10% on first purchase for referred users)
        _REFERRAL_DISCOUNT_PCT = 10
        if not active_promo and client_user and client_user.referred_by_id:
            from ..modules.subscription.subscription_manager import SubscriptionManager as _SM
            _sm = _SM(core.db)
            from ..database.models import ClientPortalPayment as _CPP
            prev_paid = core.db.query(_CPP).filter(
                _CPP.user_id == client_user.id,
                _CPP.status == "completed",
                _CPP.subscription_tier != "free",
            ).count()
            if prev_paid == 0:
                discounted = round(amount_usd * (1 - _REFERRAL_DISCOUNT_PCT / 100), 2)
                promo_notice = self.t("subscribe_referral_discount", lang,
                    discount=_REFERRAL_DISCOUNT_PCT,
                    amount=f"{discounted:.2f}",
                )
                amount_usd = discounted

        # Map currency to PaymentMethod
        currency_to_method = {
            "btc": PaymentMethod.BTC,
            "usdt": PaymentMethod.USDT_TRC20,
            "ton": PaymentMethod.TON,
            "eth": PaymentMethod.ETH,
        }
        payment_method = currency_to_method.get(currency, PaymentMethod.BTC)

        # Try CryptoPay first, fallback to test mode
        manager = SubscriptionManager(core.db)

        # Check if CryptoPay is available
        from ..api.routes import client_portal as cp_module
        cryptopay = getattr(cp_module, 'cryptopay_adapter', None)

        payment_url = None
        invoice_id = None

        if cryptopay:
            try:
                from ..modules.subscription.cryptopay_adapter import create_subscription_invoice
                invoice_data = await create_subscription_invoice(
                    adapter=cryptopay,
                    amount_usd=amount_usd,
                    currency=currency.upper(),
                    description=f"VPN Manager - {plan.name} ({duration})",
                )
                invoice_id = str(invoice_data["invoice_id"])
                payment_url = invoice_data.get("payment_url", "")
            except Exception as e:
                logger.error(f"CryptoPay invoice creation failed: {e}")
                cryptopay = None  # Fall through to test mode

        if not cryptopay:
            # Test mode - mock invoice
            invoice_id = str(secrets.randbelow(900000) + 100000)
            payment_url = f"https://t.me/CryptoBot?start=invoice_{invoice_id}"

        # Save payment record
        payment = manager.create_payment(
            user_id=client_user.id,
            amount_usd=amount_usd,
            payment_method=payment_method,
            subscription_tier=tier,
            duration_days=duration_days,
            invoice_id=invoice_id,
            provider_name="cryptopay" if cryptopay else "test",
        )

        # Show payment info
        test_mode_notice = self.t("subscribe_test_mode_notice", lang) if not cryptopay else ""

        text = self.t("subscribe_payment_link", lang,
            plan=plan.name,
            amount=f"{amount_usd:.2f}",
            currency=currency.upper(),
            days=duration_days,
            test_mode_notice=test_mode_notice,
            promo_notice=promo_notice,
            url=payment_url,
        )

        keyboard = [
            [InlineKeyboardButton(f"🔗 {self.t('btn_pay', lang)}", url=payment_url)],
            [InlineKeyboardButton(f"🔄 {self.t('btn_check_payment', lang)}", callback_data=f'check_{invoice_id}')],
            [InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data='menu')],
        ]

        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True,
        )

    async def _check_payment_status(self, query, core: ManagementCore,
                                     client_user: ClientUser, invoice_id: str, lang: str) -> None:
        """Check payment status and complete if paid"""
        manager = SubscriptionManager(core.db)
        payment = manager.get_payment_by_invoice(invoice_id)

        if not payment:
            await query.edit_message_text(self.t("payment_not_found", lang))
            return

        if payment.status == "completed":
            # Already completed - show config
            clients = self.get_user_clients(core, query.from_user.id)

            config_ready = self.t("payment_confirmed_config_ready", lang) if clients else self.t("payment_confirmed_creating", lang)
            text = self.t("payment_confirmed", lang,
                plan=payment.subscription_tier,
                days=payment.duration_days,
                config_ready=config_ready,
            )

            keyboard = []
            if clients:
                keyboard.append([InlineKeyboardButton(f"📥 {self.t('btn_download_config', lang)}", callback_data='my_config')])
            keyboard.append([InlineKeyboardButton(f"🏠 {self.t('btn_back_to_menu', lang)}", callback_data='menu')])

            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # Try to check with CryptoPay
        from ..api.routes import client_portal as cp_module
        cryptopay = getattr(cp_module, 'cryptopay_adapter', None)

        if cryptopay and payment.status != "completed":
            try:
                payment_status = await cryptopay.check_payment(int(invoice_id))
                if payment_status and payment_status.get("status") == "paid":
                    manager.complete_payment(invoice_id, tx_hash=payment_status.get("tx_hash"))

                    # Create portal credentials if user doesn't have them yet
                    portal_password = self._create_portal_credentials(core, client_user)
                    if portal_password:
                        portal_url = os.getenv("CLIENT_PORTAL_URL", "")
                        await query.message.reply_text(
                            self.t("account_credentials", lang,
                                email=client_user.email,
                                password=portal_password,
                                portal_url=portal_url,
                            ),
                            parse_mode='Markdown'
                        )

                    # Send notifications
                    sub = manager.get_subscription(client_user.id)
                    if sub and sub.expiry_date:
                        self._send_notification(core, client_user.id, payment.subscription_tier,
                            payment.duration_days or 30, sub.expiry_date.strftime('%d.%m.%Y'))
                    self._send_admin_payment_notification(core, client_user.username,
                        payment.amount_usd, payment.subscription_tier,
                        payment.payment_method.value if payment.payment_method else "crypto")

                    clients = self.get_user_clients(core, query.from_user.id)
                    config_ready = self.t("payment_confirmed_config_ready", lang) if clients else self.t("payment_confirmed_creating", lang)
                    text = self.t("payment_confirmed", lang,
                        plan=payment.subscription_tier,
                        days=payment.duration_days,
                        config_ready=config_ready,
                    )

                    keyboard = [
                        [InlineKeyboardButton(f"📥 {self.t('btn_download_config', lang)}", callback_data='my_config')],
                        [InlineKeyboardButton(f"🏠 {self.t('btn_back_to_menu', lang)}", callback_data='menu')],
                    ]

                    await query.edit_message_text(
                        text,
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    return
            except Exception as e:
                logger.error(f"CryptoPay check failed: {e}")

        # Still pending
        text = self.t("payment_pending", lang,
            plan=payment.subscription_tier,
            amount=f"{payment.amount_usd:.2f}",
        )

        keyboard = [
            [InlineKeyboardButton(f"🔄 {self.t('btn_check_payment', lang)}", callback_data=f'check_{invoice_id}')],
            [InlineKeyboardButton(f"⬅️ {self.t('btn_back', lang)}", callback_data='menu')],
        ]

        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ========================================================================
    # BOT LIFECYCLE
    # ========================================================================

    def setup_handlers(self) -> None:
        """Register all handlers"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("traffic", self.traffic_command))
        self.app.add_handler(CommandHandler("config", self.config_command))
        self.app.add_handler(CommandHandler("plans", self.plans_command))
        self.app.add_handler(CommandHandler("subscribe", self.subscribe_command))
        self.app.add_handler(CommandHandler("support", self.support_command))
        self.app.add_handler(CommandHandler("lang", self.lang_command))
        self.app.add_handler(CommandHandler("promo", self.promo_command))
        self.app.add_handler(CommandHandler("ref", self.ref_command))
        self.app.add_handler(CallbackQueryHandler(self.callback_handler))
        # Text message handler for support messages and login flow
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_message_handler))

    # ========================================================================
    # TEXT MESSAGE HANDLER (support + login flow)
    # ========================================================================

    # Emoji prefix → action mapping (language-independent routing for ReplyKeyboard)
    REPLY_KB_ROUTES = {
        "📊": "my_status",
        "📈": "my_traffic",
        "📥": "my_config",
        "💳": "subscribe",
        "📋": "plans",
        "🎁": "show_ref",
        "💬": "support",
        "➕": "add_device",
        "🔗": "link_account",
        "⌨️": "hide_keyboard",
    }

    async def text_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle plain text messages — ReplyKeyboard buttons + support/login flow"""
        text = update.message.text.strip()
        if not text:
            return

        # Check if this is a ReplyKeyboard button press (starts with a routable emoji)
        awaiting = context.user_data.get('awaiting')
        route = None
        for prefix, action in self.REPLY_KB_ROUTES.items():
            if text.startswith(prefix):
                route = action
                break

        if route and not awaiting:
            await self._handle_reply_kb_action(update, context, route)
            return

        # Otherwise handle awaiting states
        if not awaiting:
            return

        if awaiting == 'support_message':
            await self._handle_support_message(update, context, text)
        elif awaiting == 'login_email':
            await self._handle_login_email(update, context, text)
        elif awaiting == 'login_password':
            await self._handle_login_password(update, context, text)
        elif awaiting == 'device_name':
            await self._handle_device_name(update, context, text)

    async def _handle_reply_kb_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
        """Route ReplyKeyboard button presses to the appropriate handler"""
        core = self.get_core()
        try:
            user = self.get_or_create_user(core, update.effective_user)
            client_user = self.get_or_create_client_user(core, update.effective_user)
            lang = self.get_user_lang(core, update.effective_user)

            if user.is_blocked:
                await update.message.reply_text(self.t("blocked", lang))
                return

            clients = self.get_user_clients(core, user.telegram_id)

            if action == 'my_status':
                if not clients:
                    await update.message.reply_text(
                        self.t("status_no_sub", lang, sub_info=""), parse_mode='Markdown'
                    )
                elif len(clients) == 1:
                    await self._show_client_status_msg(update.message, core, clients[0], lang)
                else:
                    await update.message.reply_text(
                        self.t("status_title", lang),
                        parse_mode='Markdown',
                        reply_markup=self.get_client_select_keyboard(clients, lang)
                    )

            elif action == 'my_traffic':
                if not clients:
                    await update.message.reply_text(self.t("traffic_no_sub", lang))
                elif len(clients) == 1:
                    await self._show_traffic_msg(update.message, core, clients[0], lang)
                else:
                    await update.message.reply_text(
                        self.t("traffic_select_device", lang),
                        parse_mode='Markdown',
                        reply_markup=self.get_traffic_select_keyboard(clients, lang)
                    )

            elif action == 'my_config':
                if not clients:
                    await update.message.reply_text(
                        self.t("config_no_devices", lang), parse_mode='Markdown'
                    )
                elif len(clients) == 1:
                    await self._send_config_msg(update.message, core, clients[0], lang)
                else:
                    await update.message.reply_text(
                        self.t("config_select_device", lang),
                        parse_mode='Markdown',
                        reply_markup=self.get_config_select_keyboard(clients, lang)
                    )

            elif action == 'subscribe':
                await update.message.reply_text(
                    self.t("subscribe_select_plan", lang),
                    parse_mode='Markdown',
                    reply_markup=self.get_plans_keyboard(core, lang)
                )

            elif action == 'plans':
                await self._show_plans_msg(update.message, core, lang)

            elif action == 'show_ref':
                if client_user:
                    if not client_user.referral_code:
                        import string, random
                        client_user.referral_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                        core.db.commit()
                    ref_count = core.db.query(ClientUser).filter(
                        ClientUser.referred_by_id == client_user.id
                    ).count()
                    bot_info = await context.bot.get_me()
                    ref_link = f"https://t.me/{bot_info.username}?start=ref_{client_user.referral_code}"
                    ref_link_escaped = ref_link.replace("_", "\\_")
                    text_msg = self.t("ref_share", lang,
                        code=client_user.referral_code,
                        link=ref_link_escaped,
                        count=ref_count,
                    )
                    await update.message.reply_text(text_msg, parse_mode='Markdown')

            elif action == 'support':
                context.user_data['awaiting'] = 'support_message'
                await update.message.reply_text(
                    self.t("support_text", lang), parse_mode='Markdown'
                )

            elif action == 'add_device':
                await self._handle_add_device_msg(update.message, context, core, client_user, lang)

            elif action == 'link_account':
                context.user_data['awaiting'] = 'login_email'
                await update.message.reply_text(
                    self.t("login_enter_email", lang), parse_mode='Markdown'
                )

            elif action == 'hide_keyboard':
                await update.message.reply_text(
                    self.t("keyboard_hidden", lang),
                    reply_markup=ReplyKeyboardRemove(),
                )

        finally:
            self.close_core(core)

    async def _handle_support_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
        """Create support ticket from user's text message"""
        core = self.get_core()
        try:
            client_user = self.get_or_create_client_user(core, update.effective_user)
            lang = self.get_user_lang(core, update.effective_user)

            if not client_user:
                return

            # Create support ticket
            ticket = SupportMessage(
                user_id=client_user.id,
                subject=text[:100],  # First 100 chars as subject
                message=text,
                direction="user",
                status="open",
                is_read=False,
            )
            core.db.add(ticket)
            core.db.commit()
            core.db.refresh(ticket)

            # Notify admin
            try:
                from ..modules.notifications import NotificationService
                ns = NotificationService(core.db)
                tg_info = f" (TG: {client_user.telegram_id})" if client_user.telegram_id else ""
                ns.notify_admin(
                    f"📩 <b>New support message</b>\n"
                    f"From: {client_user.username} ({client_user.email}){tg_info}\n"
                    f"Subject: {text[:100]}\n\n"
                    f"{text[:500]}"
                )
            except Exception as e:
                logger.warning(f"Failed to notify admin about support: {e}")

            context.user_data.pop('awaiting', None)
            await update.message.reply_text(
                self.t("support_sent", lang, ticket_id=ticket.id),
                parse_mode='Markdown'
            )
        finally:
            self.close_core(core)

    async def _handle_login_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE, email: str) -> None:
        """Handle email input for account linking"""
        core = self.get_core()
        try:
            lang = self.get_user_lang(core, update.effective_user)
            context.user_data['_login_email'] = email.lower().strip()
            context.user_data['awaiting'] = 'login_password'
            await update.message.reply_text(self.t("login_enter_password", lang))
        finally:
            self.close_core(core)

    async def _handle_login_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE, password: str) -> None:
        """Handle password input — verify and link account"""
        core = self.get_core()
        try:
            lang = self.get_user_lang(core, update.effective_user)
            email = context.user_data.pop('_login_email', '')
            context.user_data.pop('awaiting', None)

            if not email:
                await update.message.reply_text(self.t("login_failed", lang))
                return

            # Find portal account by email
            target_user = core.db.query(ClientUser).filter(
                ClientUser.email == email
            ).first()

            if not target_user:
                await update.message.reply_text(self.t("login_failed", lang))
                return

            # Verify password with bcrypt
            import bcrypt
            try:
                if not bcrypt.checkpw(password.encode(), target_user.password_hash.encode()):
                    await update.message.reply_text(self.t("login_failed", lang))
                    return
            except Exception:
                await update.message.reply_text(self.t("login_failed", lang))
                return

            # Check if already linked to another TG user
            tg_id = str(update.effective_user.id)
            if target_user.telegram_id and target_user.telegram_id != tg_id:
                await update.message.reply_text(self.t("login_already_linked", lang))
                return

            # Unlink auto-created TG-only account if it exists
            auto_user = core.db.query(ClientUser).filter(
                ClientUser.telegram_id == tg_id,
                ClientUser.id != target_user.id,
            ).first()
            if auto_user:
                # Just clear telegram_id — don't delete to avoid FK issues
                auto_user.telegram_id = None
                auto_user.is_active = False
                core.db.flush()

            # Link TG to target account
            target_user.telegram_id = tg_id
            core.db.commit()
            logger.info(f"Linked TG {tg_id} to portal account {target_user.email}")

            await update.message.reply_text(
                self.t("login_success", lang, email=target_user.email),
                parse_mode='Markdown'
            )

            # Show main menu
            user = self.get_or_create_user(core, update.effective_user)
            await self._show_main_menu(update.message, core, user, target_user, lang)

        finally:
            self.close_core(core)

    def _create_portal_credentials(self, core: ManagementCore, client_user: ClientUser) -> Optional[str]:
        """Generate real portal credentials for a TG-only user. Returns password or None."""
        if self._has_portal_password(client_user):
            return None  # Already has credentials

        import bcrypt, string, random
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        client_user.password_hash = pw_hash

        # Fix email if it's a fake TG email
        if '@telegram.' in (client_user.email or ''):
            username = client_user.username or f"user_{client_user.id}"
            new_email = f"{username}@{self._email_domain}"
            counter = 1
            while core.db.query(ClientUser).filter(
                ClientUser.email == new_email, ClientUser.id != client_user.id
            ).first():
                new_email = f"{username}_{counter}@{self._email_domain}"
                counter += 1
            client_user.email = new_email

        core.db.commit()
        logger.info(f"Created portal credentials for {client_user.username} (email={client_user.email})")
        return password

    # ========================================================================
    # EXTRA COMMANDS: /lang, /promo, /ref, add_device callback
    # ========================================================================

    async def lang_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Switch language"""
        keyboard = [
            [
                InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en"),
                InlineKeyboardButton("🇷🇺 Русский", callback_data="set_lang_ru"),
            ],
            [
                InlineKeyboardButton("🇩🇪 Deutsch", callback_data="set_lang_de"),
                InlineKeyboardButton("🇪🇸 Español", callback_data="set_lang_es"),
                InlineKeyboardButton("🇫🇷 Français", callback_data="set_lang_fr"),
            ],
        ]
        core = self.get_core()
        try:
            lang = self.get_user_lang(core, update.effective_user)
            await update.message.reply_text(
                self.t("lang_select", lang),
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        finally:
            self.close_core(core)

    async def promo_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Apply promo code: /promo CODE"""
        core = self.get_core()
        try:
            client_user = self.get_or_create_client_user(core, update.effective_user)
            lang = self.get_user_lang(core, update.effective_user)

            if not context.args:
                await update.message.reply_text(self.t("promo_enter", lang))
                return

            code = context.args[0].strip().upper()
            promo = core.db.query(PromoCode).filter(PromoCode.code == code).first()

            if not promo or not promo.is_valid:
                await update.message.reply_text(self.t("promo_invalid", lang))
                return

            # Apply promo: if type=days, add free days to subscription
            mgr = SubscriptionManager(core.db)
            sub = mgr.get_subscription(client_user.id)

            if promo.discount_type == "days":
                if sub:
                    expiry = sub.expiry_date
                    if expiry and expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=timezone.utc)
                    sub.expiry_date = max(expiry or datetime.now(timezone.utc), datetime.now(timezone.utc)) + timedelta(days=int(promo.discount_value))
                    from ..modules.subscription.subscription_models import SubscriptionStatus
                    if sub.status == SubscriptionStatus.EXPIRED:
                        sub.status = SubscriptionStatus.ACTIVE
                    # Atomic increment — avoids lost-update race condition under concurrent requests
                    from sqlalchemy import text as _text
                    core.db.execute(_text("UPDATE promo_codes SET used_count = COALESCE(used_count, 0) + 1 WHERE id = :id"), {"id": promo.id})
                    core.db.commit()
                    await update.message.reply_text(
                        self.t("promo_applied", lang, code=code, value=f"+{int(promo.discount_value)} days"),
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(
                        self.t("status_no_sub", lang, sub_info=""),
                        parse_mode='Markdown'
                    )
            else:
                # Percent discount — store in user_data, apply at checkout
                # Atomic increment — avoids lost-update race condition under concurrent requests
                from sqlalchemy import text as _text
                core.db.execute(_text("UPDATE promo_codes SET used_count = COALESCE(used_count, 0) + 1 WHERE id = :id"), {"id": promo.id})
                core.db.commit()
                context.user_data['active_promo'] = {
                    'code': code,
                    'discount': promo.discount_value,
                }
                await update.message.reply_text(
                    self.t("promo_applied", lang, code=code, value=f"{int(promo.discount_value)}% discount"),
                    parse_mode='Markdown'
                )
        finally:
            self.close_core(core)

    async def ref_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show referral link and stats"""
        core = self.get_core()
        try:
            client_user = self.get_or_create_client_user(core, update.effective_user)
            lang = self.get_user_lang(core, update.effective_user)

            if not client_user:
                await update.message.reply_text("Error: user not found")
                return

            # Ensure referral code exists
            if not client_user.referral_code:
                import string, random
                client_user.referral_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                core.db.commit()

            ref_count = core.db.query(ClientUser).filter(
                ClientUser.referred_by_id == client_user.id
            ).count()

            bot_username = (await context.bot.get_me()).username
            ref_link = f"https://t.me/{bot_username}?start=ref_{client_user.referral_code}"
            ref_link_escaped = ref_link.replace("_", "\\_")

            text = self.t("ref_share", lang,
                code=client_user.referral_code,
                link=ref_link_escaped,
                count=ref_count,
            )
            await update.message.reply_text(text, parse_mode="Markdown")
        finally:
            self.close_core(core)

    async def _handle_lang_callback(self, query, lang_code: str):
        """Handle language selection callback"""
        core = self.get_core()
        try:
            client_user = self.get_or_create_client_user(core, query.from_user)
            if client_user:
                client_user.language = lang_code
                core.db.commit()
            self._locale_cache.pop(lang_code, None)
            await query.edit_message_text(self.t("lang_changed", lang_code))
        finally:
            self.close_core(core)

    async def _handle_add_device(self, query, context, core, client_user, lang):
        """Handle add device callback — ask for server first."""
        mgr = SubscriptionManager(core.db)
        sub = mgr.get_subscription(client_user.id)

        if not sub or sub.tier == "free":
            await query.edit_message_text(self.t("no_subscription_for_device", lang))
            return

        existing = mgr.get_user_wireguard_clients(client_user.id)
        if len(existing) >= (sub.max_devices or 1):
            await query.edit_message_text(
                self.t("device_limit_reached", lang, max=sub.max_devices),
                parse_mode='Markdown'
            )
            return

        servers = self._get_available_servers(core)
        if not servers:
            await query.edit_message_text(self.t("device_no_servers", lang))
            return

        await query.edit_message_text(
            self.t("device_select_server", lang),
            parse_mode='Markdown',
            reply_markup=self.get_server_select_keyboard(servers, lang),
        )

    async def _handle_add_device_server(self, query, context, core, client_user, lang: str, server_id: int) -> None:
        server = core.get_server(server_id)
        if not server:
            await query.edit_message_text(self.t("device_server_not_found", lang))
            return

        context.user_data['awaiting'] = 'device_name'
        context.user_data['device_server_id'] = server.id
        context.user_data['device_server_name'] = getattr(server, "display_name", None) or server.name
        context.user_data['device_server_protocol'] = self._protocol_display_name(getattr(server, "server_type", None))

        await query.edit_message_text(
            self.t(
                "device_create_for_server",
                lang,
                server=context.user_data['device_server_name'],
                protocol=context.user_data['device_server_protocol'],
            ),
            parse_mode='Markdown',
        )

    async def _handle_device_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE, name: str) -> None:
        """Handle device name input after user was prompted via add_device flow."""
        context.user_data.pop('awaiting', None)
        core = self.get_core()
        try:
            client_user = self.get_or_create_client_user(core, update.effective_user)
            lang = self.get_user_lang(core, update.effective_user)

            # Basic validation
            name = name.strip()[:64]
            if not name:
                await update.message.reply_text(self.t("device_create_failed", lang))
                return

            mgr = SubscriptionManager(core.db)
            server_id = context.user_data.pop('device_server_id', None)
            server_name = context.user_data.pop('device_server_name', None)
            protocol_name = context.user_data.pop('device_server_protocol', None)

            subscription = mgr.get_subscription(client_user.id)
            status_value = getattr(subscription.status, "value", str(subscription.status)).lower() if subscription else ""
            if not subscription or status_value != "active":
                await update.message.reply_text(self.t("no_subscription_for_device", lang))
                return

            existing_count = core.db.query(ClientUserClients).filter(
                ClientUserClients.client_user_id == client_user.id
            ).count()
            max_devices = subscription.max_devices or 1
            if existing_count >= max_devices:
                await update.message.reply_text(
                    self.t("device_limit_reached", lang, max=max_devices),
                    parse_mode='Markdown'
                )
                return

            if server_id is None:
                default_server = core.servers.get_default_server()
                if not default_server:
                    await update.message.reply_text(self.t("device_no_servers", lang))
                    return
                server_id = default_server.id
                server_name = getattr(default_server, "display_name", None) or default_server.name
                protocol_name = self._protocol_display_name(getattr(default_server, "server_type", None))

            if subscription.expiry_date:
                import math as _math
                expiry = subscription._aware_expiry()
                _delta_secs = (expiry - datetime.now(timezone.utc)).total_seconds()
                expiry_days = max(1, _math.ceil(_delta_secs / 86400))
            else:
                expiry_days = 30

            created_client = core.create_client(
                name=name,
                server_id=server_id,
                bandwidth_limit=subscription.bandwidth_limit_mbps,
                traffic_limit_mb=int(subscription.traffic_limit_gb * 1024) if subscription.traffic_limit_gb else None,
                expiry_days=expiry_days,
            )
            if created_client:
                link = ClientUserClients(client_user_id=client_user.id, client_id=created_client.id)
                core.db.add(link)
                core.db.commit()
                await update.message.reply_text(
                    self.t(
                        "device_created",
                        lang,
                        name=created_client.name,
                        server=server_name or "Default",
                        protocol=protocol_name or "WireGuard",
                    ),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(self.t("device_create_failed", lang))
        except Exception as e:
            logger.error(f"Failed to create device with name '{name}': {e}")
            try:
                lang = 'en'
                await update.message.reply_text(self.t("device_create_failed", lang))
            except Exception:
                pass
        finally:
            core.close()

    async def _post_init(self, app) -> None:
        """Register bot commands so the ☰ menu button appears next to the text field"""
        from telegram import BotCommand
        commands = [
            BotCommand("start",     "Main menu"),
            BotCommand("status",    "Subscription status"),
            BotCommand("traffic",   "Traffic usage"),
            BotCommand("config",    "Download VPN config"),
            BotCommand("plans",     "Available plans"),
            BotCommand("subscribe", "Subscribe"),
            BotCommand("promo",     "Apply promo code"),
            BotCommand("ref",       "Referral link"),
            BotCommand("lang",      "Change language"),
            BotCommand("support",   "Contact support"),
            BotCommand("help",      "Help"),
        ]
        await app.bot.set_my_commands(commands)
        logger.info("Bot commands registered (☰ menu button active)")

    def run(self) -> None:
        """Run the bot"""
        self.app = Application.builder().token(self.token).post_init(self._post_init).build()
        self.setup_handlers()

        logger.info("Starting client bot...")
        self.app.run_polling(drop_pending_updates=True)


def main():
    """Main entry point"""
    from loguru import logger
    import sys

    # Configure logging
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    # Check if client bot is enabled
    if os.getenv("CLIENT_BOT_ENABLED", "true").lower() != "true":
        logger.info("Client bot disabled via CLIENT_BOT_ENABLED=false, exiting.")
        sys.exit(0)

    # Get configuration from environment
    token = os.getenv("CLIENT_BOT_TOKEN")

    if not token:
        logger.error("CLIENT_BOT_TOKEN environment variable not set")
        sys.exit(1)

    bot = ClientBot(token=token)
    bot.run()


if __name__ == "__main__":
    main()
