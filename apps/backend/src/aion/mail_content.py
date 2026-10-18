"""Versioned transactional code content shared by capture and provider delivery."""


def verification_content(code: str, language: str) -> tuple[str, str]:
    if language == "es":
        return (
            "Tu código de Aion",
            f"Tu código es {code}. Caduca en diez minutos. "
            "Si no lo solicitaste, ignora este correo.",
        )
    return (
        "Your Aion sign-in code",
        f"Your code is {code}. It expires in ten minutes. "
        "If you did not request this, ignore this email.",
    )


def verification_payload(
    email: str, code: str, language: str, sender: str, reply_to: str
) -> dict[str, object]:
    subject, body = verification_content(code, language)
    return {"from": sender, "to": [email], "reply_to": reply_to, "subject": subject, "text": body}
