from slowapi import Limiter
from slowapi.util import get_remote_address

# moving-window gives accurate per-minute/per-hour counts even across window
# boundaries (vs fixed-window which resets counters at the top of each period).
# moving-window works with MemoryStorage (in-memory) and Redis.
limiter = Limiter(key_func=get_remote_address, strategy="moving-window")
