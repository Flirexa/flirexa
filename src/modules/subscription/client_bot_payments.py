"""
VPN Management Studio Client Bot - Payment Integration
Updated client bot with cryptocurrency payments via CryptoPay
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
from sqlalchemy.orm import Session

from src.database.connection import get_db
from .subscription_manager import SubscriptionManager
from src.modules.subscription.cryptopay_adapter import CryptoPayAdapter, create_subscription_invoice
from src.modules.subscription.subscription_models import SubscriptionTier

logger = logging.getLogger(__name__)


class ClientBotPayments:
    """
    Enhanced client bot with payment functionality

    New commands:
        /subscribe - View plans and subscribe
        /payment - View payment history
        /upgrade - Upgrade subscription
        /balance - Check subscription status
    """

    def __init__(self, token: str, cryptopay_token: str):
        self.app = Application.builder().token(token).build()
        self.cryptopay = CryptoPayAdapter(cryptopay_token)

        # Register handlers
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("subscribe", self.subscribe_command))
        self.app.add_handler(CommandHandler("balance", self.balance_command))
        self.app.add_handler(CommandHandler("upgrade", self.upgrade_command))
        self.app.add_handler(CommandHandler("payment", self.payment_history_command))

        # Callback handlers
        self.app.add_handler(CallbackQueryHandler(self.handle_plan_selection, pattern="^plan_"))
        self.app.add_handler(CallbackQueryHandler(self.handle_duration_selection, pattern="^duration_"))
        self.app.add_handler(CallbackQueryHandler(self.handle_currency_selection, pattern="^crypto_"))
        self.app.add_handler(CallbackQueryHandler(self.handle_check_payment, pattern="^check_payment_"))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command - welcome message"""
        telegram_id = str(update.effective_user.id)

        # Check if user exists
        db = next(get_db())
        manager = SubscriptionManager(db)
        user = manager.get_user_by_telegram_id(telegram_id)

        if not user:
            keyboard = [
                [InlineKeyboardButton("📝 Register", url="https://your-domain.com/register")],
                [InlineKeyboardButton("💎 View Plans", callback_data="subscribe")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "🧽 *Welcome to VPN Manager!*\n\n"
                "Fast, secure, and private VPN service.\n\n"
                "Please register to get started:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            keyboard = [
                [
                    InlineKeyboardButton("📊 My Subscription", callback_data="my_subscription"),
                    InlineKeyboardButton("💎 Upgrade", callback_data="upgrade")
                ],
                [
                    InlineKeyboardButton("📥 Download Config", callback_data="download_config"),
                    InlineKeyboardButton("💳 Payment History", callback_data="payment_history")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"🧽 *Welcome back, {user.username}!*\n\n"
                "Choose an action:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show subscription plans"""
        db = next(get_db())
        manager = SubscriptionManager(db)
        plans = manager.get_all_plans(active_only=True)

        keyboard = []
        for plan in plans:
            if plan.tier == SubscriptionTier.FREE:
                continue

            traffic = f"{plan.traffic_limit_gb} GB" if plan.traffic_limit_gb else "Unlimited"
            bandwidth = f"{plan.bandwidth_limit_mbps} Mbps" if plan.bandwidth_limit_mbps else "Unlimited"

            button_text = (
                f"💎 {plan.name} - ${plan.price_monthly_usd}/mo\n"
                f"📱 {plan.max_devices} devices | 📊 {traffic} | ⚡ {bandwidth}"
            )

            keyboard.append([
                InlineKeyboardButton(button_text, callback_data=f"plan_{plan.tier.value}")
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "💎 *Choose Your Plan*\n\n"
            "All plans include:\n"
            "✅ No logs policy\n"
            "✅ 24/7 support\n"
            "✅ Multiple locations\n"
            "✅ WireGuard protocol\n",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show subscription balance and status"""
        telegram_id = str(update.effective_user.id)
        db = next(get_db())
        manager = SubscriptionManager(db)

        user = manager.get_user_by_telegram_id(telegram_id)
        if not user:
            await update.message.reply_text("Please register first: /start")
            return

        subscription = manager.get_subscription(user.id)
        if not subscription:
            await update.message.reply_text("No subscription found.")
            return

        traffic_pct = subscription.traffic_percentage_used or 0
        traffic_emoji = "🟢" if traffic_pct < 70 else "🟡" if traffic_pct < 90 else "🔴"

        expiry_text = (
            f"Expires in {subscription.days_remaining} days"
            if subscription.days_remaining
            else "Never expires"
        )

        text = (
            f"📊 *Your Subscription*\n\n"
            f"Plan: *{subscription.tier.value.title()}*\n"
            f"Status: *{subscription.status.value.title()}*\n"
            f"Expiry: {expiry_text}\n\n"
            f"📈 Usage:\n"
            f"{traffic_emoji} Traffic: {subscription.traffic_used_total_gb:.2f} GB / "
            f"{subscription.traffic_limit_gb or '∞'} GB\n"
            f"📱 Devices: {subscription.max_devices} max\n"
            f"⚡ Speed: {subscription.bandwidth_limit_mbps or 'Unlimited'} Mbps\n"
        )

        keyboard = [
            [InlineKeyboardButton("⬆️ Upgrade Plan", callback_data="upgrade")],
            [InlineKeyboardButton("🔄 Renew", callback_data="renew")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def handle_plan_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle plan selection"""
        query = update.callback_query
        await query.answer()

        tier = query.data.replace("plan_", "")
        context.user_data['selected_tier'] = tier

        # Ask for duration
        keyboard = [
            [InlineKeyboardButton("1 Month - Best Value", callback_data="duration_30")],
            [InlineKeyboardButton("3 Months - Save 10%", callback_data="duration_90")],
            [InlineKeyboardButton("1 Year - Save 20%", callback_data="duration_365")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "⏰ *Select Duration*\n\n"
            "Longer subscriptions = Better savings!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def handle_duration_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle duration selection"""
        query = update.callback_query
        await query.answer()

        duration = int(query.data.replace("duration_", ""))
        context.user_data['duration'] = duration

        # Ask for currency
        keyboard = [
            [
                InlineKeyboardButton("₮ USDT", callback_data="crypto_USDT"),
                InlineKeyboardButton("₿ BTC", callback_data="crypto_BTC")
            ],
            [
                InlineKeyboardButton("💎 TON", callback_data="crypto_TON"),
                InlineKeyboardButton("Ξ ETH", callback_data="crypto_ETH")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "💎 *Select Cryptocurrency*\n\n"
            "Choose your payment method:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def handle_currency_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle currency selection and create invoice"""
        query = update.callback_query
        await query.answer("Creating invoice...")

        currency = query.data.replace("crypto_", "")
        telegram_id = str(update.effective_user.id)

        db = next(get_db())
        manager = SubscriptionManager(db)

        user = manager.get_user_by_telegram_id(telegram_id)
        if not user:
            await query.edit_message_text("Please register first via web portal.")
            return

        # Get selected plan and duration
        tier = context.user_data.get('selected_tier')
        duration = context.user_data.get('duration', 30)

        plan = manager.get_plan_by_tier(SubscriptionTier(tier))
        if not plan:
            await query.edit_message_text("Plan not found. Please try again.")
            return

        # Calculate price
        amount_usd = plan.price_monthly_usd * (duration / 30)

        try:
            # Create invoice via CryptoPay
            invoice = await create_subscription_invoice(
                adapter=self.cryptopay,
                user_id=user.id,
                plan_name=plan.name,
                amount_usd=amount_usd,
                currency=currency,
                duration_days=duration
            )

            # Save to database
            from src.modules.subscription.subscription_models import PaymentMethod
            payment = manager.create_payment(
                user_id=user.id,
                amount_usd=amount_usd,
                payment_method=PaymentMethod(currency.lower()),
                subscription_tier=plan.tier,
                duration_days=duration,
                invoice_id=invoice['invoice_id'],
                provider_name='cryptopay'
            )

            # Send invoice to user
            text = (
                f"💳 *Invoice Created*\n\n"
                f"Amount: *${amount_usd:.2f} USD*\n"
                f"Crypto: *{invoice['amount_crypto']:.6f} {currency}*\n\n"
                f"⏰ Expires in 60 minutes\n\n"
                f"Click the button below to pay:"
            )

            keyboard = [
                [InlineKeyboardButton("🚀 Pay Now", url=invoice['payment_url'])],
                [InlineKeyboardButton("🔄 Check Payment", callback_data=f"check_payment_{invoice['invoice_id']}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Failed to create invoice: {e}")
            await query.edit_message_text("Failed to create invoice. Please try again later.")

    async def handle_check_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check payment status"""
        query = update.callback_query
        await query.answer("Checking payment status...")

        invoice_id = query.data.replace("check_payment_", "")

        try:
            status = await self.cryptopay.check_payment(int(invoice_id))

            if status == "paid":
                await query.edit_message_text(
                    "✅ *Payment Received!*\n\n"
                    "Your subscription has been activated.\n"
                    "Use /balance to view details.",
                    parse_mode='Markdown'
                )
            else:
                await query.answer("Payment not received yet. Please complete the payment.", show_alert=True)

        except Exception as e:
            logger.error(f"Failed to check payment: {e}")
            await query.answer("Failed to check payment status.", show_alert=True)

    async def payment_history_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show payment history"""
        telegram_id = str(update.effective_user.id)
        db = next(get_db())
        manager = SubscriptionManager(db)

        user = manager.get_user_by_telegram_id(telegram_id)
        if not user:
            await update.message.reply_text("Please register first: /start")
            return

        payments = manager.get_user_payments(user.id, limit=10)

        if not payments:
            await update.message.reply_text("No payments yet.")
            return

        text = "💳 *Payment History*\n\n"
        for payment in payments:
            status_emoji = "✅" if payment.is_completed else "⏳"
            text += (
                f"{status_emoji} ${payment.amount_usd:.2f} via {payment.payment_method.value}\n"
                f"   {payment.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
            )

        await update.message.reply_text(text, parse_mode='Markdown')

    def run(self):
        """Start the bot"""
        logger.info("Starting client bot with payments...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


# Example usage
if __name__ == "__main__":
    import os

    BOT_TOKEN = os.getenv("CLIENT_BOT_TOKEN")
    CRYPTOPAY_TOKEN = os.getenv("CRYPTOPAY_API_TOKEN")

    bot = ClientBotPayments(BOT_TOKEN, CRYPTOPAY_TOKEN)
    bot.run()
