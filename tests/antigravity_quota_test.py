"""Exercise the installed probe's quota selection with Google's response shapes."""
from pathlib import Path
import subprocess
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from patch import Archive


class QuotaTest(unittest.TestCase):
    def test_selection_preserves_bundled_map_alias(self):
        from antigravity_quota import OLD, patch
        for alias in ['map$9', 'map$10', 'quotaMap']:
            with self.subTest(alias=alias):
                source = ('antigravity/hub/2.24.0\n'
                          'for (const endpoint of ENDPOINTS) {}\n'
                          'bucket.bucketId.startsWith("gemini-argon-")\n'
                          'const makeAntigravityUsageProbe = fn("makeAntigravityUsageProbe")\n'
                          + OLD.replace('map$9', alias))
                result = patch(source)
                self.assertIn(f'decodeModels(response).pipe({alias}(modelWindows))', result)
                self.assertIn('const windows = mergeQuotaWindows(summary, __t3ModelQuotas);', result)
                with self.assertRaisesRegex(ValueError, 'quota selection integration point'):
                    patch(source + '\n' + OLD.replace('map$9', alias))
                with self.assertRaisesRegex(ValueError, 'quota selection integration point'):
                    patch(source.replace('summary.length ? summary', 'summary.length > 1 ? summary'))

    def test_routine_build_changes_do_not_require_an_adapter_update(self):
        from antigravity_quota import patch
        from js_templates import TOKEN
        archive = Archive('/opt/t3code-nightly-bin/resources/app.asar')
        source = next(archive.read(name).decode() for name in archive.entries
                      if name.startswith('apps/server/dist/') and name.endswith('.mjs')
                      and b'// src/provider/antigravityUsageLimits.ts' in archive.read(name))
        start = source.index('// src/provider/antigravityUsageLimits.ts')
        end = source.index('\n// ', start)
        source = source[start:end]
        aliases = ['fetchWindows', 'decodeModels', 'modelWindows', 'makeAntigravityUsageProbe',
                   'forEach', 'ENDPOINTS', 'summaryWindows', 'quotaWindow', 'group', 'windows', 'responses', 'previous']
        for variant in ['aliases', 'spaces', 'quotes', 'changed_logic']:
            with self.subTest(variant=variant):
                changed = source
                if variant == 'aliases':
                    for index, alias in enumerate(aliases):
                        changed = TOKEN.sub(lambda m, a=alias, i=index:
                                            f'$renamed{i}' if m[0] == a else m[0], changed)
                elif variant == 'spaces':
                    changed = changed.replace('\t', '    ')
                elif variant == 'quotes':
                    changed = changed.replace('"fetchAvailableModels"', "'fetchAvailableModels'")
                else:
                    changed = changed.replace('window.usedPercent > previous.usedPercent',
                                              'window.usedPercent < previous.usedPercent')
                    with self.assertRaisesRegex(ValueError, 'quota endpoint selection'):
                        patch(changed)
                    continue
                result = patch(changed)
                self.assertIn('mergeQuotaWindows(', result)
                self.assertEqual(patch(result), result)
                checked = subprocess.run(['node', '--check', '--input-type=module'],
                                         input=result, text=True, capture_output=True)
                self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_summary_is_supplemented_without_overriding_shared_limits(self):
        archive_path = (Path.home() / '.cache/t3code-persisted/last-good/resources/app.asar'
                        if '--installed' in sys.argv else Path('/opt/t3code-nightly-bin/resources/app.asar'))
        archive = Archive(archive_path)
        names = [name for name in archive.entries if name.startswith('apps/server/dist/') and name.endswith('.mjs') and b'// src/provider/antigravityUsageLimits.ts' in archive.read(name)]
        self.assertEqual(len(names), 1)
        source = archive.read(names[0]).decode()
        if '--original' not in sys.argv and '--installed' not in sys.argv:
            from antigravity_quota import patch
            source = patch(source)
        self.assertTrue('antigravity/hub/2.28.2' in source, 'Old Hub version suppresses Gemini and Argon summary buckets')
        self.assertFalse('const responses = yield* forEach(ENDPOINTS' in source,
                         'Use the first usable endpoint instead of mixing differing quota reports')
        start = source.index('function quotaWindow(')
        end = source.index('const makeAntigravityUsageProbe', start)
        functions = source[start:end]
        start = source.index('const summary = yield* fetchWindows("retrieveUserQuotaSummary"')
        end = source.index('\n\t\t\tif (windows.length', start)
        selection = source[start:end]
        fetch_start = source.index('const fetchWindows = fn("AntigravityUsageProbe.fetchWindows")')
        fetch_end = source.index('\n\t\t\tconst summary =', fetch_start)
        fetching = source[fetch_start:fetch_end]
        script = '''
const assert = require('node:assert/strict');
const iso$1 = value => value;
const SUMMARY_WINDOW_MINS = new Map([['5h',300],['weekly',10080]]);
FUNCTIONS
const summary = {groups:[{buckets:[
 {bucketId:'3p-weekly',window:'weekly',remainingFraction:0},
 {bucketId:'3p-5h',window:'5h',remainingFraction:1,disabled:true}
]}]};
const models = {models:{
 'gemini-3-flash':{modelProvider:'MODEL_PROVIDER_GOOGLE',quotaInfo:{remainingFraction:0.99}},
 'claude-opus':{modelProvider:'MODEL_PROVIDER_ANTHROPIC',quotaInfo:{remainingFraction:0.6}},
 'gpt-oss':{modelProvider:'MODEL_PROVIDER_OPENAI',quotaInfo:{remainingFraction:0.6}}
}};
function run(s, m) {
 function* fetchWindows(operation) {return operation === 'retrieveUserQuotaSummary' ? summaryWindows(s) : modelWindows(m);}
 function* probe() { SELECTION; return windows; }
 return probe().next().value;
}
let windows = run(summary, models);
assert(windows.some(w => w.id === 'gemini-quota'), 'Gemini quota must remain visible when summary only covers Claude/GPT');
assert.equal(windows.find(w => w.id === '3p-weekly').usedPercent,100);
assert(!windows.some(w => w.id === '3p-5h'), 'Disabled session must stay hidden');
assert(!windows.some(w => /^(claude|gpt)-/.test(w.id)), 'Shared summary must override model quotas');
assert.equal(run({}, models).length,3, 'Older accounts must retain model fallback');
const full = {buckets:[...summary.groups[0].buckets,{bucketId:'gemini-5h',window:'5h',remainingFraction:0.8}]};
windows = run(full, models);
assert.equal(windows.length,2,'Do not duplicate Gemini when summary already covers it');
assert.equal(windows.find(w => w.id === 'gemini-5h').kind,'session');
assert.equal(run(summary,{models:{}}).length,1,'Keep summary if model request fails');
const complete = {groups:[{displayName:'Gemini Models',buckets:[
 {bucketId:'gemini-weekly',window:'weekly',remainingFraction:0.999548},
 {bucketId:'gemini-5h',window:'5h',remainingFraction:0.999183}
]}, summary.groups[0], {displayName:'Gemini 4 Argon',buckets:[
 {bucketId:'gemini-argon-wtu-weekly',window:'weekly',remainingFraction:0.75008655}
]}]};
windows = run(complete,models);
assert.equal(windows.length,4);
assert.equal(windows.find(w => w.id === 'gemini-argon-wtu-weekly').label,'Gemini 4 Argon · Weekly');
assert.equal(windows.find(w => w.id === 'gemini-weekly').kind,'weekly');
assert.equal(windows.find(w => w.id === 'gemini-5h').windowDurationMins,300);

const ENDPOINTS = ['primary','fallback'];
const accessToken = 'synthetic';
const platform = 'linux', architecture = 'x64';
const token = {};
const currentTimeMillis = (function*(){return 0;})();
const fn = () => f => f;
const post$1 = url => ({url,pipe(){return this;}});
const setHeaders$1 = () => null, bodyJsonUnsafe = () => null, flatMap$1 = () => null, orElseSucceed = () => null;
let calls = [];
let results = [[{id:'gemini-weekly',usedPercent:0.05}], [{id:'gemini-weekly',usedPercent:1}]];
function request(req) {return {pipe(){return (function*(){calls.push(req.url);return results[calls.length-1];})();}};}
FETCHING
let selected = fetchWindows('retrieveUserQuotaSummary',x=>x).next().value;
assert.equal(selected[0].usedPercent,0.05,'Primary endpoint must stay authoritative');
assert.equal(calls.length,1,'Do not query fallback after primary succeeds');
calls=[]; results=[[],[{id:'gemini-weekly',usedPercent:1}]];
selected = fetchWindows('retrieveUserQuotaSummary',x=>x).next().value;
assert.equal(selected[0].usedPercent,1);
assert.equal(calls.length,2,'Empty primary must fall back');
console.log('Quota selection regression checks passed');
'''.replace('FUNCTIONS', functions).replace('SELECTION', selection).replace('FETCHING', fetching)
        # Stub the imported operations under the aliases in this installed build.
        # Local names in the extracted probe stay unchanged.
        aliases = {'post': 'post$1', 'setHeaders': 'setHeaders$1', 'flatMap': 'flatMap$1',
                   'orElseSucceed': 'orElseSucceed', 'bodyJsonUnsafe': 'bodyJsonUnsafe'}
        declarations = []
        for name in set(re.findall(r'[A-Za-z_$][\w$]*', fetching)):
            base = name.split('$')[0]
            if base in aliases and name != aliases[base]:
                declarations.append(f'const {name} = {aliases[base]};')
        script = script.replace(fetching, '\n'.join(declarations) + '\n' + fetching)
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout.strip())


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
