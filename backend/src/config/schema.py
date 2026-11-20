from sqlalchemy import text
from src.config.database import Base,engine
from src import models  # noqa: F401  (register every table before create_all)

def ensure_schema():
 # create_all builds fresh tables; the ALTERs upgrade databases created before
 # labs and ownership existed without touching existing rows.
 Base.metadata.create_all(engine)
 with engine.begin() as c:
  c.execute(text('ALTER TABLE users ADD COLUMN IF NOT EXISTS lab_id INTEGER REFERENCES labs(id)'))
  c.execute(text('ALTER TABLE batches ADD COLUMN IF NOT EXISTS lab_id INTEGER REFERENCES labs(id)'))
  c.execute(text('CREATE INDEX IF NOT EXISTS ix_users_lab_id ON users (lab_id)'))
  c.execute(text('CREATE INDEX IF NOT EXISTS ix_batches_lab_id ON batches (lab_id)'))
