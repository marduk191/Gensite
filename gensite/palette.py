"""Gensite's single colour palette.

The stylesheet (native_theme.qss) refers to these as @name@ tokens, and painted
widgets (icons, artwork panel, title bars, canvas selection) read them from
PALETTE, so every surface uses the same small set of colours.
"""
from pathlib import Path

PALETTE = {
    # One neutral background everywhere; areas are separated by lines, not by shades.
    'sunken': '#171717',      # canvas backdrop, code editor
    'base': '#171717',        # window background
    'surface': '#171717',     # toolbar, side panels, status bar
    'raised': '#212121',      # fields, buttons, popups
    'hover': '#2a2a2a',
    'pressed': '#323232',
    # lines
    'line': '#2a2a2a',        # dividers between areas
    'border': '#363636',      # control outlines
    'border_hi': '#4a4a4a',   # hovered outlines, scrollbar hover
    # text
    'heading': '#f2f2f2',
    'text': '#e6e6e6',
    'soft': '#bdbdbd',        # secondary text, icons
    'muted': '#8f8f8f',       # hints, labels
    'faint': '#727272',       # section titles, status
    'disabled': '#565656',
    # accent: neutral light, so primary actions stand out without a second hue
    'accent': '#e6e6e6',
    'accent_hi': '#ffffff',
    'accent_lo': '#cfcfcf',
    'on_accent': '#171717',   # text/icons on the accent
    'accent_text': '#ffffff', # selected tab / row text
    'accent_tint': '#2e2e2e', # selected rows
    'accent_line': '#5a5a5a', # focus outlines, text selection
}

_HERE = Path(__file__).resolve().parent


def rgb(name):
    value = PALETTE[name].lstrip('#')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def colorref(name):
    """Windows COLORREF (0x00BBGGRR) for DWM title-bar attributes."""
    r, g, b = rgb(name)
    return (b << 16) | (g << 8) | r


def stylesheet():
    text = (_HERE / 'native_theme.qss').read_text(encoding='utf-8')
    text = text.replace('@ICONS@', (_HERE / 'icons').as_posix())
    for name, value in sorted(PALETTE.items(), key=lambda kv: -len(kv[0])):
        text = text.replace('@' + name + '@', value)
    if '@' in text.replace('@ICONS@', ''):
        leftover = text[text.index('@'):text.index('@') + 30]
        raise ValueError('Unknown colour token in native_theme.qss: ' + leftover)
    return text


def support_page_css():
    """Restyle the hosted donation page to the app palette inside the Support window only.

    The public page keeps its own look; this sheet is injected after it loads.
    """
    c = PALETTE
    return f"""
html {{ color-scheme: dark; }}
body {{ background: {c['base']} !important; color: {c['text']} !important; padding: 28px 22px !important; align-items: flex-start !important; min-height: 0 !important; }}
.donation-container {{ background: transparent !important; box-shadow: none !important; padding: 0 !important; animation: none !important; max-width: 520px !important; }}
.header {{ margin-bottom: 22px !important; }}
.header h1 {{ color: {c['heading']} !important; font-weight: 500 !important; font-size: 22px !important; margin-bottom: 6px !important; }}
.header p, .payment-desc, .section-divider span {{ color: {c['muted']} !important; }}
.wallet-section {{ background: {c['raised']} !important; border: 1px solid {c['line']} !important; border-radius: 8px !important; padding: 14px !important; margin-bottom: 12px !important; }}
.wallet-label, .payment-name {{ color: {c['text']} !important; }}
.network-badge {{ background: transparent !important; color: {c['soft']} !important; border: 1px solid {c['border']} !important; }}
.wallet-address {{ background: {c['base']} !important; color: {c['soft']} !important; border: 1px solid {c['border']} !important; margin-bottom: 10px !important; }}
.copy-btn {{ background: {c['accent']} !important; color: {c['on_accent']} !important; border: 1px solid {c['accent']} !important; box-shadow: none !important; transform: none !important; }}
.copy-btn:hover {{ background: {c['accent_hi']} !important; border-color: {c['accent_hi']} !important; }}
.copy-btn.copied {{ background: {c['accent_lo']} !important; border-color: {c['accent_lo']} !important; }}
.qr-toggle-btn {{ background: {c['hover']} !important; color: {c['text']} !important; border: 1px solid {c['border']} !important; }}
.qr-toggle-btn:hover {{ background: {c['pressed']} !important; border-color: {c['border_hi']} !important; }}
.qr-toggle-btn.active {{ background: {c['pressed']} !important; color: {c['heading']} !important; border-color: {c['border_hi']} !important; }}
.mini-qr:not(.show) {{ padding: 0 !important; margin: 0 !important; }}
.mini-qr.show {{ margin-top: 12px !important; }}
.section-divider {{ margin: 22px 0 14px !important; }}
.section-divider::before, .section-divider::after {{ background: {c['line']} !important; }}
.payment-btn {{ background: {c['raised']} !important; border: 1px solid {c['line']} !important; border-radius: 8px !important; padding: 14px 6px !important; transform: none !important; }}
.payment-btn:hover {{ background: {c['hover']} !important; border-color: {c['border_hi']} !important; }}
::-webkit-scrollbar {{ width: 10px; background: transparent; }}
::-webkit-scrollbar-thumb {{ background: {c['border']}; border-radius: 5px; border: 2px solid {c['base']}; }}
"""
