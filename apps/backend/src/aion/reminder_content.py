"""Dated calendar snapshots; no personal values in subjects, preheaders or URLs."""

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from aion.calendar import calculate
from aion.models import Profile, ReminderPreference
from aion.phrases import Collection


def render_reminder(
    profile: Profile,
    pref: ReminderPreference,
    due: datetime,
    collection: Collection,
    *,
    origin: str,
    email: str,
    sender: str,
    reply_to: str,
    token: str,
) -> tuple[dict[str, object], str | None]:
    assert profile.birth_date is not None
    local = due.astimezone(ZoneInfo(pref.timezone))
    totals = calculate(
        {
            "birthDate": profile.birth_date.isoformat(),
            "lifespanYears": profile.lifespan_years,
            "clock": {"date": local.date().isoformat(), "time": local.strftime("%H:%M:%S")},
        }
    )
    if "error" in totals:
        raise ValueError("Invalid reminder calendar")
    es = pref.language == "es"
    title = "Un momento para tu vida." if es else "A moment for your life."
    subject = "Tu recordatorio de Aion" if es else "Your Aion reminder"
    preheader = (
        "Una pausa para mirar tu vida con perspectiva."
        if es
        else "A quiet pause to put your life in perspective."
    )
    lived = f"{totals['lived']['weeks']:,}".replace(",", "." if es else ",")
    lines = [f"{'Semanas vividas' if es else 'Weeks lived'}: {lived}"]
    if not profile.hide_remaining:
        remaining = f"{totals['remaining']['weeks']:,}".replace(",", "." if es else ",")
        lines.append(f"{'Semanas restantes' if es else 'Weeks remaining'}: {remaining}")
    caveat = (
        f"Basado en tu horizonte elegido de {profile.lifespan_years} años; no es una predicción."
        if es
        else (
            f"Based on your chosen lifespan of {profile.lifespan_years} years; "
            "this is not a prediction."
        )
    )
    if totals["horizonState"] != "before":
        caveat += (
            " Tu vida continúa más allá de esta estimación."
            if es
            else "Your life continues beyond this estimate."
        )
    phrase = collection.for_date(local.date()) if pref.include_phrase else None
    passage, credit = "", ""
    if phrase:
        translated = phrase.es if es else phrase.en
        passage = translated.text
        credit = f"{phrase.author} · {phrase.work} · {phrase.location}"
        if translated.translator:
            credit += f" · {'Traducción' if es else 'Translation'}: {translated.translator}"
    calendar_url = origin + ("/es" if es else "/")
    # Opaque capability only: no identity, calendar inputs or totals in unsubscribe URLs.
    unsubscribe = origin + "/api/v1/unsubscribe/" + token
    label = "Abrir mi calendario" if es else "Open my calendar"
    stop = "Cancelar recordatorios" if es else "Unsubscribe from reminders"
    help_text = "Ayuda" if es else "Support"
    reference = f"{local.date().isoformat()} · {pref.timezone}"
    text = f"Aion\n\n{title}\n{reference}\n\n" + "\n".join(lines) + f"\n\n{caveat}\n"
    if phrase:
        text += f"\n{passage}\n— {credit}\n{phrase.source_url}\n"
    text += (
        f"\n{label}: {calendar_url}\n{stop}: {unsubscribe}\n"
        f"{help_text}: {reply_to}\n\nAion by Agape\n"
    )
    e = escape
    quote_html = (
        (
            '<blockquote style="margin:32px 0 12px;font:24px/1.5 Georgia,serif;">'
            f"{e(passage)}</blockquote>"
            f'<p style="font-size:13px;line-height:21px;color:#62584d;">— {e(credit)}</p>'
            f'<p><a href="{e(phrase.source_url, quote=True)}" style="color:#62584d;">'
            f"{'Fuente' if es else 'Source'}</a></p>"
        )
        if phrase
        else ""
    )
    html = f'''<!doctype html><html lang="{pref.language}" dir="ltr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{subject}</title></head>
<body style="margin:0;background:#faf6ee;color:#1a1a1a;">
<div lang="{pref.language}" dir="ltr">
<div aria-hidden="true"
style="display:none;
max-height:0;overflow:hidden;mso-hide:all;">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
style="background:#faf6ee;">
<tr><td align="center" style="padding:32px 16px;">
<!--[if mso]><table role="presentation" width="560"><tr><td><![endif]-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
style="max-width:560px;
background:#fffdf8;border:1px solid #d7ccba;">
<tr><td style="padding:28px;font:16px/1.65 Arial,Helvetica,sans-serif;">
<p
style="margin:0 0 32px;font-size:36px;font-weight:700;letter-spacing:-2px;">aion<span
style="color:#b5532a;">.</span>
</p>
<p style="color:#62584d;font-size:12px;">{e(reference)}</p>
<h1 style="font:32px/1.2 Georgia,serif;">{title}</h1>
{"".join(f'<p style="font-size:20px;">{e(line)}</p>' for line in lines)}
<p style="font-size:14px;color:#62584d;">{e(caveat)}</p>{quote_html}
<p style="margin:32px 0;"><a href="{e(calendar_url)}" style="color:#1a1a1a;">{label} →</a></p>
<p style="border-top:1px solid #d7ccba;padding-top:24px;font-size:13px;color:#62584d;">
<a href="{e(unsubscribe)}" style="color:#1a1a1a;">{stop}</a><br>
{help_text}: <a href="mailto:{e(reply_to)}"
style="color:#1a1a1a;word-break:break-word;">{e(reply_to)}</a>
<br>Aion by Agape</p>
</td>
</tr>
</table>
<!--[if mso]>
</td>
</tr>
</table>
<![endif]-->
</td>
</tr>
</table>
</div>
</body>
</html>'''
    return {
        "from": sender,
        "to": [email],
        "reply_to": reply_to,
        "subject": subject,
        "text": text,
        "html": html,
        "headers": {
            "List-Unsubscribe": f"<{unsubscribe}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    }, phrase.id if phrase else None
