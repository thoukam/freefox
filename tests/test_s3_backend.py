import pytest
from freefox.backends import ConflictBackendError,Inspection,InvalidSessionError
from freefox.backends.s3 import S3Backend,effective_part_size
from freefox.config import S3Config
from freefox.queue import UploadQueue

def backend(client):return S3Backend(S3Config(bucket="bags"),client=client)
def test_put_confirm_deduplicate_and_conflict(tmp_path,fake_s3_client):
    f=tmp_path/"bag";f.write_bytes(b"hello");b=backend(fake_s3_client);progress=[]
    b.upload(f,"r/bag",blake3_digest="digest",expected_size=5,progress_callback=lambda p,u:progress.append((p,u)))
    assert b.inspect("r/bag","digest",5)==Inspection.IDENTICAL and progress[-1]==(100.0,5)
    assert b.upload(f,"r/bag",blake3_digest="digest",expected_size=5).startswith("s3://")
    with pytest.raises(ConflictBackendError):b.upload(f,"r/bag",blake3_digest="other",expected_size=5)
def test_multipart_persists_and_completes(tmp_path,fake_s3_client):
    f=tmp_path/"large";f.write_bytes(b"x"*(5*1024*1024+1));q=UploadQueue(tmp_path/"q.db");e=q.add(f,"r/large",backend="s3",destination={"bucket":"bags"});q.mark_integrity(e.id,"d",f.stat().st_size);e=q.get(e.id)
    backend(fake_s3_client).upload_entry(e,q,f,5*1024*1024)
    assert q.get_multipart(e.id) is None and fake_s3_client.objects[("bags","r/large")]["ContentLength"]==f.stat().st_size
def test_part_size_limit():assert effective_part_size(5*1024**4,5*1024*1024)*10000>=5*1024**4
