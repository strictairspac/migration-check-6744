"""Live end-to-end check against a running uvicorn + worker."""
import json, os, sys, threading, time, urllib.error, urllib.request, uuid

BASE = os.environ.get('BASE', 'http://127.0.0.1:18000')
PW = 'Migrate2026!'


def call(method, path, token=None, body=None, raw=False):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = r.read()
            return r.status, (payload if raw else json.loads(payload or b'null'))
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except Exception:
            return e.code, payload


def login(email):
    st, body = call('POST', '/auth/login', body={'email': email, 'password': PW})
    assert st == 200, (st, body)
    return body['token'], body['user']


def wait_status(token, run_id, want, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st, run = call('GET', f'/runs/{run_id}', token)
        if st == 200 and run['status'] == want:
            return run
        time.sleep(0.3)
    raise AssertionError(f'run {run_id} never reached {want}: {run}')


def main():
    admin, _ = login('admin@migration.local')
    op_a, ua = login('operator@migration.local')
    op_b, ub = login('operator.b@migration.local')
    assert ua['lab_code'] == 'LAB-A' and ub['lab_code'] == 'LAB-B'

    st, batches = call('GET', '/batches', admin)
    assert st == 200
    by_name = {b['name']: b for b in batches}
    a_batch = by_name['见山日班检验结果']
    assert a_batch['lab_code'] == 'LAB-A'
    assert by_name['旧字段异常样本']['lab_code'] is None
    st, labs = call('GET', '/labs', admin)
    lab_b = next(l for l in labs if l['code'] == 'LAB-B')['id']

    # A lists only its own lab.
    st, a_list = call('GET', '/batches', op_a)
    assert [b['name'] for b in a_list] == ['见山日班检验结果']
    st, b_list = call('GET', '/batches', op_b)
    assert b_list == []

    # Start a run as A and let the real worker finish it.
    st, maps = call('GET', '/mappings', op_a)
    mapping = maps[0]
    name = 'live-run-' + uuid.uuid4().hex[:8]
    st, run = call('POST', '/runs', op_a, {'name': name, 'mapping_id': mapping['id']})
    assert st == 200, (st, run)
    wait_status(op_a, run['id'], 'completed')
    st, backup = call('GET', f"/runs/{run['id']}/backup", op_a, raw=False)
    assert st == 200 and backup['rows'], backup
    print('worker completed run', run['id'])

    # Concurrent handover + restore + unrelated write.
    errs = []
    def handover():
        try:
            st, body = call('POST', '/handovers', admin, {
                'request_id': 'live-' + uuid.uuid4().hex, 'batch_id': a_batch['id'],
                'to_lab_id': lab_b})
            assert st == 200, (st, body)
        except Exception as e: errs.append(('handover', e))
    def restore():
        try:
            st, body = call('POST', f"/runs/{run['id']}/restore", admin, {'backup': backup})
            assert st == 200 and body['verified'], (st, body)
        except Exception as e: errs.append(('restore', e))
    def unrelated():
        try:
            st, body = call('GET', '/batches', admin)
            assert st == 200
        except Exception as e: errs.append(('read', e))
    ts = [threading.Thread(target=f) for f in (handover, restore, unrelated, handover)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errs, errs

    # A's existing session is revoked for the moved batch; B now sees everything.
    st, a_after = call('GET', '/batches', op_a)
    assert a_after == [], a_after
    st, _ = call('GET', f"/runs/{run['id']}/backup", op_a)
    assert st == 404, st
    st, b_after = call('GET', '/mappings', op_b)
    assert any(m['batch_id'] == a_batch['id'] for m in b_after), b_after
    st, t = call('GET', f"/runs/{run['id']}/targets", op_b)
    assert st == 200 and t['count'] == 12, (st, t)
    print('handover revoked old session and moved history; targets intact')

    # Receipt replay after another move does not move it back.
    rid = 'live-' + uuid.uuid4().hex
    st, first = call('POST', '/handovers', admin, {
        'request_id': rid, 'batch_id': by_name['旧字段异常样本']['id'], 'to_lab_id': 1})
    assert st == 200 and first['moved'], (st, first)
    st, replay = call('POST', '/handovers', admin, {
        'request_id': rid, 'batch_id': by_name['旧字段异常样本']['id'], 'to_lab_id': 2})
    assert st == 200 and replay['to_lab']['code'] == 'LAB-A' and replay.get('replayed'), replay
    st, onward = call('POST', '/handovers', admin, {
        'request_id': 'live-' + uuid.uuid4().hex, 'batch_id': by_name['旧字段异常样本']['id'], 'to_lab_id': 2})
    assert st == 200 and onward['moved'], (st, onward)
    st, again = call('POST', '/handovers', admin, {
        'request_id': rid, 'batch_id': by_name['旧字段异常样本']['id'], 'to_lab_id': 1})
    assert again['to_lab']['code'] == 'LAB-A' and again.get('replayed'), again
    st, batches2 = call('GET', '/batches', admin)
    moved = {b['name']: b for b in batches2}['旧字段异常样本']
    assert moved['lab_code'] == 'LAB-B', moved
    print('receipt replay never moved the batch again')

    # Failed handover keeps original ownership (bad target lab).
    st, miss = call('POST', '/handovers', admin, {
        'request_id': 'live-' + uuid.uuid4().hex, 'batch_id': a_batch['id'], 'to_lab_id': 9999})
    assert st == 404, (st, miss)
    assert call('GET', f"/runs/{run['id']}/targets", op_b)[0] == 200
    print('failed handover leaves ownership unchanged')
    print('\nlive e2e ok')


if __name__ == '__main__':
    main()
