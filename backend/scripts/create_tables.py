from sqlalchemy import inspect

import models  # noqa: F401  (registers every table on Base.metadata)
from database import Base, engine

Base.metadata.create_all(engine)
print("tables:", sorted(t for t in inspect(engine).get_table_names() if t in Base.metadata.tables))
