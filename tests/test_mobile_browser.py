"""Real Windows Edge UI gate; actual iPhone/Safari remains a separate gate."""
import base64
import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.test_mobile import mobile


@pytest.mark.skipif(os.name!='nt',reason='uses preinstalled Windows Edge, no browser download')
def test_mobile_in_real_edge(mobile):
    from playwright.sync_api import sync_playwright
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    server,_,_=mobile
    leaf=x509.load_pem_x509_certificate((server.managed/'mobile-tls/server.pem').read_bytes())
    spki=base64.b64encode(hashlib.sha256(leaf.public_key().public_bytes(
        serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)).digest()).decode()
    failures=[];external=[]
    with sync_playwright() as p:
        # QA trusts exactly this ephemeral leaf public key, not all invalid certs.
        # Separate network tests verify installed-CA trust and rejection without it.
        browser=p.chromium.launch(channel='msedge',headless=True,args=[
            '--disable-background-networking','--no-first-run','--disable-sync',
            '--ignore-certificate-errors-spki-list='+spki])
        context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
        def route(request):
            if request.request.url.startswith(server.server.origin+'/'):request.continue_()
            else:external.append(request.request.url);request.abort()
        context.route('**/*',route)
        page=context.new_page();page.on('pageerror',lambda e:failures.append(str(e)))
        page.goto(server.server.origin)
        page.locator('#code').fill(server.auth.code);page.locator('#pairform button').click()
        page.wait_for_function("() => (document.querySelector('#pairmsg').textContent.includes('確認番号'))")
        ticket=server.auth.pending_ticket();assert ticket is not None
        server.auth.approve(ticket[0])
        page.locator('#library').wait_for(state='visible')
        page.wait_for_function("() => (document.querySelectorAll('.card').length===1)")
        page.locator('.card').first.click()
        page.wait_for_function("() => (document.querySelector('#display img')?.naturalWidth===32)")
        page.locator('#after').click()
        assert page.locator('#position').text_content()=='2 / 3'
        page.locator('#before').click()
        assert page.locator('#position').text_content()=='1 / 3'
        page.locator('#close').click();page.locator('[data-category=image]').click()
        page.wait_for_function("() => (document.querySelector('.card .name')?.textContent==='日本語')")
        page.locator('.card').click()
        page.wait_for_function("() => (document.querySelector('#display img')?.naturalWidth===32)")
        page.locator('#close').click();page.locator('[data-category=video]').click()
        page.wait_for_function("() => (document.querySelectorAll('.card').length===2)")
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        page.locator('#search').fill('作品A')
        page.wait_for_function("() => (document.querySelectorAll('.card').length===1 && document.querySelector('.card .name').textContent==='作品A')")
        page.locator('#search').fill('');page.wait_for_function("() => (document.querySelectorAll('.card').length===2)")
        page.locator('#sort').select_option('title')
        page.wait_for_function("() => (document.querySelector('.card .name')?.textContent==='作品A')")
        # Inline source test verifies title order; wait on actual committed render.
        page.locator('.card').first.click()
        page.wait_for_function("() => (document.querySelectorAll('.card').length===3)")
        assert page.locator('.card .name').all_text_contents()==['1','2','10']
        assert not page.locator('#sort').is_visible()
        page.locator('.card').first.click()
        page.wait_for_function("() => (document.querySelector('video')?.readyState>=2)")
        page.locator('video').evaluate('(v)=>{v.muted=true;return v.play()}')
        page.wait_for_function("() => (document.querySelector('video').videoWidth>0 && document.querySelector('video').currentTime>0.2)")
        page.locator('video').evaluate('(v)=>{v.pause();v.currentTime=1}')
        page.wait_for_function("() => (Math.abs(document.querySelector('video').currentTime-1)<0.2)")
        assert page.locator('video').evaluate('(v)=>v.controls && v.playsInline && v.paused')
        page.locator('#close').click()
        assert page.locator('video').count()==0
        page.locator('#backwork').click();page.wait_for_function("() => (document.querySelectorAll('.card').length===2)")
        report=Path('dist/browser-probe.json');report.parent.mkdir(exist_ok=True)
        page.screenshot(path='dist/browser-ui.png',full_page=True)
        server.auth.revoke();page.reload();page.locator('#pair').wait_for(state='visible')
        assert not page.locator('#library').is_visible()
        assert not failures,failures
        assert not external,external
        report.write_text(json.dumps(dict(result='PASS',manga_navigation=True,image_loaded=True,
            work_navigation=True,search=True,sort=True,video_decoded=True,seek_pause=True,
            mobile_width=True,revoked=True,external_asset_requests=0,page_errors=0)),encoding='utf-8')
        browser.close()
