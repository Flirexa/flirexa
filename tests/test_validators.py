"""
Unit tests for SpongeBot validators
"""

import pytest
from src.utils.validators import (
    validate_client_name,
    validate_ip_address,
    validate_port,
    validate_endpoint,
    validate_wireguard_key,
    validate_dns,
)


class TestClientNameValidator:
    def test_valid_names(self):
        assert validate_client_name("MyPhone")[0] is True
        assert validate_client_name("test_client")[0] is True
        assert validate_client_name("user-1")[0] is True
        assert validate_client_name("a")[0] is True
        assert validate_client_name("Client123")[0] is True

    def test_empty_name(self):
        valid, msg = validate_client_name("")
        assert valid is False
        assert "empty" in msg.lower()

    def test_too_long_name(self):
        valid, msg = validate_client_name("a" * 101)
        assert valid is False
        assert "long" in msg.lower()

    def test_invalid_characters(self):
        valid, msg = validate_client_name("my phone")
        assert valid is False

        valid, msg = validate_client_name("test@client")
        assert valid is False

        valid, msg = validate_client_name("name.with.dots")
        assert valid is False

    def test_dash_prefix(self):
        valid, msg = validate_client_name("-invalid")
        assert valid is False
        assert "dash" in msg.lower()

    def test_reserved_names(self):
        for name in ["all", "none", "default", "server", "admin", "root"]:
            valid, msg = validate_client_name(name)
            assert valid is False
            assert "reserved" in msg.lower()

        # Case insensitive check
        valid, msg = validate_client_name("ALL")
        assert valid is False


class TestIPAddressValidator:
    def test_valid_ips(self):
        assert validate_ip_address("192.168.1.1")[0] is True
        assert validate_ip_address("10.0.0.1")[0] is True
        assert validate_ip_address("255.255.255.255")[0] is True
        assert validate_ip_address("0.0.0.0")[0] is True

    def test_empty_ip(self):
        valid, _ = validate_ip_address("")
        assert valid is False

    def test_invalid_format(self):
        assert validate_ip_address("not-an-ip")[0] is False
        assert validate_ip_address("192.168.1")[0] is False
        assert validate_ip_address("192.168.1.1.1")[0] is False

    def test_out_of_range_octets(self):
        assert validate_ip_address("256.1.1.1")[0] is False
        assert validate_ip_address("1.1.1.999")[0] is False


class TestPortValidator:
    def test_valid_ports(self):
        assert validate_port(80)[0] is True
        assert validate_port(443)[0] is True
        assert validate_port(51820)[0] is True
        assert validate_port(65535)[0] is True
        assert validate_port(1)[0] is True

    def test_invalid_ports(self):
        assert validate_port(0)[0] is False
        assert validate_port(-1)[0] is False
        assert validate_port(65536)[0] is False

    def test_privileged_port_warning(self):
        valid, msg = validate_port(80)
        assert valid is True
        assert "root" in msg.lower()

    def test_non_integer(self):
        valid, _ = validate_port("80")
        assert valid is False


class TestEndpointValidator:
    def test_valid_endpoints(self):
        assert validate_endpoint("192.168.1.1:51820")[0] is True
        assert validate_endpoint("example.com:51820")[0] is True
        assert validate_endpoint("vpn.example.com:443")[0] is True

    def test_empty_endpoint(self):
        valid, _ = validate_endpoint("")
        assert valid is False

    def test_no_port(self):
        valid, _ = validate_endpoint("192.168.1.1")
        assert valid is False

    def test_invalid_port(self):
        valid, _ = validate_endpoint("192.168.1.1:0")
        assert valid is False

        valid, _ = validate_endpoint("192.168.1.1:abc")
        assert valid is False


class TestWireGuardKeyValidator:
    def test_valid_key(self):
        import base64
        key = base64.b64encode(b"x" * 32).decode()
        assert validate_wireguard_key(key)[0] is True

    def test_empty_key(self):
        valid, _ = validate_wireguard_key("")
        assert valid is False

    def test_wrong_length(self):
        valid, _ = validate_wireguard_key("tooshort")
        assert valid is False

    def test_invalid_base64(self):
        valid, _ = validate_wireguard_key("!" * 44)
        assert valid is False


class TestDNSValidator:
    def test_valid_dns(self):
        assert validate_dns("1.1.1.1")[0] is True
        assert validate_dns("1.1.1.1,8.8.8.8")[0] is True
        assert validate_dns("8.8.8.8, 8.8.4.4")[0] is True

    def test_empty_dns(self):
        valid, _ = validate_dns("")
        assert valid is False

    def test_invalid_dns(self):
        valid, _ = validate_dns("not-an-ip")
        assert valid is False
