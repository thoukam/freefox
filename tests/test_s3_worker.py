from freefox.backends import TransientCredentialError,AuthenticationBackendError,ConflictBackendError
from freefox.worker import UploadWorkerPool

def test_destination_key_lock_is_stable(tmp_path):
    pool=UploadWorkerPool(queue=None,backend=None,config=type("C",(),{"workers":1})())
    assert pool._lock_for("s3:x:k") is pool._lock_for("s3:x:k")
    assert pool._lock_for("s3:x:k") is not pool._lock_for("s3:x:other")
