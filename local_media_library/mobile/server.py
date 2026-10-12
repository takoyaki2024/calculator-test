"""Bounded opt-in LAN HTTPS viewer. No outbound network calls or file writes."""
import hashlib
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import ssl
import stat
import threading
import time
from urllib.parse import parse_qs, urlsplit

from .auth import Authorization
from .certificates import ensure_certificate

PRIVATE_NETS = tuple(ipaddress.IPv4Network(x) for x in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
MIME = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp',
        '.bmp': 'image/bmp', '.gif': 'image/gif', '.mp4': 'video/mp4', '.m4v': 'video/mp4',
        '.mov': 'video/quicktime', '.webm': 'video/webm', '.mkv': 'video/x-matroska', '.avi': 'video/x-msvideo'}
COOKIE = '__Host-lml'


def private_address(value, testing=False):
    address = ipaddress.IPv4Address(value)
    return any(address in network for network in PRIVATE_NETS) or (testing and value == '127.0.0.1')


def byte_range(value, size):
    if not value:
        return 0, size - 1, False
    match = re.fullmatch(r'bytes=(\d{0,20})-(\d{0,20})', value)
    if not match or size <= 0 or not any(match.groups()):
        raise ValueError('range')
    left, right = match.groups()
    if not left:
        length = int(right)
        if length <= 0:
            raise ValueError('range')
        start, end = max(0, size - length), size - 1
    else:
        start = int(left)
        end = min(int(right), size - 1) if right else size - 1
    if start >= size or start > end:
        raise ValueError('range')
    return start, end, True


def safe_open(reference, managed):
    """ID-derived reference, confined source, reject symlinks/junctions, open read-only."""
    root = reference.root
    if os.name == "nt":
        import ctypes
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(root.anchor))
        if drive_type == 4 or str(root).startswith("\\\\"):
            raise FileNotFoundError("network sources are not published")
    relative = Path(reference.relative_path)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise FileNotFoundError('unavailable')
    resolved_root = root.resolve(strict=True)
    candidate = root / relative
    if not candidate.resolve(strict=True).is_relative_to(resolved_root):
        raise FileNotFoundError('unavailable')
    if candidate.resolve(strict=True).is_relative_to(managed.resolve()):
        raise FileNotFoundError('unavailable')
    # Includes ancestors of the configured root, so replacing a source with a
    # junction/symlink after a scan cannot export a different directory.
    for path in (candidate, *candidate.parents):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise FileNotFoundError('unavailable')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(candidate, flags)
    try:
        current = os.fstat(fd)
        after = candidate.stat()
        if (not stat.S_ISREG(current.st_mode) or current.st_size != reference.size or
                current.st_mtime_ns != reference.mtime_ns or
                (current.st_dev, current.st_ino) != (after.st_dev, after.st_ino) or
                not candidate.resolve(strict=True).is_relative_to(resolved_root)):
            raise FileNotFoundError('unavailable')
        return os.fdopen(fd, 'rb')
    except BaseException:
        os.close(fd)
        raise


class BoundedServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    request_queue_size = 8

    def __init__(self, address, handler, *, context=None):
        self.context = context
        self.slots = threading.BoundedSemaphore(8)
        self.active = set()
        self.active_lock = threading.Lock()
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        raw = request
        request.settimeout(10)
        with self.active_lock:
            self.active.add(raw)
        try:
            if self.context:
                request = self.context.wrap_socket(request, server_side=True, do_handshake_on_connect=False)
                with self.active_lock:
                    self.active.discard(raw)
                    self.active.add(request)
                request.do_handshake()
            super().process_request_thread(request, client_address)
        except (OSError, ssl.SSLError):
            self.shutdown_request(request)
        finally:
            with self.active_lock:
                self.active.discard(raw)
                self.active.discard(request)
            self.slots.release()

    def handle_error(self, _request, _client_address):
        pass  # No access/error logs containing private paths, tokens or history.

    def stop(self):
        self.shutdown()
        with self.active_lock:
            for connection in tuple(self.active):
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
        self.server_close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'LocalMediaLibrary'
    sys_version = ''

    def log_message(self, *_):
        pass

    def send_error(self, code, *_):
        self.reply(code, b'Unavailable', 'text/plain; charset=utf-8')

    def reply(self, code, content=b'', mime='application/json; charset=utf-8', extra=None):
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Connection', 'close')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.close_connection = True
        if self.command != 'HEAD':
            self.wfile.write(content)

    def json_reply(self, code, value, extra=None):
        self.reply(code, json.dumps(value, ensure_ascii=False).encode('utf-8'), extra=extra)

    def token(self):
        try:
            cookie = SimpleCookie()
            cookie.load(self.headers.get('Cookie', '')[:2048])
            return cookie[COOKIE].value if COOKIE in cookie else ''
        except CookieError:
            return ''

    def valid_request(self):
        hosts = self.headers.get_all('Host', [])
        # Literal configured address, no aliases/rebinding/forwarded-host trust.
        if len(hosts) != 1 or hosts[0] != self.server.expected_host or len(self.path) > 2048:
            self.reply(400)
            return False
        if not private_address(self.client_address[0], self.server.testing):
            self.reply(403)
            return False
        if len(self.headers.get_all('Cookie', [])) > 1 or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.reply(400)
            return False
        return True

    def do_POST(self):
        if not self.valid_request():
            return
        if (self.path != '/api/pair' or self.headers.get_all('Origin', []) != [self.server.origin] or
                self.headers.get_all('Content-Type', []) != ['application/json'] or
                self.headers.get_all('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1):
            self.reply(403)
            return
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if not 1 <= length <= 256:
                raise ValueError('body')
            data = json.loads(self.rfile.read(length))
            token, challenge = self.server.auth.pair(data['code'])
            self.json_reply(200, dict(status='pending', challenge=challenge),
                            {'Set-Cookie': f'{COOKIE}={token}; Secure; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'})
        except PermissionError:
            self.json_reply(403, dict(error='接続できません。PCで接続コードを作り直してください。'))
        except (ValueError, TypeError, KeyError):
            self.reply(400)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self.valid_request():
            return
        try:
            url = urlsplit(self.path)
            if url.scheme or url.netloc or url.fragment:
                self.reply(400)
                return
            if url.path in ('/', '/app.js', '/style.css') and not url.query:
                name = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[url.path]
                mime = {'/': 'text/html', '/app.js': 'text/javascript', '/style.css': 'text/css'}[url.path]
                self.reply(200, (Path(__file__).parent / name).read_bytes(), mime + '; charset=utf-8')
                return
            status = self.server.auth.status(self.token())
            if url.path == '/api/session' and not url.query:
                self.json_reply(200, dict(status=status))
                return
            if status != 'approved':
                self.reply(401)
                return
            if url.path == '/api/library':
                args = parse_qs(url.query, max_num_fields=6, strict_parsing=True) if url.query else {}
                if any(len(v) != 1 for v in args.values()) or set(args) - {'category', 'query', 'sort', 'offset', 'work'}:
                    raise ValueError('query')
                get = lambda key, default: args.get(key, [default])[0]
                self.json_reply(200, self.server.catalog.library(get('category', 'manga'), get('query', ''),
                    get('sort', 'newest'), int(get('offset', '0')), int(get('work', '0')) if 'work' in args else None))
                return
            match = re.fullmatch(r'/(media|thumb)/(manga|image|video)/(\d{1,12})(?:/(\d{1,8}))?', url.path)
            if match and not url.query:
                route, category, item, index = match.groups()
                reference = self.server.catalog.reference(category, int(item), int(index or 0))
                if route == 'thumb':
                    with safe_open(reference, self.server.managed):
                        pass
                    source = (reference.root / reference.relative_path).resolve()
                    key = hashlib.sha256(f'{source}\0{reference.size}\0{reference.mtime_ns}'.encode('utf-8', 'surrogatepass')).hexdigest()
                    cache = self.server.managed / 'thumbnails' / (key + '.jpg')
                    if cache.is_symlink() or not cache.is_file() or cache.stat().st_size > 4 * 1024 * 1024:
                        raise FileNotFoundError('unavailable')
                    self.reply(200, cache.read_bytes(), 'image/jpeg')
                else:
                    self.stream(reference)
                return
            self.reply(404)
        except (KeyError, FileNotFoundError, PermissionError, OSError):
            if not getattr(self, '_stream_started', False):
                self.reply(404)
        except (ValueError, TypeError):
            self.reply(400)

    def stream(self, reference):
        mime = MIME.get(Path(reference.relative_path).suffix.lower())
        if mime is None:
            raise FileNotFoundError('unavailable')
        with safe_open(reference, self.server.managed) as source:
            size = os.fstat(source.fileno()).st_size
            try:
                ranges = self.headers.get_all('Range', [])
                if len(ranges) > 1:
                    raise ValueError('range')
                start, end, partial = byte_range(ranges[0] if ranges else None, size)
            except ValueError:
                self.reply(416, extra={'Content-Range': f'bytes */{size}'})
                return
            self.send_response(206 if partial else 200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(max(0, end - start + 1)))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'; sandbox")
            self.send_header('Connection', 'close')
            if partial:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            self._stream_started = True
            self.close_connection = True
            if self.command == 'HEAD':
                return
            source.seek(start)
            remaining = end - start + 1
            deadline = time.monotonic() + 3600
            token = self.token()
            while remaining > 0 and time.monotonic() < deadline and self.server.auth.status(token) == 'approved':
                chunk = source.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


class CertificateHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if (self.path != '/LocalMediaLibrary.cer' or self.headers.get_all('Host', []) != [self.server.expected_host]
                or not private_address(self.client_address[0], self.server.testing)):
            self.send_response(404)
            content = b''
        else:
            self.send_response(200)
            content = self.server.certificate
        self.send_header('Content-Type', 'application/pkix-cert')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(content)
        self.close_connection = True


class MobileServer:
    def __init__(self, catalog, managed: Path):
        self.catalog = catalog
        self.managed = managed
        self.server = None
        self.bootstrap = None
        self.bootstrap_lock = threading.RLock()
        self.auth = None

    def start(self, address, port=18766, *, testing=False):
        if self.server or not private_address(address, testing):
            raise ValueError('自宅内のIPv4アドレスを選んでください。')
        context, ca, fingerprint = ensure_certificate(self.managed / 'mobile-tls', address)
        auth = Authorization()
        server = BoundedServer((address, port), Handler, context=context)
        server.catalog, server.managed, server.auth = self.catalog, self.managed, auth
        server.testing = testing
        server.expected_host = f'{address}:{server.server_port}'
        server.origin = 'https://' + server.expected_host
        self.server, self.auth, self.ca_file, self.fingerprint = server, auth, ca, fingerprint
        self.thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.1}, daemon=True)
        self.thread.start()
        return server.origin

    def open_bootstrap(self, port=18767):
        if not self.server or self.bootstrap:
            raise ValueError('bootstrap state')
        address = self.server.server_address[0]
        server = BoundedServer((address, port), CertificateHandler)
        server.testing = self.server.testing
        server.expected_host = f'{address}:{server.server_port}'
        server.certificate = self.ca_file.read_bytes()
        self.bootstrap = server
        self.bootstrap_thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.1}, daemon=True)
        self.bootstrap_thread.start()
        self.bootstrap_timer = threading.Timer(300, self.close_bootstrap)
        self.bootstrap_timer.daemon = True
        self.bootstrap_timer.start()
        return 'http://' + server.expected_host + '/LocalMediaLibrary.cer'

    def close_bootstrap(self):
        with self.bootstrap_lock:
            server, self.bootstrap = self.bootstrap, None
            if server:
                self.bootstrap_timer.cancel()
                server.stop()
                self.bootstrap_thread.join(timeout=2)

    def stop(self):
        if self.auth:
            self.auth.revoke()
        self.close_bootstrap()
        server, self.server = self.server, None
        if server:
            server.stop()
            self.thread.join(timeout=2)
