import re
from django.utils.safestring import mark_safe

LOCATOR_RE = re.compile(r"\[(\d+)\]")
BLANK_RE = re.compile(r"\{\[.*?\]\s*\[=([^\]]+)\]\}")


def hide_locators(text):
    """Return passage text for exam page with locator tags removed."""
    return LOCATOR_RE.sub('', text)


def show_locators_html(text):
    """Return passage HTML where locator numbers are functionally interactive but visually hidden."""
    def repl(m):
        num = m.group(1)
        # Using a 0-width span or hidden elements keeps the DOM element for jumpToLocator
        # without ruining the natural visual text representation for the student.
        return f"<span class=\"locator\" id=\"locator-{num}\" style=\"display: inline-block; width: 0; height: 0; overflow: hidden; position: absolute;\">[{num}]</span>"
    return mark_safe(LOCATOR_RE.sub(repl, text))


def parse_blanks_to_inputs(text, prefix='ans', values=None, results=None, choices=None):
    """
    Convert blanks like {[ ][=q1]} to input fields.
    Returns (html, keys) where keys is list of blank keys found.
    Input names will be like '{prefix}_q1'.
    If choices is provided as a dict mapping keys to lists of strings,
    a <select> will be rendered instead of an <input>.
    """
    keys = []
    values = values or {}
    results = results or {}
    choices = choices or {}

    def repl(m):
        key = m.group(1).strip()
        keys.append(key)
        name = f"{prefix}_{key}"
        # Remove 'q' prefix to show only the number
        display_num = key.replace('q', '', 1) if key.startswith('q') else key
        val = values.get(key, '')
        readonly = "readonly" if values else ""
        
        border_color = ""
        text_color = "inherit"
        if key in results:
            if results[key]:
                border_color = "#38a169" # Success green
                text_color = "#276749"
            else:
                border_color = "#e53e3e" # Danger red
                text_color = "#c53030"

        # If we have choices for this specific key or a common list for all keys in this call
        # (common list can be passed with key '*' or if choices is just a list)
        options = []
        if isinstance(choices, list):
            options = choices
        elif isinstance(choices, dict):
            options = choices.get(key) or choices.get('*')

        dynamic_style = f"color: {text_color} !important;"
        if border_color:
            dynamic_style += f" border-bottom-color: {border_color} !important;"

        if options:
            # Default option for exam is blank/hyphen, for result it shows nothing or the selected value
            default_text = "-" if not values else (val or "-")
            options_html = [f'<option value="">{default_text}</option>']
            for opt in options:
                selected = 'selected' if str(val).strip().lower() == str(opt).strip().lower() else ''
                options_html.append(f'<option value="{opt}" {selected}>{opt}</option>')
            
            if readonly:
                return f"<select name=\"{name}\" class=\"ielts-inline-input\" data-key=\"{key}\" disabled style=\"{dynamic_style}\">{''.join(options_html)}</select>"
            return f"<select name=\"{name}\" class=\"ielts-inline-input\" data-key=\"{key}\" style=\"{dynamic_style}\" onclick=\"jumpToLocator('{key.replace('q','')}')\">{''.join(options_html)}</select>"

        placeholder_text = f"{display_num}" if not values else ""
        content_length = len(str(val)) if val else len(placeholder_text)
        initial_width = max(30, (content_length + 1) * 9 + 10)
        input_style = dynamic_style + f" width: {initial_width}px;"
        
        return f"<input type=\"text\" name=\"{name}\" class=\"ielts-inline-input blank-input\" value=\"{val}\" data-key=\"{key}\" placeholder=\"{placeholder_text}\" {readonly} autocomplete=\"off\" style=\"{input_style}\" oninput=\"this.style.width = Math.max(30, (this.value.length || this.placeholder.length || 1) * 9 + 10) + 'px'\" onclick=\"jumpToLocator('{key.replace('q','')}')\" />"

    html = BLANK_RE.sub(repl, text)
    return mark_safe(html), keys

def extract_blank_keys(text):
    return BLANK_RE.findall(text)