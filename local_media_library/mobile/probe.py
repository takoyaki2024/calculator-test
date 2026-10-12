"""Explicit synthetic loopback packaging gate. Never called during normal use."""
import hashlib
from http.client import HTTPSConnection
import json
from pathlib import Path
import shutil
import ssl
import tempfile


def run_probe(fixtures, report):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage
    from ..database import Database
    from ..mobile_catalog import MobileCatalog
    from ..service import LibraryService
    from .server import MobileServer
    app = QApplication.instance() or QApplication(['mobile-probe'])
    result = dict(result='FAIL', verified_tls=False, unauthorized_denied=False, approved=False,
                  ranges=False, revoked=False, assets=False, originals_unchanged=False)
    server = None
    try:
        with tempfile.TemporaryDirectory(prefix='lml-mobile-probe-') as name:
            root = Path(name);managed=root/'data';media=root/'media';media.mkdir()
            folder=media/'synthetic-work';folder.mkdir()
            video=folder/'1.mp4';shutil.copyfile(fixtures/'baseline.mp4',video)
            image=QImage(32,32,QImage.Format.Format_RGB32);image.fill('red');image.save(str(media/'synthetic.png'))
            original=hashlib.sha256(video.read_bytes()).hexdigest()
            db=Database(managed/'library.sqlite3');service=LibraryService(db,managed_directory=managed)
            service.add_source(media,'gallery');service.scan_all()
            catalog=MobileCatalog(db);server=MobileServer(catalog,managed)
            server.start('127.0.0.1',0,testing=True)
            context=ssl.create_default_context(cadata=ssl.DER_cert_to_PEM_cert(server.ca_file.read_bytes()))
            def call(method,path,cookie='',body=None,extra=None):
                connection=HTTPSConnection('127.0.0.1',server.server.server_port,context=context,timeout=5)
                headers=dict(extra or {})
                if cookie:headers['Cookie']=cookie
                if body is not None:
                    headers['Origin']=server.server.origin;headers['Content-Type']='application/json'
                    body=json.dumps(body).encode()
                connection.request(method,path,body=body,headers=headers)
                response=connection.getresponse();output=(response.status,dict(response.getheaders()),response.read());connection.close()
                return output
            assert call('GET','/')[0]==200
            result['verified_tls']=True
            assert all(call('GET',path)[0]==200 for path in ('/app.js','/style.css'))
            result['assets']=True
            assert call('GET','/api/library')[0]==401
            result['unauthorized_denied']=True
            status,headers,body=call('POST','/api/pair',body={'code':server.auth.code})
            assert status==200 and json.loads(body)['challenge']==server.auth.pending_challenge()
            cookie=headers['Set-Cookie'].split(';')[0]
            assert call('GET','/api/library',cookie)[0]==401
            server.auth.approve(cookie.split('=', 1)[1])
            works=json.loads(call('GET','/api/library?category=video',cookie)[2])
            assert works['total']==1
            contents=json.loads(call('GET',f"/api/library?category=video&work={works['items'][0]['id']}",cookie)[2])
            item=contents['items'][0]['id'];result['approved']=True
            status,headers,body=call('GET',f'/media/video/{item}',cookie,extra={'Range':'bytes=0-99'})
            assert status==206 and body==video.read_bytes()[:100];result['ranges']=True
            server.auth.revoke()
            assert call('GET',f'/media/video/{item}',cookie)[0]==401;result['revoked']=True
            assert hashlib.sha256(video.read_bytes()).hexdigest()==original;result['originals_unchanged']=True
            server.stop();server=None
            result['result']='PASS'
    except Exception as exc:
        result['error_type']=type(exc).__name__  # never include paths, keys or raw exception text
    finally:
        if server:server.stop()
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['result']=='PASS' else 1
