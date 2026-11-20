from fastapi import HTTPException
from src.config.database import Session
from src.models.batch import Batch
from src.models.mapping import Mapping
from src.models.run import Run

def visible(batch,user):
 # Administrators see every batch, including old batches not yet claimed by a
 # lab. Everyone else sees only batches currently owned by their own lab.
 return user.role=='admin' or (user.lab_id is not None and batch.lab_id==user.lab_id)

def batch_or_404(s,batch_id,user,lock=False):
 q=s.query(Batch).filter(Batch.id==batch_id)
 if lock:q=q.with_for_update()
 batch=q.first()
 if not batch or not visible(batch,user):raise HTTPException(404,'未找到记录')
 return batch

def mapping_or_404(s,mapping_id,user):
 mapping=s.get(Mapping,mapping_id)
 if not mapping or not batch_or_404(s,mapping.batch_id,user):raise HTTPException(404,'未找到记录')
 return mapping

def run_or_404(s,run_id,user,lock=False):
 # Lock order is always batch first, then run, matching handover and mapping
 # edits. This closes the race where a cancel reads old ownership while a
 # handover is committing.
 run=s.get(Run,run_id)
 if not run or not batch_or_404(s,run.batch_id,user,lock=lock):raise HTTPException(404,'未找到对账运行')
 if lock:
  run=s.query(Run).filter(Run.id==run_id).with_for_update().first()
  if not run or not visible(s.get(Batch,run.batch_id),user):raise HTTPException(404,'未找到对账运行')
 return run

def lock_batches(s,batch_ids,user):
 # Lock only the named batch rows, always in ascending id order so concurrent
 # edits/handovers cannot deadlock. Other batches remain fully writable.
 for batch_id in sorted({b for b in batch_ids if b is not None}):
  batch_or_404(s,batch_id,user,lock=True)
