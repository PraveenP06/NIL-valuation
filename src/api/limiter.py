from slowapi import Limiter
from slowapi.util import get_remote_address

# Single shared limiter instance — imported by main.py and all route files.
# main.py registers this on app.state so the middleware can enforce limits.
limiter = Limiter(key_func=get_remote_address, default_limits=["200/hour"])
