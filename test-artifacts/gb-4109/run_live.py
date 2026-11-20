"""Start API + worker in-process, then run the live e2e scenario."""
import os, subprocess, sys, time

env = dict(os.environ, PYTHONPATH='/workspace/backend')
api = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'src.main:app', '--host', '127.0.0.1',
                        '--port', '18000'], cwd='/workspace/backend', env=env,
                       stdout=open('/tmp/gb4109/live-api.log', 'w'), stderr=subprocess.STDOUT)
worker = subprocess.Popen([sys.executable, '-m', 'src.worker'], cwd='/workspace/backend', env=env,
                          stdout=open('/tmp/gb4109/live-worker.log', 'w'), stderr=subprocess.STDOUT)
try:
    import urllib.request
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:18000/health', timeout=2); break
        except Exception: time.sleep(0.5)
    r = subprocess.run([sys.executable, '/workspace/test-artifacts/gb-4109/test_live.py'],
                       env=dict(env, BASE='http://127.0.0.1:18000'))
    sys.exit(r.returncode)
finally:
    api.terminate(); worker.terminate()
    api.wait(timeout=10); worker.wait(timeout=10)
