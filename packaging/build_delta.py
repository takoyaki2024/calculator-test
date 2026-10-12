"""Offline changed-app-files update builder; never accepts/sends management data."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def files(archive):
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('damaged input ZIP')
        result={}
        for name in z.namelist():
            parts=PurePosixPath(name).parts
            if not parts or parts[0]!='LocalMediaLibrary' or '..' in parts:
                raise ValueError('unexpected package layout')
            if len(parts)==1 or name.endswith('/') or parts[1]=='data':continue
            relative='/'.join(parts[1:])
            if relative in result:raise ValueError('duplicate package path')
            result[relative]=z.read(name)
        if 'LocalMediaLibrary.exe' not in result:raise ValueError('missing executable')
        return result


def build(before_zip,after_zip,output):
    before,after=files(before_zip),files(after_zip)
    digest=lambda data:hashlib.sha256(data).hexdigest()
    changed=[dict(path=p,old_sha256=digest(before[p]) if p in before else None,
                  new_sha256=digest(after[p]) if p in after else None)
             for p in sorted(before.keys()|after.keys()) if before.get(p)!=after.get(p)]
    manifest=dict(before=[dict(path=p,sha256=digest(data)) for p,data in sorted(before.items())],
                  after=[dict(path=p,sha256=digest(data)) for p,data in sorted(after.items())],changed=changed)
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for item in changed:
            if item['new_sha256']:z.writestr('payload/'+item['path'],after[item['path']])
        z.writestr('manifest.json',json.dumps(manifest,indent=2))
        z.write(Path(__file__).with_name('update.ps1'),'update.ps1')
        z.writestr('更新する.cmd','@echo off\r\npowershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0update.ps1"\r\n')
        guide=Path(__file__).resolve().parents[1]/'docs/iphone-guide.md'
        z.writestr('iPhone利用手順.txt',guide.read_text(encoding='utf-8').replace('\n','\r\n').encode('utf-8-sig'))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('before',type=Path);parser.add_argument('after',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();manifest=build(args.before,args.after,args.output)
    print(json.dumps(dict(changed_files=len(manifest['changed']),zip_bytes=args.output.stat().st_size)))
