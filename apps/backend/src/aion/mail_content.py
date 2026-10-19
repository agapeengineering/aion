"""Versioned transactional content; render once before sealing provider requests."""

import re
from html import escape

COPY = {
    "en": {
        "subject": "Your Aion sign-in code",
        "preview": "Your sign-in code expires in 10 minutes. Return to Aion to continue.",
        "eyebrow": "A LITTLE CONTINUITY",
        "heading": "Your sign-in code.",
        "intro": "Enter this code in the browser where you requested it to sign in to Aion.",
        "expiry": "Expires in 10 minutes.",
        "security": "Keep this code private. Aion will never ask you to share it by email.",
        "ignore": "If you didn’t request this code, you can safely ignore this email.",
        "help": "Need help? Reply to this email or contact",
    },
    "es": {
        "subject": "Tu código de Aion",
        "preview": "Tu código caduca en 10 minutos. Vuelve a Aion para continuar.",
        "eyebrow": "UN POCO DE CONTINUIDAD",
        "heading": "Tu código de acceso.",
        "intro": "Introduce este código en el navegador donde lo solicitaste para entrar en Aion.",
        "expiry": "Caduca en 10 minutos.",
        "security": (
            "Mantén este código en privado. Aion nunca te pedirá que lo compartas por correo."
        ),
        "ignore": "Si no solicitaste este código, puedes ignorar este correo.",
        "help": "¿Necesitas ayuda? Responde a este correo o escribe a",
    },
}


def wording(code: str, language: str, purpose: str = "login") -> dict[str, str]:
    if not re.fullmatch(r"[0-9]{8}", code):
        raise ValueError("Verification code must contain eight digits")
    if language not in COPY:
        raise ValueError("Unsupported email language")
    if purpose == "login":
        return COPY[language]
    if purpose != "reverify":
        raise ValueError("Unsupported verification purpose")
    return {
        **COPY[language],
        **(
            {
                "subject": "Confirm your Aion account action",
                "preview": "Confirm your account action in Aion. Your code expires in 10 minutes.",
                "heading": "Confirm it’s you.",
                "intro": (
                    "Enter this code in Aion to allow a sensitive account action. "
                    "It does not sign you in on another device."
                ),
            }
            if language == "en"
            else {
                "subject": "Confirma tu acción de cuenta en Aion",
                "preview": "Confirma tu acción en Aion. Tu código caduca en 10 minutos.",
                "heading": "Confirma que eres tú.",
                "intro": (
                    "Introduce este código en Aion para permitir una acción sensible de tu cuenta. "
                    "No inicia sesión en otro dispositivo."
                ),
            }
        ),
    }


def verification_content(
    code: str, language: str, reply_to: str, purpose: str = "login"
) -> tuple[str, str]:
    c = wording(code, language, purpose)
    body = (
        f"Aion\n\n{c['heading']}\n\n{c['intro']}\n\n{code}\n\n{c['expiry']}\n\n"
        f"{c['security']}\n{c['ignore']}\n\n{c['help']} {reply_to}.\n\nAion by Agape\n"
    )
    return c["subject"], body


def verification_html(code: str, language: str, reply_to: str, purpose: str = "login") -> str:
    c = {key: escape(value) for key, value in wording(code, language, purpose).items()}
    contact = escape(reply_to, quote=True)
    # Inline styles, presentation tables and system fonts survive email-client stripping.
    # The code remains a single uninterrupted text node for selection and auto-detection.
    return f"""<!doctype html>
<html lang="{language}" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{c["subject"]}</title>
</head>
<body style="margin:0;padding:0;background-color:#faf6ee;color:#1a1a1a;">
<div lang="{language}" dir="ltr">
<div aria-hidden="true" style="display:none;max-height:0;overflow:hidden;
font-size:1px;line-height:1px;color:#faf6ee;mso-hide:all;">{c["preview"]}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
style="width:100%;background-color:#faf6ee;">
<tr><td align="center" style="padding:40px 16px;">
<!--[if mso]><table role="presentation" width="560" cellpadding="0" cellspacing="0"
border="0"><tr><td><![endif]-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
style="width:100%;max-width:560px;background-color:#fffdf8;border:1px solid #d7ccba;">
<tr><td style="padding:32px 28px 28px;font-family:Arial,Helvetica,sans-serif;">
<p style="margin:0;font-size:36px;line-height:40px;font-weight:700;letter-spacing:-2px;
color:#1a1a1a;">aion<span style="color:#b5532a;">.</span></p>
</td></tr>
<tr><td style="padding:0 28px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td style="border-top:1px solid #d7ccba;font-size:1px;line-height:1px;">&nbsp;</td></tr>
</table>
</td></tr>
<tr><td style="padding:28px 28px 0;font-family:Arial,Helvetica,sans-serif;">
<p style="margin:0 0 16px;font-family:'Courier New',Courier,monospace;font-size:11px;
line-height:18px;letter-spacing:1px;color:#62584d;">{c["eyebrow"]}</p>
<h1 style="margin:0 0 20px;font-family:Georgia,'Times New Roman',serif;font-size:32px;
line-height:38px;font-weight:400;letter-spacing:-0.5px;color:#1a1a1a;">{c["heading"]}</h1>
<p style="margin:0;font-size:16px;line-height:26px;color:#1a1a1a;">{c["intro"]}</p>
</td></tr>
<tr><td style="padding:28px 28px 0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
style="width:100%;background-color:#f1ebdf;border:1px solid #d7ccba;">
<tr><td align="center" style="padding:22px 8px;">
<p dir="ltr" style="margin:0;font-family:'Courier New',Courier,monospace;font-size:32px;
line-height:40px;font-weight:700;letter-spacing:3px;white-space:nowrap;color:#1a1a1a;">{code}</p>
</td></tr></table>
<p style="margin:12px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:14px;
line-height:22px;text-align:center;color:#62584d;">{c["expiry"]}</p>
</td></tr>
<tr><td style="padding:28px;font-family:Arial,Helvetica,sans-serif;">
<p style="margin:0 0 12px;font-size:14px;line-height:23px;color:#62584d;">{c["security"]}</p>
<p style="margin:0;font-size:14px;line-height:23px;color:#62584d;">{c["ignore"]}</p>
</td></tr>
<tr><td style="padding:0 28px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td style="border-top:1px solid #d7ccba;font-size:1px;line-height:1px;">&nbsp;</td></tr>
</table>
</td></tr>
<tr><td style="padding:24px 28px 28px;font-family:Arial,Helvetica,sans-serif;">
<p style="margin:0 0 12px;font-size:13px;line-height:21px;color:#62584d;">{c["help"]}
<a href="mailto:{contact}" style="color:#1a1a1a;text-decoration:underline;
word-break:break-word;">{contact}</a>.</p>
<p style="margin:0;font-size:12px;line-height:20px;color:#62584d;">Aion by Agape</p>
</td></tr>
</table>
<!--[if mso]></td></tr></table><![endif]-->
</td></tr></table>
</div>
</body>
</html>"""


def verification_payload(
    email: str, code: str, language: str, sender: str, reply_to: str, purpose: str = "login"
) -> dict[str, object]:
    subject, body = verification_content(code, language, reply_to, purpose)
    return {
        "from": sender,
        "to": [email],
        "reply_to": reply_to,
        "subject": subject,
        "text": body,
        "html": verification_html(code, language, reply_to, purpose),
    }
