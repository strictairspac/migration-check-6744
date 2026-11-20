from datetime import datetime,timezone
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from src.config.database import Session
from src.models.lab import Lab,Handover
from src.services.access import batch_or_404

def _lab_brief(lab):
 return {'id':lab.id,'code':lab.code,'name':lab.name} if lab else None

def list_items(user):
 with Session() as s:
  rows=s.query(Handover).order_by(Handover.id.desc()).limit(200).all()
  return [dict(r.result or {},handover_id=r.id,actor=r.actor,created_at=r.created_at.isoformat() if r.created_at else None) for r in rows]

def perform(data,user):
 with Session() as s:
  # A lost receipt retry carries the same request_id. Return the original
  # receipt untouched: never move the batch a second time, even if it has been
  # handed over again since.
  existing=s.query(Handover).filter_by(request_id=data.request_id).first()
  if existing:
   if existing.batch_id!=data.batch_id:raise HTTPException(409,'回执编号已用于其他批次，请使用新的回执编号')
   return dict(existing.result or {},handover_id=existing.id,replayed=True)
  # Lock only this batch row: migrations and restores for other batches, and
  # the worker's final target commit, keep running concurrently.
  batch=batch_or_404(s,data.batch_id,user,lock=True)
  target=s.get(Lab,data.to_lab_id)
  if not target:raise HTTPException(404,'未找到目标实验室')
  source=s.get(Lab,batch.lab_id) if batch.lab_id else None
  moved=batch.lab_id!=target.id
  # Whole history (mappings, runs, target rows) follows the batch, because all
  # of it is looked up through batch_id. A failed request rolls back and the
  # batch remains with its original lab.
  if moved:batch.lab_id=target.id
  receipt={'request_id':data.request_id,'batch_id':batch.id,'batch_name':batch.name,
   'from_lab':_lab_brief(source),'to_lab':_lab_brief(target),'moved':moved,'status':'completed',
   'occurred_at':datetime.now(timezone.utc).isoformat()}
  h=Handover(request_id=data.request_id,actor=user.email,batch_id=batch.id,
   from_lab_id=source.id if source else None,to_lab_id=target.id,moved=moved,result=receipt)
  s.add(h)
  try:
   s.flush()
   h.result=dict(receipt,handover_id=h.id)
   s.commit()
  except IntegrityError:
   # A concurrent request with the same request_id won the unique key.
   s.rollback()
   other=s.query(Handover).filter_by(request_id=data.request_id).first()
   if not other:raise
   return dict(other.result or {},handover_id=other.id,replayed=True)
  return h.result
