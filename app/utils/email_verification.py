"""
Esqueleto para verificacion de email.

ESTADO ACTUAL: stubs. La app no tiene SMTP configurado.

Para activarlo:

1. Anadir dependencia: pip install aiosmtplib email-validator
2. Configurar SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS en .env
3. Crear tabla 'email_verifications' en database.py con:
   - user_id, token_hash, expires_at, used_at
4. Implementar send_verification_email() usando aiosmtplib
5. Agregar middleware o dependencia que requiera email_verified=True
   en endpoints sensibles

Variables de entorno necesarias:
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=noreply@creditospro.com
  SMTP_PASS=app-password-aqui
  SMTP_FROM="CreditosPro <noreply@creditospro.com>"
"""
import logging

logger = logging.getLogger(__name__)


def is_smtp_configured() -> bool:
    """Devuelve True si hay configuracion SMTP minima."""
    import os
    return bool(
        os.getenv("SMTP_HOST")
        and os.getenv("SMTP_USER")
        and os.getenv("SMTP_PASS")
    )


def send_verification_email(to_email: str, verification_url: str) -> bool:
    """Envia email de verificacion. Esqueleto.

    Implementacion real (cuando SMTP este configurado):
        import aiosmtplib
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["From"] = os.getenv("SMTP_FROM")
        msg["To"] = to_email
        msg["Subject"] = "Verifica tu email - CreditosPro"
        msg.set_content(f"Click para verificar: {verification_url}")
        await aiosmtplib.send(msg, hostname=os.getenv("SMTP_HOST"),
                              port=int(os.getenv("SMTP_PORT", 587)),
                              username=os.getenv("SMTP_USER"),
                              password=os.getenv("SMTP_PASS"))
    """
    if not is_smtp_configured():
        logger.info(
            "SMTP no configurado — email a %s no enviado. URL: %s",
            to_email, verification_url[:80],
        )
        return False
    logger.warning("send_verification_email() es un esqueleto — no enviar en prod")
    return False
