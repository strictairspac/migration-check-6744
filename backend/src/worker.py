import time,logging,redis
from pathlib import Path
from src.config.settings import REDIS_URL
from src.config.database import Session
from src.models.run import Run,TargetRow
from src.services.migration import migrate,make_backup,key_digest,Cancelled
from src.services.audit import log
q=redis.Redis.from_url(REDIS_URL)
def progress(run_id,info):
 Path('/tmp/worker-heartbeat').touch()
 with Session() as s:
  r=s.get(Run,run_id)
  if r.cancel_requested or r.status=='cancelled':raise Cancelled()
  r.progress=info;s.commit()
def process_run(run_id):
 # Runs are always keyed by run_id and linked to their batch. Ownership is read
 # from the batch at query time, so a handover during execution simply makes
 # the committed target rows belong to the lab that owns the batch at the end.
 with Session() as s:
  r=s.query(Run).filter_by(id=run_id).with_for_update().first()
  if not r or r.status!='queued':return False
  r.status='running';snapshot=r.snapshot;s.commit()
 try:
  result=migrate(snapshot['batch']['rows'],snapshot['mapping']['rules'],snapshot['mapping']['chunk_size'],lambda info:progress(run_id,info))
  result['backup']=make_backup(result,run_id,snapshot['batch']['name'])
  with Session() as s:
   r=s.query(Run).filter_by(id=run_id).with_for_update().first()
   if r.cancel_requested:raise Cancelled()
   for i,row in enumerate(result['accepted_rows']):s.add(TargetRow(run_id=run_id,ordinal=i,key_digest=key_digest(row),payload=row))
   r.result=result;r.status='completed';s.commit()
  log('worker','run.completed',str(run_id));return True
 except Cancelled:
  with Session() as s:r=s.get(Run,run_id);r.status='cancelled';r.error='用户取消，未提交目标行';s.commit()
  log('worker','run.cancelled',str(run_id));return True
 except Exception as exc:
  logging.exception('migration failed')
  with Session() as s:r=s.get(Run,run_id);r.status='failed';r.error=str(exc)[:1000];s.commit()
  return False
def main():
 while True:
  Path('/tmp/worker-heartbeat').touch()
  try:
   item=q.blpop('migration-runs',timeout=2)
   if not item:continue
   process_run(int(item[1]))
  except Exception:logging.exception('worker loop');time.sleep(2)
if __name__=='__main__':main()
