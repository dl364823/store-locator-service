from slowapi import Limiter
from slowapi.util import get_remote_address

# Single limiter instance shared across the app.
# key_func=get_remote_address extracts the client IP (checks X-Forwarded-For first).
limiter = Limiter(key_func=get_remote_address)
