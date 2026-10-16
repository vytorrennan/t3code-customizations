"""Exercise the actual installed Electron UI using synthetic local threads."""
import json
import os
from pathlib import Path
import signal
import shutil
import sqlite3
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = Path('/tmp/t3-persisted-native-test')
OUTPUT.mkdir(exist_ok=True)
membership_directory = OUTPUT / 'membership'
if membership_directory.exists():
    shutil.rmtree(membership_directory)
state = OUTPUT / 'state/userdata'
state.mkdir(parents=True, exist_ok=True)
database = state / 'statev2.sqlite'
if not database.exists():
    original = sqlite3.connect((Path.home()/'.t3/userdata/statev2.sqlite').as_uri() + '?mode=ro', uri=True)
    fixture = database.with_suffix('.fixture.tmp')
    fixture.unlink(missing_ok=True)
    target = sqlite3.connect(fixture)
    # Copy schema and migration bookkeeping only. No personal threads, messages,
    # provider sessions, credentials or events are copied into the test fixture.
    for (sql,) in original.execute("select sql from sqlite_master where sql is not null and name not glob 'sqlite_*' order by case type when 'table' then 0 else 1 end"):
        target.execute(sql)
    columns = list(original.execute('pragma table_info(effect_sql_migrations)'))
    rows = list(original.execute('select * from effect_sql_migrations'))
    target.executemany('insert into effect_sql_migrations values (' + ','.join('?' for _ in columns) + ')', rows)
    now = '2026-10-11T12:00:00.000Z'
    target.execute('insert into projection_projects(project_id,title,workspace_root,scripts_json,created_at,updated_at) values (?,?,?,?,?,?)', ('persisted-test-project', 'Example project', str(OUTPUT), '[]', now, now))
    for number, title in [(1, 'Plan the next release'), (2, 'Review the settings page')]:
        thread = f'persisted-test-thread-{number}'
        payload = dict(id=thread, projectId='persisted-test-project', title=title, createdBy='user', creationSource='web', providerInstanceId='codex', modelSelection={'instanceId': 'codex', 'model': 'gpt-6.1-sol'}, runtimeMode='full-access', interactionMode='default', activeProviderThreadId=None, branch=None, worktreePath=None, createdAt=now, updatedAt=now, lastVisitedAt=None, settledOverride=None, settledAt=None, unsettledAt=None, snoozedUntil=None, snoozedAt=None, pinnedAt=None, pinOrderKey=None, activeOrderKey=None, archivedAt=None, deletedAt=None, titleRegeneration=None, lineage={'parentThreadId':None,'relationshipToParent':None,'rootThreadId':thread}, forkedFrom=None, limitRecovery=None)
        target.execute('insert into orchestration_v2_projection_threads(thread_id,project_id,title,default_provider,runtime_mode,interaction_mode,created_at,updated_at,payload_json) values (?,?,?,?,?,?,?,?,?)', (thread,'persisted-test-project',title,'codex','full-access','default',now,now,json.dumps(payload)))
    target.execute('insert into orchestration_v2_projection_metadata values (?,?,?,?)', ('thread-projections',2,0,now))
    target.commit()
    original.close()
    target.close()
    fixture.replace(database)
(state/'client-settings.json').write_text(json.dumps({'onboardingCompletedAt': '2026-10-11T12:00:00.000Z', 'legacySidebarEnabled': False, 'sidebarWorkingShelfEnabled': False, 'panelAnimationDurationMs': 0}))
(state/'desktop-settings.json').write_text(json.dumps({'localEnvironmentEnabled': True,'mainWindowBounds':{'x':0,'y':0,'width':1100,'height':800}}))
for phase in ['native', 'add', 'restart', 'corrupt']:
    if phase == 'corrupt':
        (OUTPUT/'membership/membership.json').write_text('{broken-fixture')
    environment = os.environ.copy()
    environment.pop('ELECTRON_RUN_AS_NODE', None)
    environment.update(T3CODE_HOME=str(OUTPUT/'state'),XDG_CONFIG_HOME=str(OUTPUT/'config'),XDG_DATA_HOME=str(OUTPUT/'data'),T3CODE_DISABLE_AUTO_UPDATE='true',T3_PERSISTED_DATA_DIR=str(OUTPUT/'membership'),T3_PERSISTED_TEST_DRIVER=str(ROOT/'tests/native-driver.cjs'),T3_PERSISTED_TEST_OUTPUT=str(OUTPUT),T3_PERSISTED_TEST_PHASE=phase)
    result_file = OUTPUT / (phase + '.json')
    result_file.unlink(missing_ok=True)
    log = (OUTPUT / (phase + '.log')).open('w')
    overlay = OUTPUT / (phase + '-app')
    if overlay.exists():
        shutil.rmtree(overlay)
    process = subprocess.Popen(['/usr/bin/python3',str(ROOT/'src/patch.py'),'--destination',str(overlay),'--ozone-platform=wayland'],env=environment,stdout=log,stderr=log,start_new_session=True)
    try:
        process.wait(timeout=35)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGTERM)
        process.wait(timeout=8)
    log.close()
    if overlay.exists():
        shutil.rmtree(overlay)
    result = json.loads(result_file.read_text()) if result_file.exists() else {'error':'No result; see '+str(OUTPUT/(phase+'.log'))}
    print(phase, json.dumps({k:v for k,v in result.items() if k not in ['nativeBefore','persistedCard','body']}),flush=True)
    if not result.get('ok'):
        raise SystemExit(1)
target = sqlite3.connect(database)
for (payload,) in target.execute('select payload_json from orchestration_v2_projection_threads'):
    thread = json.loads(payload)
    assert thread['settledOverride'] is None and thread['snoozedUntil'] is None and thread['archivedAt'] is None
assert (OUTPUT/'membership/membership.json').read_text() == '{broken-fixture'
target.close()
print('Native thread lifecycle unchanged; corrupt membership preserved.', flush=True)
