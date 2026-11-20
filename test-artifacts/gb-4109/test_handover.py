"""gb-4109 acceptance tests: lab isolation, admin handover, idempotent receipts.

Run with the embedded PostgreSQL/Redis URLs in the environment:
  JWT_SECRET=test-secret DATABASE_URL=... REDIS_URL=... python test_handover.py
"""
import os
import sys
import threading
import uuid

sys.path.insert(0, '/workspace/backend')

from fastapi.testclient import TestClient
from src.main import app
from src.config.database import Base, engine, Session
from src.config.schema import ensure_schema
from src.models.batch import Batch
from src.models.mapping import Mapping
from src.models.run import Run, TargetRow
from src.models.identity import User
from src.models.lab import Lab, Handover
from scripts.seed_demo import seed, RULES
from src.worker import process_run

PASSWORD = 'Migrate2026!'
ADMIN = 'admin@migration.local'
OP_A = 'operator@migration.local'
OP_B = 'operator.b@migration.local'
VIEW_A = 'viewer@migration.local'
VIEW_B = 'viewer.b@migration.local'


def reset():
    Base.metadata.drop_all(engine)
    ensure_schema()
    seed()


def login(client, email):
    r = client.post('/auth/login', json={'email': email, 'password': PASSWORD})
    assert r.status_code == 200, r.text
    body = r.json()
    return {'Authorization': 'Bearer ' + body['token']}, body['user']


def bid(name):
    with Session() as s:
        return s.query(Batch).filter_by(name=name).one().id


def mid(name):
    with Session() as s:
        return s.query(Mapping).filter_by(name=name).one().id


def lab_id(code):
    with Session() as s:
        return s.query(Lab).filter_by(code=code).one().id


def make_run(client, headers, mapping_name, name):
    r = client.post('/runs', json={'name': name, 'mapping_id': mid(mapping_name)}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()['id']


def test_lab_isolation():
    reset()
    c = TestClient(app)
    ah, au = login(c, ADMIN)
    oh, _ = login(c, OP_A)
    bh, _ = login(c, OP_B)

    a_batches = c.get('/batches', headers=oh).json()
    assert [b['name'] for b in a_batches] == ['见山日班检验结果'], a_batches
    b_batches = c.get('/batches', headers=bh).json()
    assert b_batches == [], b_batches
    admin_batches = c.get('/batches', headers=ah).json()
    assert len(admin_batches) == 3, admin_batches
    assert {b['lab_code'] for b in admin_batches} == {'LAB-A', None}, admin_batches
    # Old unclaimed batches are admin-only.
    assert c.get('/mappings', headers=oh).json()[0]['batch_name'] == '见山日班检验结果'
    assert c.get('/mappings', headers=bh).json() == []
    print('ok test_lab_isolation')


def test_cross_lab_access_denied():
    reset()
    c = TestClient(app)
    oh, _ = login(c, OP_A)
    bh, _ = login(c, OP_B)
    a_batch = bid('见山日班检验结果')
    a_map = mid('检验结果标准映射')
    run_id = make_run(c, oh, '检验结果标准映射', 'run-a-1')
    process_run(run_id)

    # B cannot read/modify A's batch, mapping or runs, and gets no existence leak.
    assert c.put(f'/batches/{a_batch}', headers=bh, json={
        'name': 'hijack', 'source_file': 'x', 'description': '', 'rows': []}).status_code == 404
    assert c.post('/mappings', headers=bh, json={
        'name': 'b-on-a', 'batch_id': a_batch, 'rules': RULES, 'chunk_size': 4}).status_code == 404
    assert c.post('/runs', headers=bh, json={'name': 'b-run', 'mapping_id': a_map}).status_code == 404
    for path in (f'/runs/{run_id}', f'/runs/{run_id}/targets', f'/runs/{run_id}/export',
                 f'/runs/{run_id}/backup'):
        assert c.get(path, headers=bh).status_code == 404, path
    assert c.post(f'/runs/{run_id}/cancel', headers=bh).status_code == 404
    # Missing rows also 404 for A when the id does not exist.
    assert c.get('/runs/999999', headers=oh).status_code == 404
    print('ok test_cross_lab_access_denied')


def test_handover_moves_history_and_revokes_old_session():
    reset()
    c = TestClient(app)
    ah, _ = login(c, ADMIN)
    oh, _ = login(c, OP_A)
    bh, _ = login(c, OP_B)
    a_batch = bid('见山日班检验结果')
    run_id = make_run(c, oh, '检验结果标准映射', 'run-a-history')
    process_run(run_id)
    assert c.get(f'/runs/{run_id}/backup', headers=oh).status_code == 200

    r = c.post('/handovers', headers=ah, json={
        'request_id': 'handover-' + uuid.uuid4().hex, 'batch_id': a_batch,
        'to_lab_id': lab_id('LAB-B')})
    assert r.status_code == 200, r.text
    receipt = r.json()
    assert receipt['moved'] is True and receipt['to_lab']['code'] == 'LAB-B'
    assert receipt['from_lab']['code'] == 'LAB-A'

    # The old lab's still-valid JWT can no longer list, read or download history.
    assert c.get('/batches', headers=oh).json() == []
    assert c.get('/mappings', headers=oh).json() == []
    assert c.get('/runs', headers=oh).json() == []
    for path in (f'/runs/{run_id}', f'/runs/{run_id}/targets', f'/runs/{run_id}/export',
                 f'/runs/{run_id}/backup'):
        assert c.get(path, headers=oh).status_code == 404, path
    assert c.post(f'/runs/{run_id}/cancel', headers=oh).status_code == 404

    # The new lab sees the batch plus its whole history.
    assert [b['name'] for b in c.get('/batches', headers=bh).json()] == ['见山日班检验结果']
    assert [m['name'] for m in c.get('/mappings', headers=bh).json()] == ['检验结果标准映射']
    assert [x['id'] for x in c.get('/runs', headers=bh).json()] == [run_id]
    assert c.get(f'/runs/{run_id}/backup', headers=bh).status_code == 200
    assert c.get(f'/runs/{run_id}/targets', headers=bh).json()['count'] == 12
    print('ok test_handover_moves_history_and_revokes_old_session')


def test_handover_receipt_replay_never_moves_twice():
    reset()
    c = TestClient(app)
    ah, _ = login(c, ADMIN)
    a_batch = bid('旧字段异常样本')  # old unclaimed batch, admin-only
    request_id = 'handover-' + uuid.uuid4().hex

    first = c.post('/handovers', headers=ah, json={
        'request_id': request_id, 'batch_id': a_batch, 'to_lab_id': lab_id('LAB-A')}).json()
    assert first['moved'] is True and first['from_lab'] is None
    replay = c.post('/handovers', headers=ah, json={
        'request_id': request_id, 'batch_id': a_batch, 'to_lab_id': lab_id('LAB-B')}).json()
    # Same receipt, not moved again even though the target lab changed.
    assert replay['request_id'] == request_id and replay['moved'] is True
    assert replay['to_lab']['code'] == 'LAB-A' and replay.get('replayed') is True
    with Session() as s:
        assert s.get(Batch, a_batch).lab_id == lab_id('LAB-A')
        assert s.query(Handover).filter_by(request_id=request_id).count() == 1

    # Move it onward legitimately, then replay the original receipt again.
    second = c.post('/handovers', headers=ah, json={
        'request_id': 'handover-' + uuid.uuid4().hex, 'batch_id': a_batch,
        'to_lab_id': lab_id('LAB-B')}).json()
    assert second['moved'] is True
    again = c.post('/handovers', headers=ah, json={
        'request_id': request_id, 'batch_id': a_batch, 'to_lab_id': lab_id('LAB-A')}).json()
    assert again['to_lab']['code'] == 'LAB-A' and again['replayed'] is True
    with Session() as s:
        assert s.get(Batch, a_batch).lab_id == lab_id('LAB-B')
        assert s.query(Handover).filter_by(request_id=request_id).count() == 1
    print('ok test_handover_receipt_replay_never_moves_twice')


def test_handover_failure_keeps_original_lab():
    reset()
    c = TestClient(app)
    ah, _ = login(c, ADMIN)
    oh, _ = login(c, OP_A)
    a_batch = bid('见山日班检验结果')
    bad = c.post('/handovers', headers=ah, json={
        'request_id': 'handover-' + uuid.uuid4().hex, 'batch_id': a_batch,
        'to_lab_id': 999999})
    assert bad.status_code == 404, bad.text
    missing = c.post('/handovers', headers=ah, json={
        'request_id': 'handover-' + uuid.uuid4().hex, 'batch_id': 999999,
        'to_lab_id': lab_id('LAB-A')})
    assert missing.status_code == 404
    with Session() as s:
        assert s.get(Batch, a_batch).lab_id == lab_id('LAB-A')
        assert s.query(Handover).count() == 0
    # The original lab still fully owns the batch.
    assert [b['name'] for b in c.get('/batches', headers=oh).json()] == ['见山日班检验结果']
    print('ok test_handover_failure_keeps_original_lab')


def test_handover_is_admin_only():
    reset()
    c = TestClient(app)
    oh, _ = login(c, OP_A)
    vh, _ = login(c, VIEW_A)
    body = {'request_id': 'handover-' + uuid.uuid4().hex, 'batch_id': bid('见山日班检验结果'),
            'to_lab_id': lab_id('LAB-B')}
    assert c.post('/handovers', headers=oh, json=body).status_code == 403
    assert c.post('/handovers', headers=vh, json=body).status_code == 403
    assert c.get('/handovers', headers=oh).status_code == 403
    print('ok test_handover_is_admin_only')


def test_unassigned_lab_cannot_create_batch():
    reset()
    c = TestClient(app)
    with Session() as s:
        orphan = s.query(User).filter_by(email='operator.b@migration.local').one()
        orphan.lab_id = None
        s.commit()
    bh, _ = login(c, OP_B)
    r = c.post('/batches', headers=bh, json={
        'name': 'orphan-batch', 'source_file': 'x.json', 'description': '', 'rows': []})
    assert r.status_code == 403, r.text
    with Session() as s:
        assert s.query(Batch).filter_by(lab_id=None).count() == 2  # only seeded old batches
    print('ok test_unassigned_lab_cannot_create_batch')


def test_receipt_id_cannot_cross_batches():
    reset()
    c = TestClient(app)
    ah, _ = login(c, ADMIN)
    request_id = 'handover-' + uuid.uuid4().hex
    first = c.post('/handovers', headers=ah, json={
        'request_id': request_id, 'batch_id': bid('旧字段异常样本'),
        'to_lab_id': lab_id('LAB-A')})
    assert first.status_code == 200
    clash = c.post('/handovers', headers=ah, json={
        'request_id': request_id, 'batch_id': bid('空批次验收'),
        'to_lab_id': lab_id('LAB-A')})
    assert clash.status_code == 409, clash.text
    with Session() as s:
        assert s.get(Batch, bid('空批次验收')).lab_id is None
    print('ok test_receipt_id_cannot_cross_batches')


def test_queued_migration_lands_with_current_owner():
    reset()
    c = TestClient(app)
    ah, _ = login(c, ADMIN)
    oh, _ = login(c, OP_A)
    bh, _ = login(c, OP_B)
    a_batch = bid('见山日班检验结果')
    run_id = make_run(c, oh, '检验结果标准映射', 'run-inflight')
    # Handover happens while the run is still queued ("已接单").
    c.post('/handovers', headers=ah, json={
        'request_id': 'handover-' + uuid.uuid4().hex, 'batch_id': a_batch,
        'to_lab_id': lab_id('LAB-B')})
    process_run(run_id)
    with Session() as s:
        assert s.get(Run, run_id).status == 'completed'
    assert c.get(f'/runs/{run_id}/targets', headers=bh).json()['count'] == 12
    assert c.get(f'/runs/{run_id}/targets', headers=oh).status_code == 404
    print('ok test_queued_migration_lands_with_current_owner')


def test_concurrent_handover_restore_and_other_batch_write():
    reset()
    c = TestClient(app)
    ah, au = login(c, ADMIN)
    oh, _ = login(c, OP_A)
    # Prepare a completed A run and a backup.
    a_batch = bid('见山日班检验结果')
    run_id = make_run(c, oh, '检验结果标准映射', 'run-restore')
    process_run(run_id)
    backup = c.get(f'/runs/{run_id}/backup', headers=ah).json()

    errors = []

    def do_restore():
        try:
            client = TestClient(app)
            h, _ = login(client, ADMIN)
            r = client.post(f'/runs/{run_id}/restore', headers=h, json={'backup': backup})
            assert r.status_code == 200, r.text
            assert r.json()['verified'] is True
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    def do_handover():
        try:
            client = TestClient(app)
            h, _ = login(client, ADMIN)
            r = client.post('/handovers', headers=h, json={
                'request_id': 'handover-' + uuid.uuid4().hex, 'batch_id': a_batch,
                'to_lab_id': lab_id('LAB-B')})
            assert r.status_code == 200, r.text
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    t1 = threading.Thread(target=do_restore)
    t2 = threading.Thread(target=do_handover)
    t1.start(); t2.start()
    t1.join(); t2.join()
    assert not errors, errors

    # A different batch remains writable throughout.
    other = bid('空批次验收')
    r = c.put(f'/batches/{other}', headers=ah, json={
        'name': '空批次验收', 'source_file': 'empty-results.json',
        'description': 'concurrent write ok', 'rows': []})
    assert r.status_code == 200, r.text
    # Ownership landed with B and the restored target rows followed it.
    with Session() as s:
        assert s.get(Batch, a_batch).lab_id == lab_id('LAB-B')
        assert s.query(TargetRow).filter_by(run_id=run_id).count() == 12
    bh, _ = login(c, OP_B)
    assert c.get(f'/runs/{run_id}/targets', headers=bh).json()['count'] == 12
    print('ok test_concurrent_handover_restore_and_other_batch_write')


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    for test in tests:
        test()
    print(f'\n{len(tests)} tests passed')
