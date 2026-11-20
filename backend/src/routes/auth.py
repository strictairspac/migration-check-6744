from fastapi import APIRouter,HTTPException,Depends
from src.config.database import Session
from src.models.identity import User
from src.models.lab import Lab
from src.schemas.business import Login
from src.utils.security import verify_password,token
from src.middlewares.auth import current
from src.services.audit import log
router=APIRouter()
def profile(u,lab):
 return {'email':u.email,'role':u.role,'lab_id':u.lab_id,'lab_code':lab.code if lab else None,'lab_name':lab.name if lab else None}
@router.post('/auth/login')
def login(data:Login):
 with Session() as s:
  u=s.query(User).filter_by(email=data.email).first()
  if not u or not verify_password(data.password,u.password):raise HTTPException(401,'邮箱或密码不正确')
  lab=s.get(Lab,u.lab_id) if u.lab_id else None
  body=profile(u,lab)
 log(u.email,'auth.login');return {'token':token(u),'user':body}
@router.get('/auth/me')
def me(u=Depends(current)):
 with Session() as s:return profile(u,s.get(Lab,u.lab_id) if u.lab_id else None)
