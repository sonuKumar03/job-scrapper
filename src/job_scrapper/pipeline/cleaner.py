"""Text and HTML normalization utilities."""

import re
from selectolax.lexbor import LexborHTMLParser as HTMLParser
import trafilatura


def clean_html_to_text(raw_html: str) -> str:
    """Extract clean, structured plain text from HTML job descriptions."""
    if not raw_html or not raw_html.strip():
        return ""

    tree = HTMLParser(raw_html)
    # Remove boilerplate non-content tags
    for tag in tree.css("script, style, noscript, nav, footer"):
        tag.decompose()

    text = tree.text(separator=" ")
    return normalize_whitespace(text)


def normalize_whitespace(text: str) -> str:
    """Collapse consecutive spaces and linebreaks into clean prose."""
    # Replace multiple empty lines with a double newline
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Replace multiple spaces/tabs on a single line with a single space
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()
