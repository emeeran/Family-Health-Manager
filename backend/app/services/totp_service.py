"""TOTP service — 2FA setup and verification."""
import base64
import io
import json
import logging
import secrets

import pyotp
import qrcode

logger = logging.getLogger(__name__)

ISSUER_NAME = "Health Keeper"


class TOTPService:
    """Handle TOTP-based two-factor authentication."""

    @staticmethod
    def generate_secret() -> str:
        """Generate a new TOTP secret."""
        return pyotp.random_base32()

    @staticmethod
    def generate_qr_code_base64(secret: str, username: str) -> str:
        """Generate QR code as base64-encoded PNG for authenticator app setup."""
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=username, issuer_name=ISSUER_NAME)

        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    @staticmethod
    def verify_code(secret: str, code: str) -> bool:
        """Verify a TOTP code against the secret. Allows 1 period drift."""
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)

    @staticmethod
    def generate_backup_codes(count: int = 8) -> list[str]:
        """Generate single-use backup codes."""
        return [secrets.token_hex(4).upper() for _ in range(count)]

    @staticmethod
    def verify_backup_code(backup_codes_json: str | None, code: str) -> tuple[bool, str]:
        """Verify and consume a backup code. Returns (valid, updated_json)."""
        if not backup_codes_json:
            return False, backup_codes_json or "[]"

        codes: list[str] = json.loads(backup_codes_json)
        if code.upper() not in codes:
            return False, backup_codes_json

        codes.remove(code.upper())
        return True, json.dumps(codes)
