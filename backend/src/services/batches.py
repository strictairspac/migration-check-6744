from fastapi import HTTPException
from src.config.database import Session
from src.models.batch import Batch
from src.models.lab import Lab
from src.services.access import batch_or_404,visible
from src.utils.serialization import record

def decorate(s,row):
 data=record(row);lab=s.get(Lab,row.lab_id) if row.lab_id else None
 data['lab_code']=lab.code if lab else None
 data['lab_name']=lab.name if lab else None
 return data

def list_items(user):
 with Session() as s:
  q=s.query(Batch)
  if user.role!='admin':
   if user.lab_id is None:return []
   q=q.filter(Batch.lab_id==user.lab_id)
  return [decorate(s,r) for r in q.order_by(Batch.id.desc()).all()]

def save(data,user,item_id=None):
 with Session() as s:
  if item_id:
   row=batch_or_404(s,item_id,user,lock=True)
  else:
   # Only administrators may create an old, unclaimed batch. A lab account
   # always creates for its own lab; one without a lab may not create at all,
   # otherwise it would leave a batch only administrators can see.
   if user.role=='admin':row=Batch()
   elif user.lab_id is None:raise HTTPException(403,'账号未分配实验室，无法登记批次')
   else:row=Batch(lab_id=user.lab_id)
  for k,v in data.model_dump().items():setattr(row,k,v)
  s.add(row);s.commit();s.refresh(row);return decorate(s,row)
