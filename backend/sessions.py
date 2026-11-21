"""Where the dialogue manager keeps each conversation's State between turns.

    REDIS_URL unset   -> MemoryStore: a dict in this process (tests, CLI, one-process demo)
    REDIS_URL=redis://redis:6379/0 -> RedisStore: State pickled into Redis with a 30-minute idle timeout,
                         so conversations survive a backend restart and several backend workers or
                         containers can serve the same patient (the proposal's "session state management").
"""
import os
import pickle

SESSION_TTL = int(os.environ.get("MEDBOOK_SESSION_TTL", 30 * 60))   # seconds of silence before a chat is forgotten


class MemoryStore(dict):
    kind = "memory"

    def save(self, sid, state):
        self[sid] = state

    def describe(self):
        return "memory"


class RedisStore:
    kind = "redis"

    def __init__(self, url, ttl=SESSION_TTL, prefix="medbook:session:"):
        import redis
        self.r = redis.Redis.from_url(url)
        self.r.ping()
        self.url, self.ttl, self.prefix = url, ttl, prefix

    def get(self, sid, default=None):
        raw = self.r.get(self.prefix + sid)
        return pickle.loads(raw) if raw else default   # only this backend writes these keys

    def save(self, sid, state):
        self.r.set(self.prefix + sid, pickle.dumps(state), ex=self.ttl)

    def pop(self, sid, default=None):
        st = self.get(sid, default)
        self.r.delete(self.prefix + sid)
        return st

    def __getitem__(self, sid):
        st = self.get(sid)
        if st is None:
            raise KeyError(sid)
        return st

    def __len__(self):
        return sum(1 for _ in self.r.scan_iter(self.prefix + "*"))

    def clear(self):
        for k in self.r.scan_iter(self.prefix + "*"):
            self.r.delete(k)

    def describe(self):
        return "redis://" + self.url.rsplit("@", 1)[-1].split("://", 1)[-1]


def make_store(url=None):
    url = url if url is not None else os.environ.get("REDIS_URL", "")
    return RedisStore(url) if url else MemoryStore()
