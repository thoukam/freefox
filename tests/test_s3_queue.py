import json,sqlite3,time
import pytest
from freefox.queue import UploadQueue,Status

def test_binding_conflict_and_multipart(tmp_path):
    f=tmp_path/"b.mcap";f.write_bytes(b"abc");q=UploadQueue(tmp_path/"q.db")
    e=q.add(f,"p/b.mcap",backend="s3",destination={"bucket":"x"}); assert e.backend=="s3" and e.destination=={"bucket":"x"}
    q.create_multipart(e.id,"u","x",e.remote_path,5*1024*1024,3,"d");q.upsert_part(e.id,1,"etag",3)
    assert q.get_multipart(e.id).upload_id=="u" and q.get_parts(e.id)[0].etag=="etag"
    q.mark_conflict(e.id,"different");assert q.get(e.id).status==Status.CONFLICT and q.requeue_failed()==0

def test_restart_preserves_multipart(tmp_path):
    f=tmp_path/"b";f.write_bytes(b"abc");db=tmp_path/"q.db";q=UploadQueue(db);e=q.add(f,"k",backend="s3",destination={"bucket":"x"});q.create_multipart(e.id,"u","x","k",5*1024*1024,3,"d");q.next_ready()
    q2=UploadQueue(db);assert q2.get(e.id).status==Status.QUEUED and q2.get_multipart(e.id).upload_id=="u"

def test_legacy_migration_requires_context(tmp_path):
    db=tmp_path/"old.db";c=sqlite3.connect(db);c.execute("CREATE TABLE queue(id INTEGER PRIMARY KEY,local_path TEXT UNIQUE,remote_path TEXT,status TEXT,retries INTEGER,next_retry_at REAL,created_at REAL,size_bytes INTEGER,error TEXT)");c.execute("INSERT INTO queue VALUES(1,'a','b','queued',0,0,?,1,NULL)",(time.time(),));c.commit();c.close()
    with pytest.raises(RuntimeError,match="ambiguous"):UploadQueue(db)
    q=UploadQueue(db,legacy_backend="gdrive",legacy_destination={"target_folder_id":"f"});assert q.get(1).backend=="gdrive"
