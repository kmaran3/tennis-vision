"""Release-download integrity and archive containment checks, without networking."""
import io
import json
from pathlib import Path
import tarfile
import pytest
from scripts.fetch_serving import digest,extract


def archive(tmp_path,extra=None):
    path=tmp_path/'asset.tar.gz';content=b'verified fixture'
    import hashlib
    manifest={'snapshot':'fixture','metric_version':'test','files':{'serving.duckdb':hashlib.sha256(content).hexdigest()}}
    with tarfile.open(path,'w:gz') as tar:
        for name,data in [('serving.duckdb',content),('manifest.json',json.dumps(manifest).encode())]:
            info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
        if extra:
            info=tarfile.TarInfo(extra)
            if extra=='link':info.type=tarfile.SYMTYPE;info.linkname='../outside'
            tar.addfile(info,io.BytesIO(b''))
    return path,{'sha256':digest(path),'snapshot':'fixture','metric_version':'test'}


def test_verified_asset_extracts_atomically_and_preserves_existing_release(tmp_path):
    path,expected=archive(tmp_path);target=tmp_path/'current';extract(path,target,expected)
    assert (target/'serving.duckdb').read_bytes()==b'verified fixture'
    with pytest.raises(ValueError,match='existing'):extract(path,target,expected)


@pytest.mark.parametrize('extra',['../outside','/outside','link','unmanifested.txt'])
def test_unsafe_or_unmanifested_assets_never_activate(tmp_path,extra):
    path,expected=archive(tmp_path,extra);target=tmp_path/'current'
    with pytest.raises(ValueError):extract(path,target,expected)
    assert not target.exists() and not (tmp_path/'outside').exists()


def test_outer_checksum_and_snapshot_both_gate_activation(tmp_path):
    path,expected=archive(tmp_path);target=tmp_path/'current'
    with pytest.raises(ValueError,match='checksum'):extract(path,target,{**expected,'sha256':'0'*64})
    with pytest.raises(ValueError,match='version'):extract(path,target,{**expected,'snapshot':'another'})
    assert not target.exists()
