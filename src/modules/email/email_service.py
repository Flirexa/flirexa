"""
VPN Manager Email Service
SMTP email for client registration verification and notifications
"""

import smtplib
import ssl
import logging
from urllib.parse import urljoin
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

logger = logging.getLogger(__name__)


EMAIL_TEXTS = {
    "en": {
        "verification_subject": "{app_name} Email Verification",
        "verification_label": "Email verification",
        "verification_title": "Verify your email",
        "verification_intro": "Use the code below to confirm your email address.",
        "verification_steps_title": "How to use it",
        "verification_step_1": "Open the verification screen in the client portal.",
        "verification_step_2": "Paste the code from this email.",
        "verification_step_3": "Confirm your account to finish sign up.",
        "verification_expiry": "This code expires in 24 hours. If you did not request it, you can ignore this email.",
        "verification_plain": (
            "{app_name}\n\n"
            "Verify your email.\n"
            "Verification code: {token}\n"
            "{portal_hint}\n"
            "This code expires in 24 hours.\n"
            "{support_hint}"
        ),
        "reset_subject": "{app_name} Password Reset",
        "reset_label": "Password reset request",
        "reset_title": "Reset your password",
        "reset_intro": "We received a request to reset the password for your account.",
        "reset_account": "Requested for: {email}",
        "reset_token_intro": "Use the token below in the client portal password reset form.",
        "reset_steps_title": "How to use it",
        "reset_step_1": "Open the client portal login page.",
        "reset_step_2": "Open the password reset form.",
        "reset_step_3": "Paste the token and set a new password.",
        "reset_cta": "Open Reset Form",
        "reset_manual_url": "If the button does not open, use this address:",
        "reset_token_label": "Reset token",
        "reset_expiry": "This token expires in 1 hour. If you did not request a password reset, you can safely ignore this email.",
        "reset_plain": (
            "{app_name}\n\n"
            "Reset your password.\n"
            "Requested for: {email}\n"
            "Reset token: {token}\n"
            "{portal_hint}\n"
            "This token expires in 1 hour.\n"
            "{support_hint}"
        ),
        "support": "Support: {support_email}",
    },
    "ru": {
        "verification_subject": "Подтверждение email - {app_name}",
        "verification_label": "Подтверждение email",
        "verification_title": "Подтвердите ваш email",
        "verification_intro": "Используйте код ниже, чтобы подтвердить адрес электронной почты.",
        "verification_steps_title": "Что нужно сделать",
        "verification_step_1": "Откройте экран подтверждения в клиентском портале.",
        "verification_step_2": "Вставьте код из этого письма.",
        "verification_step_3": "Подтвердите аккаунт и завершите регистрацию.",
        "verification_expiry": "Код действует 24 часа. Если вы не запрашивали подтверждение, просто проигнорируйте это письмо.",
        "verification_plain": (
            "{app_name}\n\n"
            "Подтвердите email.\n"
            "Код подтверждения: {token}\n"
            "{portal_hint}\n"
            "Код действует 24 часа.\n"
            "{support_hint}"
        ),
        "reset_subject": "Сброс пароля - {app_name}",
        "reset_label": "Запрос на сброс пароля",
        "reset_title": "Сбросьте пароль",
        "reset_intro": "Мы получили запрос на сброс пароля для вашего аккаунта.",
        "reset_account": "Запрос для: {email}",
        "reset_token_intro": "Используйте токен ниже в форме сброса пароля в клиентском портале.",
        "reset_steps_title": "Что нужно сделать",
        "reset_step_1": "Откройте страницу входа в клиентский портал.",
        "reset_step_2": "Перейдите к форме сброса пароля.",
        "reset_step_3": "Вставьте токен и задайте новый пароль.",
        "reset_cta": "Открыть форму сброса",
        "reset_manual_url": "Если кнопка не открылась, используйте этот адрес:",
        "reset_token_label": "Токен сброса",
        "reset_expiry": "Токен действует 1 час. Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо.",
        "reset_plain": (
            "{app_name}\n\n"
            "Сбросьте пароль.\n"
            "Запрос для: {email}\n"
            "Токен сброса: {token}\n"
            "{portal_hint}\n"
            "Токен действует 1 час.\n"
            "{support_hint}"
        ),
        "support": "Поддержка: {support_email}",
    },
}


class EmailService:
    """
    SMTP email service for sending verification and notification emails.
    Uses Python built-in smtplib (no extra dependencies).

    Usage:
        service = EmailService(
            host="smtp.gmail.com", port=587, username="...",
            password="...", tls=True, from_address="noreply@example.com"
        )
        await service.send_verification_email("user@example.com", "abc123")
    """

    def __init__(
        self,
        host: str,
        port: int = 587,
        username: str = "",
        password: str = "",
        tls: bool = True,
        from_address: str = "",
        from_name: str = "VPN Manager",
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.tls = tls
        self.from_address = from_address or username
        self.from_name = from_name

    def _copy(self, lang: str, key: str, **kwargs) -> str:
        texts = EMAIL_TEXTS.get(lang, EMAIL_TEXTS["en"])
        template = texts.get(key, EMAIL_TEXTS["en"][key])
        return template.format(**kwargs)

    def _resolve_logo_url(self, logo_url: str, portal_url: str = "") -> str:
        """Make branding logo URLs absolute so they render in email clients."""
        logo_url = (logo_url or "").strip()
        portal_url = (portal_url or "").strip()
        if not logo_url:
            return ""
        if logo_url.startswith(("http://", "https://")):
            return logo_url
        if portal_url:
            return urljoin(portal_url.rstrip("/") + "/", logo_url.lstrip("/"))
        return ""

    def _render_email(
        self,
        *,
        app_name: str,
        section_label: str,
        title: str,
        intro_html: str,
        body_html: str,
        footer_html: str = "",
        logo_url: str = "",
    ) -> str:
        logo_html = (
            f'<div style="margin-bottom:14px;"><img src="{logo_url}" alt="{app_name}" style="max-height:52px;max-width:180px;"></div>'
            if logo_url and logo_url.startswith(("http://", "https://"))
            else ""
        )
        return f"""
        <div style="max-width:560px;margin:0 auto;font-family:Arial,sans-serif;color:#334155;background:#f8fafc;padding:24px;">
            <div style="background:linear-gradient(135deg,#1a1a2e,#0f3460);padding:28px 24px;text-align:center;border-radius:16px 16px 0 0;">
                {logo_html}
                <h1 style="color:#fff;margin:0;font-size:24px;letter-spacing:0.3px;">{app_name}</h1>
                <p style="color:#cbd5e1;margin:8px 0 0;font-size:14px;">{section_label}</p>
            </div>
            <div style="background:#fff;padding:28px 24px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 16px 16px;">
                <h2 style="margin:0 0 14px;font-size:22px;color:#0f172a;">{title}</h2>
                <div style="margin:0 0 16px;line-height:1.65;color:#475569;">{intro_html}</div>
                {body_html}
                {footer_html}
            </div>
        </div>
        """

    def _send(self, to: str, subject: str, html_body: str, plain_body: Optional[str] = None) -> bool:
        """Send an email (synchronous, call from async via to_thread)"""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_address}>"
            msg["To"] = to

            if plain_body:
                msg.attach(MIMEText(plain_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html"))

            if self.tls and self.port == 465:
                # SSL
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=15) as server:
                    if self.username and self.password:
                        server.login(self.username, self.password)
                    server.send_message(msg)
            else:
                # STARTTLS or plain
                with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                    if self.tls:
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                    if self.username and self.password:
                        server.login(self.username, self.password)
                    server.send_message(msg)

            logger.info(f"Email sent to {to}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            return False

    def send_verification_email(
        self,
        to: str,
        token: str,
        portal_url: str = "",
        app_name: str = "VPN Manager",
        support_email: str = "",
        lang: str = "en",
        logo_url: str = "",
    ) -> bool:
        """Send email verification link"""
        lang = "ru" if (lang or "").lower().startswith("ru") else "en"
        verify_url = f"{portal_url}/verify-email?token={token}" if portal_url else ""
        portal_hint = verify_url or portal_url or ""
        support_hint = self._copy(lang, "support", support_email=support_email) if support_email else ""
        logo_url = self._resolve_logo_url(logo_url, portal_url)

        cta_html = (
            f"""
            <div style="margin:18px 0 0;">
                <a href="{verify_url}" style="display:inline-block;background:#0f3460;color:#ffffff;text-decoration:none;padding:12px 18px;border-radius:8px;font-weight:bold;">
                    {self._copy(lang, "verification_title")}
                </a>
            </div>
            """
            if verify_url else ""
        )
        body_html = f"""
            <div style="background:#f8fafc;border:1px solid #cbd5e1;border-radius:12px;padding:18px 16px;margin:20px 0;text-align:center;">
                <div style="font-size:12px;letter-spacing:1.2px;text-transform:uppercase;color:#64748b;margin-bottom:8px;">
                    {self._copy(lang, "verification_label")}
                </div>
                <div style="font-family:'Courier New',monospace;font-size:20px;line-height:1.7;font-weight:bold;color:#0f172a;word-break:break-word;overflow-wrap:anywhere;">
                    {token}
                </div>
            </div>
            <div style="background:#eff6ff;border-left:4px solid #2563eb;border-radius:10px;padding:14px 16px;margin:20px 0;">
                <div style="font-weight:bold;color:#1e3a8a;margin-bottom:8px;">{self._copy(lang, "verification_steps_title")}</div>
                <ol style="margin:0;padding-left:18px;color:#334155;line-height:1.7;">
                    <li>{self._copy(lang, "verification_step_1")}</li>
                    <li>{self._copy(lang, "verification_step_2")}</li>
                    <li>{self._copy(lang, "verification_step_3")}</li>
                </ol>
            </div>
            {cta_html}
        """
        footer_html = f"""
            <p style="margin:22px 0 0;color:#64748b;font-size:13px;line-height:1.6;">
                {self._copy(lang, "verification_expiry")}
            </p>
            {f'<p style="margin:10px 0 0;color:#64748b;font-size:13px;line-height:1.6;">{support_hint}</p>' if support_hint else ''}
        """
        html = self._render_email(
            app_name=app_name,
            section_label=self._copy(lang, "verification_label"),
            title=self._copy(lang, "verification_title"),
            intro_html=f"<p>{self._copy(lang, 'verification_intro')}</p>",
            body_html=body_html,
            footer_html=footer_html,
            logo_url=logo_url,
        )
        plain = self._copy(
            lang,
            "verification_plain",
            app_name=app_name,
            token=token,
            portal_hint=portal_hint,
            support_hint=support_hint,
        ).strip()
        return self._send(
            to,
            self._copy(lang, "verification_subject", app_name=app_name),
            html,
            plain,
        )

    def send_welcome_email(
        self,
        to: str,
        username: str,
        app_name: str = "VPN Manager",
        support_email: str = "",
        lang: str = "en",
        logo_url: str = "",
    ) -> bool:
        """Send welcome email after verification"""
        lang = "ru" if (lang or "").lower().startswith("ru") else "en"
        logo_url = self._resolve_logo_url(logo_url)
        texts = {
            "en": {
                "label": "Account verified",
                "title": f"Welcome, {username}!",
                "intro": "Your email has been verified successfully. You can now sign in and manage your VPN connections.",
                "footer": f"Thank you for choosing {app_name}.",
                "subject": f"Welcome to {app_name}!",
                "plain": (
                    f"{app_name}\n\n"
                    f"Welcome, {username}!\n"
                    "Your email has been verified successfully.\n"
                    "You can now sign in and manage your VPN connections.\n"
                ),
            },
            "ru": {
                "label": "Аккаунт подтверждён",
                "title": f"Добро пожаловать, {username}!",
                "intro": "Ваш email успешно подтверждён. Теперь вы можете войти в клиентский портал и управлять своими VPN-подключениями.",
                "footer": f"Спасибо, что выбрали {app_name}.",
                "subject": f"Добро пожаловать в {app_name}!",
                "plain": (
                    f"{app_name}\n\n"
                    f"Добро пожаловать, {username}!\n"
                    "Ваш email успешно подтверждён.\n"
                    "Теперь вы можете войти и управлять своими VPN-подключениями.\n"
                ),
            },
        }["ru" if lang == "ru" else "en"]
        support_hint = self._copy(lang, "support", support_email=support_email) if support_email else ""
        footer_html = f"""
            <p style="margin:22px 0 0;color:#64748b;font-size:13px;line-height:1.6;">{texts['footer']}</p>
            {f'<p style="margin:10px 0 0;color:#64748b;font-size:13px;line-height:1.6;">{support_hint}</p>' if support_hint else ''}
        """
        html = self._render_email(
            app_name=app_name,
            section_label=texts["label"],
            title=texts["title"],
            intro_html=f"<p>{texts['intro']}</p>",
            body_html="",
            footer_html=footer_html,
            logo_url=logo_url,
        )
        plain = texts["plain"] + (f"\n{support_hint}\n" if support_hint else "")
        return self._send(to, texts["subject"], html, plain)

    def send_test_email(self, to: str) -> bool:
        """Send test email to verify SMTP configuration"""
        html = """
        <div style="max-width:500px;margin:0 auto;font-family:Arial,sans-serif;color:#333;">
            <div style="background:linear-gradient(135deg,#1a1a2e,#0f3460);padding:30px;text-align:center;border-radius:12px 12px 0 0;">
                <h1 style="color:#fff;margin:0;font-size:24px;">VPN Manager</h1>
            </div>
            <div style="background:#fff;padding:30px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 12px 12px;">
                <h2 style="margin-top:0;">SMTP Test</h2>
                <p>If you received this email, your SMTP configuration is working correctly.</p>
            </div>
        </div>
        """
        return self._send(to, "VPN Manager SMTP Test", html)

    def send_password_reset_email(
        self,
        to: str,
        token: str,
        portal_url: str = "",
        app_name: str = "VPN Manager",
        support_email: str = "",
        lang: str = "en",
        logo_url: str = "",
    ) -> bool:
        """Send password reset token/instructions"""
        lang = "ru" if (lang or "").lower().startswith("ru") else "en"
        reset_url = f"{portal_url.rstrip('/')}/login?reset_token={token}" if portal_url else ""
        portal_hint = reset_url or portal_url or ""
        support_hint = self._copy(lang, "support", support_email=support_email) if support_email else ""
        logo_url = self._resolve_logo_url(logo_url, portal_url)

        login_hint = (
            f"""
            <div style="margin:18px 0 0;">
                <a href="{reset_url}" style="display:inline-block;background:#0f3460;color:#ffffff;text-decoration:none;padding:12px 18px;border-radius:8px;font-weight:bold;">
                    {self._copy(lang, "reset_cta")}
                </a>
                <p style="margin:12px 0 0;color:#64748b;font-size:13px;word-break:break-all;">
                    {self._copy(lang, "reset_manual_url")}<br>{reset_url}
                </p>
            </div>
            """
            if reset_url else
            "<p style=\"margin:14px 0 0;color:#475569;\">Open the client portal login page and use the reset token below.</p>"
        )

        body_html = f"""
            <p style="margin:0 0 10px;line-height:1.6;color:#475569;">{self._copy(lang, "reset_account", email=to)}</p>
            <p style="margin:0 0 16px;line-height:1.6;color:#475569;">{self._copy(lang, "reset_token_intro")}</p>

            <div style="background:#f8fafc;border:1px solid #cbd5e1;border-radius:12px;padding:18px 16px;margin:20px 0;text-align:center;">
                <div style="font-size:12px;letter-spacing:1.2px;text-transform:uppercase;color:#64748b;margin-bottom:8px;">
                    {self._copy(lang, "reset_token_label")}
                </div>
                <div style="font-family:'Courier New',monospace;font-size:16px;line-height:1.7;font-weight:bold;color:#0f172a;word-break:break-word;overflow-wrap:anywhere;">
                    {token}
                </div>
            </div>

            <div style="background:#eff6ff;border-left:4px solid #2563eb;border-radius:10px;padding:14px 16px;margin:20px 0;">
                <div style="font-weight:bold;color:#1e3a8a;margin-bottom:8px;">{self._copy(lang, "reset_steps_title")}</div>
                <ol style="margin:0;padding-left:18px;color:#334155;line-height:1.7;">
                    <li>{self._copy(lang, "reset_step_1")}</li>
                    <li>{self._copy(lang, "reset_step_2")}</li>
                    <li>{self._copy(lang, "reset_step_3")}</li>
                </ol>
            </div>

            {login_hint}
        """
        footer_html = f"""
            <p style="margin:22px 0 0;color:#64748b;font-size:13px;line-height:1.6;">
                {self._copy(lang, "reset_expiry")}
            </p>
            {f'<p style="margin:10px 0 0;color:#64748b;font-size:13px;line-height:1.6;">{support_hint}</p>' if support_hint else ''}
        """
        html = self._render_email(
            app_name=app_name,
            section_label=self._copy(lang, "reset_label"),
            title=self._copy(lang, "reset_title"),
            intro_html=f"<p>{self._copy(lang, 'reset_intro')}</p>",
            body_html=body_html,
            footer_html=footer_html,
            logo_url=logo_url,
        )
        plain = self._copy(
            lang,
            "reset_plain",
            app_name=app_name,
            email=to,
            token=token,
            portal_hint=portal_hint,
            support_hint=support_hint,
        ).strip()
        return self._send(
            to,
            self._copy(lang, "reset_subject", app_name=app_name),
            html,
            plain,
        )

    def test_connection(self) -> dict:
        """Test SMTP connection without sending email"""
        try:
            if self.tls and self.port == 465:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=10) as server:
                    if self.username and self.password:
                        server.login(self.username, self.password)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                    if self.tls:
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                    if self.username and self.password:
                        server.login(self.username, self.password)

            return {"connected": True, "message": "SMTP connection successful"}

        except Exception as e:
            return {"connected": False, "message": str(e)}
