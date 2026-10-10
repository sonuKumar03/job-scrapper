"""Text and HTML normalization utilities."""

import re
from selectolax.lexbor import LexborHTMLParser as HTMLParser


def clean_html_to_text(raw_html: str) -> str:
    """Extract clean, structured plain text from HTML job descriptions."""
    if not raw_html or not raw_html.strip():
        return ""

    tree = HTMLParser(raw_html)
    # Remove boilerplate non-content tags
    for tag in tree.css("script, style, noscript, nav, footer"):
        tag.decompose()

    for tag in tree.css("p, div, li, h1, h2, h3, h4, h5, h6, section, article, blockquote, tr, br"):
        tag.insert_before("\n")
        tag.insert_after("\n")
    text = tree.text(separator=" ")
    return normalize_whitespace(text)


def normalize_whitespace(text: str) -> str:
    """Collapse consecutive spaces and linebreaks into clean prose."""
    # Replace multiple empty lines with a double newline
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Replace multiple spaces/tabs on a single line with a single space
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()
