#!/usr/bin/env python3
"""
Flirexa Admin Bot
Telegram bot for VPN administration - refactored to use Core API
"""

import os
import io
import asyncio
import html
from datetime import datetime, timedelta, timezone
from typing import Optional, List

import qrcode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import BadRequest
from loguru import logger

from ..database.connection import SessionLocal
from ..core.management import ManagementCore


class AdminBot:
    """
    Admin Telegram Bot for WireGuard management

    Uses ManagementCore for all operations instead of direct file access.
    """

    def __init__(
        self,
        token: str,
        allowed_users: List[int],
    ):
        """
        Initialize the admin bot

        Args:
            token: Telegram bot token
            allowed_users: List of Telegram user IDs allowed to use the bot
        """
        self.token = token
        self.allowed_users = allowed_users
        self.app: Optional[Application] = None

    @staticmethod
    def _h(value) -> str:
        return html.escape(str(value), quote=True)

    @staticmethod
    def _button_text(value, limit: int = 60) -> str:
        text = str(value).replace("\n", " ").strip()
        return text if len(text) <= limit else text[: limit - 1] + "…"

    @staticmethod
    def _get_client_by_ref(core: ManagementCore, reference: str):
        """Resolve an ID, or an unambiguous legacy name from an old message."""
        if str(reference).isdigit():
            client = core.get_client(int(reference))
            if client:
                return client
        from ..database.models import Client as ClientModel

        matches = core.db.query(ClientModel).filter(
            ClientModel.name == str(reference)
        ).limit(2).all()
        return matches[0] if len(matches) == 1 else None

    # ========================================================================
    # AUTHORIZATION
    # ========================================================================

    def check_auth(self, user_id: int) -> bool:
        """Check if user is authorized"""
        return user_id in self.allowed_users

    async def unauthorized_response(self, update: Update) -> None:
        """Send unauthorized message"""
        await update.message.reply_text(
            f"❌ У вас нет доступа к этому боту!\n"
            f"Ваш ID: {update.effective_user.id}"
        )

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def get_core(self) -> ManagementCore:
        """Get a new ManagementCore instance with fresh DB session"""
        db = SessionLocal()
        return ManagementCore(db)

    def close_core(self, core: ManagementCore) -> None:
        """Close the database session"""
        core.db.close()

    @staticmethod
    def _has_feature(feature: str) -> bool:
        try:
            from ..modules.license.manager import get_license_manager
            return get_license_manager().has_feature(feature)
        except Exception:
            return False

    @staticmethod
    def _feature_denied_text(feature: str) -> str:
        from ..api.middleware.license_gate import FEATURE_MINIMUM_TIER
        tier = FEATURE_MINIMUM_TIER.get(feature, "business").title()
        return f"🔒 Эта функция доступна с тарифом {tier}."

    @staticmethod
    def _enum_value(value) -> str:
        return str(getattr(value, "value", value) or "")

    async def _run_sync(self, func, timeout: float = 30.0):
        """Run a sync function in a thread to avoid blocking the event loop.
        All ManagementCore operations (DB + SSH) are synchronous and must be
        wrapped in this to keep the bot responsive.
        timeout: max seconds to wait (default 30s — SSH ops can be slow but shouldn't hang forever)"""
        try:
            return await asyncio.wait_for(asyncio.to_thread(func), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"_run_sync timeout ({timeout}s) for {getattr(func, '__name__', repr(func))}")
            raise

    async def safe_edit(self, query, text, **kwargs):
        """Safely edit a message, falling back to reply if it can't be edited
        (e.g., when the message is a photo/document or was deleted)."""
        try:
            await query.edit_message_text(text, **kwargs)
        except BadRequest as e:
            err = str(e).lower()
            if "message is not modified" in err:
                return
            if "no text in the message" in err:
                try:
                    await query.message.reply_text(text, **kwargs)
                except Exception:
                    pass
            else:
                logger.warning(f"safe_edit BadRequest: {e}")

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Global error handler for the bot"""
        error = context.error
        if isinstance(error, asyncio.TimeoutError):
            msg = (
                "⏱ Сервер отвечает дольше обычного. Операция могла продолжиться в фоне. "
                "Проверьте состояние перед повторным запуском."
            )
            logger.warning(f"Bot operation timeout: {error}")
        else:
            msg = "⚠️ Произошла ошибка, попробуйте снова"
            logger.error(f"Bot error: {error}")
        if update and hasattr(update, 'callback_query') and update.callback_query:
            try:
                await update.callback_query.answer(msg, show_alert=True)
            except Exception:
                pass
        elif update and hasattr(update, 'message') and update.message:
            try:
                await update.message.reply_text(msg)
            except Exception:
                pass

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

    # ========================================================================
    # KEYBOARDS
    # ========================================================================

    def get_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        """Main menu keyboard"""
        keyboard = [
            [
                InlineKeyboardButton("➕ Создать", callback_data='menu_new'),
                InlineKeyboardButton("📋 Клиенты", callback_data='menu_list'),
            ],
            [
                InlineKeyboardButton("🟢 Онлайн", callback_data='menu_online'),
                InlineKeyboardButton("🖥 Серверы", callback_data='menu_servers'),
            ],
            [
                InlineKeyboardButton("💼 Бизнес", callback_data='menu_business'),
                InlineKeyboardButton("🛡 Система", callback_data='menu_system'),
            ],
            [InlineKeyboardButton("📊 Статистика", callback_data='menu_stats')],
            [InlineKeyboardButton("❓ Помощь", callback_data='menu_help')]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_business_menu_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👤 Пользователи портала", callback_data="biz_users"),
                InlineKeyboardButton("💳 Платежи", callback_data="biz_payments"),
            ],
            [
                InlineKeyboardButton("💬 Поддержка", callback_data="biz_support"),
                InlineKeyboardButton("🎟 Промокоды", callback_data="biz_promos"),
            ],
            [
                InlineKeyboardButton("📦 Тарифы", callback_data="biz_tariffs"),
                InlineKeyboardButton("📣 Рассылка", callback_data="biz_broadcast"),
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")],
        ])

    def get_system_menu_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("❤️ Состояние", callback_data="sys_health"),
                InlineKeyboardButton("🔑 Лицензия", callback_data="sys_license"),
            ],
            [
                InlineKeyboardButton("💾 Резервные копии", callback_data="sys_backups"),
                InlineKeyboardButton("⬆️ Обновления", callback_data="sys_updates"),
            ],
            [InlineKeyboardButton("📜 Последние действия", callback_data="sys_audit")],
            [InlineKeyboardButton("🚦 Правила трафика", callback_data="sys_traffic_rules")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")],
        ])

    def get_servers_list_keyboard(self, page: int = 0) -> InlineKeyboardMarkup:
        """Server list keyboard (lightweight — no SSH/WG calls)"""
        core = self.get_core()
        try:
            servers = core.get_all_servers()
            page_size = 15
            page_count = max(1, (len(servers) + page_size - 1) // page_size)
            page = max(0, min(page, page_count - 1))
            keyboard = []
            for server in servers[page * page_size:(page + 1) * page_size]:
                # Use DB status + client count instead of expensive get_server_stats()
                from ..database.models import Client as ClientModel
                total_clients = core.db.query(ClientModel).filter(
                    ClientModel.server_id == server.id
                ).count()
                is_online = server.status.value in ('ONLINE', 'online') if hasattr(server.status, 'value') else str(server.status) in ('ONLINE', 'online')
                status_icon = "🟢" if is_online else "🔴"
                label = self._button_text(f"{status_icon} {server.name} ({total_clients} кл.)")
                keyboard.append([InlineKeyboardButton(
                    label,
                    callback_data=f'srv_{server.id}'
                )])
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton("◀️", callback_data=f'servers_page_{page - 1}'))
            if page_count > 1:
                nav.append(InlineKeyboardButton(f"{page + 1}/{page_count}", callback_data='noop'))
            if page + 1 < page_count:
                nav.append(InlineKeyboardButton("▶️", callback_data=f'servers_page_{page + 1}'))
            if nav:
                keyboard.append(nav)
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='menu_main')])
            return InlineKeyboardMarkup(keyboard)
        finally:
            self.close_core(core)

    def get_server_menu_keyboard(self, server_id: int, is_online: bool) -> InlineKeyboardMarkup:
        """Server management menu"""
        keyboard = []
        if is_online:
            keyboard.append([InlineKeyboardButton("🔴 Остановить", callback_data=f'srv_confirm_stop_{server_id}')])
            keyboard.append([InlineKeyboardButton("🔄 Перезапустить", callback_data=f'srv_confirm_restart_{server_id}')])
        else:
            keyboard.append([InlineKeyboardButton("🟢 Запустить", callback_data=f'srv_start_{server_id}')])
        keyboard.append([InlineKeyboardButton("👥 Клиенты сервера", callback_data=f'srv_clients_{server_id}')])
        keyboard.append([InlineKeyboardButton("💾 Сохранить конфиг", callback_data=f'srv_saveconf_{server_id}')])
        keyboard.append([InlineKeyboardButton("⬅️ К серверам", callback_data='menu_servers')])
        return InlineKeyboardMarkup(keyboard)

    def get_server_select_keyboard(self, action: str) -> InlineKeyboardMarkup:
        """Keyboard for selecting a server (used when creating client with multiple servers)"""
        core = self.get_core()
        try:
            servers = core.get_all_servers()
            keyboard = []
            for server in servers:
                from ..database.models import Client as ClientModel
                total = core.db.query(ClientModel).filter(
                    ClientModel.server_id == server.id
                ).count()
                max_c = server.max_clients or 250
                label = self._button_text(f"{server.name} ({total}/{max_c})")
                keyboard.append([InlineKeyboardButton(
                    label,
                    callback_data=f'{action}_{server.id}'
                )])
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='menu_main')])
            return InlineKeyboardMarkup(keyboard)
        finally:
            self.close_core(core)

    def get_client_menu_keyboard(self, client_id: int, client_enabled: bool) -> InlineKeyboardMarkup:
        """Client management menu"""
        keyboard = []

        # Enable/Disable button
        if client_enabled:
            keyboard.append([InlineKeyboardButton(
                "⏸ Отключить клиента",
                callback_data=f'disable_{client_id}'
            )])
        else:
            keyboard.append([InlineKeyboardButton(
                "▶️ Включить клиента",
                callback_data=f'enable_{client_id}'
            )])

        # Speed buttons
        keyboard.append([
            InlineKeyboardButton("🐌 10 Mbps", callback_data=f'speed_{client_id}_10'),
            InlineKeyboardButton("🚶 20 Mbps", callback_data=f'speed_{client_id}_20')
        ])
        keyboard.append([
            InlineKeyboardButton("🏃 30 Mbps", callback_data=f'speed_{client_id}_30'),
            InlineKeyboardButton("🚄 50 Mbps", callback_data=f'speed_{client_id}_50')
        ])
        keyboard.append([
            InlineKeyboardButton("🚀 100 Mbps", callback_data=f'speed_{client_id}_100'),
            InlineKeyboardButton("♾️ Без ограничений", callback_data=f'speed_{client_id}_0')
        ])

        # Timer button
        keyboard.append([InlineKeyboardButton(
            "⏱ Установить таймер",
            callback_data=f'timer_menu_{client_id}'
        )])

        # Traffic limit button
        keyboard.append([InlineKeyboardButton(
            "📊 Лимит трафика",
            callback_data=f'traffic_menu_{client_id}'
        )])

        # Get config button
        keyboard.append([InlineKeyboardButton(
            "📥 Получить конфиг",
            callback_data=f'getconf_{client_id}'
        )])

        # Delete button
        keyboard.append([InlineKeyboardButton(
            "🗑 Удалить клиента",
            callback_data=f'delete_ask_{client_id}'
        )])

        # Back button
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='menu_list')])

        return InlineKeyboardMarkup(keyboard)

    def get_timer_menu_keyboard(self, client_ref: str) -> InlineKeyboardMarkup:
        """Timer setting menu"""
        keyboard = [
            [
                InlineKeyboardButton("1 день", callback_data=f'setexpiry_{client_ref}_1'),
                InlineKeyboardButton("3 дня", callback_data=f'setexpiry_{client_ref}_3')
            ],
            [
                InlineKeyboardButton("7 дней", callback_data=f'setexpiry_{client_ref}_7'),
                InlineKeyboardButton("15 дней", callback_data=f'setexpiry_{client_ref}_15')
            ],
            [
                InlineKeyboardButton("30 дней", callback_data=f'setexpiry_{client_ref}_30'),
                InlineKeyboardButton("90 дней", callback_data=f'setexpiry_{client_ref}_90')
            ],
            [InlineKeyboardButton("♾️ Без ограничения", callback_data=f'setexpiry_{client_ref}_0')],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f'client_{client_ref}')]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_traffic_menu_keyboard(self, client_ref: str) -> InlineKeyboardMarkup:
        """Traffic limit menu"""
        keyboard = [
            [
                InlineKeyboardButton("500 MB", callback_data=f'traffic_set_{client_ref}_500'),
                InlineKeyboardButton("1 GB", callback_data=f'traffic_set_{client_ref}_1024')
            ],
            [
                InlineKeyboardButton("3 GB", callback_data=f'traffic_set_{client_ref}_3072'),
                InlineKeyboardButton("5 GB", callback_data=f'traffic_set_{client_ref}_5120')
            ],
            [
                InlineKeyboardButton("10 GB", callback_data=f'traffic_set_{client_ref}_10240'),
                InlineKeyboardButton("20 GB", callback_data=f'traffic_set_{client_ref}_20480')
            ],
            [
                InlineKeyboardButton("50 GB", callback_data=f'traffic_set_{client_ref}_51200'),
                InlineKeyboardButton("100 GB", callback_data=f'traffic_set_{client_ref}_102400')
            ],
            [InlineKeyboardButton("♾️ Без лимита", callback_data=f'traffic_set_{client_ref}_0')],
            [InlineKeyboardButton("🔄 Сбросить счётчик", callback_data=f'resettraffic_{client_ref}')],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f'client_{client_ref}')]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_clients_list_keyboard(self, page: int = 0) -> InlineKeyboardMarkup:
        """Client list keyboard (lightweight — no SSH/WG calls, DB only)"""
        core = self.get_core()
        try:
            from ..database.models import Client as ClientModel
            clients = core.db.query(ClientModel).order_by(ClientModel.name).all()

            page_size = 20
            page_count = max(1, (len(clients) + page_size - 1) // page_size)
            page = max(0, min(page, page_count - 1))
            keyboard = []
            for c in clients[page * page_size:(page + 1) * page_size]:
                status = "✅" if c.enabled else "❌"

                # Bandwidth info from DB
                bw = f"⚡{c.bandwidth_limit}M" if c.bandwidth_limit else "♾️"

                # Expiry info from DB
                expiry_text = ""
                if c.expiry_date:
                    from datetime import datetime, timezone
                    now = datetime.now(timezone.utc)
                    expiry = c.expiry_date if c.expiry_date.tzinfo else c.expiry_date.replace(tzinfo=timezone.utc)
                    remaining = expiry - now
                    if remaining.total_seconds() > 0:
                        days = remaining.days
                        if days > 0:
                            expiry_text = f" ⏱{days}д"
                        else:
                            hours = int(remaining.total_seconds() // 3600)
                            expiry_text = f" ⏱{hours}ч"

                # Traffic warning from DB
                traffic_text = ""
                if c.traffic_limit_mb and c.traffic_limit_mb > 0:
                    used = (c.traffic_used_rx or 0) + (c.traffic_used_tx or 0)
                    limit_bytes = c.traffic_limit_mb * 1024 * 1024
                    if limit_bytes > 0:
                        pct = used / limit_bytes * 100
                        if pct >= 80:
                            traffic_text = f" 📊{int(pct)}%"

                label = self._button_text(f"{status} {c.name} ({bw}{expiry_text}{traffic_text})")
                keyboard.append([InlineKeyboardButton(
                    label,
                    callback_data=f"client_{c.id}"
                )])

            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton("◀️", callback_data=f'clients_page_{page - 1}'))
            if page_count > 1:
                nav.append(InlineKeyboardButton(f"{page + 1}/{page_count}", callback_data='noop'))
            if page + 1 < page_count:
                nav.append(InlineKeyboardButton("▶️", callback_data=f'clients_page_{page + 1}'))
            if nav:
                keyboard.append(nav)
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='menu_main')])
            return InlineKeyboardMarkup(keyboard)

        finally:
            self.close_core(core)

    # ========================================================================
    # COMMAND HANDLERS
    # ========================================================================

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command"""
        if not self.check_auth(update.effective_user.id):
            await self.unauthorized_response(update)
            return

        await update.message.reply_text(
            "🔐 <b>Flirexa</b>\n\n"
            "Добро пожаловать! Выберите действие:",
            parse_mode='HTML',
            reply_markup=self.get_main_menu_keyboard()
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command"""
        if not self.check_auth(update.effective_user.id):
            await self.unauthorized_response(update)
            return

        help_text = """
📖 <b>Справка по боту</b>

<b>Основные команды:</b>
/start - Главное меню
/new <имя> [id_сервера] - Создать клиента
/list - Список клиентов
/settimer <id|имя> <дни> - Установить таймер
/settraffic <id|имя> <MB> - Лимит трафика
/newpromo <код> <процент> [лимит] - Создать промокод
/grant <user_id> <tier> <дни> - Выдать тариф
/help - Эта справка

<b>Команды серверов:</b>
/servers - Список серверов
/serverinfo <id|имя> - Информация о сервере

<b>Управление клиентом:</b>
• Нажмите на клиента в списке
• Включить/выключить клиента
• Установить ограничение скорости
• Установить таймер (автоотключение)
• Установить лимит трафика
• Получить конфиг и QR код

<b>Управление серверами:</b>
• Запуск/остановка/перезапуск
• Просмотр клиентов на сервере
• Сохранение конфигурации
• Безопасная миграция клиентов выполняется в веб-панели

<b>Бизнес и система:</b>
• Онлайн-клиенты и актуальные рукопожатия
• Пользователи портала, платежи и обращения поддержки
• Промокоды с серверной проверкой тарифа
• Health, лицензия, создание/проверка backup
• Проверка и защищённый запуск обновлений
• Последние записи аудита

Восстановление backup, сетевые настройки, плагины, branding и массовые
операции намеренно остаются в веб-панели: их нельзя безопасно свести к
одному Telegram-нажатию без полного контекста и rollback-параметров.

<b>Ограничения скорости:</b>
10, 20, 30, 50, 100 Mbps или без ограничений

<b>Таймер:</b>
Клиент автоматически отключается после истечения срока

<b>Лимит трафика:</b>
Клиент отключается при превышении лимита
"""

        await update.message.reply_text(
            help_text,
            parse_mode='HTML',
            reply_markup=self.get_main_menu_keyboard()
        )

    async def new_client_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /new command - create new client"""
        if not self.check_auth(update.effective_user.id):
            await self.unauthorized_response(update)
            return

        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Укажите имя клиента!\n"
                "Пример: /new MyPhone"
            )
            return

        client_name = context.args[0]

        # Validate name
        if (
            len(client_name) > 48
            or not client_name[0].isalnum()
            or not all(c.isascii() and (c.isalnum() or c in '-_') for c in client_name)
        ):
            await update.message.reply_text(
                "❌ Используйте 1–48 латинских букв, цифр, дефисов или подчёркиваний."
            )
            return

        server_id = None
        if len(context.args) > 1:
            try:
                server_id = int(context.args[1])
            except ValueError:
                await update.message.reply_text("❌ ID сервера должен быть числом")
                return
            if server_id < 1:
                await update.message.reply_text("❌ ID сервера должен быть положительным числом")
                return

        await update.message.reply_text("⏳ Создаю нового клиента...")

        def _sync():
            core = self.get_core()
            try:
                target_server = core.get_server(server_id) if server_id is not None else core.servers.get_default_server()
                if not target_server:
                    return {'error': "❌ Сервер не найден"}
                from ..database.models import Client as ClientModel
                if core.db.query(ClientModel).filter(
                    ClientModel.server_id == target_server.id,
                    ClientModel.name == client_name,
                ).first():
                    return {'error': f"❌ Клиент '{client_name}' уже существует!"}

                client = core.create_client(name=client_name, server_id=target_server.id)
                if not client:
                    return {'error': "❌ Ошибка создания клиента"}

                config = core.get_client_config(client.id)
                return {
                    'id': client.id,
                    'name': client.name,
                    'ipv4': client.ipv4,
                    'config': config,
                    'server': target_server.name,
                    'protocol': getattr(target_server, 'server_type', 'wireguard'),
                    'extension': (
                        'yaml' if getattr(target_server, 'server_type', '') == 'hysteria2'
                        else 'json' if getattr(target_server, 'server_type', '') in {'tuic', 'vless-reality'}
                        else 'conf'
                    ),
                }
            except Exception as e:
                logger.error(f"Error creating client: {e}")
                return {'error': "❌ Не удалось создать клиента. Подробности записаны в журнал сервиса."}
            finally:
                self.close_core(core)

        result = await self._run_sync(_sync)
        if 'error' in result:
            await update.message.reply_text(result['error'])
            return

        await update.message.reply_text(
            f"✅ <b>Клиент создан успешно!</b>\n\n"
            f"👤 Имя: <code>{self._h(result['name'])}</code>\n"
            f"🖥 Сервер: <code>{self._h(result['server'])}</code>\n"
            f"🌐 IP: <code>{self._h(result['ipv4'])}</code>\n"
            f"⚡ Скорость: Без ограничений",
            parse_mode='HTML'
        )

        if result['config']:
            qr_image = self.create_qr_code(result['config'])
            await update.message.reply_photo(
                photo=qr_image,
                caption=f"📱 QR код для {client_name}"
            )

            config_bio = io.BytesIO(result['config'].encode())
            config_bio.name = f"{client_name}.{result['extension']}"
            await update.message.reply_document(
                document=config_bio,
                filename=config_bio.name,
                caption="💾 Файл конфигурации",
                reply_markup=self.get_client_menu_keyboard(result['id'], True)
            )

    async def list_clients_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /list command"""
        if not self.check_auth(update.effective_user.id):
            await self.unauthorized_response(update)
            return

        def _sync():
            core = self.get_core()
            try:
                clients = core.get_all_clients()
                return len(clients) if clients else 0
            finally:
                self.close_core(core)

        count = await self._run_sync(_sync)
        if count == 0:
            await update.message.reply_text(
                "📭 Нет созданных клиентов\n\n"
                "Создайте первого клиента: /new MyPhone"
            )
            return

        keyboard = await self._run_sync(self.get_clients_list_keyboard)
        await update.message.reply_text(
            "📋 <b>Список клиентов</b>\n\n"
            "Выберите клиента для управления:",
            parse_mode='HTML',
            reply_markup=keyboard
        )

    async def set_timer_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /settimer command"""
        if not self.check_auth(update.effective_user.id):
            await self.unauthorized_response(update)
            return

        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "❌ Неправильный формат!\n\n"
                "Использование: /settimer <id|имя> <дни>\n"
                "Пример: /settimer MyPhone 30"
            )
            return

        client_name = context.args[0]
        try:
            days = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Количество дней должно быть числом!")
            return
        if not 0 <= days <= 36500:
            await update.message.reply_text("❌ Допустимый срок: от 0 до 36500 дней")
            return

        def _sync():
            core = self.get_core()
            try:
                client = self._get_client_by_ref(core, client_name)
                if not client:
                    return {'error': f"❌ Клиент '{client_name}' не найден!"}
                if core.set_expiry(client.id, days):
                    expiry_info = core.get_expiry_info(client.id)
                    return {'success': True, 'expiry_info': expiry_info}
                return {'error': "❌ Ошибка установки таймера"}
            finally:
                self.close_core(core)

        result = await self._run_sync(_sync)
        if 'error' in result:
            await update.message.reply_text(result['error'])
        elif days > 0:
            expiry_info = result['expiry_info']
            await update.message.reply_text(
                f"✅ Таймер для {client_name} установлен на {days} дней\n"
                f"📅 Истекает: {expiry_info['expiry_date'].strftime('%d.%m.%Y %H:%M')}"
            )
        else:
            await update.message.reply_text(f"✅ Таймер для {client_name} убран")

    async def set_traffic_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /settraffic command"""
        if not self.check_auth(update.effective_user.id):
            await self.unauthorized_response(update)
            return

        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "❌ Неправильный формат!\n\n"
                "Использование: /settraffic <id|имя> <MB>\n"
                "Пример: /settraffic MyPhone 5120"
            )
            return

        client_name = context.args[0]
        try:
            limit_mb = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Лимит должен быть числом!")
            return
        if not 0 <= limit_mb <= 100_000_000:
            await update.message.reply_text("❌ Допустимый лимит: от 0 до 100000000 MB")
            return

        def _sync():
            core = self.get_core()
            try:
                client = self._get_client_by_ref(core, client_name)
                if not client:
                    return 'not_found'
                return core.set_traffic_limit(client.id, limit_mb)
            finally:
                self.close_core(core)

        result = await self._run_sync(_sync)
        if result == 'not_found':
            await update.message.reply_text(f"❌ Клиент '{client_name}' не найден!")
        elif result:
            if limit_mb > 0:
                await update.message.reply_text(f"✅ Лимит трафика для {client_name}: {limit_mb} MB")
            else:
                await update.message.reply_text(f"✅ Лимит трафика для {client_name} убран")
        else:
            await update.message.reply_text("❌ Ошибка установки лимита")

    # ========================================================================
    # SERVER COMMANDS
    # ========================================================================

    async def servers_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /servers command"""
        if not self.check_auth(update.effective_user.id):
            await self.unauthorized_response(update)
            return

        keyboard = await self._run_sync(self.get_servers_list_keyboard)
        await update.message.reply_text(
            "🖥 <b>VPN-серверы</b>\n\n"
            "Выберите сервер для управления:",
            parse_mode='HTML',
            reply_markup=keyboard
        )

    async def serverinfo_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /serverinfo <id|name> command"""
        if not self.check_auth(update.effective_user.id):
            await self.unauthorized_response(update)
            return

        if not context.args:
            await update.message.reply_text(
                "❌ Укажите ID или имя сервера!\n"
                "Пример: /serverinfo 1"
            )
            return

        arg = context.args[0]

        def _sync():
            core = self.get_core()
            try:
                try:
                    server = core.get_server(int(arg))
                except ValueError:
                    server = core.servers.get_server_by_name(arg)
                if not server:
                    return None
                stats = core.get_server_stats(server.id)
                return {
                    'id': server.id,
                    'name': server.name,
                    'endpoint': server.endpoint,
                    'interface': server.interface,
                    'listen_port': server.listen_port,
                    'max_clients': server.max_clients,
                    'location': server.location,
                    'protocol': getattr(server, 'server_type', 'wireguard'),
                    'address_pool_ipv4': server.address_pool_ipv4,
                    'public_key': server.public_key,
                    'is_default': server.is_default,
                    'agent_mode': server.agent_mode or 'ssh',
                    'drift_detected': bool(server.drift_detected),
                    'stats': stats,
                }
            finally:
                self.close_core(core)

        data = await self._run_sync(_sync)
        if data is None:
            await update.message.reply_text(f"❌ Сервер '{arg}' не найден!")
            return

        stats = data['stats'] or {}
        status_icon = "🟢 Онлайн" if stats and stats.get('is_online') else "🔴 Офлайн"

        text = (
            f"🖥 <b>{self._h(data['name'])}</b>\n\n"
            f"📊 Статус: {status_icon}\n"
            f"🌐 Endpoint: <code>{self._h(data['endpoint'])}</code>\n"
            f"🔧 Интерфейс: <code>{self._h(data['interface'])}</code>\n"
            f"🔌 Порт: {data['listen_port']}\n"
            f"🧩 Протокол: <code>{self._h(data['protocol'])}</code>\n"
            f"🗂 IPv4 pool: <code>{self._h(data['address_pool_ipv4'])}</code>\n"
            f"🔑 Public key: <code>{self._h(data['public_key'])}</code>\n"
            f"🤖 Управление: {self._h(data['agent_mode'])}\n"
            f"⭐ Сервер по умолчанию: {'да' if data['is_default'] else 'нет'}\n"
            f"🧭 Drift: {'⚠️ обнаружен' if data['drift_detected'] else 'нет'}\n"
            f"👥 Клиентов: {stats.get('total_clients', 0)}/{data['max_clients']}\n"
            f"✅ Активных: {stats.get('active_clients', 0)}\n"
        )
        if data['location']:
            text += f"📍 Локация: {self._h(data['location'])}\n"

        is_online = stats.get('is_online', False) if stats else False
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=self.get_server_menu_keyboard(data['id'], is_online)
        )

    async def moveuser_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /moveuser <client_name> <target_server_id> command"""
        if not self.check_auth(update.effective_user.id):
            await self.unauthorized_response(update)
            return

        await update.message.reply_text(
            "⚠️ Старый перенос через Telegram отключён: он не может безопасно "
            "проверить совместимость протоколов, ключей и откат удалённых операций.\n\n"
            "Используйте защищённую миграцию в веб-панели: Серверы → нужный сервер → Миграция клиентов."
        )

    # ========================================================================
    # CALLBACK HANDLERS
    # ========================================================================

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle all callback queries"""
        query = update.callback_query
        await query.answer()

        if not self.check_auth(update.effective_user.id):
            await self.safe_edit(query, "❌ У вас нет доступа!")
            return

        data = query.data

        if data == 'noop':
            return

        # Menu navigation
        if data == 'menu_main':
            await self.safe_edit(query,
                "🔐 <b>Flirexa</b>\n\n"
                "Выберите действие:",
                parse_mode='HTML',
                reply_markup=self.get_main_menu_keyboard()
            )

        elif data == 'menu_list':
            keyboard = await self._run_sync(self.get_clients_list_keyboard)
            await self.safe_edit(query,
                "📋 <b>Список клиентов</b>\n\n"
                "Выберите клиента для управления:",
                parse_mode='HTML',
                reply_markup=keyboard
            )

        elif data.startswith('clients_page_'):
            page = int(data.rsplit('_', 1)[1])
            keyboard = await self._run_sync(lambda: self.get_clients_list_keyboard(page))
            await self.safe_edit(
                query,
                "📋 <b>Список клиентов</b>\n\nВыберите клиента для управления:",
                parse_mode='HTML', reply_markup=keyboard,
            )

        elif data == 'menu_new':
            await self.safe_edit(query,
                "➕ <b>Создание клиента</b>\n\n"
                "Отправьте команду:\n"
                "<code>/new ИмяКлиента</code>\n"
                "или выберите сервер явно:\n"
                "<code>/new ИмяКлиента ID_сервера</code>",
                parse_mode='HTML'
            )

        elif data == 'menu_servers':
            keyboard = await self._run_sync(self.get_servers_list_keyboard)
            await self.safe_edit(query,
                "🖥 <b>VPN-серверы</b>\n\n"
                "Выберите сервер для управления:",
                parse_mode='HTML',
                reply_markup=keyboard
            )

        elif data.startswith('servers_page_'):
            page = int(data.rsplit('_', 1)[1])
            keyboard = await self._run_sync(lambda: self.get_servers_list_keyboard(page))
            await self.safe_edit(
                query,
                "🖥 <b>VPN-серверы</b>\n\nВыберите сервер для управления:",
                parse_mode='HTML', reply_markup=keyboard,
            )

        elif data == 'menu_stats':
            await self.show_stats(query)

        elif data == 'menu_online':
            await self.show_online_clients(query)

        elif data == 'menu_business':
            await self.safe_edit(
                query,
                "💼 <b>Бизнес-операции</b>\n\nПользователи, платежи, поддержка и промокоды.",
                parse_mode="HTML",
                reply_markup=self.get_business_menu_keyboard(),
            )

        elif data == 'menu_system':
            await self.safe_edit(
                query,
                "🛡 <b>Система</b>\n\nДиагностика, лицензия, backups и обновления.",
                parse_mode="HTML",
                reply_markup=self.get_system_menu_keyboard(),
            )

        elif data == 'biz_users':
            await self.show_portal_users(query)

        elif data == 'biz_payments':
            await self.show_portal_payments(query)

        elif data == 'biz_support':
            await self.show_support_tickets(query)

        elif data == 'biz_promos':
            await self.show_promo_codes(query)

        elif data == 'biz_tariffs':
            await self.show_tariffs(query)

        elif data == 'biz_broadcast':
            await self.safe_edit(
                query,
                "📣 <b>Push-рассылка</b>\n\n"
                "Создайте уведомление командой:\n"
                "<code>/broadcast Заголовок | Текст сообщения</code>",
                parse_mode="HTML", reply_markup=self.get_business_menu_keyboard(),
            )

        elif data == 'broadcast_do':
            await self.apply_broadcast(query, context)

        elif data.startswith('puser_'):
            await self.show_portal_user(query, int(data[6:]))

        elif data.startswith('grant_do_'):
            user_id, plan_id, days = data[9:].split('_', 2)
            await self.apply_subscription_grant(query, int(user_id), int(plan_id), int(days))

        elif data.startswith('payment_ask_confirm_'):
            await self.confirm_payment_action(
                query, int(data[20:]), "confirm"
            )

        elif data.startswith('payment_ask_reject_'):
            await self.confirm_payment_action(
                query, int(data[19:]), "reject"
            )

        elif data.startswith('payment_do_confirm_'):
            await self.apply_payment_action(query, int(data[19:]), "confirm")

        elif data.startswith('payment_do_reject_'):
            await self.apply_payment_action(query, int(data[18:]), "reject")

        elif data.startswith('payment_'):
            await self.show_portal_payment(query, int(data[8:]))

        elif data.startswith('support_reply_'):
            ticket_id = int(data[14:])
            context.user_data['awaiting'] = 'admin_support_reply'
            context.user_data['support_ticket_id'] = ticket_id
            await self.safe_edit(
                query,
                f"↩️ Отправьте текст ответа для обращения <b>#{ticket_id}</b>.\n\n"
                "Отмена: /cancel",
                parse_mode="HTML",
            )

        elif data.startswith('support_close_'):
            await self.close_support_ticket(query, int(data[14:]))

        elif data.startswith('support_'):
            await self.show_support_ticket(query, int(data[8:]))

        elif data == 'sys_health':
            await self.show_system_health(query)

        elif data == 'sys_license':
            await self.show_license(query)

        elif data == 'sys_backups':
            await self.show_backups(query)

        elif data == 'backup_ask_create':
            await self.safe_edit(
                query,
                "⚠️ <b>Создать полный backup сейчас?</b>\n\n"
                "В архив войдут база, конфигурации и защищённый env.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Создать", callback_data="backup_do_create")],
                    [InlineKeyboardButton("⬅️ Отмена", callback_data="sys_backups")],
                ]),
            )

        elif data == 'backup_do_create':
            await self.create_backup(query)

        elif data.startswith('backup_verify_'):
            await self.verify_backup(query, data[14:])

        elif data == 'sys_updates':
            await self.show_updates(query)

        elif data == 'updates_check':
            await self.check_updates(query)

        elif data == 'updates_ask_apply':
            await self.confirm_update(query)

        elif data == 'updates_do_apply':
            await self.apply_update(query)

        elif data == 'sys_audit':
            await self.show_audit_log(query)

        elif data == 'sys_traffic_rules':
            await self.show_traffic_rules(query)

        elif data == 'traffic_rules_check':
            await self.check_traffic_rules(query)

        elif data == 'menu_help':
            await self.safe_edit(query,
                "Используйте /help для просмотра справки",
                reply_markup=self.get_main_menu_keyboard()
            )

        # Server management
        elif data.startswith('srv_') and data[4:].isdigit():
            server_id = int(data[4:])
            await self.show_server_info(query, server_id)

        elif data.startswith('srv_confirm_'):
            _, _, action, server_id = data.split('_', 3)
            await self.confirm_server_action(query, int(server_id), action)

        elif data.startswith('srv_do_'):
            _, _, action, server_id = data.split('_', 3)
            await self.server_action(query, int(server_id), action)

        elif data.startswith('srv_start_'):
            server_id = int(data[10:])
            await self.server_action(query, server_id, 'start')

        elif data.startswith('srv_stop_'):
            server_id = int(data[9:])
            await self.confirm_server_action(query, server_id, 'stop')

        elif data.startswith('srv_restart_'):
            server_id = int(data[12:])
            await self.confirm_server_action(query, server_id, 'restart')

        elif data.startswith('srv_clients_'):
            server_id = int(data[12:])
            await self.show_server_clients(query, server_id)

        elif data.startswith('srvclients_page_'):
            server_id, page = data[16:].rsplit('_', 1)
            await self.show_server_clients(query, int(server_id), int(page))

        elif data.startswith('srv_saveconf_'):
            server_id = int(data[13:])
            await self.save_server_config(query, server_id)

        # Client selection
        elif data.startswith('client_'):
            client_name = data[7:]
            await self.show_client_info(query, client_name)

        # Enable/Disable
        elif data.startswith('enable_'):
            client_name = data[7:]
            await self.toggle_client(query, client_name, enable=True)

        elif data.startswith('disable_'):
            client_name = data[8:]
            await self.toggle_client(query, client_name, enable=False)

        # Speed settings
        elif data.startswith('speed_'):
            client_ref, raw_speed = data[6:].rsplit('_', 1)
            await self.set_speed(query, client_ref, int(raw_speed))

        # Timer menu
        elif data.startswith('timer_menu_'):
            client_ref = data[11:]
            await self.safe_edit(query,
                "⏱ <b>Установка таймера</b>\n\n"
                "Выберите период:",
                parse_mode='HTML',
                reply_markup=self.get_timer_menu_keyboard(client_ref)
            )

        # Set expiry
        elif data.startswith('setexpiry_'):
            client_ref, raw_days = data[10:].rsplit('_', 1)
            await self.set_expiry(query, client_ref, int(raw_days))

        # Traffic menu
        elif data.startswith('traffic_menu_'):
            client_ref = data[13:]
            await self.safe_edit(query,
                "📊 <b>Лимит трафика</b>\n\n"
                "Выберите лимит:",
                parse_mode='HTML',
                reply_markup=self.get_traffic_menu_keyboard(client_ref)
            )

        # Set traffic limit
        elif data.startswith('traffic_set_'):
            client_ref, raw_limit = data[12:].rsplit('_', 1)
            await self.set_traffic_limit(query, client_ref, int(raw_limit))

        # Reset traffic
        elif data.startswith('resettraffic_'):
            client_name = data[13:]
            await self.reset_traffic(query, client_name)

        # Get config
        elif data.startswith('getconf_'):
            client_name = data[8:]
            await self.send_config(query, client_name)

        # Delete client
        elif data.startswith('delete_ask_'):
            await self.confirm_delete_client(query, data[11:])

        elif data.startswith('delete_do_'):
            await self.delete_client(query, data[10:])

        elif data.startswith('delete_'):
            # Old buttons are deliberately upgraded to a confirmation step.
            await self.confirm_delete_client(query, data[7:])

    # ========================================================================
    # CALLBACK ACTION HANDLERS
    # ========================================================================

    async def show_client_info(self, query, client_ref: str) -> None:
        """Show client information"""
        def _sync():
            core = self.get_core()
            try:
                client = self._get_client_by_ref(core, client_ref)
                if not client:
                    return None
                return core.get_client_full_info(client.id)
            finally:
                self.close_core(core)

        info = await self._run_sync(_sync)
        if info is None:
            await self.safe_edit(query, "❌ Клиент не найден!")
            return

        status = "✅ Включен" if info['enabled'] else "❌ Отключен"
        bw = f"{info['bandwidth_limit']} Mbps" if info['bandwidth_limit'] else "Без ограничений"

        traffic = info['traffic']
        traffic_text = f"↓{traffic['rx_formatted']} ↑{traffic['tx_formatted']}"
        if traffic['limit_mb']:
            traffic_text += f" / {traffic['limit_mb']} MB ({int(traffic['percent_used'])}%)"

        expiry = info['expiry']
        expiry_text = expiry['display_text'] if expiry else "Без ограничений"

        handshake_text = "Нет данных"
        if info['last_handshake']:
            handshake_text = info['last_handshake']

        text = (
            f"👤 <b>{self._h(info['name'])}</b>\n\n"
            f"📊 Статус: {status}\n"
            f"🌐 IP: <code>{self._h(info['ipv4'])}</code>\n"
            f"⚡ Скорость: {bw}\n"
            f"📈 Трафик: {traffic_text}\n"
            f"⏱ Таймер: {expiry_text}\n"
            f"🤝 Последнее соединение: {handshake_text}"
        )

        await self.safe_edit(query, text,
            parse_mode='HTML',
            reply_markup=self.get_client_menu_keyboard(info['id'], info['enabled'])
        )

    async def toggle_client(self, query, client_ref: str, enable: bool) -> None:
        """Enable or disable a client"""
        def _sync():
            core = self.get_core()
            try:
                client = self._get_client_by_ref(core, client_ref)
                if not client:
                    return None, None, None
                if enable:
                    success = core.enable_client(client.id)
                else:
                    success = core.disable_client(client.id)
                return client.id, client.name, success
            finally:
                self.close_core(core)

        client_id, client_name, success = await self._run_sync(_sync)
        if client_id is None:
            await self.safe_edit(query, "❌ Клиент не найден!")
        elif success:
            action = "включен" if enable else "отключен"
            await self.safe_edit(query,
                f"✅ Клиент {client_name} {action}",
                reply_markup=self.get_client_menu_keyboard(client_id, enable)
            )
        else:
            await self.safe_edit(query, "❌ Ошибка при изменении статуса")

    async def set_speed(self, query, client_ref: str, speed: int) -> None:
        """Set bandwidth limit"""
        def _sync():
            core = self.get_core()
            try:
                client = self._get_client_by_ref(core, client_ref)
                if not client:
                    return None, None, None, False
                success = core.set_bandwidth_limit(client.id, speed)
                return client.id, client.name, client.enabled, success
            finally:
                self.close_core(core)

        client_id, client_name, enabled, success = await self._run_sync(_sync)
        if client_id is None:
            await self.safe_edit(query, "❌ Клиент не найден!")
        elif success:
            if speed > 0:
                text = f"✅ Скорость для {client_name}: {speed} Mbps"
            else:
                text = f"✅ Ограничение скорости для {client_name} убрано"
            await self.safe_edit(query, text,
                reply_markup=self.get_client_menu_keyboard(client_id, enabled)
            )
        else:
            await self.safe_edit(query, "❌ Ошибка установки скорости")

    async def set_expiry(self, query, client_ref: str, days: int) -> None:
        """Set expiry timer"""
        def _sync():
            core = self.get_core()
            try:
                client = self._get_client_by_ref(core, client_ref)
                if not client:
                    return None, None, None, False
                success = core.set_expiry(client.id, days)
                return client.id, client.name, client.enabled, success
            finally:
                self.close_core(core)

        client_id, client_name, enabled, success = await self._run_sync(_sync)
        if client_id is None:
            await self.safe_edit(query, "❌ Клиент не найден!")
        elif success:
            text = f"✅ Таймер для {client_name}: {days} дней" if days > 0 else f"✅ Таймер для {client_name} убран"
            await self.safe_edit(query, text,
                reply_markup=self.get_client_menu_keyboard(client_id, enabled)
            )
        else:
            await self.safe_edit(query, "❌ Ошибка установки таймера")

    async def set_traffic_limit(self, query, client_ref: str, limit_mb: int) -> None:
        """Set traffic limit"""
        def _sync():
            core = self.get_core()
            try:
                client = self._get_client_by_ref(core, client_ref)
                if not client:
                    return None, None, None, False
                success = core.set_traffic_limit(client.id, limit_mb)
                return client.id, client.name, client.enabled, success
            finally:
                self.close_core(core)

        client_id, client_name, enabled, success = await self._run_sync(_sync)
        if client_id is None:
            await self.safe_edit(query, "❌ Клиент не найден!")
        elif success:
            text = f"✅ Лимит трафика для {client_name}: {limit_mb} MB" if limit_mb > 0 else f"✅ Лимит трафика для {client_name} убран"
            await self.safe_edit(query, text,
                reply_markup=self.get_client_menu_keyboard(client_id, enabled)
            )
        else:
            await self.safe_edit(query, "❌ Ошибка установки лимита")

    async def reset_traffic(self, query, client_ref: str) -> None:
        """Reset traffic counter"""
        def _sync():
            core = self.get_core()
            try:
                client = self._get_client_by_ref(core, client_ref)
                if not client:
                    return None, None, None, False
                success = core.reset_traffic_counter(client.id)
                return client.id, client.name, client.enabled, success
            finally:
                self.close_core(core)

        client_id, client_name, enabled, success = await self._run_sync(_sync)
        if client_id is None:
            await self.safe_edit(query, "❌ Клиент не найден!")
        elif success:
            await self.safe_edit(query,
                f"✅ Счётчик трафика для {client_name} сброшен",
                reply_markup=self.get_client_menu_keyboard(client_id, enabled)
            )
        else:
            await self.safe_edit(query, "❌ Ошибка сброса счётчика")

    async def send_config(self, query, client_ref: str) -> None:
        """Send client config and QR code"""
        def _sync():
            core = self.get_core()
            try:
                client = self._get_client_by_ref(core, client_ref)
                if not client:
                    return None
                config = core.get_client_config(client.id)
                server_type = getattr(client.server, "server_type", "wireguard") if client.server else "wireguard"
                extension = "yaml" if server_type == "hysteria2" else (
                    "json" if server_type in {"tuic", "vless-reality"} else "conf"
                )
                return {
                    "id": client.id,
                    "name": client.name,
                    "enabled": client.enabled,
                    "config": config,
                    "extension": extension,
                    "protocol": server_type,
                }
            finally:
                self.close_core(core)

        payload = await self._run_sync(_sync)
        if payload is None or not payload["config"]:
            await self.safe_edit(query, "❌ Конфигурация клиента недоступна")
            return

        # Send QR code
        qr_image = self.create_qr_code(payload["config"])
        await query.message.reply_photo(
            photo=qr_image,
            caption=f"📱 QR-код для {payload['name']} · {payload['protocol']}"
        )

        # Send config file
        config_bio = io.BytesIO(payload["config"].encode())
        config_bio.name = f"{payload['name']}.{payload['extension']}"
        await query.message.reply_document(
            document=config_bio,
            filename=config_bio.name,
            caption="💾 Файл конфигурации"
        )

        # Update the original message to show config was sent
        await self.safe_edit(query,
            f"📥 Конфиг для {payload['name']} отправлен",
            reply_markup=self.get_client_menu_keyboard(payload['id'], payload['enabled'])
        )

    async def confirm_delete_client(self, query, client_ref: str) -> None:
        def _sync():
            core = self.get_core()
            try:
                client = self._get_client_by_ref(core, client_ref)
                return (client.id, client.name) if client else (None, None)
            finally:
                self.close_core(core)

        client_id, client_name = await self._run_sync(_sync)
        if client_id is None:
            await self.safe_edit(query, "❌ Клиент не найден!")
            return
        await self.safe_edit(
            query,
            f"⚠️ Удалить клиента <b>{self._h(client_name)}</b>?\n\n"
            "Его текущая VPN-конфигурация перестанет работать. Это действие нельзя отменить.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Да, удалить", callback_data=f"delete_do_{client_id}")],
                [InlineKeyboardButton("⬅️ Отмена", callback_data=f"client_{client_id}")],
            ]),
        )

    async def delete_client(self, query, client_ref: str) -> None:
        """Delete a client"""
        def _sync():
            core = self.get_core()
            try:
                client = self._get_client_by_ref(core, client_ref)
                if not client:
                    return None, None
                return client.name, core.delete_client(client.id)
            finally:
                self.close_core(core)

        client_name, result = await self._run_sync(_sync)
        if client_name is None:
            await self.safe_edit(query, "❌ Клиент не найден!")
        elif result:
            await self.safe_edit(query,
                f"✅ Клиент {client_name} удалён",
                reply_markup=self.get_main_menu_keyboard()
            )
        else:
            await self.safe_edit(query, "❌ Ошибка удаления клиента")

    async def show_stats(self, query) -> None:
        """Show system statistics"""
        def _sync():
            core = self.get_core()
            try:
                return core.get_system_status()
            finally:
                self.close_core(core)

        status = await self._run_sync(_sync)

        text = (
            "📊 <b>Статистика системы</b>\n\n"
            f"<b>Серверы:</b>\n"
            f"  • Всего: {status['servers']['total']}\n"
            f"  • Онлайн: {status['servers']['online']}\n\n"
            f"<b>Клиенты:</b>\n"
            f"  • Всего: {status['clients']['total']}\n"
            f"  • Активных: {status['clients']['active']}\n"
            f"  • Отключенных: {status['clients']['disabled']}\n\n"
            f"<b>Трафик:</b>\n"
            f"  • Всего: {status['traffic']['total_formatted']}\n"
            f"  • Превысили лимит: {status['traffic']['exceeded_count']}\n\n"
            f"<b>Таймеры:</b>\n"
            f"  • Истекает сегодня: {status['expiry']['expiring_today']}\n"
            f"  • Истекает за неделю: {status['expiry']['expiring_week']}"
        )

        await self.safe_edit(query, text,
            parse_mode='HTML',
            reply_markup=self.get_main_menu_keyboard()
        )

    async def show_online_clients(self, query) -> None:
        def _sync():
            core = self.get_core()
            try:
                from ..database.models import Client, Server
                clients = core.db.query(Client).filter(Client.enabled.is_(True)).all()
                try:
                    from ..api.routes.clients import _enrich_handshakes
                    _enrich_handshakes(clients, core.db)
                except Exception as exc:
                    logger.debug("Admin bot live handshake refresh failed: {}", exc)
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=3)
                servers = {s.id: s for s in core.db.query(Server).all()}
                rows = []
                for client in clients:
                    handshake = client.last_handshake
                    if handshake and handshake.tzinfo is None:
                        handshake = handshake.replace(tzinfo=timezone.utc)
                    if handshake and handshake >= cutoff:
                        rows.append((client, servers.get(client.server_id), handshake))
                rows.sort(key=lambda item: item[2], reverse=True)
                now = datetime.now(timezone.utc)
                return [{
                    "id": client.id, "name": client.name,
                    "server": server.name if server else f"#{client.server_id}",
                    "ago": max(0, int((now - handshake).total_seconds())),
                } for client, server, handshake in rows[:30]]
            finally:
                self.close_core(core)

        rows = await self._run_sync(_sync, timeout=90)
        lines = [f"🟢 <b>Онлайн-клиенты: {len(rows)}</b>"]
        keyboard = []
        for row in rows:
            lines.append(f"• {self._h(row['name'])} · {self._h(row['server'])} · {row['ago']}с назад")
            keyboard.append([InlineKeyboardButton(
                self._button_text(f"👤 {row['name']}"), callback_data=f"client_{row['id']}"
            )])
        if not rows:
            lines.append("\nЗа последние 3 минуты рукопожатий не было.")
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")])
        await self.safe_edit(
            query, "\n".join(lines)[:4000], parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def show_portal_users(self, query) -> None:
        def _sync():
            core = self.get_core()
            try:
                from ..modules.subscription.subscription_models import ClientPortalSubscription, ClientUser
                users = core.db.query(ClientUser).order_by(ClientUser.created_at.desc()).limit(25).all()
                ids = [user.id for user in users]
                subs = {sub.user_id: sub for sub in core.db.query(ClientPortalSubscription).filter(
                    ClientPortalSubscription.user_id.in_(ids)
                ).all()} if ids else {}
                return [{
                    "id": user.id, "label": user.username or user.email,
                    "active": bool(user.is_active and not user.is_banned),
                    "tier": getattr(subs.get(user.id), "tier", None) or "—",
                } for user in users]
            finally:
                self.close_core(core)

        users = await self._run_sync(_sync)
        rows = [[InlineKeyboardButton(
            self._button_text(f"{'✅' if u['active'] else '🚫'} {u['label']} · {u['tier']}"),
            callback_data=f"puser_{u['id']}",
        )] for u in users]
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu_business")])
        await self.safe_edit(
            query, f"👤 <b>Пользователи портала</b>\n\nПоказаны последние {len(users)} аккаунтов.",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows),
        )

    async def show_portal_user(self, query, user_id: int) -> None:
        def _sync():
            core = self.get_core()
            try:
                from ..modules.subscription.subscription_models import (
                    ClientPortalSubscription, ClientUser, ClientUserClients, DeviceSlot,
                )
                user = core.db.get(ClientUser, user_id)
                if not user:
                    return None
                sub = core.db.query(ClientPortalSubscription).filter_by(user_id=user.id).first()
                slots = core.db.query(DeviceSlot).filter_by(client_user_id=user.id).count()
                legacy = core.db.query(ClientUserClients).filter(
                    ClientUserClients.client_user_id == user.id,
                    ClientUserClients.slot_id.is_(None),
                ).count()
                return {
                    "username": user.username, "email": user.email,
                    "active": user.is_active, "banned": user.is_banned,
                    "verified": user.email_verified, "telegram": user.telegram_id,
                    "tier": getattr(sub, "tier", None) or "—",
                    "status": self._enum_value(getattr(sub, "status", None)) or "—",
                    "expiry": sub.expiry_date.isoformat()[:10] if sub and sub.expiry_date else "∞",
                    "devices": slots + legacy,
                    "max_devices": getattr(sub, "max_devices", None) if sub else None,
                }
            finally:
                self.close_core(core)

        user = await self._run_sync(_sync)
        if not user:
            await self.safe_edit(query, "❌ Пользователь не найден.")
            return
        await self.safe_edit(
            query,
            f"👤 <b>{self._h(user['username'])}</b>\n"
            f"Email: <code>{self._h(user['email'])}</code>\n"
            f"Аккаунт: {'активен' if user['active'] and not user['banned'] else 'ограничен'}\n"
            f"Email подтверждён: {'да' if user['verified'] else 'нет'}\n"
            f"Telegram: <code>{self._h(user['telegram'] or 'не привязан')}</code>\n\n"
            f"Тариф: <b>{self._h(user['tier'])}</b> · {self._h(user['status'])}\n"
            f"До: {self._h(user['expiry'])}\n"
            f"Устройства: {user['devices']}/{user['max_devices'] or '∞'}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ К пользователям", callback_data="biz_users")
            ]]),
        )

    async def show_portal_payments(self, query) -> None:
        if not self._has_feature("payments"):
            await self.safe_edit(query, self._feature_denied_text("payments"), reply_markup=self.get_business_menu_keyboard())
            return
        def _sync():
            core = self.get_core()
            try:
                from ..modules.subscription.subscription_models import ClientPortalPayment, ClientUser
                payments = core.db.query(ClientPortalPayment).order_by(ClientPortalPayment.created_at.desc()).limit(25).all()
                ids = {p.user_id for p in payments}
                users = {u.id: u for u in core.db.query(ClientUser).filter(ClientUser.id.in_(ids)).all()} if ids else {}
                return [{
                    "id": p.id, "status": p.status, "amount": p.amount_usd,
                    "user": getattr(users.get(p.user_id), "email", None) or f"user#{p.user_id}",
                } for p in payments]
            finally:
                self.close_core(core)
        payments = await self._run_sync(_sync)
        icons = {"completed": "✅", "pending": "⏳", "rejected": "🚫", "failed": "❌", "expired": "⌛"}
        rows = [[InlineKeyboardButton(
            self._button_text(f"{icons.get(str(p['status']).lower(), '•')} ${p['amount']:.2f} · {p['user']}"),
            callback_data=f"payment_{p['id']}",
        )] for p in payments]
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu_business")])
        await self.safe_edit(query, f"💳 <b>Последние платежи: {len(payments)}</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

    async def show_portal_payment(self, query, payment_id: int) -> None:
        if not self._has_feature("payments"):
            await self.safe_edit(query, self._feature_denied_text("payments"))
            return
        def _sync():
            core = self.get_core()
            try:
                from ..modules.subscription.subscription_models import ClientPortalPayment, ClientUser
                p = core.db.get(ClientPortalPayment, payment_id)
                if not p:
                    return None
                user = core.db.get(ClientUser, p.user_id)
                return {
                    "id": p.id, "invoice": p.invoice_id, "amount": p.amount_usd,
                    "status": p.status, "method": self._enum_value(p.payment_method),
                    "provider": p.provider_name or "—", "tier": p.subscription_tier or "—",
                    "days": p.duration_days or "—", "user": user.email if user else f"#{p.user_id}",
                    "pending": str(p.status).lower() == "pending",
                }
            finally:
                self.close_core(core)
        payment = await self._run_sync(_sync)
        if not payment:
            await self.safe_edit(query, "❌ Платёж не найден.")
            return
        rows = []
        if payment["pending"]:
            rows.append([
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"payment_ask_confirm_{payment_id}"),
                InlineKeyboardButton("🚫 Отклонить", callback_data=f"payment_ask_reject_{payment_id}"),
            ])
        rows.append([InlineKeyboardButton("⬅️ К платежам", callback_data="biz_payments")])
        await self.safe_edit(
            query,
            f"💳 <b>Платёж #{payment['id']}</b>\nInvoice: <code>{self._h(payment['invoice'])}</code>\n"
            f"Клиент: {self._h(payment['user'])}\nСумма: <b>${payment['amount']:.2f}</b>\n"
            f"Тариф: {self._h(payment['tier'])} · {payment['days']} дней\n"
            f"Метод: {self._h(payment['method'])} / {self._h(payment['provider'])}\n"
            f"Статус: <b>{self._h(payment['status'])}</b>",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows),
        )

    async def confirm_payment_action(self, query, payment_id: int, action: str) -> None:
        label = "подтвердить" if action == "confirm" else "отклонить"
        await self.safe_edit(
            query, f"⚠️ Действительно <b>{label}</b> платёж #{payment_id}?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Выполнить", callback_data=f"payment_do_{action}_{payment_id}")],
                [InlineKeyboardButton("⬅️ Отмена", callback_data=f"payment_{payment_id}")],
            ]),
        )

    async def apply_payment_action(self, query, payment_id: int, action: str) -> None:
        if not self._has_feature("payments"):
            await self.safe_edit(query, self._feature_denied_text("payments"))
            return
        def _sync():
            core = self.get_core()
            try:
                from ..api.routes.portal_users import confirm_payment, reject_payment
                return confirm_payment(payment_id, db=core.db) if action == "confirm" else reject_payment(payment_id, db=core.db)
            finally:
                self.close_core(core)
        try:
            await self._run_sync(_sync, timeout=90)
            await self.safe_edit(query, "✅ Платёж обработан.", reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ К платежам", callback_data="biz_payments")
            ]]))
        except Exception as exc:
            await self.safe_edit(query, f"❌ Не удалось обработать платёж: {self._h(getattr(exc, 'detail', exc))}", parse_mode="HTML")

    async def show_support_tickets(self, query) -> None:
        def _sync():
            core = self.get_core()
            try:
                from ..modules.subscription.subscription_models import SupportMessage, ClientUser
                tickets = core.db.query(SupportMessage).filter(SupportMessage.parent_id.is_(None)).order_by(SupportMessage.created_at.desc()).limit(25).all()
                ids = {ticket.user_id for ticket in tickets}
                users = {u.id: u for u in core.db.query(ClientUser).filter(ClientUser.id.in_(ids)).all()} if ids else {}
                return [{
                    "id": t.id, "status": t.status,
                    "user": getattr(users.get(t.user_id), "email", None) or f"user#{t.user_id}",
                    "unread": (not t.is_read) or core.db.query(SupportMessage).filter(
                        SupportMessage.parent_id == t.id,
                        SupportMessage.direction == "user",
                        SupportMessage.is_read.is_(False),
                    ).count() > 0,
                } for t in tickets]
            finally:
                self.close_core(core)
        tickets = await self._run_sync(_sync)
        rows = [[InlineKeyboardButton(
            self._button_text(f"{'🔴' if t['unread'] else '💬'} #{t['id']} {t['user']} · {t['status']}"),
            callback_data=f"support_{t['id']}",
        )] for t in tickets]
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu_business")])
        await self.safe_edit(query, f"💬 <b>Обращения: {len(tickets)}</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

    async def show_support_ticket(self, query, ticket_id: int) -> None:
        def _sync():
            core = self.get_core()
            try:
                from ..modules.subscription.subscription_models import SupportMessage, ClientUser
                ticket = core.db.query(SupportMessage).filter(SupportMessage.id == ticket_id, SupportMessage.parent_id.is_(None)).first()
                if not ticket:
                    return None
                user = core.db.get(ClientUser, ticket.user_id)
                replies = core.db.query(SupportMessage).filter(SupportMessage.parent_id == ticket.id).order_by(SupportMessage.created_at.asc()).all()
                ticket.is_read = True
                for reply in replies:
                    if reply.direction == "user":
                        reply.is_read = True
                core.db.commit()
                return {
                    "id": ticket.id, "subject": ticket.subject, "message": ticket.message,
                    "status": ticket.status, "user": user.email if user else f"#{ticket.user_id}",
                    "replies": [(reply.direction, reply.message) for reply in replies[-10:]],
                }
            finally:
                self.close_core(core)
        ticket = await self._run_sync(_sync)
        if not ticket:
            await self.safe_edit(query, "❌ Обращение не найдено.")
            return
        lines = [
            f"💬 <b>#{ticket['id']} · {self._h(ticket['subject'])}</b>",
            f"Клиент: {self._h(ticket['user'])}", f"Статус: {self._h(ticket['status'])}",
            f"\n{self._h(ticket['message'])}",
        ]
        for direction, message in ticket["replies"]:
            lines.append(f"\n<b>{'Поддержка' if direction == 'admin' else 'Клиент'}:</b> {self._h(message)}")
        rows = []
        if ticket["status"] != "closed":
            rows.append([
                InlineKeyboardButton("↩️ Ответить", callback_data=f"support_reply_{ticket_id}"),
                InlineKeyboardButton("✅ Закрыть", callback_data=f"support_close_{ticket_id}"),
            ])
        rows.append([InlineKeyboardButton("⬅️ К обращениям", callback_data="biz_support")])
        await self.safe_edit(query, "\n".join(lines)[:4000], parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

    async def close_support_ticket(self, query, ticket_id: int) -> None:
        def _sync():
            core = self.get_core()
            try:
                from ..api.routes.portal_users import close_ticket
                return close_ticket(ticket_id, db=core.db)
            finally:
                self.close_core(core)
        try:
            await self._run_sync(_sync)
            await self.show_support_ticket(query, ticket_id)
        except Exception as exc:
            await self.safe_edit(query, f"❌ Не удалось закрыть обращение: {self._h(exc)}", parse_mode="HTML")

    async def show_promo_codes(self, query) -> None:
        if not self._has_feature("promo_codes"):
            await self.safe_edit(query, self._feature_denied_text("promo_codes"), reply_markup=self.get_business_menu_keyboard())
            return
        def _sync():
            core = self.get_core()
            try:
                from ..modules.subscription.subscription_models import PromoCode
                promos = core.db.query(PromoCode).order_by(PromoCode.id.desc()).limit(25).all()
                return [{"code": p.code, "type": p.discount_type, "value": p.discount_value,
                         "uses": p.used_count, "max": p.max_uses, "active": p.is_valid} for p in promos]
            finally:
                self.close_core(core)
        promos = await self._run_sync(_sync)
        lines = ["🎟 <b>Промокоды</b>"]
        for promo in promos:
            suffix = "%" if promo["type"] == "percent" else " дн."
            lines.append(f"{'✅' if promo['active'] else '⛔'} <code>{self._h(promo['code'])}</code> · {promo['value']:g}{suffix} · {promo['uses']}/{promo['max'] or '∞'}")
        lines.append("\nСоздать: <code>/newpromo CODE PERCENT [MAX_USES]</code>")
        await self.safe_edit(query, "\n".join(lines)[:4000], parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Назад", callback_data="menu_business")
        ]]))

    async def show_tariffs(self, query) -> None:
        def _sync():
            core = self.get_core()
            try:
                from ..modules.subscription.subscription_models import SubscriptionPlan
                plans = core.db.query(SubscriptionPlan).order_by(SubscriptionPlan.display_order, SubscriptionPlan.id).all()
                return [{
                    "tier": plan.tier, "name": plan.name, "active": plan.is_active,
                    "visible": plan.is_visible, "devices": plan.max_devices,
                    "monthly": plan.price_monthly_usd,
                    "options": len(plan.pricing_tiers or []),
                } for plan in plans]
            finally:
                self.close_core(core)
        plans = await self._run_sync(_sync)
        lines = ["📦 <b>Тарифы клиентского портала</b>"]
        for plan in plans:
            lines.append(
                f"{'✅' if plan['active'] and plan['visible'] else '⛔'} <b>{self._h(plan['name'])}</b> "
                f"(<code>{self._h(plan['tier'])}</code>) · {plan['devices']} устр. · "
                f"${plan['monthly']:.2f}/мес · вариантов: {plan['options'] or 'legacy'}"
            )
        await self.safe_edit(query, "\n".join(lines)[:4000], parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Назад", callback_data="menu_business")
        ]]))

    async def show_traffic_rules(self, query) -> None:
        if not self._has_feature("traffic_rules"):
            await self.safe_edit(query, self._feature_denied_text("traffic_rules"), reply_markup=self.get_system_menu_keyboard())
            return
        def _sync():
            core = self.get_core()
            try:
                from ..database.models import TrafficRule
                rules = core.db.query(TrafficRule).order_by(TrafficRule.id).all()
                return [{
                    "name": rule.name, "period": rule.period,
                    "threshold": rule.threshold_mb, "speed": rule.bandwidth_limit_mbps,
                    "enabled": rule.enabled, "client": rule.client_id,
                } for rule in rules]
            finally:
                self.close_core(core)
        rules = await self._run_sync(_sync)
        lines = [f"🚦 <b>Правила трафика: {len(rules)}</b>"]
        for rule in rules:
            target = f"client#{rule['client']}" if rule["client"] else "все клиенты"
            lines.append(
                f"{'✅' if rule['enabled'] else '⛔'} <b>{self._h(rule['name'])}</b> · "
                f"{rule['threshold']} MB/{self._h(rule['period'])} → {rule['speed']} Mbps · {target}"
            )
        await self.safe_edit(query, "\n".join(lines)[:4000], parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ Проверить сейчас", callback_data="traffic_rules_check")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu_system")],
        ]))

    async def check_traffic_rules(self, query) -> None:
        if not self._has_feature("traffic_rules"):
            await self.safe_edit(query, self._feature_denied_text("traffic_rules"))
            return
        def _sync():
            core = self.get_core()
            try:
                return core.traffic.check_traffic_rules()
            finally:
                self.close_core(core)
        affected = await self._run_sync(_sync, timeout=120)
        await self.safe_edit(
            query, f"✅ Проверка завершена. Изменено клиентов: {len(affected) if isinstance(affected, list) else affected or 0}.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ К правилам", callback_data="sys_traffic_rules")
            ]]),
        )

    async def show_system_health(self, query) -> None:
        def _sync():
            core = self.get_core()
            try:
                from ..modules.health.checker import SystemHealthChecker
                return SystemHealthChecker(db_session=core.db).check_quick().to_dict()
            finally:
                self.close_core(core)
        health = await self._run_sync(_sync, timeout=45)
        icons = {"healthy": "✅", "warning": "⚠️", "error": "❌", "offline": "🔴", "unknown": "❔"}
        lines = [
            f"❤️ <b>Состояние системы: {self._h(health['status'])}</b>",
            self._h(health.get("summary", "")), "",
        ]
        for component in health.get("components", []):
            lines.append(
                f"{icons.get(component['status'], '•')} <b>{self._h(component['name'])}</b>: "
                f"{self._h(component.get('message', ''))}"
            )
        await self.safe_edit(query, "\n".join(lines)[:4000], parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Обновить", callback_data="sys_health")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu_system")],
        ]))

    async def show_license(self, query) -> None:
        def _sync():
            from ..modules.license.manager import get_license_manager
            info = get_license_manager().get_license_info()
            return {
                "plan": info.plan, "valid": info.is_valid, "message": info.validation_message,
                "clients": info.max_clients, "servers": info.max_servers,
                "expires": info.expires_at.isoformat()[:10] if info.expires_at else "lifetime",
                "billing": info.billing_type, "license_type": info.license_type,
                "grace": info.grace_period, "features": len(info.features),
            }
        try:
            info = await self._run_sync(_sync, timeout=30)
            text = (
                f"🔑 <b>Лицензия {self._h(info['plan'])}</b>\n"
                f"Статус: {'✅ действительна' if info['valid'] else '❌ недействительна'}\n"
                f"Тип: {self._h(info['license_type'])} / {self._h(info['billing'])}\n"
                f"Срок: {self._h(info['expires'])}\n"
                f"Лимиты: {info['clients']} клиентов · {info['servers']} серверов\n"
                f"Функций: {info['features']}\n"
                f"Grace: {'да' if info['grace'] else 'нет'}\n\n"
                f"{self._h(info['message'])}"
            )
        except Exception as exc:
            text = f"❌ Не удалось прочитать лицензию: {self._h(exc)}"
        await self.safe_edit(query, text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Назад", callback_data="menu_system")
        ]]))

    async def show_backups(self, query) -> None:
        def _sync():
            core = self.get_core()
            try:
                from ..modules.backup_manager import BackupManager
                return BackupManager(core.db).list_backups()[:12]
            finally:
                self.close_core(core)
        backups = await self._run_sync(_sync, timeout=60)
        lines = [f"💾 <b>Резервные копии: {len(backups)}</b>"]
        rows = [[InlineKeyboardButton("➕ Создать полный backup", callback_data="backup_ask_create")]]
        for backup in backups:
            backup_id = str(backup.get("backup_id", ""))
            lines.append(
                f"• <code>{self._h(backup_id)}</code> · {backup.get('archive_size_mb', 0)} MB · "
                f"v{self._h(backup.get('version') or '—')}"
            )
            callback = f"backup_verify_{backup_id}"
            if backup_id and len(callback.encode("utf-8")) <= 64:
                rows.append([InlineKeyboardButton(
                    self._button_text(f"🔎 Проверить {backup_id}"), callback_data=callback
                )])
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu_system")])
        await self.safe_edit(query, "\n".join(lines)[:4000], parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

    async def create_backup(self, query) -> None:
        await self.safe_edit(query, "⏳ Создаю и проверяю полный backup…")
        def _sync():
            core = self.get_core()
            try:
                from ..modules.backup_manager import BackupManager
                manager = BackupManager(core.db)
                meta = manager.create_full_backup(audit_actor="admin", audit_source="telegram-admin-bot")
                backup_id = meta.get("backup_id") or meta.get("timestamp", "")
                verification = manager.verify_backup(backup_id)
                return meta, verification
            finally:
                self.close_core(core)
        try:
            meta, verification = await self._run_sync(_sync, timeout=300)
            await self.safe_edit(
                query,
                f"{'✅' if verification.get('ok') else '⚠️'} <b>Backup создан</b>\n"
                f"ID: <code>{self._h(meta.get('backup_id') or meta.get('timestamp'))}</code>\n"
                f"Размер: {meta.get('archive_size_mb', 0)} MB\n"
                f"Проверка: {'успешна' if verification.get('ok') else 'есть ошибки'}",
                parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ К backups", callback_data="sys_backups")
                ]]),
            )
        except Exception as exc:
            await self.safe_edit(query, f"❌ Backup не создан: {self._h(exc)}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ К backups", callback_data="sys_backups")
            ]]))

    async def verify_backup(self, query, backup_id: str) -> None:
        def _sync():
            core = self.get_core()
            try:
                from ..modules.backup_manager import BackupManager
                return BackupManager(core.db).verify_backup(backup_id)
            finally:
                self.close_core(core)
        result = await self._run_sync(_sync, timeout=120)
        errors = result.get("errors") or []
        await self.safe_edit(
            query,
            f"{'✅' if result.get('ok') else '❌'} <b>Проверка backup</b>\n"
            f"ID: <code>{self._h(backup_id)}</code>\n"
            f"Файлов проверено: {result.get('files_checked', 0)}\n"
            f"Ошибки: {self._h('; '.join(errors[:5]) if errors else 'нет')}",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ К backups", callback_data="sys_backups")
            ]]),
        )

    async def show_updates(self, query) -> None:
        core = self.get_core()
        try:
            from ..api.routes.updates import update_status
            status = await update_status(db=core.db)
        finally:
            self.close_core(core)
        available = status.get("available_update")
        lines = [
            "⬆️ <b>Обновления</b>",
            f"Текущая версия: <code>{self._h(status.get('current_version'))}</code>",
            f"Канал: <b>{self._h(status.get('channel'))}</b>",
            f"Процесс обновления: {'идёт' if status.get('update_in_progress') else 'нет'}",
        ]
        rows = [[InlineKeyboardButton("🔎 Проверить", callback_data="updates_check")]]
        if available:
            lines.append(f"Доступна: <b>{self._h(available.get('version'))}</b>")
            rows.append([InlineKeyboardButton("⬆️ Установить", callback_data="updates_ask_apply")])
        elif status.get("check_error"):
            lines.append(f"Ошибка проверки: {self._h(status['check_error'])}")
        else:
            lines.append("Новых версий в локальном кеше нет.")
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu_system")])
        await self.safe_edit(query, "\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

    async def check_updates(self, query) -> None:
        await self.safe_edit(query, "⏳ Проверяю подписанный manifest…")
        core = self.get_core()
        try:
            from ..api.routes.updates import check_updates
            result = await check_updates(db=core.db)
        finally:
            self.close_core(core)
        available = result.get("available_update")
        text = (
            f"⬆️ Доступна версия <b>{self._h(available.get('version'))}</b>."
            if available else
            (f"❌ {self._h(result.get('error'))}" if result.get("error") else "✅ Установлена актуальная версия.")
        )
        rows = []
        if available:
            rows.append([InlineKeyboardButton("⬆️ Установить", callback_data="updates_ask_apply")])
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="sys_updates")])
        await self.safe_edit(query, text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

    async def confirm_update(self, query) -> None:
        await self.safe_edit(
            query,
            "⚠️ <b>Установить доступное обновление?</b>\n\n"
            "Перед применением механизм обновления создаст rollback snapshot. "
            "Сервисы и сам бот могут кратковременно перезапуститься.",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Установить", callback_data="updates_do_apply")],
                [InlineKeyboardButton("⬅️ Отмена", callback_data="sys_updates")],
            ]),
        )

    async def apply_update(self, query) -> None:
        await self.safe_edit(query, "⏳ Запускаю защищённое обновление…")
        core = self.get_core()
        try:
            from ..api.routes.updates import ApplyRequest, apply_update_endpoint
            result = await apply_update_endpoint(ApplyRequest(), db=core.db)
            text = (
                f"✅ Обновление <b>{self._h(result['from_version'])} → {self._h(result['to_version'])}</b> запущено.\n"
                f"ID процесса: <code>{result['update_id']}</code>\n\n"
                "Бот может временно отключиться во время перезапуска сервисов."
            )
        except Exception as exc:
            text = f"❌ Не удалось запустить обновление: {self._h(getattr(exc, 'detail', exc))}"
        finally:
            self.close_core(core)
        await self.safe_edit(query, text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ К обновлениям", callback_data="sys_updates")
        ]]))

    async def show_audit_log(self, query) -> None:
        def _sync():
            core = self.get_core()
            try:
                from ..database.models import AuditLog
                rows = core.db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(20).all()
                return [{
                    "action": self._enum_value(row.action), "target": row.target_name or row.target_type or "system",
                    "time": row.created_at.strftime("%m-%d %H:%M") if row.created_at else "—",
                } for row in rows]
            finally:
                self.close_core(core)
        rows = await self._run_sync(_sync)
        lines = ["📜 <b>Последние действия</b>"] + [
            f"• {self._h(row['time'])} · <b>{self._h(row['action'])}</b> · {self._h(row['target'])}"
            for row in rows
        ]
        await self.safe_edit(query, "\n".join(lines)[:4000], parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Назад", callback_data="menu_system")
        ]]))

    # ========================================================================
    # SERVER CALLBACK HANDLERS
    # ========================================================================

    async def confirm_server_action(self, query, server_id: int, action: str) -> None:
        if action not in {"stop", "restart"}:
            await self.safe_edit(query, "❌ Неизвестное действие")
            return

        def _sync():
            core = self.get_core()
            try:
                server = core.get_server(server_id)
                return server.name if server else None
            finally:
                self.close_core(core)

        server_name = await self._run_sync(_sync)
        if not server_name:
            await self.safe_edit(query, "❌ Сервер не найден!")
            return
        verb = "остановить" if action == "stop" else "перезапустить"
        await self.safe_edit(
            query,
            f"⚠️ Вы действительно хотите {verb} сервер <b>{self._h(server_name)}</b>?\n\n"
            "Активные VPN-подключения могут кратковременно прерваться.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Подтвердить", callback_data=f"srv_do_{action}_{server_id}")],
                [InlineKeyboardButton("⬅️ Отмена", callback_data=f"srv_{server_id}")],
            ]),
        )

    async def show_server_info(self, query, server_id: int) -> None:
        """Show server information via callback"""
        def _sync():
            core = self.get_core()
            try:
                server = core.get_server(server_id)
                if not server:
                    return None
                stats = core.get_server_stats(server_id)
                return {
                    'name': server.name,
                    'endpoint': server.endpoint,
                    'interface': server.interface,
                    'listen_port': server.listen_port,
                    'max_clients': server.max_clients,
                    'location': server.location,
                    'stats': stats,
                }
            finally:
                self.close_core(core)

        data = await self._run_sync(_sync)
        if data is None:
            await self.safe_edit(query, "❌ Сервер не найден!")
            return

        stats = data['stats']
        is_online = stats.get('is_online', False) if stats else False
        status_icon = "🟢 Онлайн" if is_online else "🔴 Офлайн"

        text = (
            f"🖥 <b>{self._h(data['name'])}</b>\n\n"
            f"📊 Статус: {status_icon}\n"
            f"🌐 Endpoint: <code>{self._h(data['endpoint'])}</code>\n"
            f"🔧 Интерфейс: <code>{self._h(data['interface'])}</code>\n"
            f"🔌 Порт: {data['listen_port']}\n"
            f"👥 Клиентов: {stats['total_clients'] if stats else 0}/{data['max_clients']}\n"
            f"✅ Активных: {stats['active_clients'] if stats else 0}\n"
        )
        if data['location']:
            text += f"📍 Локация: {self._h(data['location'])}\n"

        await self.safe_edit(query, text,
            parse_mode='HTML',
            reply_markup=self.get_server_menu_keyboard(server_id, is_online)
        )

    async def server_action(self, query, server_id: int, action: str) -> None:
        """Start, stop, or restart a server"""
        action_labels = {
            'start': ('Запускаю', 'запущен', '🟢'),
            'stop': ('Останавливаю', 'остановлен', '🔴'),
            'restart': ('Перезапускаю', 'перезапущен', '🔄'),
        }
        if action not in action_labels:
            await self.safe_edit(query, "❌ Неизвестное действие")
            return
        label_progress, label_done, icon = action_labels[action]

        # Get server name first (fast DB query)
        def _get_name():
            core = self.get_core()
            try:
                server = core.get_server(server_id)
                return server.name if server else None
            finally:
                self.close_core(core)

        server_name = await self._run_sync(_get_name)
        if not server_name:
            await self.safe_edit(query, "❌ Сервер не найден!")
            return

        # Show progress
        await self.safe_edit(query, f"⏳ {label_progress} сервер {server_name}...")

        # Do the action in a thread (SSH operation)
        def _do_action():
            core = self.get_core()
            try:
                if action == 'start':
                    success = core.servers.start_server(server_id)
                elif action == 'stop':
                    success = core.servers.stop_server(server_id)
                else:
                    success = core.servers.restart_server(server_id)

                is_online = action != 'stop'
                if success:
                    stats = core.get_server_stats(server_id)
                    if stats:
                        is_online = stats.get('is_online', False)
                return success, is_online
            except Exception as e:
                logger.error(f"Server action error: {e}")
                return False, action != 'start'
            finally:
                self.close_core(core)

        success, is_online = await self._run_sync(_do_action)
        if success:
            await self.safe_edit(query,
                f"{icon} Сервер {server_name} {label_done}",
                reply_markup=self.get_server_menu_keyboard(server_id, is_online)
            )
        else:
            await self.safe_edit(query,
                f"❌ Ошибка: не удалось выполнить действие '{action}' для {server_name}",
                reply_markup=self.get_server_menu_keyboard(server_id, not is_online)
            )

    async def show_server_clients(self, query, server_id: int, page: int = 0) -> None:
        """Show clients list for a specific server"""
        def _sync():
            core = self.get_core()
            try:
                server = core.get_server(server_id)
                if not server:
                    return None, None, False
                clients = core.get_all_clients(server_id=server_id)
                client_data = [
                    {'id': c.id, 'name': c.name, 'ipv4': c.ipv4, 'enabled': c.enabled,
                     'bandwidth_limit': c.bandwidth_limit}
                    for c in sorted(clients, key=lambda c: c.name)
                ] if clients else []
                raw_status = getattr(server.status, "value", server.status)
                return server.name, client_data, str(raw_status).lower() == "online"
            finally:
                self.close_core(core)

        server_name, clients, is_online = await self._run_sync(_sync)
        if server_name is None:
            await self.safe_edit(query, "❌ Сервер не найден!")
            return

        if not clients:
            await self.safe_edit(query,
                f"📭 На сервере {server_name} нет клиентов",
                reply_markup=self.get_server_menu_keyboard(server_id, is_online)
            )
            return

        page_size = 15
        page_count = max(1, (len(clients) + page_size - 1) // page_size)
        page = max(0, min(page, page_count - 1))
        visible = clients[page * page_size:(page + 1) * page_size]
        text = f"👥 <b>Клиенты на {self._h(server_name)}</b> · {len(clients)}\n\n"
        keyboard = []

        for c in visible:
            status_icon = "✅" if c['enabled'] else "❌"
            bw = f"⚡{c['bandwidth_limit']}M" if c['bandwidth_limit'] else ""
            text += f"{status_icon} {self._h(c['name'])} — {self._h(c['ipv4'])} {bw}\n"
            keyboard.append([InlineKeyboardButton(
                self._button_text(f"{status_icon} {c['name']}"),
                callback_data=f'client_{c["id"]}'
            )])

        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=f'srvclients_page_{server_id}_{page - 1}'))
        if page_count > 1:
            nav.append(InlineKeyboardButton(f"{page + 1}/{page_count}", callback_data='noop'))
        if page + 1 < page_count:
            nav.append(InlineKeyboardButton("▶️", callback_data=f'srvclients_page_{server_id}_{page + 1}'))
        if nav:
            keyboard.append(nav)

        keyboard.append([InlineKeyboardButton(
            f"⬅️ К серверу {server_name}",
            callback_data=f'srv_{server_id}'
        )])

        await self.safe_edit(query, text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def save_server_config(self, query, server_id: int) -> None:
        """Save WireGuard config for a server"""
        # Get server name first (fast)
        def _get_name():
            core = self.get_core()
            try:
                server = core.get_server(server_id)
                return server.name if server else None
            finally:
                self.close_core(core)

        server_name = await self._run_sync(_get_name)
        if not server_name:
            await self.safe_edit(query, "❌ Сервер не найден!")
            return

        await self.safe_edit(query, f"⏳ Сохраняю конфигурацию {server_name}...")

        # Do the save in a thread (SSH operation)
        def _do_save():
            core = self.get_core()
            try:
                success = core.servers.save_server_config(server_id)
                is_online = False
                if success:
                    stats = core.get_server_stats(server_id)
                    is_online = stats.get('is_online', False) if stats else False
                return success, is_online
            except Exception as e:
                logger.error(f"Save config error: {e}")
                return False, True
            finally:
                self.close_core(core)

        success, is_online = await self._run_sync(_do_save)
        if success:
            await self.safe_edit(query,
                f"💾 Конфигурация сервера {server_name} сохранена",
                reply_markup=self.get_server_menu_keyboard(server_id, is_online)
            )
        else:
            await self.safe_edit(query,
                f"❌ Ошибка сохранения конфигурации {server_name}",
                reply_markup=self.get_server_menu_keyboard(server_id, True)
            )

    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.check_auth(update.effective_user.id):
            await self.unauthorized_response(update)
            return
        if not self._has_feature("app_integration"):
            await update.message.reply_text(self._feature_denied_text("app_integration"))
            return
        raw = " ".join(context.args).strip()
        if "|" not in raw:
            await update.message.reply_text("Формат: /broadcast Заголовок | Текст сообщения")
            return
        title, message = (part.strip() for part in raw.split("|", 1))
        if not title or not message or len(title) > 255 or len(message) > 4000:
            await update.message.reply_text("Заголовок: 1–255 символов; сообщение: 1–4000.")
            return
        context.user_data["pending_broadcast"] = {"title": title, "message": message}
        await update.message.reply_text(
            f"⚠️ <b>Отправить push всем пользователям?</b>\n\n"
            f"<b>{self._h(title)}</b>\n{self._h(message)}",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Отправить всем", callback_data="broadcast_do")],
                [InlineKeyboardButton("⬅️ Отмена", callback_data="menu_business")],
            ]),
        )

    async def apply_broadcast(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        payload = context.user_data.pop("pending_broadcast", None)
        if not payload:
            await self.safe_edit(query, "❌ Черновик рассылки истёк. Создайте его заново.")
            return
        if not self._has_feature("app_integration"):
            await self.safe_edit(query, self._feature_denied_text("app_integration"))
            return
        def _sync():
            core = self.get_core()
            try:
                from ..api.routes.system import SendNotificationRequest, send_notification
                return send_notification(SendNotificationRequest(
                    user_id=None, title=payload["title"], message=payload["message"],
                    notification_type="info",
                ), db=core.db)
            finally:
                self.close_core(core)
        try:
            result = await self._run_sync(_sync)
            await self.safe_edit(
                query, f"✅ Push-рассылка создана (ID {result['id']}).",
                reply_markup=self.get_business_menu_keyboard(),
            )
        except Exception as exc:
            await self.safe_edit(query, f"❌ Рассылка не создана: {self._h(exc)}", parse_mode="HTML")

    async def new_promo_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.check_auth(update.effective_user.id):
            await self.unauthorized_response(update)
            return
        if not self._has_feature("promo_codes"):
            await update.message.reply_text(self._feature_denied_text("promo_codes"))
            return
        if len(context.args) not in {2, 3}:
            await update.message.reply_text("Формат: /newpromo CODE PERCENT [MAX_USES]")
            return
        import re
        code = context.args[0].strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]{3,50}", code):
            await update.message.reply_text("Код: 3–50 символов A-Z, 0-9, _ или -.")
            return
        try:
            percent = float(context.args[1])
            max_uses = int(context.args[2]) if len(context.args) == 3 else None
            if not 0 < percent <= 100 or (max_uses is not None and max_uses < 1):
                raise ValueError
        except ValueError:
            await update.message.reply_text("Скидка должна быть 0–100%, MAX_USES — положительным числом.")
            return
        def _sync():
            core = self.get_core()
            try:
                from ..api.routes.promo_codes import PromoCodeCreate, create_promo_code
                return create_promo_code(PromoCodeCreate(
                    code=code, discount_type="percent", discount_value=percent,
                    max_uses=max_uses, is_active=True,
                ), db=core.db)
            finally:
                self.close_core(core)
        try:
            result = await self._run_sync(_sync)
            await update.message.reply_text(
                f"✅ Промокод <code>{self._h(result['code'])}</code> создан: "
                f"{result['discount_value']:g}%, лимит {result['max_uses'] or '∞'}.",
                parse_mode="HTML",
            )
        except Exception as exc:
            await update.message.reply_text(
                f"❌ Не удалось создать промокод: {self._h(getattr(exc, 'detail', exc))}",
                parse_mode="HTML",
            )

    async def grant_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.check_auth(update.effective_user.id):
            await self.unauthorized_response(update)
            return
        if len(context.args) != 3:
            await update.message.reply_text("Формат: /grant USER_ID TIER DAYS")
            return
        try:
            user_id = int(context.args[0])
            days = int(context.args[2])
            tier = context.args[1].strip().lower()
            if user_id < 1 or days < 1 or days > 36500 or not tier.replace("-", "").isalnum():
                raise ValueError
        except ValueError:
            await update.message.reply_text("USER_ID и DAYS должны быть положительными; DAYS ≤ 36500.")
            return
        def _preflight():
            core = self.get_core()
            try:
                from ..modules.subscription.subscription_models import ClientUser, SubscriptionPlan
                user = core.db.get(ClientUser, user_id)
                plan = core.db.query(SubscriptionPlan).filter(SubscriptionPlan.tier.ilike(tier)).first()
                return (
                    user.email if user else None,
                    plan.id if plan else None,
                    plan.tier if plan else None,
                )
            finally:
                self.close_core(core)
        email, plan_id, canonical_tier = await self._run_sync(_preflight)
        if not email or not canonical_tier:
            await update.message.reply_text("❌ Пользователь или тариф не найден.")
            return
        await update.message.reply_text(
            f"⚠️ Выдать <b>{self._h(canonical_tier)}</b> на {days} дней пользователю "
            f"<code>{self._h(email)}</code>?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✅ Выдать",
                    callback_data=f"grant_do_{user_id}_{plan_id}_{days}",
                )
            ]]),
        )

    async def apply_subscription_grant(self, query, user_id: int, plan_id: int, days: int) -> None:
        def _sync():
            core = self.get_core()
            try:
                from ..modules.subscription.subscription_models import SubscriptionPlan
                from ..api.routes.portal_users import GrantSubscriptionRequest, grant_subscription
                plan = core.db.get(SubscriptionPlan, plan_id)
                if not plan:
                    raise ValueError("Plan not found")
                return grant_subscription(
                    user_id,
                    GrantSubscriptionRequest(tier=plan.tier, duration_days=days),
                    db=core.db,
                )
            finally:
                self.close_core(core)
        try:
            result = await self._run_sync(_sync, timeout=60)
            subscription = result["subscription"]
            await self.safe_edit(
                query,
                f"✅ Тариф <b>{self._h(subscription['tier'])}</b> выдан на {days} дней.",
                parse_mode="HTML", reply_markup=self.get_business_menu_keyboard(),
            )
        except Exception as exc:
            await self.safe_edit(query, f"❌ Не удалось выдать тариф: {self._h(exc)}", parse_mode="HTML")

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.check_auth(update.effective_user.id):
            await self.unauthorized_response(update)
            return
        context.user_data.clear()
        await update.message.reply_text("Отменено.", reply_markup=self.get_main_menu_keyboard())

    async def text_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.check_auth(update.effective_user.id):
            await self.unauthorized_response(update)
            return
        if context.user_data.get("awaiting") != "admin_support_reply":
            return
        ticket_id = context.user_data.pop("support_ticket_id", None)
        context.user_data.pop("awaiting", None)
        message = (update.message.text or "").strip()[:4000]
        if not ticket_id or not message:
            await update.message.reply_text("❌ Пустой ответ не отправлен.")
            return
        def _sync():
            core = self.get_core()
            try:
                from ..api.routes.portal_users import AdminReplyRequest, reply_to_ticket
                return reply_to_ticket(ticket_id, AdminReplyRequest(message=message), db=core.db)
            finally:
                self.close_core(core)
        try:
            await self._run_sync(_sync, timeout=60)
            await update.message.reply_text(
                f"✅ Ответ отправлен в обращение #{ticket_id}.",
                reply_markup=self.get_business_menu_keyboard(),
            )
        except Exception as exc:
            await update.message.reply_text(
                f"❌ Ответ не отправлен: {self._h(getattr(exc, 'detail', exc))}",
                parse_mode="HTML",
            )

    # ========================================================================
    # BOT LIFECYCLE
    # ========================================================================

    def setup_handlers(self) -> None:
        """Register all handlers"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("new", self.new_client_command))
        self.app.add_handler(CommandHandler("list", self.list_clients_command))
        self.app.add_handler(CommandHandler("settimer", self.set_timer_command))
        self.app.add_handler(CommandHandler("settraffic", self.set_traffic_command))
        self.app.add_handler(CommandHandler("servers", self.servers_command))
        self.app.add_handler(CommandHandler("serverinfo", self.serverinfo_command))
        self.app.add_handler(CommandHandler("moveuser", self.moveuser_command))
        self.app.add_handler(CommandHandler("newpromo", self.new_promo_command))
        self.app.add_handler(CommandHandler("grant", self.grant_command))
        self.app.add_handler(CommandHandler("broadcast", self.broadcast_command))
        self.app.add_handler(CommandHandler("cancel", self.cancel_command))
        self.app.add_handler(CallbackQueryHandler(self.callback_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_message_handler))
        self.app.add_error_handler(self.error_handler)

    async def _post_init(self, app) -> None:
        from telegram import BotCommand
        await app.bot.set_my_commands([
            BotCommand("start", "Главное меню"),
            BotCommand("new", "Создать клиента: /new имя [server_id]"),
            BotCommand("list", "Список клиентов"),
            BotCommand("servers", "Список VPN-серверов"),
            BotCommand("serverinfo", "Информация о сервере"),
            BotCommand("settimer", "Срок действия клиента"),
            BotCommand("settraffic", "Лимит трафика клиента"),
            BotCommand("newpromo", "Создать процентный промокод"),
            BotCommand("grant", "Выдать тариф пользователю портала"),
            BotCommand("broadcast", "Push-рассылка пользователям"),
            BotCommand("cancel", "Отменить ввод"),
            BotCommand("help", "Справка"),
        ])
        logger.info("Admin bot commands registered")

    def run(self) -> None:
        """Run the bot"""
        from telegram.request import HTTPXRequest
        self.app = (
            Application.builder()
            .token(self.token)
            .post_init(self._post_init)
            .request(HTTPXRequest(connect_timeout=10, read_timeout=30, write_timeout=30, pool_timeout=5))
            .build()
        )
        self.setup_handlers()

        logger.info("Starting admin bot...")
        # Preserve commands received during a short service restart. Telegram
        # already removes acknowledged updates, so dropping the pending queue
        # only loses legitimate operator actions.
        self.app.run_polling(drop_pending_updates=False)


def main():
    """Main entry point"""
    from loguru import logger
    import sys

    # Configure logging
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    # Get configuration from environment
    token = os.getenv("ADMIN_BOT_TOKEN")
    allowed_users_str = os.getenv("ADMIN_BOT_ALLOWED_USERS", "")

    if not token:
        logger.info(
            "Admin bot disabled — ADMIN_BOT_TOKEN not set in .env, exiting cleanly. "
            "Set ADMIN_BOT_TOKEN and `systemctl restart vpnmanager-admin-bot` to enable."
        )
        sys.exit(0)

    try:
        allowed_users = [int(x.strip()) for x in allowed_users_str.split(",") if x.strip()]
    except ValueError:
        logger.error("Invalid ADMIN_BOT_ALLOWED_USERS format")
        sys.exit(1)

    if not allowed_users:
        logger.warning("No allowed users configured - bot will reject all requests")

    bot = AdminBot(token=token, allowed_users=allowed_users)
    bot.run()


if __name__ == "__main__":
    main()
