import redis
from datetime import datetime,timezone
from fastapi import HTTPException
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models.batch import Batch
from src.models.mapping import Mapping
from src.models.run import Run,TargetRow
from src.services.access import mapping_or_404,run_or_404
from src.utils.serialization import record
from src.services.migration import digest,key_digest,validate_backup
queue=redis.Redis.from_url(REDIS_URL)
def list_items(user):
 with Session() as s:
  q=s.query(Run).join(Batch,Run.batch_id==Batch.id)
  if user.role!='admin':
   if user.lab_id is None:return []
   q=q.filter(Batch.lab_id==user.lab_id)
  return [record(r) for r in q.order_by(Run.id.desc()).limit(100).all()]
def detail(item_id,user):
 with Session() as s:return record(run_or_404(s,item_id,user))
def create(data,user):
 with Session() as s:
  # Only mappings attached to a batch the caller can access may be run.
  m=mapping_or_404(s,data.mapping_id,user)
  b=s.get(Batch,m.batch_id)
  r=Run(name=data.name,batch_id=b.id,mapping_id=m.id,status='queued',snapshot={'batch':record(b),'mapping':record(m)})
  s.add(r);s.commit();s.refresh(r);result=record(r)
 try:queue.rpush('migration-runs',result['id'])
 except redis.RedisError:
  with Session() as s:r=s.get(Run,result['id']);r.status='failed';r.error='队列不可用，请创建新任务';s.commit()
  raise HTTPException(503,'队列不可用，请稍后重试')
 return result
def cancel(item_id,user):
 with Session() as s:
  r=run_or_404(s,item_id,user,lock=True)
  if r.status not in ('queued','running'):raise HTTPException(409,'运行已终止，无法取消')
  r.cancel_requested=True
  if r.status=='queued':r.status='cancelled'
  s.commit();return record(r)
def targets(item_id,user):
 detail(item_id,user)
 with Session() as s:rows=[r.payload for r in s.query(TargetRow).filter_by(run_id=item_id).order_by(TargetRow.ordinal)]
 return {'rows':rows,'count':len(rows),'checksum':digest(rows)}
def backup(item_id,user):
 r=detail(item_id,user)
 if r['status']!='completed':raise HTTPException(409,'仅完成运行可以备份')
 return r['result']['backup']
def restore(item_id,user,data):
 with Session() as s:
  r=run_or_404(s,item_id,user,lock=True)
  if r.status!='completed':raise HTTPException(409,'仅完成运行可以恢复')
  try:rows=validate_backup(data.backup,r.result['checksum'],item_id)
  except ValueError as e:raise HTTPException(422,str(e))
  before=s.query(TargetRow).filter_by(run_id=item_id).count()
  s.query(TargetRow).filter_by(run_id=item_id).delete()
  for i,row in enumerate(rows):s.add(TargetRow(run_id=item_id,ordinal=i,key_digest=key_digest(row),payload=row))
  s.flush()
  actual=[x.payload for x in s.query(TargetRow).filter_by(run_id=item_id).order_by(TargetRow.ordinal)]
  proof={'restored_at':datetime.now(timezone.utc).isoformat(),'previous_count':before,'restored_count':len(actual),'checksum':digest(actual),'verified':digest(actual)==r.result['checksum']}
  if not proof['verified']:raise HTTPException(409,'恢复后校验失败，已回滚')
  r.recovery=(r.recovery or [])+[proof];s.commit();return proof
