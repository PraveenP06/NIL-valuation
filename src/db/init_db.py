from connection import get_engine
from models import Base

engine = get_engine()

Base.metadata.create_all(bind=engine)

print("Tables created.")
