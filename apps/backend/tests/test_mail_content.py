from html.parser import HTMLParser

import pytest

from aion.mail_content import verification_content, verification_html, verification_payload
from aion.verification_mail import LocalCapture, Message

CODE = "00123456"


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


@pytest.mark.parametrize("language", ["en", "es"])
def test_accessible_self_contained_html_and_text_have_the_same_code_and_contact(language):
    contact = "support@example.test"
    payload = verification_payload("person@example.test", CODE, language, "Aion", contact)
    html = payload["html"]
    parsed = Elements(html)
    assert sum(tag == "h1" for tag, _ in parsed.elements) == 1
    assert all(
        attrs.get("role") == "presentation" for tag, attrs in parsed.elements if tag == "table"
    )
    assert ("html", {"lang": language, "dir": "ltr"}) in parsed.elements
    assert all(tag not in {"script", "img", "link", "iframe", "form"} for tag, _ in parsed.elements)
    assert CODE in parsed.text  # One intact text node, including leading zeroes.
    assert html.count(CODE) == 1 and payload["text"].count(CODE) == 1
    assert CODE not in payload["subject"]
    assert contact in payload["text"] and payload["reply_to"] == contact
    links = [attrs["href"] for tag, attrs in parsed.elements if tag == "a"]
    assert links == [f"mailto:{contact}"]
    assert len(html.encode()) < 10000
    assert ("10 minutos" if language == "es" else "10 minutes") in payload["text"]
    assert (
        "Keep this code" in payload["text"]
        if language == "en"
        else "Mantén este código" in payload["text"]
    )


def test_contact_is_escaped_as_text_and_attribute():
    html = verification_html(CODE, "en", 'x"><img src="https://example.test">&@example.test')
    assert "&lt;img" in html and "&quot;" in html and "&amp;" in html
    assert not any(tag == "img" for tag, _ in Elements(html).elements)


@pytest.mark.parametrize(
    "code,language", [("123", "en"), ("<script>", "en"), ("１２３４５６７８", "es"), (CODE, "fr")]
)
def test_invalid_template_input_fails_without_echoing_secrets(code, language):
    with pytest.raises(ValueError) as caught:
        verification_html(code, language, "support@example.test")
    assert code not in str(caught.value)


@pytest.mark.parametrize("language", ["en", "es"])
def test_smtp_capture_sends_plain_text_and_html_alternatives(monkeypatch, language):
    messages = []

    class Smtp:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def send_message(self, value):
            messages.append(value)

    monkeypatch.setattr("aion.verification_mail.smtplib.SMTP", Smtp)
    LocalCapture().send(Message("person@example.test", CODE, language), "synthetic-key")
    mail = messages[0]
    assert mail.get_content_type() == "multipart/alternative"
    text, html = list(mail.iter_parts())
    assert text.get_content_type() == "text/plain"
    assert html.get_content_type() == "text/html"
    assert (
        text.get_content().strip()
        == verification_content(CODE, language, "support@example.test")[1].strip()
    )
    assert (
        html.get_content().strip()
        == verification_html(CODE, language, "support@example.test").strip()
    )
    assert mail["Reply-To"] == "support@example.test"
