import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest

spec=importlib.util.spec_from_file_location('build_delta',Path('packaging/build_delta.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def inputs(tmp_path):
    before={'LocalMediaLibrary.exe':b'old synthetic app','_internal/stable.dll':b'stable',
            '_internal/removed.dll':b'removed','README.md':b'old readme'}
    after={'LocalMediaLibrary.exe':b'new synthetic app','_internal/stable.dll':b'stable',
           '_internal/new.dll':b'new dependency','README.md':b'new readme'}
    for name,files in (('before.zip',before),('after.zip',after)):
        with zipfile.ZipFile(tmp_path/name,'w') as z:
            for path,data in files.items():z.writestr('LocalMediaLibrary/'+path,data)
            z.writestr('LocalMediaLibrary/data/library.sqlite3',b'excluded synthetic management data')
    output=tmp_path/'delta.zip'
    manifest=module.build(tmp_path/'before.zip',tmp_path/'after.zip',output)
    return before,after,output,manifest


def test_delta_roundtrip_and_no_data_or_unchanged_payload(tmp_path):
    before,after,output,manifest=inputs(tmp_path)
    merged=dict(before)
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        assert not any(n.startswith('payload/data/') for n in z.namelist())
        assert 'payload/_internal/stable.dll' not in z.namelist()
        for entry in manifest['changed']:
            if entry['new_sha256']:
                data=z.read('payload/'+entry['path']);assert hashlib.sha256(data).hexdigest()==entry['new_sha256'];merged[entry['path']]=data
            else:merged.pop(entry['path'])
    assert merged==after


@pytest.mark.skipif(os.name!='nt',reason='requires real Windows PowerShell updater')
@pytest.mark.parametrize('scenario',['apply','wrong_old','damaged_payload','rollback','second_base'])
def test_windows_offline_update_and_data_preservation(tmp_path,scenario):
    before,after,output,manifest=inputs(tmp_path)
    if scenario=='second_base':
        before={**before,'LocalMediaLibrary.exe':b'other supported synthetic app'}
        alternate=tmp_path/'alternate.zip'
        with zipfile.ZipFile(alternate,'w') as z:
            for path,data in before.items():z.writestr('LocalMediaLibrary/'+path,data)
        manifest=module.build([tmp_path/'before.zip',alternate],tmp_path/'after.zip',output)
    patch=tmp_path/'patch';patch.mkdir()
    with zipfile.ZipFile(output) as z:z.extractall(patch)
    target=tmp_path/'日本語 app folder';target.mkdir()
    for path,data in before.items():
        file=target/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)
    managed=target/'data';managed.mkdir();db=managed/'library.sqlite3';db.write_bytes(b'keep DB cache and settings')
    if scenario=='wrong_old':(target/'LocalMediaLibrary.exe').write_bytes(b'unsupported synthetic version')
    if scenario=='damaged_payload':(patch/'payload/README.md').write_bytes(b'corrupt')
    if scenario=='rollback':
        script=patch/'update.ps1'
        fault="function Copy-Item { param([string]$LiteralPath,[string]$Destination,[switch]$Force) if ($LiteralPath -like '*_update-stage-*' -and $Destination -like '*README.md') { throw 'Synthetic copy failure' }; Microsoft.PowerShell.Management\\Copy-Item -LiteralPath $LiteralPath -Destination $Destination -Force:$Force }\n"
        source=script.read_text()
        script.write_text(source.replace("$ErrorActionPreference = 'Stop'","$ErrorActionPreference = 'Stop'\n"+fault))
    command=['powershell.exe','-NoProfile','-STA','-ExecutionPolicy','Bypass','-File',str(patch/'update.ps1'),'-TargetDirectory',str(target),'-NonInteractive']
    result=subprocess.run(command,capture_output=True,timeout=30)
    assert db.read_bytes()==b'keep DB cache and settings'
    if scenario in ('apply','second_base'):
        assert result.returncode==0,result.stdout.decode(errors='replace')+result.stderr.decode(errors='replace')
        for path,data in after.items():assert (target/path).read_bytes()==data
        assert not (target/'_internal/removed.dll').exists()
        backups=list(target.glob('_update-backup-*'));assert len(backups)==1
        assert (backups[0]/'LocalMediaLibrary.exe').read_bytes()==before['LocalMediaLibrary.exe']
        assert subprocess.run(command,capture_output=True,timeout=30).returncode==0
    else:
        assert result.returncode!=0
        expected=(b'Unsupported or modified old version' if scenario=='wrong_old' else
                  b'Synthetic copy failure' if scenario=='rollback' else b'Damaged update file')
        assert expected in result.stdout,result.stdout.decode(errors='replace')
        assert (target/'README.md').read_bytes()==before['README.md']
        if scenario=='rollback':
            assert b'Changed application files were restored.' in result.stdout
            for path,data in before.items():assert (target/path).read_bytes()==data
            assert not (target/'_internal/new.dll').exists()
        else:assert not list(target.glob('_update-backup-*'))
