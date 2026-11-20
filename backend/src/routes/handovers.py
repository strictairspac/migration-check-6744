from fastapi import APIRouter,Depends
from src.middlewares.auth import admin
from src.schemas.business import HandoverInput
from src.services import handovers,labs
from src.services.audit import log
router=APIRouter()
@router.get('/labs')
def lab_listing(u=Depends(admin)):return labs.list_items()
@router.get('/handovers')
def listing(u=Depends(admin)):return handovers.list_items(u)
@router.post('/handovers')
def create(data:HandoverInput,u=Depends(admin)):
 receipt=handovers.perform(data,u)
 log(u.email,'batch.handover',f"{receipt.get('batch_id')}:{receipt.get('request_id')}")
 return receipt
