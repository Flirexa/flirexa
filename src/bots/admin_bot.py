#!/usr/bin/env python3
"""
VPN Management Studio Admin Bot
Telegram bot for VPN administration - refactored to use Core API
"""

import os
import io
import asyncio
from typing import Optional, List
from datetime import datetime

import qrcode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.error import BadRequest
from loguru import logger

from ..database.connection import SessionLocal
from ..core.management import ManagementCore
from ..core.traffic_manager import TrafficManager


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
            if "no text in the message" in err or "message is not modified" in err:
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
            msg = "⏱ Операция превысила таймаут (сервер недоступен?). Попробуйте позже."
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
            [InlineKeyboardButton("➕ Создать клиента", callback_data='menu_new')],
            [InlineKeyboardButton("📋 Список клиентов", callback_data='menu_list')],
            [InlineKeyboardButton("🖥 Серверы", callback_data='menu_servers')],
            [InlineKeyboardButton("📊 Статистика", callback_data='menu_stats')],
            [InlineKeyboardButton("❓ Помощь", callback_data='menu_help')]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_servers_list_keyboard(self) -> InlineKeyboardMarkup:
        """Server list keyboard (lightweight — no SSH/WG calls)"""
        core = self.get_core()
        try:
            servers = core.get_all_servers()
            keyboard = []
            for server in servers:
                # Use DB status + client count instead of expensive get_server_stats()
                from ..database.models import Client as ClientModel
                total_clients = core.db.query(ClientModel).filter(
                    ClientModel.server_id == server.id
                ).count()
                is_online = server.status.value in ('ONLINE', 'online') if hasattr(server.status, 'value') else str(server.status) in ('ONLINE', 'online')
                status_icon = "🟢" if is_online else "🔴"
                label = f"{status_icon} {server.name} ({total_clients} кл.)"
                keyboard.append([InlineKeyboardButton(
                    label,
                    callback_data=f'srv_{server.id}'
                )])
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='menu_main')])
            return InlineKeyboardMarkup(keyboard)
        finally:
            self.close_core(core)

    def get_server_menu_keyboard(self, server_id: int, is_online: bool) -> InlineKeyboardMarkup:
        """Server management menu"""
        keyboard = []
        if is_online:
            keyboard.append([InlineKeyboardButton("🔴 Остановить", callback_data=f'srv_stop_{server_id}')])
            keyboard.append([InlineKeyboardButton("🔄 Перезапустить", callback_data=f'srv_restart_{server_id}')])
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
                label = f"{server.name} ({total}/{max_c})"
                keyboard.append([InlineKeyboardButton(
                    label,
                    callback_data=f'{action}_{server.id}'
                )])
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='menu_main')])
            return InlineKeyboardMarkup(keyboard)
        finally:
            self.close_core(core)

    def get_client_menu_keyboard(self, client_name: str, client_enabled: bool) -> InlineKeyboardMarkup:
        """Client management menu"""
        keyboard = []

        # Enable/Disable button
        if client_enabled:
            keyboard.append([InlineKeyboardButton(
                "⏸ Отключить клиента",
                callback_data=f'disable_{client_name}'
            )])
        else:
            keyboard.append([InlineKeyboardButton(
                "▶️ Включить клиента",
                callback_data=f'enable_{client_name}'
            )])

        # Speed buttons
        keyboard.append([
            InlineKeyboardButton("🐌 10 Mbps", callback_data=f'speed_{client_name}_10'),
            InlineKeyboardButton("🚶 20 Mbps", callback_data=f'speed_{client_name}_20')
        ])
        keyboard.append([
            InlineKeyboardButton("🏃 30 Mbps", callback_data=f'speed_{client_name}_30'),
            InlineKeyboardButton("🚄 50 Mbps", callback_data=f'speed_{client_name}_50')
        ])
        keyboard.append([
            InlineKeyboardButton("🚀 100 Mbps", callback_data=f'speed_{client_name}_100'),
            InlineKeyboardButton("♾️ Без ограничений", callback_data=f'speed_{client_name}_0')
        ])

        # Timer button
        keyboard.append([InlineKeyboardButton(
            "⏱ Установить таймер",
            callback_data=f'timer_menu_{client_name}'
        )])

        # Traffic limit button
        keyboard.append([InlineKeyboardButton(
            "📊 Лимит трафика",
            callback_data=f'traffic_menu_{client_name}'
        )])

        # Get config button
        keyboard.append([InlineKeyboardButton(
            "📥 Получить конфиг",
            callback_data=f'getconf_{client_name}'
        )])

        # Delete button
        keyboard.append([InlineKeyboardButton(
            "🗑 Удалить клиента",
            callback_data=f'delete_{client_name}'
        )])

        # Back button
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='menu_list')])

        return InlineKeyboardMarkup(keyboard)

    def get_timer_menu_keyboard(self, client_name: str) -> InlineKeyboardMarkup:
        """Timer setting menu"""
        keyboard = [
            [
                InlineKeyboardButton("1 день", callback_data=f'setexpiry_{client_name}_1'),
                InlineKeyboardButton("3 дня", callback_data=f'setexpiry_{client_name}_3')
            ],
            [
                InlineKeyboardButton("7 дней", callback_data=f'setexpiry_{client_name}_7'),
                InlineKeyboardButton("15 дней", callback_data=f'setexpiry_{client_name}_15')
            ],
            [
                InlineKeyboardButton("30 дней", callback_data=f'setexpiry_{client_name}_30'),
                InlineKeyboardButton("90 дней", callback_data=f'setexpiry_{client_name}_90')
            ],
            [InlineKeyboardButton("♾️ Без ограничения", callback_data=f'setexpiry_{client_name}_0')],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f'client_{client_name}')]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_traffic_menu_keyboard(self, client_name: str) -> InlineKeyboardMarkup:
        """Traffic limit menu"""
        keyboard = [
            [
                InlineKeyboardButton("500 MB", callback_data=f'traffic_set_{client_name}_500'),
                InlineKeyboardButton("1 GB", callback_data=f'traffic_set_{client_name}_1024')
            ],
            [
                InlineKeyboardButton("3 GB", callback_data=f'traffic_set_{client_name}_3072'),
                InlineKeyboardButton("5 GB", callback_data=f'traffic_set_{client_name}_5120')
            ],
            [
                InlineKeyboardButton("10 GB", callback_data=f'traffic_set_{client_name}_10240'),
                InlineKeyboardButton("20 GB", callback_data=f'traffic_set_{client_name}_20480')
            ],
            [
                InlineKeyboardButton("50 GB", callback_data=f'traffic_set_{client_name}_51200'),
                InlineKeyboardButton("100 GB", callback_data=f'traffic_set_{client_name}_102400')
            ],
            [InlineKeyboardButton("♾️ Без лимита", callback_data=f'traffic_set_{client_name}_0')],
            [InlineKeyboardButton("🔄 Сбросить счётчик", callback_data=f'resettraffic_{client_name}')],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f'client_{client_name}')]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_clients_list_keyboard(self) -> InlineKeyboardMarkup:
        """Client list keyboard (lightweight — no SSH/WG calls, DB only)"""
        core = self.get_core()
        try:
            from ..database.models import Client as ClientModel
            clients = core.db.query(ClientModel).order_by(ClientModel.name).all()

            keyboard = []
            for c in clients:
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

                label = f"{status} {c.name} ({bw}{expiry_text}{traffic_text})"
                keyboard.append([InlineKeyboardButton(
                    label,
                    callback_data=f"client_{c.name}"
                )])

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
            "🔐 <b>VPN Manager</b>\n\n"
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
/new <имя> - Создать клиента
/list - Список клиентов
/settimer <имя> <дни> - Установить таймер
/settraffic <имя> <MB> - Лимит трафика
/help - Эта справка

<b>Команды серверов:</b>
/servers - Список серверов
/serverinfo <id|имя> - Информация о сервере
/moveuser <клиент> <id_сервера> - Переместить клиента

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
• Перемещение клиентов между серверами

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
        if not all(c.isalnum() or c in '-_' for c in client_name):
            await update.message.reply_text(
                "❌ Имя может содержать только буквы, цифры, дефис и подчеркивание!"
            )
            return

        await update.message.reply_text("⏳ Создаю нового клиента...")

        def _sync():
            core = self.get_core()
            try:
                if core.get_client_by_name(client_name):
                    return {'error': f"❌ Клиент '{client_name}' уже существует!"}

                client = core.create_client(name=client_name)
                if not client:
                    return {'error': "❌ Ошибка создания клиента"}

                config = core.get_client_config(client.id)
                return {
                    'name': client.name,
                    'ipv4': client.ipv4,
                    'config': config,
                }
            except Exception as e:
                logger.error(f"Error creating client: {e}")
                return {'error': f"❌ Ошибка: {str(e)}"}
            finally:
                self.close_core(core)

        result = await self._run_sync(_sync)
        if 'error' in result:
            await update.message.reply_text(result['error'])
            return

        await update.message.reply_text(
            f"✅ <b>Клиент создан успешно!</b>\n\n"
            f"👤 Имя: <code>{result['name']}</code>\n"
            f"🌐 IP: <code>{result['ipv4']}</code>\n"
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
            config_bio.name = f"{client_name}.conf"
            await update.message.reply_document(
                document=config_bio,
                filename=f"{client_name}.conf",
                caption="💾 Файл конфигурации",
                reply_markup=self.get_client_menu_keyboard(client_name, True)
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
                "Использование: /settimer <имя> <дни>\n"
                "Пример: /settimer MyPhone 30"
            )
            return

        client_name = context.args[0]
        try:
            days = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Количество дней должно быть числом!")
            return

        def _sync():
            core = self.get_core()
            try:
                client = core.get_client_by_name(client_name)
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
                "Использование: /settraffic <имя> <MB>\n"
                "Пример: /settraffic MyPhone 5120"
            )
            return

        client_name = context.args[0]
        try:
            limit_mb = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Лимит должен быть числом!")
            return

        def _sync():
            core = self.get_core()
            try:
                client = core.get_client_by_name(client_name)
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
            "🖥 <b>Серверы WireGuard</b>\n\n"
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
                    'stats': stats,
                }
            finally:
                self.close_core(core)

        data = await self._run_sync(_sync)
        if data is None:
            await update.message.reply_text(f"❌ Сервер '{arg}' не найден!")
            return

        stats = data['stats']
        status_icon = "🟢 Онлайн" if stats and stats.get('is_online') else "🔴 Офлайн"

        text = (
            f"🖥 <b>{data['name']}</b>\n\n"
            f"📊 Статус: {status_icon}\n"
            f"🌐 Endpoint: <code>{data['endpoint']}</code>\n"
            f"🔧 Интерфейс: <code>{data['interface']}</code>\n"
            f"🔌 Порт: {data['listen_port']}\n"
            f"👥 Клиентов: {stats['total_clients']}/{data['max_clients']}\n"
            f"✅ Активных: {stats['active_clients']}\n"
        )
        if data['location']:
            text += f"📍 Локация: {data['location']}\n"

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

        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "❌ Неправильный формат!\n\n"
                "Использование: /moveuser <имя_клиента> <id_сервера>\n"
                "Пример: /moveuser MyPhone 2"
            )
            return

        client_name = context.args[0]
        try:
            target_server_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ ID сервера должен быть числом!")
            return

        await update.message.reply_text(f"⏳ Перемещаю клиента {client_name}...")

        def _sync():
            core = self.get_core()
            try:
                client = core.get_client_by_name(client_name)
                if not client:
                    return {'error': f"❌ Клиент '{client_name}' не найден!"}

                target_server = core.get_server(target_server_id)
                if not target_server:
                    return {'error': f"❌ Сервер #{target_server_id} не найден!"}

                if client.server_id == target_server_id:
                    return {'error': f"ℹ️ Клиент '{client_name}' уже на сервере '{target_server.name}'"}

                old_server = core.get_server(client.server_id)
                old_server_name = old_server.name if old_server else "?"

                was_enabled = client.enabled
                if was_enabled:
                    core.disable_client(client.id)

                new_ip = core.clients._get_next_available_ip(
                    target_server_id, target_server.address_pool_ipv4
                )
                if new_ip is None:
                    if was_enabled:
                        core.enable_client(client.id)
                    return {'error': "❌ Нет свободных IP на целевом сервере!"}

                ipv4_base = target_server.address_pool_ipv4.split("/")[0].rsplit(".", 1)[0]
                new_ipv4 = f"{ipv4_base}.{new_ip}"
                new_ipv6 = None
                if target_server.address_pool_ipv6:
                    ipv6_base = target_server.address_pool_ipv6.split("/")[0].rstrip(":")
                    new_ipv6 = f"{ipv6_base}:{new_ip}"

                client.server_id = target_server_id
                client.ip_index = new_ip
                client.ipv4 = new_ipv4
                client.ipv6 = new_ipv6
                core.db.commit()

                if was_enabled:
                    new_wg = core.clients._get_wg(target_server)
                    allowed_ips = [f"{new_ipv4}/32"]
                    if new_ipv6:
                        allowed_ips.append(f"{new_ipv6}/128")
                    try:
                        new_wg.add_peer(
                            public_key=client.public_key,
                            allowed_ips=allowed_ips,
                            preshared_key=client.preshared_key
                        )
                    finally:
                        if hasattr(new_wg, 'close'):
                            new_wg.close()
                    client.enabled = True
                    client.status = "active"
                    core.db.commit()

                return {
                    'old_server': old_server_name,
                    'new_server': target_server.name,
                    'new_ipv4': new_ipv4,
                }
            except Exception as e:
                logger.error(f"Error moving client: {e}")
                return {'error': f"❌ Ошибка: {str(e)}"}
            finally:
                self.close_core(core)

        result = await self._run_sync(_sync)
        if 'error' in result:
            await update.message.reply_text(result['error'])
        else:
            await update.message.reply_text(
                f"✅ Клиент '{client_name}' перемещён\n\n"
                f"📤 С: {result['old_server']}\n"
                f"📥 На: {result['new_server']}\n"
                f"🌐 Новый IP: <code>{result['new_ipv4']}</code>",
                parse_mode='HTML'
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

        # Menu navigation
        if data == 'menu_main':
            await self.safe_edit(query,
                "🔐 <b>VPN Manager</b>\n\n"
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

        elif data == 'menu_new':
            await self.safe_edit(query,
                "➕ <b>Создание клиента</b>\n\n"
                "Отправьте команду:\n"
                "<code>/new ИмяКлиента</code>",
                parse_mode='HTML'
            )

        elif data == 'menu_servers':
            keyboard = await self._run_sync(self.get_servers_list_keyboard)
            await self.safe_edit(query,
                "🖥 <b>Серверы WireGuard</b>\n\n"
                "Выберите сервер для управления:",
                parse_mode='HTML',
                reply_markup=keyboard
            )

        elif data == 'menu_stats':
            await self.show_stats(query)

        elif data == 'menu_help':
            await self.safe_edit(query,
                "Используйте /help для просмотра справки",
                reply_markup=self.get_main_menu_keyboard()
            )

        # Server management
        elif data.startswith('srv_') and not data.startswith('srv_stop_') and not data.startswith('srv_start_') and not data.startswith('srv_restart_') and not data.startswith('srv_clients_') and not data.startswith('srv_saveconf_'):
            server_id = int(data[4:])
            await self.show_server_info(query, server_id)

        elif data.startswith('srv_start_'):
            server_id = int(data[10:])
            await self.server_action(query, server_id, 'start')

        elif data.startswith('srv_stop_'):
            server_id = int(data[9:])
            await self.server_action(query, server_id, 'stop')

        elif data.startswith('srv_restart_'):
            server_id = int(data[12:])
            await self.server_action(query, server_id, 'restart')

        elif data.startswith('srv_clients_'):
            server_id = int(data[12:])
            await self.show_server_clients(query, server_id)

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
            parts = data.split('_')
            client_name = parts[1]
            speed = int(parts[2])
            await self.set_speed(query, client_name, speed)

        # Timer menu
        elif data.startswith('timer_menu_'):
            client_name = data[11:]
            await self.safe_edit(query,
                f"⏱ <b>Установка таймера для {client_name}</b>\n\n"
                "Выберите период:",
                parse_mode='HTML',
                reply_markup=self.get_timer_menu_keyboard(client_name)
            )

        # Set expiry
        elif data.startswith('setexpiry_'):
            parts = data.split('_')
            client_name = parts[1]
            days = int(parts[2])
            await self.set_expiry(query, client_name, days)

        # Traffic menu
        elif data.startswith('traffic_menu_'):
            client_name = data[13:]
            await self.safe_edit(query,
                f"📊 <b>Лимит трафика для {client_name}</b>\n\n"
                "Выберите лимит:",
                parse_mode='HTML',
                reply_markup=self.get_traffic_menu_keyboard(client_name)
            )

        # Set traffic limit
        elif data.startswith('traffic_set_'):
            parts = data.split('_')
            client_name = parts[2]
            limit_mb = int(parts[3])
            await self.set_traffic_limit(query, client_name, limit_mb)

        # Reset traffic
        elif data.startswith('resettraffic_'):
            client_name = data[13:]
            await self.reset_traffic(query, client_name)

        # Get config
        elif data.startswith('getconf_'):
            client_name = data[8:]
            await self.send_config(query, client_name)

        # Delete client
        elif data.startswith('delete_'):
            client_name = data[7:]
            await self.delete_client(query, client_name)

    # ========================================================================
    # CALLBACK ACTION HANDLERS
    # ========================================================================

    async def show_client_info(self, query, client_name: str) -> None:
        """Show client information"""
        def _sync():
            core = self.get_core()
            try:
                client = core.get_client_by_name(client_name)
                if not client:
                    return None
                return core.get_client_full_info(client.id)
            finally:
                self.close_core(core)

        info = await self._run_sync(_sync)
        if info is None:
            await self.safe_edit(query, f"❌ Клиент '{client_name}' не найден!")
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
            f"👤 <b>{client_name}</b>\n\n"
            f"📊 Статус: {status}\n"
            f"🌐 IP: <code>{info['ipv4']}</code>\n"
            f"⚡ Скорость: {bw}\n"
            f"📈 Трафик: {traffic_text}\n"
            f"⏱ Таймер: {expiry_text}\n"
            f"🤝 Последнее соединение: {handshake_text}"
        )

        await self.safe_edit(query, text,
            parse_mode='HTML',
            reply_markup=self.get_client_menu_keyboard(client_name, info['enabled'])
        )

    async def toggle_client(self, query, client_name: str, enable: bool) -> None:
        """Enable or disable a client"""
        def _sync():
            core = self.get_core()
            try:
                client = core.get_client_by_name(client_name)
                if not client:
                    return None
                if enable:
                    success = core.enable_client(client.id)
                else:
                    success = core.disable_client(client.id)
                return success
            finally:
                self.close_core(core)

        success = await self._run_sync(_sync)
        if success is None:
            await self.safe_edit(query, f"❌ Клиент '{client_name}' не найден!")
        elif success:
            action = "включен" if enable else "отключен"
            await self.safe_edit(query,
                f"✅ Клиент {client_name} {action}",
                reply_markup=self.get_client_menu_keyboard(client_name, enable)
            )
        else:
            await self.safe_edit(query, f"❌ Ошибка при изменении статуса")

    async def set_speed(self, query, client_name: str, speed: int) -> None:
        """Set bandwidth limit"""
        def _sync():
            core = self.get_core()
            try:
                client = core.get_client_by_name(client_name)
                if not client:
                    return None, False
                success = core.set_bandwidth_limit(client.id, speed)
                return client.enabled, success
            finally:
                self.close_core(core)

        enabled, success = await self._run_sync(_sync)
        if enabled is None:
            await self.safe_edit(query, f"❌ Клиент '{client_name}' не найден!")
        elif success:
            if speed > 0:
                text = f"✅ Скорость для {client_name}: {speed} Mbps"
            else:
                text = f"✅ Ограничение скорости для {client_name} убрано"
            await self.safe_edit(query, text,
                reply_markup=self.get_client_menu_keyboard(client_name, enabled)
            )
        else:
            await self.safe_edit(query, "❌ Ошибка установки скорости")

    async def set_expiry(self, query, client_name: str, days: int) -> None:
        """Set expiry timer"""
        def _sync():
            core = self.get_core()
            try:
                client = core.get_client_by_name(client_name)
                if not client:
                    return None, False
                success = core.set_expiry(client.id, days)
                return client.enabled, success
            finally:
                self.close_core(core)

        enabled, success = await self._run_sync(_sync)
        if enabled is None:
            await self.safe_edit(query, f"❌ Клиент '{client_name}' не найден!")
        elif success:
            text = f"✅ Таймер для {client_name}: {days} дней" if days > 0 else f"✅ Таймер для {client_name} убран"
            await self.safe_edit(query, text,
                reply_markup=self.get_client_menu_keyboard(client_name, enabled)
            )
        else:
            await self.safe_edit(query, "❌ Ошибка установки таймера")

    async def set_traffic_limit(self, query, client_name: str, limit_mb: int) -> None:
        """Set traffic limit"""
        def _sync():
            core = self.get_core()
            try:
                client = core.get_client_by_name(client_name)
                if not client:
                    return None, False
                success = core.set_traffic_limit(client.id, limit_mb)
                return client.enabled, success
            finally:
                self.close_core(core)

        enabled, success = await self._run_sync(_sync)
        if enabled is None:
            await self.safe_edit(query, f"❌ Клиент '{client_name}' не найден!")
        elif success:
            text = f"✅ Лимит трафика для {client_name}: {limit_mb} MB" if limit_mb > 0 else f"✅ Лимит трафика для {client_name} убран"
            await self.safe_edit(query, text,
                reply_markup=self.get_client_menu_keyboard(client_name, enabled)
            )
        else:
            await self.safe_edit(query, "❌ Ошибка установки лимита")

    async def reset_traffic(self, query, client_name: str) -> None:
        """Reset traffic counter"""
        def _sync():
            core = self.get_core()
            try:
                client = core.get_client_by_name(client_name)
                if not client:
                    return None, False
                success = core.reset_traffic_counter(client.id)
                return client.enabled, success
            finally:
                self.close_core(core)

        enabled, success = await self._run_sync(_sync)
        if enabled is None:
            await self.safe_edit(query, f"❌ Клиент '{client_name}' не найден!")
        elif success:
            await self.safe_edit(query,
                f"✅ Счётчик трафика для {client_name} сброшен",
                reply_markup=self.get_client_menu_keyboard(client_name, enabled)
            )
        else:
            await self.safe_edit(query, "❌ Ошибка сброса счётчика")

    async def send_config(self, query, client_name: str) -> None:
        """Send client config and QR code"""
        def _sync():
            core = self.get_core()
            try:
                client = core.get_client_by_name(client_name)
                if not client:
                    return None
                return core.get_client_config(client.id)
            finally:
                self.close_core(core)

        config = await self._run_sync(_sync)
        if config is None:
            await self.safe_edit(query, f"❌ Клиент '{client_name}' не найден!")
            return

        # Send QR code
        qr_image = self.create_qr_code(config)
        await query.message.reply_photo(
            photo=qr_image,
            caption=f"📱 QR код для {client_name}"
        )

        # Send config file
        config_bio = io.BytesIO(config.encode())
        config_bio.name = f"{client_name}.conf"
        await query.message.reply_document(
            document=config_bio,
            filename=f"{client_name}.conf",
            caption="💾 Файл конфигурации"
        )

        # Update the original message to show config was sent
        await self.safe_edit(query,
            f"📥 Конфиг для {client_name} отправлен",
            reply_markup=self.get_client_menu_keyboard(client_name, True)
        )

    async def delete_client(self, query, client_name: str) -> None:
        """Delete a client"""
        def _sync():
            core = self.get_core()
            try:
                client = core.get_client_by_name(client_name)
                if not client:
                    return None
                return core.delete_client(client.id)
            finally:
                self.close_core(core)

        result = await self._run_sync(_sync)
        if result is None:
            await self.safe_edit(query, f"❌ Клиент '{client_name}' не найден!")
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

    # ========================================================================
    # SERVER CALLBACK HANDLERS
    # ========================================================================

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
            f"🖥 <b>{data['name']}</b>\n\n"
            f"📊 Статус: {status_icon}\n"
            f"🌐 Endpoint: <code>{data['endpoint']}</code>\n"
            f"🔧 Интерфейс: <code>{data['interface']}</code>\n"
            f"🔌 Порт: {data['listen_port']}\n"
            f"👥 Клиентов: {stats['total_clients'] if stats else 0}/{data['max_clients']}\n"
            f"✅ Активных: {stats['active_clients'] if stats else 0}\n"
        )
        if data['location']:
            text += f"📍 Локация: {data['location']}\n"

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

    async def show_server_clients(self, query, server_id: int) -> None:
        """Show clients list for a specific server"""
        def _sync():
            core = self.get_core()
            try:
                server = core.get_server(server_id)
                if not server:
                    return None, None, None
                clients = core.get_all_clients(server_id=server_id)
                client_data = [
                    {'name': c.name, 'ipv4': c.ipv4, 'enabled': c.enabled,
                     'bandwidth_limit': c.bandwidth_limit}
                    for c in sorted(clients, key=lambda c: c.name)
                ] if clients else []
                return server.name, client_data, server_id
            finally:
                self.close_core(core)

        server_name, clients, sid = await self._run_sync(_sync)
        if server_name is None:
            await self.safe_edit(query, "❌ Сервер не найден!")
            return

        if not clients:
            await self.safe_edit(query,
                f"📭 На сервере {server_name} нет клиентов",
                reply_markup=self.get_server_menu_keyboard(server_id, True)
            )
            return

        text = f"👥 <b>Клиенты на {server_name}</b>\n\n"
        keyboard = []

        for c in clients:
            status_icon = "✅" if c['enabled'] else "❌"
            bw = f"⚡{c['bandwidth_limit']}M" if c['bandwidth_limit'] else ""
            text += f"{status_icon} {c['name']} — {c['ipv4']} {bw}\n"
            keyboard.append([InlineKeyboardButton(
                f"{status_icon} {c['name']}",
                callback_data=f'client_{c["name"]}'
            )])

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
        self.app.add_handler(CallbackQueryHandler(self.callback_handler))
        self.app.add_error_handler(self.error_handler)

    def run(self) -> None:
        """Run the bot"""
        from telegram.request import HTTPXRequest
        self.app = (
            Application.builder()
            .token(self.token)
            .request(HTTPXRequest(connect_timeout=10, read_timeout=30, write_timeout=30, pool_timeout=5))
            .build()
        )
        self.setup_handlers()

        logger.info("Starting admin bot...")
        self.app.run_polling(drop_pending_updates=True)


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
