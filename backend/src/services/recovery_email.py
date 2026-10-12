"""Corten recovery email: escaped HTML, plain text and encrypted queue payloads."""
import base64
import hashlib
import json
from html import escape
from urllib.parse import urlsplit
from cryptography.fernet import Fernet
from src.config.settings import settings

def cipher():
    # Domain separation keeps the queue encryption key distinct from the signing key.
    key = hashlib.sha256(("corten/recovery-email/v1\0" + settings.JWT_SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))

def reset_url(token):
    origin = settings.EMAIL_PUBLIC_BASE_URL.rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Configure the recovery email application origin")
    if settings.APP_ENV == "production" and parsed.scheme != "https":
        raise ValueError("Recovery links require HTTPS in production")
    return origin + "/auth/reset-password#token=" + token

def reset_message(name, recipient, token):
    url = reset_url(token)
    minutes = settings.PASSWORD_RESET_EXPIRE_MINUTES
    greeting = escape(name or "there")
    safe_url = escape(url, quote=True)
    text = f"Hi {name or 'there'},\n\nYou requested a password reset for your Corten account.\n\nReset your password: {url}\n\nThis link expires in {minutes} minutes and works once. If you didn't request this, ignore this email. Your password hasn't changed.\n\nCorten — developed by Chryselys Private Limited."
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reset your Corten password</title>
<style>@media(max-width:620px){{.card{{width:100%!important}}.pad{{padding:28px 24px!important}}}} </style></head>
<body style="margin:0;padding:0;background:#f2f4f7;font-family:Arial,Helvetica,sans-serif;color:#19222c">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">Your secure Corten password reset link expires in {minutes} minutes.</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f2f4f7"><tr><td align="center" style="padding:40px 16px">
<table class="card" role="presentation" width="560" cellspacing="0" cellpadding="0" style="width:560px;max-width:560px;background:white;border-radius:20px;overflow:hidden;border:1px solid #e3e7eb">
<tr><td class="pad" style="padding:34px 40px;background:#101416"><table role="presentation" cellspacing="0" cellpadding="0"><tr><td style="width:40px;height:40px;background:#9ed0c2;color:#101416;border-radius:12px;text-align:center;font-size:24px;font-weight:bold">C</td><td style="padding-left:13px;color:white;font-size:24px;font-weight:bold;letter-spacing:-.6px">Corten</td></tr></table><p style="margin:25px 0 0;color:#9ed0c2;font-size:11px;letter-spacing:2px;font-weight:bold">ACCOUNT SECURITY</p><h1 style="margin:10px 0 0;font-size:30px;line-height:38px;color:white;letter-spacing:-.8px">A fresh start,<br>securely.</h1></td></tr>
<tr><td class="pad" style="padding:36px 40px"><p style="margin:0 0 18px;font-size:16px;line-height:25px">Hi {greeting},</p><p style="margin:0 0 26px;color:#55616e;font-size:15px;line-height:25px">We received a request to reset the password for your Corten account. Choose a new password to get back to your workspace.</p>
<table role="presentation" cellspacing="0" cellpadding="0"><tr><td bgcolor="#101416" style="border-radius:10px;text-align:center"><a href="{safe_url}" style="display:inline-block;padding:16px 28px;background:#101416;border:1px solid #101416;border-radius:10px;color:white;text-decoration:none;font-size:15px;font-weight:bold">Reset password &nbsp; →</a></td></tr></table>
<p style="margin:24px 0;color:#697583;font-size:13px;line-height:21px">This link expires in <strong style="color:#273442">{minutes} minutes</strong> and can be used only once.</p>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f5f8f7;border:1px solid #e0ebe6;border-radius:10px"><tr><td style="padding:16px 18px;color:#55616e;font-size:13px;line-height:22px"><strong style="color:#273442">Didn't request this?</strong><br>You can safely ignore this email. Your password hasn't changed.</td></tr></table>
<p style="margin:24px 0 8px;color:#697583;font-size:12px;line-height:20px">If the button doesn't work, copy this link into your browser:</p><p style="margin:0;font-size:12px;line-height:20px;word-break:break-all"><a href="{safe_url}" style="color:#337969;text-decoration:underline">{safe_url}</a></p></td></tr>
<tr><td style="padding:22px 40px;background:#fafbfc;border-top:1px solid #e9edf0;color:#7b8590;font-size:11px;line-height:18px"><strong style="color:#4c5965">Corten</strong> · Your research and analyst workspace<br>Developed by Chryselys Private Limited.<br>This is an automated account-security email.</td></tr></table></td></tr></table></body></html>"""
    return {"FromEmailAddress": "Corten <" + settings.EMAIL_FROM + ">", "Destination": {"ToAddresses": [recipient]},
        "Content": {"Simple": {"Subject": {"Data": "Reset your Corten password", "Charset": "UTF-8"},
            "Body": {"Text": {"Data": text, "Charset": "UTF-8"}, "Html": {"Data": html, "Charset": "UTF-8"}}}}}

def protect_payload(message):
    return cipher().encrypt(json.dumps(message, ensure_ascii=False).encode()).decode()

def open_payload(payload):
    return json.loads(cipher().decrypt(payload.encode()))
