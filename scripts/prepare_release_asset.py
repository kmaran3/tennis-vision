"""Prepare the public data asset and exact build manifest, without publishing."""
from pathlib import Path
import tarfile
import gzip
from baseline.config import ROOT,ARTIFACTS,serving_path,write_json,digest,reserve
from baseline.release import check_release,PUBLIC_REPORTS


def main():
    reserve(1)
    source=serving_path().parent.resolve();manifest=check_release(source)
    report_files={p.name for p in (source/'reports').glob('*.json')}
    if not report_files.issubset(PUBLIC_REPORTS):raise ValueError('Repackage first: non-public operating reports are present')
    target=ARTIFACTS/'release-assets/baseline-serving.tar.gz';target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('wb') as output,gzip.GzipFile(filename='',mode='wb',fileobj=output,compresslevel=3,mtime=0) as compressed,tarfile.open(fileobj=compressed,mode='w') as tar:
        for path in sorted(source.rglob('*')):
            if path.is_symlink():raise ValueError('Serving asset must contain regular files')
            if path.is_file():
                info=tar.gettarinfo(str(path),arcname=str(path.relative_to(source)))
                info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0;info.pax_headers={};info.mode=0o644
                with path.open('rb') as source_file:tar.addfile(info,source_file)
    checksum=digest(target);tag='serving-'+manifest['snapshot'][:12]+'-'+checksum[:12]
    metadata=dict(url=f'https://github.com/kmaran3/tennis-vision/releases/download/{tag}/{target.name}',sha256=checksum,bytes=target.stat().st_size,snapshot=manifest['snapshot'],metric_version=manifest['metric_version'],tag=tag)
    write_json(ROOT/'deployment/serving-release.json',metadata)
    print('Prepared',target,'tag',tag,'bytes',metadata['bytes'])


if __name__=='__main__':main()
