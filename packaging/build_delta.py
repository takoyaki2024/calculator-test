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
    inputs=[before_zip] if isinstance(before_zip,(str,Path)) else list(before_zip)
    if not inputs:raise ValueError("at least one supported base required")
    bases=[files(path) for path in inputs]
    before,after=bases[0],files(after_zip)
    digest=lambda data:hashlib.sha256(data).hexdigest()
    variants=[]
    for base in bases:
        changed=[dict(path=p,old_sha256=digest(base[p]) if p in base else None,
                      new_sha256=digest(after[p]) if p in after else None)
                 for p in sorted(base.keys()|after.keys()) if base.get(p)!=after.get(p)]
        variants.append(dict(before=[dict(path=p,sha256=digest(data)) for p,data in sorted(base.items())],changed=changed))
    manifest=dict(before=variants[0]['before'],changed=variants[0]['changed'],variants=variants,
                  after=[dict(path=p,sha256=digest(data)) for p,data in sorted(after.items())])
    payload={item['path'] for variant in variants for item in variant['changed'] if item['new_sha256']}
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(payload):z.writestr('payload/'+path,after[path])
        z.writestr('manifest.json',json.dumps(manifest,indent=2))
        z.write(Path(__file__).with_name('update.ps1'),'update.ps1')
        z.writestr('更新する.cmd','@echo off\r\npowershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0update.ps1"\r\n')
        guide=Path(__file__).resolve().parents[1]/'docs/iphone-guide.md'
        z.writestr('iPhone利用手順.txt',guide.read_text(encoding='utf-8').replace('\n','\r\n').encode('utf-8-sig'))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('before',type=Path);parser.add_argument('after',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--also-from',type=Path,action='append',default=[])
    args=parser.parse_args();manifest=build([args.before,*args.also_from],args.after,args.output)
    print(json.dumps(dict(changed_files=len(manifest['changed']),zip_bytes=args.output.stat().st_size)))
