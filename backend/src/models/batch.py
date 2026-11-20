from sqlalchemy import Column,Integer,String,JSON,ForeignKey
from src.config.database import Base
class Batch(Base):
 __tablename__='batches'
 id=Column(Integer,primary_key=True)
 name=Column(String(120),unique=True,nullable=False)
 source_file=Column(String(160),nullable=False)
 description=Column(String(500),nullable=False,default='')
 rows=Column(JSON,nullable=False)
 # NULL means an old, not-yet-claimed batch: administrator-only until handover.
 lab_id=Column(Integer,ForeignKey('labs.id'),nullable=True,index=True)
