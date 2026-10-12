"""In-memory authorization only. No accounts, persisted bearer tokens or analytics."""
import secrets
import threading
import time


class Authorization:
    def __init__(self, clock=time.monotonic):
        self.lock = threading.RLock()
        self.clock = clock
        self.code = f'{secrets.randbelow(100000000):08d}'
        self.code_until = clock() + 300
        self.attempts = 0
        self.pending = None
        self.sessions = {}

    def pair(self, code):
        with self.lock:
            if self.attempts >= 5 or self.clock() >= self.code_until or self.pending or self.sessions:
                raise PermissionError('pairing closed')
            self.attempts += 1
            if not isinstance(code, str) or not secrets.compare_digest(code, self.code):
                raise PermissionError('invalid pairing code')
            token = secrets.token_urlsafe(32)
            challenge = f'{secrets.randbelow(10000):04d}'
            self.pending = (token, challenge, self.clock() + 120)
            return token, challenge

    def pending_challenge(self):
        with self.lock:
            if self.pending and self.pending[2] > self.clock():
                return self.pending[1]
            self.pending = None
            return None

    def approve(self):
        with self.lock:
            if not self.pending_challenge():
                raise PermissionError('pairing expired')
            token = self.pending[0]
            self.sessions[token] = self.clock() + 8 * 3600
            self.pending = None
            self.code_until = 0

    def status(self, token):
        with self.lock:
            if self.sessions.get(token, 0) > self.clock():
                return 'approved'
            if self.pending and self.pending[0] == token and self.pending_challenge():
                return 'pending'
            return 'denied'

    def revoke(self):
        with self.lock:
            self.pending = None
            self.sessions.clear()
            self.code_until = 0
