from sqlalchemy import Column,Integer,String,JSON,DateTime,func,ForeignKey,Boolean
from src.config.database import Base

class Lab(Base):
 __tablename__='labs'
 id=Column(Integer,primary_key=True)
 code=Column(String(60),unique=True,nullable=False)
 name=Column(String(120),unique=True,nullable=False)
 created_at=Column(DateTime,server_default=func.now())

class Handover(Base):
 __tablename__='handovers'
 id=Column(Integer,primary_key=True)
 request_id=Column(String(128),unique=True,nullable=False)
 actor=Column(String(120),nullable=False,default='')
 batch_id=Column(Integer,ForeignKey('batches.id'),nullable=False,index=True)
 from_lab_id=Column(Integer,ForeignKey('labs.id'),nullable=True)
 to_lab_id=Column(Integer,ForeignKey('labs.id'),nullable=False)
 moved=Column(Boolean,nullable=False,default=False)
 result=Column(JSON,nullable=False)
 created_at=Column(DateTime,server_default=func.now())
