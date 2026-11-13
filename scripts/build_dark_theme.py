"""Generate app/dark-theme.css from the site's light stylesheets.

The site has about 100 kB of hand-written light styles. Instead of rewriting
each page, every colour declaration is re-emitted under `html.svDark` with a
dark-terminal equivalent that keeps the original hue:

- light surfaces become near-black panels (tinted surfaces keep a dim tint);
- dark ink becomes light ink, coloured ink is lifted until it reads on black;
- light borders become hairlines; soft drop shadows are removed.

Run `python3 scripts/build_dark_theme.py` after editing any source stylesheet;
`--check` fails when the committed output is stale (used by the test suite).
"""
import argparse
import colorsys
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('app/globals.css', 'app/product-v2.css', 'app/market.css', 'app/favorite-pattern.css',
           'app/interface.css', 'app/multifactor.css', 'app/app/style.css', 'app/evidence/style.css')
OUT = ROOT / 'app/dark-theme.css'
SCOPE = 'html.svDark'
NAMED = {'white': '#ffffff', 'black': '#000000'}
VAR = re.compile(r'var\(\s*(--[\w-]+)\s*(?:,[^)]*)?\)')
COLOR = re.compile(r'#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|\b(?:white|black)\b')
PROPS = {'background', 'background-color', 'background-image', 'color', 'border', 'border-color', 'border-top',
         'border-bottom', 'border-left', 'border-right', 'border-top-color', 'border-bottom-color',
         'border-left-color', 'border-right-color', 'outline', 'outline-color', 'box-shadow', 'fill', 'stroke',
         'text-decoration-color', 'caret-color', 'accent-color', 'column-rule'}
SURFACE = {'background', 'background-color', 'background-image'}
LINE = {'border', 'border-color', 'border-top', 'border-bottom', 'border-left', 'border-right', 'border-top-color',
        'border-bottom-color', 'border-left-color', 'border-right-color', 'outline', 'outline-color', 'column-rule'}


def parse_color(token):
    token = NAMED.get(token, token)
    if token.startswith('#'):
        h = token[1:]
        if len(h) in (3, 4):
            h = ''.join(c * 2 for c in h)
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return r, g, b, a
    parts = [p.strip() for p in re.split(r'[,/\s]+', token[token.index('(') + 1:-1]) if p.strip()]
    r, g, b = (float(p[:-1]) / 100 if p.endswith('%') else float(p) / 255 for p in parts[:3])
    a = parts[3] if len(parts) > 3 else '1'
    return r, g, b, float(a[:-1]) / 100 if a.endswith('%') else float(a)


def emit(r, g, b, a):
    rgb = [max(0, min(255, round(v * 255))) for v in (r, g, b)]
    if a >= 0.999:
        return '#%02x%02x%02x' % tuple(rgb)
    return 'rgba(%d,%d,%d,%s)' % (*rgb, f'{a:.3f}'.rstrip('0').rstrip('.'))


def remap(token, role):
    r, g, b, a = parse_color(token)
    h, light, s = colorsys.rgb_to_hls(r, g, b)
    if role == 'surface':
        if light >= 0.8:
            light, s = 0.045 + (1 - light) * 0.38, min(s, 0.5) * 0.55
        elif light < 0.3:
            light, s = 0.06 + light * 0.3, s * 0.45
        # Mid-tone fills (buttons, bars, badges) keep their colour on the dark page.
    elif role == 'line':
        if light >= 0.7:
            light, s = 0.13 + (1 - light) * 0.35, s * 0.3
    else:  # ink
        if light < 0.55:
            if s < 0.28:
                light, s = 0.92 - light * 0.6, s * 0.5
            else:
                light, s = max(light, 0.66), min(1, s * 1.1)
    r, g, b = colorsys.hls_to_rgb(h, light, s)
    return emit(r, g, b, a)


def convert_value(prop, value):
    if prop == 'box-shadow':
        # Light-theme depth shadows vanish on black; keep only inset accent rules (selected rows).
        if 'inset' not in value:
            return 'none'
        return COLOR.sub(lambda m: remap(m.group(0), 'ink'), value)
    role = 'surface' if prop in SURFACE else 'line' if prop in LINE else 'ink'
    return COLOR.sub(lambda m: remap(m.group(0), role), value)


def scope_selector(selector):
    out = []
    for part in split_top(selector, ','):
        part = part.strip()
        if not part:
            continue
        if part.startswith(':root'):
            out.append(SCOPE + part[5:])
        elif re.match(r'html\b', part):
            out.append(SCOPE + part[4:])
        else:
            out.append(f'{SCOPE} {part}')
    return ','.join(out)


def split_top(text, sep):
    parts, depth, buf = [], 0, ''
    for ch in text:
        depth += ch in '([' and 1 or ch in ')]' and -1 or 0
        if ch == sep and depth == 0:
            parts.append(buf)
            buf = ''
        else:
            buf += ch
    parts.append(buf)
    return parts


def blocks(css):
    """Yield (prelude, body) for each top-level block, comments removed."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    i, n = 0, len(css)
    while i < n:
        start = css.find('{', i)
        if start < 0:
            return
        prelude = css[i:start].strip()
        # A statement such as `@import "x";` before the block belongs to nobody.
        prelude = prelude.rsplit(';', 1)[-1].strip()
        depth, j = 1, start + 1
        while j < n and depth:
            depth += {'{': 1, '}': -1}.get(css[j], 0)
            j += 1
        yield prelude, css[start + 1:j - 1]
        i = j


def collect_vars(css):
    """Custom properties holding a single literal colour, by name."""
    found = {}
    for prop, value in re.findall(r'(--[\w-]+)\s*:\s*([^;{}]+)', re.sub(r'/\*.*?\*/', '', css, flags=re.S)):
        value = value.strip()
        if COLOR.fullmatch(value):
            found[prop] = value
    return found


def convert_rules(css, variables):
    out = []
    for prelude, body in blocks(css):
        if prelude.startswith('@keyframes') or prelude.startswith('@font-face'):
            continue
        if prelude.startswith('@'):
            inner = convert_rules(body, variables)
            if inner:
                out.append(prelude + '{' + ''.join(inner) + '}')
            continue
        decls = []
        for decl in split_top(body, ';'):
            if ':' not in decl:
                continue
            prop, value = decl.split(':', 1)
            prop = prop.strip().lower()
            value = value.strip()
            if prop.startswith('--'):
                if COLOR.search(value):
                    role = 'surface' if any(k in prop for k in ('paper', 'bg', 'panel', 'surface')) else \
                        'line' if 'line' in prop or 'border' in prop else 'ink'
                    decls.append(f'{prop}:' + COLOR.sub(lambda m, r=role: remap(m.group(0), r), value))
                continue
            if prop in (SURFACE | LINE) and VAR.search(value):
                # A text-colour variable used as a fill (dark ink buttons): resolve it, then recolour as a surface.
                value = VAR.sub(lambda m: variables.get(m.group(1), m.group(0)), value)
            if prop in PROPS and (COLOR.search(value) or (prop == 'box-shadow' and value != 'none')):
                decls.append(f'{prop}:{convert_value(prop, value)}')
        if decls:
            out.append(scope_selector(prelude) + '{' + ';'.join(decls) + '}')
    return out


def build():
    parts = ['/* Generated by scripts/build_dark_theme.py from the light stylesheets. Do not edit by hand. */']
    variables = {}
    for name in SOURCES:
        variables.update(collect_vars((ROOT / name).read_text()))
    for name in SOURCES:
        rules = convert_rules((ROOT / name).read_text(), variables)
        parts.append(f'/* {name} */')
        parts.extend(rules)
    return '\n'.join(parts) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    css = build()
    if args.check:
        if not OUT.exists() or OUT.read_text() != css:
            sys.exit('app/dark-theme.css is stale: run python3 scripts/build_dark_theme.py')
        return
    OUT.write_text(css)
    print(f'wrote {OUT.relative_to(ROOT)} ({len(css):,} bytes)')


if __name__ == '__main__':
    main()
