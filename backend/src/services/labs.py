from src.config.database import Session
from src.models.lab import Lab
from src.utils.serialization import record

def list_items():
 with Session() as s:return [record(r) for r in s.query(Lab).order_by(Lab.id)]
