from src.config.database import Base,engine,Session
from src.config.schema import ensure_schema
from src.models.identity import User,Audit
from src.models.batch import Batch
from src.models.mapping import Mapping
from src.models.run import Run,TargetRow
from src.models.lab import Lab,Handover
from src.utils.security import hash_password
RULES=[{'source':a,'target':b,'type':c,'required':True} for a,b,c in [('委托号','sample_code','text'),('检测项','test_name','text'),('结果','result_value','decimal'),('单位','unit','text'),('时间','measured_at','datetime')]]
LABS=[('LAB-A','检验一室'),('LAB-B','检验二室')]
ACCOUNTS=[('admin','admin',None),('operator','operator','LAB-A'),('viewer','viewer','LAB-A'),('operator.b','operator','LAB-B'),('viewer.b','viewer','LAB-B')]
def seed():
 ensure_schema()
 with Session() as s:
  for code,name in LABS:
   if not s.query(Lab).filter_by(code=code).first():s.add(Lab(code=code,name=name))
  s.flush()
  for prefix,role,lab_code in ACCOUNTS:
   email=prefix+'@migration.local'
   if not s.query(User).filter_by(email=email).first():
    s.add(User(email=email,role=role,password=hash_password('Migrate2026!'),lab_id=s.query(Lab).filter_by(code=lab_code).one().id if lab_code else None))
   elif lab_code and s.query(User).filter_by(email=email).one().lab_id is None:
    s.query(User).filter_by(email=email).one().lab_id=s.query(Lab).filter_by(code=lab_code).one().id
  good=[{'委托号':f'JS-20261117-{i:03d}','检测项':'拉伸强度','结果':str(420+i/10),'单位':'MPa','时间':'2026-11-17T09:00:00+08:00'} for i in range(1,13)]
  bad=[good[0],{'委托号':'JS-BAD-01','检测项':'拉伸强度','结果':'四百二十','单位':'MPa','时间':'2026-11-17T09:00:00+08:00'},{'委托号':'JS-BAD-02','检测项':'拉伸强度','结果':None,'单位':'MPa','时间':'2026-11-17T09:00:00+08:00'},{'委托号':'JS-BAD-03','检测项':'拉伸强度','结果':'430','时间':'2026-11-17T09:00:00+08:00'}]
  # The first batch already belongs to lab A. The other two are old, unclaimed
  # batches: only the administrator sees them until an explicit handover.
  seeds=[('见山日班检验结果',good,'lab-results-20261117.json','12条正常检测结果','LAB-A'),('旧字段异常样本',good[:2]+bad,'legacy-edge-20261117.json','重复自然键、非法数字、空值与缺列',None),('空批次验收',[],'empty-results.json','空输入可完成备份与恢复',None)]
  for name,rows,file,desc,lab_code in seeds:
   if not s.query(Batch).filter_by(name=name).first():
    s.add(Batch(name=name,rows=rows,source_file=file,description=desc,lab_id=s.query(Lab).filter_by(code=lab_code).one().id if lab_code else None))
  s.flush()
  for i,(name,_,_,_,_) in enumerate(seeds):
   mname=['检验结果标准映射','异常隔离复核映射','空批次映射'][i]
   if not s.query(Mapping).filter_by(name=mname).first():s.add(Mapping(name=mname,batch_id=s.query(Batch).filter_by(name=name).one().id,rules=RULES,chunk_size=4,note='sample_code + test_name 为自然键'))
  s.commit();counts={m.__tablename__:s.query(m).count() for m in (User,Batch,Mapping,Run,TargetRow,Lab,Handover)};print(counts);return counts
if __name__=='__main__':seed()
