"""Real verified TLS and read-only synthetic-media integration, not mock HTTP."""
import hashlib
from http.client import HTTPSConnection, HTTPConnection
import json
from pathlib import Path
import shutil
import socket
import ssl

import pytest
from PySide6.QtGui import QImage

from local_media_library.database import Database
from local_media_library.mobile_catalog import MobileCatalog, FileReference
from local_media_library.service import LibraryService
from local_media_library.mobile.auth import Authorization
from local_media_library.mobile.server import MobileServer, byte_range, safe_open, private_address
from local_media_library.thumbnails import ThumbnailCache


@pytest.fixture
def mobile(tmp_path, qapp):
    managed = tmp_path / 'data'
    db = Database(managed / 'library.sqlite3')
    service = LibraryService(db, managed_directory=managed)
    manga, gallery = tmp_path / '漫画', tmp_path / '画像と動画'
    manga.mkdir(); gallery.mkdir()
    image = QImage(32, 32, QImage.Format.Format_RGB32); image.fill('red')
    for name in ('10.png', '2.png', '1.png'):
        image.save(str(manga / name))
    image.save(str(gallery / '日本語.png'))
    for work in ('作品A', '作品B'):
        folder = gallery / work; folder.mkdir()
        for number in (1, 2, 10):
            shutil.copyfile('tests/fixtures/baseline.mp4', folder / f'{number}.mp4')
    service.add_source(manga, 'manga');service.add_source(gallery, 'gallery');service.scan_all()
    catalog = MobileCatalog(db)
    cache = ThumbnailCache(managed / 'thumbnails')
    original = catalog.images.list()[0]
    cache.image(original.path, original.size, original.mtime_ns)
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for root in (manga, gallery) for p in root.rglob('*') if p.is_file()}
    server = MobileServer(catalog, managed)
    server.start('127.0.0.1', 0, testing=True)
    ca_der = server.ca_file.read_bytes()
    context = ssl.create_default_context(cadata=ssl.DER_cert_to_PEM_cert(ca_der))
    yield server, context, hashes
    server.stop()
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p,h in hashes.items())


def call(mobile, method, path, *, cookie=None, data=None, headers=None):
    server, context, _ = mobile
    connection = HTTPSConnection('127.0.0.1', server.server.server_port, context=context, timeout=5)
    values = dict(headers or {})
    if cookie: values['Cookie'] = cookie
    if data is not None:
        values.setdefault('Origin', server.server.origin)
        values.setdefault('Content-Type','application/json')
        data = json.dumps(data).encode()
    connection.request(method, path, body=data, headers=values)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def approve(mobile):
    server, _, _ = mobile
    status, headers, body = call(mobile, 'POST', '/api/pair', data={'code':server.auth.code})
    assert status == 200
    assert json.loads(body)['challenge'] == server.auth.pending_challenge()
    cookie = headers['Set-Cookie'].split(';')[0]
    assert 'Secure; HttpOnly; SameSite=Strict' in headers['Set-Cookie']
    assert call(mobile, 'GET', '/api/library', cookie=cookie)[0] == 401
    server.auth.approve(cookie.split('=', 1)[1])
    return cookie


def test_tls_auth_readonly_catalog_and_revoke(mobile):
    server, _, _ = mobile
    assert call(mobile, 'GET', '/')[0] == 200
    assert call(mobile, 'GET', '/api/library')[0] == 401
    cookie = approve(mobile)
    status, headers, body = call(mobile, 'GET', '/api/library?category=video', cookie=cookie)
    catalog = json.loads(body)
    assert status == 200 and catalog['total'] == 2
    assert b'relative_path' not in body and str(server.managed).encode() not in body
    assert headers['Cache-Control'] == 'no-store'
    assert headers['Content-Security-Policy'].startswith("default-src 'none'")
    work = catalog['items'][0]['id']
    videos = json.loads(call(mobile, 'GET', f'/api/library?category=video&work={work}', cookie=cookie)[2])
    assert [v['title'] for v in videos['items']] == ['1', '2', '10']
    video = videos['items'][0]['id']
    reference = server.catalog.reference('video',video)
    expected = (reference.root/reference.relative_path).read_bytes()
    response = call(mobile,'GET',f'/media/video/{video}',cookie=cookie,headers={'Range':'bytes=0-99'})
    assert response[0] == 206 and response[2] == expected[:100]
    assert response[1]['Content-Range'] == f'bytes 0-99/{len(expected)}'
    assert call(mobile,'HEAD',f'/media/video/{video}',cookie=cookie)[2] == b''
    server.auth.revoke()
    assert call(mobile,'GET',f'/media/video/{video}',cookie=cookie)[0] == 401


def test_real_images_manga_search_thumbnail_and_missing(mobile):
    server, _, _ = mobile
    cookie = approve(mobile)
    from urllib.parse import urlencode
    data = json.loads(call(mobile,'GET','/api/library?'+urlencode({'category':'image','query':'日本語'}),cookie=cookie)[2])
    assert data['total'] == 1
    item = data['items'][0]
    assert call(mobile,'GET',item['thumb'],cookie=cookie)[0] == 200
    assert call(mobile,'GET',f"/media/image/{item['id']}",cookie=cookie)[2].startswith(b'\x89PNG')
    mangas = json.loads(call(mobile,'GET','/api/library?category=manga',cookie=cookie)[2])
    work = mangas['items'][0]['id']
    assert mangas['items'][0]['count'] == 3
    assert [server.catalog.reference('manga',work,i).relative_path for i in range(3)] == ['1.png','2.png','10.png']
    assert call(mobile,'GET',f'/media/manga/{work}/1',cookie=cookie)[0] == 200
    assert call(mobile,'GET',f'/media/manga/{work}/3',cookie=cookie)[0] == 404
    # Changing a source fingerprint after scanning is withheld, not streamed.
    ref = server.catalog.reference('image',item['id'])
    from dataclasses import replace
    with pytest.raises(FileNotFoundError):
        safe_open(replace(ref,size=ref.size+1),server.managed)


def test_host_origin_methods_paths_and_range(mobile):
    cookie = approve(mobile)
    assert call(mobile,'GET','/api/library',cookie=cookie,headers={'Host':'evil.invalid'})[0] == 400
    assert call(mobile,'POST','/api/pair',data={'code':'00000000'},headers={'Origin':'https://evil.invalid'})[0] == 403
    assert call(mobile,'POST','/api/delete',cookie=cookie,data={})[0] == 403
    assert call(mobile,'DELETE','/media/image/1',cookie=cookie)[0] == 501
    for path in ('/media/image/../../data/library.sqlite3','/media/image/%2e%2e/server-key.pem','/server-key.pem','/data/library.sqlite3','/media/image/999999','/api/library?category=image&sort=malicious'):
        assert call(mobile,'GET',path,cookie=cookie)[0] in (400,404)
    video = mobile[0].catalog.videos.list()[0]
    for value in ('bytes=99999999999-', 'bytes=0-1,2-3','bytes=-0','bytes=5-3','items=1-2'):
        assert call(mobile,'GET',f'/media/video/{video.id}',cookie=cookie,headers={'Range':value})[0] == 416
    assert call(mobile,'GET',f'/media/video/{video.id}',cookie=cookie,headers={'Range':'bytes=-10'})[2] == video.path.read_bytes()[-10:]


def test_certificate_bootstrap_exports_only_public_certificate_and_stop(mobile):
    server,_,_ = mobile
    url = server.open_bootstrap(0)
    port = server.bootstrap.server_port
    for path, expected in (('/LocalMediaLibrary.cer',200),('/api/library',404),('/server-key.pem',404),('/LocalMediaLibrary.cer?path=server-key.pem',404)):
        client = HTTPConnection('127.0.0.1',port,timeout=5);client.request('GET',path)
        response=client.getresponse();body=response.read();client.close()
        assert response.status==expected
        if expected==200: assert body==server.ca_file.read_bytes()
        else: assert not body
    server.close_bootstrap()
    with pytest.raises(OSError): socket.create_connection(('127.0.0.1',port),timeout=1)
    secure_port=server.server.server_port
    server.stop()
    with pytest.raises(OSError): socket.create_connection(('127.0.0.1',secure_port),timeout=1)


def test_authorization_deadlines_limits_and_unapproved_tokens():
    now=[0];auth=Authorization(lambda:now[0])
    for _ in range(5):
        with pytest.raises(PermissionError):auth.pair('not the code')
    with pytest.raises(PermissionError):auth.pair(auth.code)
    auth=Authorization(lambda:now[0]);token,challenge=auth.pair(auth.code)
    assert auth.status(token)=='pending' and auth.status('made-up')=='denied'
    now[0]=121
    with pytest.raises(PermissionError):auth.approve(token)
    now[0]=0;auth=Authorization(lambda:now[0]);token,_=auth.pair(auth.code);auth.approve(token)
    now[0]=8*3600+1
    assert auth.status(token)=='denied'
    now[0]=0;auth=Authorization(lambda:now[0]);now[0]=301
    with pytest.raises(PermissionError):auth.pair(auth.code)


def test_safe_open_rejects_symlinks_escape_and_management(tmp_path):
    root=tmp_path/'root';root.mkdir();file=root/'a.mp4';file.write_bytes(b'synthetic')
    managed=tmp_path/'data';managed.mkdir();secret=managed/'key.mp4';secret.write_bytes(b'secret')
    def ref(root,relative):
        path=root/relative; info=path.stat();return FileReference(root,str(relative),info.st_size,info.st_mtime_ns,'video')
    with pytest.raises(FileNotFoundError):safe_open(ref(root,'../data/key.mp4'),managed)
    with pytest.raises(FileNotFoundError):safe_open(ref(managed,'key.mp4'),managed)
    link=root/'link.mp4'
    try:link.symlink_to(file)
    except OSError:pytest.skip('Windows account cannot create symlinks')
    with pytest.raises(FileNotFoundError):safe_open(ref(root,'link.mp4'),managed)


def test_rfc1918_only_and_certificate_reuse(mobile):
    for value in ('0.0.0.0','8.8.8.8','169.254.1.1','127.0.0.1','192.0.2.1'):
        assert not private_address(value)
    for value in ('10.1.2.3','192.168.1.2','172.16.0.1'):assert private_address(value)
    server,_,_=mobile
    from local_media_library.mobile.certificates import ensure_certificate
    _,certificate,fingerprint=ensure_certificate(server.managed/'mobile-tls','127.0.0.1')
    assert fingerprint==server.fingerprint and certificate.read_bytes()==server.ca_file.read_bytes()
    assert not (certificate.parent/'ca-key.pem').exists()
    # Untrusted client cannot silently downgrade/accept a self-signed chain.
    client=HTTPSConnection('127.0.0.1',server.server.server_port,context=ssl.create_default_context(),timeout=5)
    with pytest.raises(ssl.SSLError):client.request('GET','/')
    client.close()


def test_off_by_default_desktop_lazy_mobile(tmp_path,qapp,monkeypatch):
    from local_media_library.window import MainWindow
    from local_media_library.paths import AppPaths
    from local_media_library.mobile.server import BoundedServer
    binds=[]
    original=BoundedServer.server_bind
    def capture(self):binds.append(self.server_address);return original(self)
    monkeypatch.setattr(BoundedServer,'server_bind',capture)
    window=MainWindow(AppPaths(tmp_path));qapp.processEvents()
    assert window.mobile_settings is None and not binds
    window.show_mobile_settings();qapp.processEvents()
    assert window.mobile_settings.controller.server is None and not binds
    window.close()


def test_bounded_handshake_clients_and_clean_shutdown(mobile):
    from tests.test_ui import wait_until
    server,_,_=mobile
    clients=[]
    try:
        for _ in range(8):
            clients.append(socket.create_connection(('127.0.0.1',server.server.server_port),timeout=2))
        assert wait_until(lambda:len(server.server.active)==8,timeout_ms=2000)
        extra=socket.create_connection(('127.0.0.1',server.server.server_port),timeout=2)
        extra.settimeout(2)
        assert extra.recv(1)==b''
        extra.close()
        old=server.server
        server.stop()
        assert wait_until(lambda:not old.active,timeout_ms=2000)
    finally:
        for client in clients:client.close()


def test_cross_site_get_and_catalog_bounded_pages(mobile):
    cookie=approve(mobile)
    assert call(mobile,'GET','/api/library',cookie=cookie,headers={'Sec-Fetch-Site':'cross-site'})[0]==400
    assert call(mobile,'GET','/api/library?category=image&category=video',cookie=cookie)[0]==400
    assert call(mobile,'GET','/api/library?category=image&offset=-1',cookie=cookie)[0]==400
    page=json.loads(call(mobile,'GET','/api/library?category=image&offset=24',cookie=cookie)[2])
    assert page['items']==[] and page['total']==1


def test_desktop_approval_cannot_authorize_a_replacement_request(tmp_path,qapp):
    from local_media_library.mobile.settings import MobileSettings
    now=[0];auth=Authorization(lambda:now[0])
    first,_=auth.pair(auth.code)
    db=Database(tmp_path/'data/library.sqlite3')
    widget=MobileSettings(db,tmp_path/'data')
    widget.controller.auth=auth;widget.controller.server=object()
    widget.origin='https://127.0.0.1:18766';widget.poll()
    now[0]=121;auth.pending_challenge()
    replacement,_=auth.pair(auth.code)
    # User clicks based on the old displayed request before the next GUI poll.
    widget.approve()
    assert auth.status(replacement)=='pending'
    assert auth.status(first)=='denied'
    widget.controller.server=None;widget.close()


@pytest.mark.parametrize('damage',['private_key','wrong_ca'])
def test_certificate_recovers_from_interrupted_or_mixed_bundle(tmp_path,damage):
    from local_media_library.mobile.certificates import ensure_certificate
    from cryptography import x509
    directory=tmp_path/'certificates'
    _,ca_file,old_fingerprint=ensure_certificate(directory,'127.0.0.1')
    if damage=='private_key':
        (directory/'server-key.pem').write_bytes(b'interrupted synthetic key write')
    else:
        _,other_ca,_=ensure_certificate(tmp_path/'other','127.0.0.1')
        ca_file.write_bytes(other_ca.read_bytes())
    _,ca_file,fingerprint=ensure_certificate(directory,'127.0.0.1')
    leaf=x509.load_pem_x509_certificate((directory/'server.pem').read_bytes())
    ca=x509.load_der_x509_certificate(ca_file.read_bytes())
    leaf.verify_directly_issued_by(ca)
    assert fingerprint!=old_fingerprint


@pytest.mark.parametrize('target',['original.mp4','existing.cer','new.cer'])
def test_export_certificate_cannot_overwrite_originals(tmp_path,qapp,monkeypatch,target):
    from local_media_library.mobile.settings import MobileSettings
    from PySide6.QtWidgets import QFileDialog,QMessageBox
    db=Database(tmp_path/'data/library.sqlite3');widget=MobileSettings(db,tmp_path/'data')
    ca=tmp_path/'public.cer';ca.write_bytes(b'synthetic public certificate');widget.controller.ca_file=ca
    path=tmp_path/target
    if target!='new.cer':path.write_bytes(b'preserve original')
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(path),''))
    warnings=[];monkeypatch.setattr(QMessageBox,'warning',lambda *a:warnings.append(a))
    widget.export_certificate()
    if target=='new.cer':assert path.read_bytes()==ca.read_bytes() and not warnings
    else:assert path.read_bytes()==b'preserve original' and len(warnings)==1
    widget.close()
