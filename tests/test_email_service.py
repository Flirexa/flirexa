from src.modules.email.email_service import EmailService


class CapturingEmailService(EmailService):
    def __init__(self):
        super().__init__(host="smtp.example.com")
        self.calls = []

    def _send(self, to: str, subject: str, html_body: str, plain_body=None) -> bool:
        self.calls.append(
            {
                "to": to,
                "subject": subject,
                "html": html_body,
                "plain": plain_body,
            }
        )
        return True


class TestEmailService:
    def test_password_reset_email_contains_branding_and_link(self):
        service = CapturingEmailService()

        ok = service.send_password_reset_email(
            to="user@example.com",
            token="abc123-reset-token",
            portal_url="https://portal.example.com",
            app_name="Acme VPN",
            support_email="support@example.com",
            lang="en",
            logo_url="https://portal.example.com/logo.png",
        )

        assert ok is True
        call = service.calls[-1]
        assert call["subject"] == "Acme VPN Password Reset"
        assert "abc123-reset-token" in call["html"]
        assert "https://portal.example.com/login?reset_token=abc123-reset-token" in call["html"]
        assert "support@example.com" in call["html"]
        assert "img src=\"https://portal.example.com/logo.png\"" in call["html"]
        assert "Reset token: abc123-reset-token" in call["plain"]

    def test_relative_logo_url_is_converted_to_absolute(self):
        service = CapturingEmailService()

        ok = service.send_password_reset_email(
            to="user@example.com",
            token="abc123-reset-token",
            portal_url="https://portal.example.com",
            app_name="Acme VPN",
            lang="en",
            logo_url="/static/logo.png",
        )

        assert ok is True
        call = service.calls[-1]
        assert "img src=\"https://portal.example.com/static/logo.png\"" in call["html"]

    def test_verification_email_localizes_to_russian(self):
        service = CapturingEmailService()

        ok = service.send_verification_email(
            to="user@example.com",
            token="verify-code-123",
            portal_url="https://portal.example.com",
            app_name="Acme VPN",
            support_email="support@example.com",
            lang="ru",
        )

        assert ok is True
        call = service.calls[-1]
        assert call["subject"] == "Подтверждение email - Acme VPN"
        assert "Подтвердите ваш email" in call["html"]
        assert "Код подтверждения: verify-code-123" in call["plain"]

    def test_welcome_email_uses_branding_and_plain_text(self):
        service = CapturingEmailService()

        ok = service.send_welcome_email(
            to="user@example.com",
            username="alice",
            app_name="Acme VPN",
            support_email="support@example.com",
            lang="en",
        )

        assert ok is True
        call = service.calls[-1]
        assert call["subject"] == "Welcome to Acme VPN!"
        assert "Welcome, alice!" in call["html"]
        assert "support@example.com" in call["plain"]
