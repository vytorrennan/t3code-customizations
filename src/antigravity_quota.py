"""Supplement Google's partial quota summary with uncovered model families."""
import re
import textwrap
from js_templates import match_template, template_pattern

OLD = 'const windows = summary.length ? summary : yield* fetchWindows("fetchAvailableModels", (response) => decodeModels(response).pipe(map$9(modelWindows)));'
HELPER = '''function mergeQuotaWindows(summary, models) {
	const covered = new Set();
	for (const window of summary) {
		if (window.id.startsWith("gemini-")) covered.add("gemini");
		if (window.id.startsWith("3p-")) {
			covered.add("claude");
			covered.add("gpt");
		}
	}
	return [...summary, ...models.filter(window => !covered.has(window.id.split("-")[0]))];
}
'''
USER_AGENT = re.compile(r'antigravity/hub/\d+(?:\.\d+)+')
HUB_VERSION = 'antigravity/hub/2.28.2'


def patch_user_agent(source):
    """A stale Hub version withholds Gemini and Argon summary buckets."""
    matches = list(USER_AGENT.finditer(source))
    if len(matches) != 1:
        raise ValueError('Cannot identify the Antigravity Hub user agent.')
    match = matches[0]
    version = lambda value: tuple(map(int, value.rsplit('/', 1)[1].split('.')))
    if version(match[0]) >= version(HUB_VERSION):
        return source
    return source[:match.start()] + HUB_VERSION + source[match.end():]


def patch_sequential_endpoints(source):
    """Query endpoints in order and stop at the first usable report."""
    if '__t3QuotaWindows.length' in source or 'for (const endpoint of ENDPOINTS)' in source:
        return source
    template = """const responses = yield* forEach(ENDPOINTS, (endpoint) => gen(function* () {
        BODY
    }), { concurrency: "unbounded" });
    const windows = new Map();
    for (const window of responses.flat()) {
        const previous = windows.get(window.id);
        if (!previous || window.usedPercent > previous.usedPercent) windows.set(window.id, window);
    }
    return [...windows.values()];"""
    match = match_template(source, template, 'Antigravity quota endpoint selection',
                           bindings=['responses', 'forEach', 'ENDPOINTS', 'endpoint',
                                     'gen', 'windows', 'window', 'previous'], bodies=['BODY'])
    body = textwrap.dedent(match['BODY']).strip()
    # Keep the installed request, headers, parser and error handling intact.
    request = match_template(body, 'return yield*', 'Antigravity quota endpoint request')
    body = body[:request.start()] + 'const __t3QuotaWindows = yield*' + body[request.end():]
    replacement = (f"for (const {match['endpoint']} of {match['ENDPOINTS']}) {{\n"
                   + body + '\nif (__t3QuotaWindows.length) return __t3QuotaWindows;\n}\nreturn [];')
    return source[:match.start()] + replacement + source[match.end():]


def patch_argon_labels(source):
    """Upstream may already separate Argon from the shared Gemini family."""
    if template_pattern('bucket.bucketId.startsWith("gemini-argon-")', ['bucket']).search(source):
        return source
    family = match_template(source, 'bucket.bucketId.startsWith("gemini-") ? "Gemini" :',
                            'Antigravity summary labels', bindings=['bucket'])
    group = match_template(source, 'for (const bucket of group.buckets ?? [])',
                           'Antigravity summary bucket group', bindings=['bucket', 'group'])
    if family['bucket'] != group['bucket']:
        raise ValueError('Cannot identify the Antigravity summary bucket binding.')
    replacement = (f"{family['bucket']}.bucketId.startsWith(\"gemini-argon-\") ? "
                   f"{group['group']}.displayName?.trim() || \"Gemini 4 Argon\" : " + family[0])
    return source[:family.start()] + replacement + source[family.end():]


def patch(source):
    marker = '// src/provider/antigravityUsageLimits.ts'
    if marker in source:
        start = source.index(marker)
        end_match = re.search(r'^// ', source[start + len(marker):], re.M)
        end = start + len(marker) + end_match.start() if end_match else len(source)
        return source[:start] + patch_module(source[start:end]) + source[end:]
    return patch_module(source)


def patch_module(source):
    source = patch_user_agent(source)
    source = patch_sequential_endpoints(source)
    if 'function mergeQuotaWindows(' not in source:
        match = match_template(
            source, OLD.replace('map$9', 'mapAlias'), 'Antigravity quota selection integration point',
            bindings=['windows', 'summary', 'fetchWindows', 'response', 'decodeModels',
                      'mapAlias', 'modelWindows'])
        # Reuse the original model request expression, including its generated aliases.
        expression = match[0][match[0].index('yield'):].rstrip().removesuffix(';')
        replacement = (f'const __t3ModelQuotas = {expression};\n'
                       f"const {match['windows']} = mergeQuotaWindows({match['summary']}, __t3ModelQuotas);")
        source = source[:match.start()] + replacement + source[match.end():]
        boundary = match_template(source, 'const makeAntigravityUsageProbe = fn("makeAntigravityUsageProbe")',
                                  'Antigravity usage probe boundary',
                                  bindings=['makeAntigravityUsageProbe', 'fn'])
        source = source[:boundary.start()] + HELPER + source[boundary.start():]
    source = patch_argon_labels(source)
    return source
