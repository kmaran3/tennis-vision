"""Download and verify a pinned public serving asset during the image build."""
import argparse
import hashlib
import json
from pathlib import Path,PurePosixPath
import shutil
import tarfile
import tempfile
from urllib.request import Request,urlopen


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def extract(archive,target,expected):
    if digest(archive)!=expected['sha256']:raise ValueError('Serving asset checksum mismatch')
    target=Path(target)
    if target.exists() or target.is_symlink():raise ValueError('Refusing to replace an existing serving directory')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        stage=Path(temp)/'serving';stage.mkdir()
        with tarfile.open(archive,'r:gz') as tar:
            members=tar.getmembers();names=set();total=0
            for member in members:
                path=PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts or member.issym() or member.islnk() or not (member.isfile() or member.isdir()):raise ValueError('Unsafe serving archive member')
                if member.name in names:raise ValueError('Duplicate serving archive member')
                names.add(member.name);total+=member.size
            if total>1024**3 or len(members)>1000:raise ValueError('Serving archive exceeds its extraction budget')
            for member in members:
                path=stage/member.name
                if member.isdir():path.mkdir(parents=True,exist_ok=True);continue
                path.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(member) as source,path.open('wb') as destination:shutil.copyfileobj(source,destination)
        manifest=json.loads((stage/'manifest.json').read_text())
        if manifest['snapshot']!=expected['snapshot'] or manifest['metric_version']!=expected['metric_version']:raise ValueError('Serving asset version mismatch')
        actual={str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file()}
        if actual!=set(manifest['files'])|{'manifest.json'}:raise ValueError('Unexpected serving asset files')
        for name,checksum in manifest['files'].items():
            path=PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or digest(stage/name)!=checksum:raise ValueError('Serving file checksum mismatch')
        stage.rename(target)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',default='deployment/serving-release.json')
    parser.add_argument('--target',default='data/releases/current')
    args=parser.parse_args();expected=json.loads(Path(args.manifest).read_text())
    if not expected['url'].startswith('https://github.com/kmaran3/tennis-vision/releases/download/'):raise ValueError('Unexpected serving asset host/path')
    with tempfile.TemporaryDirectory() as temp:
        archive=Path(temp)/'serving.tar.gz'
        with urlopen(Request(expected['url'],headers={'User-Agent':'Baseline-serving-build'}),timeout=120) as source,archive.open('wb') as output:
            size=0
            while chunk:=source.read(1024*1024):
                size+=len(chunk)
                if size>1024**3:raise ValueError('Serving download exceeds its byte budget')
                output.write(chunk)
        if size!=expected['bytes']:raise ValueError('Serving download size mismatch')
        extract(archive,args.target,expected)
    print('Verified serving snapshot',expected['snapshot'])


if __name__=='__main__':main()
