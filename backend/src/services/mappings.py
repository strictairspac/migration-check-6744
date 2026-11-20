from fastapi import HTTPException
from src.config.database import Session
from src.models.batch import Batch
from src.models.mapping import Mapping
from src.services.access import batch_or_404,lock_batches
from src.utils.serialization import record

def decorate(s,row):
 data=record(row);batch=s.get(Batch,row.batch_id)
 data['lab_id']=batch.lab_id if batch else None
 data['batch_name']=batch.name if batch else None
 return data

def list_items(user):
 with Session() as s:
  q=s.query(Mapping).join(Batch,Mapping.batch_id==Batch.id)
  if user.role!='admin':
   if user.lab_id is None:return []
   q=q.filter(Batch.lab_id==user.lab_id)
  return [decorate(s,r) for r in q.order_by(Mapping.id.desc()).all()]

def save(data,user,item_id=None):
 with Session() as s:
  previous=s.get(Mapping,item_id) if item_id else None
  if item_id and not previous:raise HTTPException(404,'未找到记录')
  # Lock both the current and the target batch (ascending ids) so a handover
  # cannot slip in between the permission check and the commit, and so two
  # mapping edits cannot deadlock. Only these batch rows are locked.
  lock_batches(s,[previous.batch_id if previous else None,data.batch_id],user)
  row=s.query(Mapping).filter(Mapping.id==item_id).with_for_update().first() if item_id else Mapping()
  if item_id and (not row or row.batch_id!=previous.batch_id):raise HTTPException(409,'映射已被修改，请刷新后重试')
  for k,v in data.model_dump().items():setattr(row,k,v)
  s.add(row);s.commit();s.refresh(row);return decorate(s,row)
