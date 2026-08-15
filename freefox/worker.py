"""Upload worker pool with durable provider-neutral policy."""
from __future__ import annotations
import logging, threading, time
from pathlib import Path
from typing import TYPE_CHECKING
from freefox.backends import AuthenticationBackendError, ConfigurationBackendError, ConflictBackendError, QuotaBackendError, TransientBackendError
from freefox.integrity import calculate_blake3
from freefox.queue import UploadQueue
if TYPE_CHECKING:
    from freefox.backends import StorageBackend
    from freefox.config import UploadConfig
logger=logging.getLogger(__name__)


def _is_storage_quota_error(error_msg:str)->bool:
    x=error_msg.lower();return "storagequotaexceeded" in x or "storage quota" in x

def _is_transient_network_error(error_msg:str)->bool:
    x=error_msg.lower();return any(m in x for m in ("temporary failure in name resolution","nameresolutionerror","failed to resolve","read timed out","connect timed out","connection timed out","max retries exceeded","connection reset","connection aborted","temporarily unavailable","transient drive upload error"))


class UploadWorkerPool:
    def __init__(self,queue:UploadQueue,backend=None,config:'UploadConfig'=None,delete_after:bool=False,registry=None)->None:
        self._queue=queue;self._backend=backend;self._registry=registry;self._config=config;self._delete_after=delete_after;self._stop=threading.Event();self._threads=[];self._key_locks={};self._key_locks_guard=threading.Lock()
    def _lock_for(self,key):
        with self._key_locks_guard:return self._key_locks.setdefault(key,threading.Lock())
    def _record_progress(self,entry_id,pct,uploaded):
        try:self._queue.mark_progress(entry_id,pct,uploaded)
        except Exception as exc:logger.warning("Could not record upload progress for #%d: %s",entry_id,exc)
    def _backend_for(self,entry): return self._registry.get(entry.backend,entry.destination) if self._registry else self._backend
    def _worker(self,worker_id:int)->None:
        while not self._stop.is_set():
            entry=self._queue.next_ready()
            if entry is None:self._stop.wait(2);continue
            local=Path(entry.local_path)
            if not local.exists():self._queue.mark_failed(entry.id,"local file missing",max_retries=0);continue
            digest=entry.blake3_digest
            if self._config.verify_blake3 and not digest:
                digest=calculate_blake3(local,chunk_size=max(1024*1024,self._config.chunk_size));self._queue.mark_integrity(entry.id,digest,local.stat().st_size);entry.blake3_digest=digest;entry.size_bytes=local.stat().st_size
            backend=self._backend_for(entry); key=f"{entry.backend}:{entry.destination_json}:{entry.remote_path}"
            try:
                with self._lock_for(key):
                    upload_entry=getattr(backend,"upload_entry",None)
                    if callable(upload_entry):
                        upload_entry(entry,self._queue,local,self._config.chunk_size,lambda p,u:self._record_progress(entry.id,p,u))
                    else:
                        if digest and self._config.deduplicate_by_hash and backend.find_duplicate(entry.remote_path,digest,entry.size_bytes):
                            self._queue.mark_done(entry.id);continue
                        if not digest and backend.exists(entry.remote_path):self._queue.mark_done(entry.id);continue
                        backend.upload(local,entry.remote_path,chunk_size=self._config.chunk_size,progress_callback=lambda p,u:self._record_progress(entry.id,p,u),session_uri=entry.upload_session_uri,session_callback=lambda u:self._queue.mark_upload_session(entry.id,u),blake3_digest=digest,expected_size=entry.size_bytes)
                    self._queue.mark_done(entry.id)
                    if self._delete_after:local.unlink()
            except ConflictBackendError as exc:
                logger.error("bag=%s backend=%s destination=%s disposition=operator conflict=%s",local.name,entry.backend,entry.remote_path,exc);self._queue.mark_conflict(entry.id,str(exc))
            except QuotaBackendError as exc:
                self._queue.defer(entry.id,str(exc),self._config.quota_retry_delay)
            except TransientBackendError as exc:
                self._queue.defer(entry.id,str(exc),self._config.transient_retry_delay)
            except (AuthenticationBackendError,ConfigurationBackendError) as exc:
                logger.error("bag=%s backend=%s destination=%s disposition=failed cause=%s",local.name,entry.backend,entry.remote_path,exc);self._queue.mark_failed(entry.id,str(exc),max_retries=0)
            except Exception as exc:
                msg=str(exc)
                if _is_storage_quota_error(msg):self._queue.defer(entry.id,"Storage quota exceeded",self._config.quota_retry_delay)
                elif _is_transient_network_error(msg):self._queue.defer(entry.id,"Temporary network error",self._config.transient_retry_delay)
                else:self._queue.mark_failed(entry.id,msg,backoff_base=self._config.retry_backoff_base,backoff_max=self._config.retry_backoff_max,max_retries=self._config.max_retries)
    def start(self):
        for i in range(self._config.workers):
            t=threading.Thread(target=self._worker,args=(i,),daemon=True,name=f"uploader-{i}");t.start();self._threads.append(t)
    def stop(self,drain_timeout:float=30.0):
        self._stop.set();deadline=time.monotonic()+drain_timeout
        for t in self._threads:t.join(timeout=max(0,deadline-time.monotonic()))
        if self._queue.pending_count():logger.warning("%d items still pending in queue",self._queue.pending_count())
