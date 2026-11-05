"""Match small JavaScript templates without depending on build-generated names.

This is deliberately a template matcher, not a JavaScript parser. Only explicitly
listed bindings can vary; properties, operators and control flow must still match.
"""
import re

TOKEN = re.compile(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|[A-Za-z_$][\w$]*|\d+|=>|===|!==|\.\.\.|\?\.|\S''')
GAP = r'(?:\s|/\*.*?\*/)*+'


def template_pattern(template, bindings=(), bodies=()):
    seen = set()
    parts = []
    for token in TOKEN.findall(template):
        if token in bodies:
            parts.append(f'(?P<{token}>.*?)')
        elif token in bindings:
            if token in seen:
                parts.append(f'(?P={token})')
            else:
                parts.append(f'(?P<{token}>[A-Za-z_$][\\w$]*)')
                seen.add(token)
        elif token.startswith(('"', "'", '`')) and '\\' not in token and '${' not in token:
            literal = re.escape(token[1:-1])
            parts.append(f'(?:"{literal}"|\'{literal}\'|`{literal}`)')
        elif re.fullmatch(r'[A-Za-z_$][\w$]*|\d+', token):
            parts.append(r'(?<![\w$])' + re.escape(token) + r'(?![\w$])')
        else:
            parts.append(re.escape(token))
    return re.compile(GAP.join(parts), re.S)


def match_template(source, template, description, bindings=(), bodies=()):
    matches = list(template_pattern(template, bindings, bodies).finditer(source))
    if len(matches) != 1:
        raise ValueError(f'Cannot identify the {description}: expected one integration point, found {len(matches)}.')
    return matches[0]
