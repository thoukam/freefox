"""AWS S3 and MinIO-compatible backend with durable multipart recovery."""
from __future__ import annotations
import logging, math, re
from pathlib import Path
from typing import TYPE_CHECKING
from freefox.backends import (AuthenticationBackendError, ConfigurationBackendError, ConflictBackendError, Inspection, InvalidSessionError, QuotaBackendError, TransientBackendError, TransientCredentialError)
from freefox.config import S3Config
if TYPE_CHECKING:
    from freefox.queue import QueueEntry, UploadQueue
logger=logging.getLogger(__name__)
_MIN_PART=5*1024*1024; _MAX_PARTS=10000
_SECRET_RE=re.compile(r"(?i)(access[_ -]?key|secret|token|authorization|signature|x-amz-credential)([^,; ]*)")


def _safe_message(exc: Exception) -> str: return _SECRET_RE.sub(r"\1=<redacted>",str(exc))
def _code(exc: Exception) -> str:
    return str(getattr(exc,"response",{}).get("Error",{}).get("Code", ""))
def _not_found(exc: Exception) -> bool: return _code(exc) in {"404","NoSuchKey","NotFound"}
def _invalid_session(exc: Exception) -> bool: return _code(exc)=="NoSuchUpload"
def effective_part_size(size:int, configured:int)->int: return max(_MIN_PART,configured,math.ceil(max(1,size)/_MAX_PARTS))


class S3Backend:
    def __init__(self, config:S3Config, client=None) -> None:
        self.config=config; self._client=client
    @property
    def client(self):
        if self._client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as exc: raise ConfigurationBackendError("Le backend S3 requiert pip install freefox[s3]") from exc
            kwargs={};
            if self.config.profile: kwargs["profile_name"]=self.config.profile
            session=boto3.Session(**kwargs)
            client_kwargs={"config":Config(signature_version="s3v4",retries={"max_attempts":3,"mode":"standard"},s3={"addressing_style":self.config.addressing_style})}
            if self.config.region: client_kwargs["region_name"]=self.config.region
            if self.config.endpoint_url: client_kwargs["endpoint_url"]=self.config.endpoint_url
            if self.config.ca_bundle: client_kwargs["verify"]=str(self.config.ca_bundle)
            self._client=session.client("s3",**client_kwargs)
        return self._client
    def exists(self, remote_path:str)->bool:
        try:self.client.head_object(Bucket=self.config.bucket,Key=remote_path);return True
        except Exception as exc:
            if _not_found(exc):return False
            raise self._translate(exc)
    def inspect(self, remote_path:str,digest:str,size:int)->Inspection:
        try: head=self.client.head_object(Bucket=self.config.bucket,Key=remote_path)
        except Exception as exc:
            if _not_found(exc):return Inspection.MISSING
            raise self._translate(exc)
        meta={str(k).lower():str(v) for k,v in head.get("Metadata",{}).items()}
        if int(head.get("ContentLength",-1))==size and meta.get("freefox-blake3","")==digest and meta.get("freefox-size")==str(size): return Inspection.IDENTICAL
        return Inspection.CONFLICT
    def find_duplicate(self,remote_path:str,blake3_digest:str,size_bytes:int)->bool:return self.inspect(remote_path,blake3_digest,size_bytes)==Inspection.IDENTICAL
    def upload(self,local_path:Path,remote_path:str,chunk_size:int=2*1024*1024,progress_callback=None,session_uri:str="",session_callback=None,blake3_digest:str="",expected_size:int=0)->str:
        size=local_path.stat().st_size
        if expected_size and size!=expected_size: raise ConfigurationBackendError(f"Local file size changed: {expected_size} -> {size}")
        state=self.inspect(remote_path,blake3_digest,size)
        if state==Inspection.IDENTICAL:return f"s3://{self.config.bucket}/{remote_path}"
        if state==Inspection.CONFLICT:raise ConflictBackendError(f"S3 object conflict: {self.config.bucket}/{remote_path}")
        metadata={"freefox-blake3":blake3_digest,"freefox-size":str(size)}
        if size<=max(chunk_size,_MIN_PART):
            with local_path.open("rb") as fh:self.client.put_object(Bucket=self.config.bucket,Key=remote_path,Body=fh,Metadata=metadata)
            if progress_callback:progress_callback(100.0,size)
        else:
            self._multipart_basic(local_path,remote_path,effective_part_size(size,chunk_size),metadata,progress_callback)
        if self.inspect(remote_path,blake3_digest,size)!=Inspection.IDENTICAL:raise TransientBackendError("S3 completion confirmation mismatch")
        return f"s3://{self.config.bucket}/{remote_path}"
    def upload_entry(self,entry:'QueueEntry',queue:'UploadQueue',local_path:Path,chunk_size:int,progress_callback=None)->str:
        size=local_path.stat().st_size; digest=entry.blake3_digest
        if size!=entry.size_bytes:raise ConfigurationBackendError(f"Local file size changed: {entry.size_bytes} -> {size}")
        state=self.inspect(entry.remote_path,digest,size)
        if state==Inspection.IDENTICAL:queue.clear_multipart(entry.id);return f"s3://{self.config.bucket}/{entry.remote_path}"
        if state==Inspection.CONFLICT:raise ConflictBackendError(f"S3 object conflict: {self.config.bucket}/{entry.remote_path}")
        part_size=effective_part_size(size,chunk_size); upload=queue.get_multipart(entry.id)
        if upload and (upload.source_size!=size or upload.source_blake3!=digest or upload.bucket!=self.config.bucket or upload.object_key!=entry.remote_path):
            raise ConfigurationBackendError("Local source or S3 destination changed during multipart upload")
        if not upload:
            response=self.client.create_multipart_upload(Bucket=self.config.bucket,Key=entry.remote_path,Metadata={"freefox-blake3":digest,"freefox-size":str(size)})
            queue.create_multipart(entry.id,response["UploadId"],self.config.bucket,entry.remote_path,part_size,size,digest); upload=queue.get_multipart(entry.id)
        assert upload
        try:
            remote=self.client.list_parts(Bucket=self.config.bucket,Key=entry.remote_path,UploadId=upload.upload_id).get("Parts",[])
        except Exception as exc:
            if _invalid_session(exc):
                final=self.inspect(entry.remote_path,digest,size)
                if final==Inspection.IDENTICAL:queue.clear_multipart(entry.id);return f"s3://{self.config.bucket}/{entry.remote_path}"
                if final==Inspection.CONFLICT:raise ConflictBackendError("S3 object conflict after invalid session")
                queue.clear_multipart(entry.id);raise InvalidSessionError("S3 multipart session expired") from exc
            raise self._translate(exc)
        expected={n:min(part_size,size-(n-1)*part_size) for n in range(1,math.ceil(size/part_size)+1)}
        reusable=[(int(p["PartNumber"]),str(p["ETag"]),int(p["Size"])) for p in remote if int(p["PartNumber"]) in expected and int(p["Size"])==expected[int(p["PartNumber"])]]
        queue.replace_parts(entry.id,reusable); parts={p.part_number:p for p in queue.get_parts(entry.id)}
        uploaded=sum(p.size_bytes for p in parts.values())
        with local_path.open("rb") as fh:
            for number,want in expected.items():
                if number in parts:continue
                fh.seek((number-1)*part_size); data=fh.read(want)
                response=self.client.upload_part(Bucket=self.config.bucket,Key=entry.remote_path,UploadId=upload.upload_id,PartNumber=number,Body=data)
                queue.upsert_part(entry.id,number,str(response["ETag"]),len(data)); uploaded+=len(data)
                if progress_callback:progress_callback(uploaded*100/size,uploaded)
        ordered=[{"PartNumber":p.part_number,"ETag":p.etag} for p in queue.get_parts(entry.id)]
        try:self.client.complete_multipart_upload(Bucket=self.config.bucket,Key=entry.remote_path,UploadId=upload.upload_id,MultipartUpload={"Parts":ordered})
        except Exception as exc:
            if self.inspect(entry.remote_path,digest,size)!=Inspection.IDENTICAL:raise self._translate(exc)
        if self.inspect(entry.remote_path,digest,size)!=Inspection.IDENTICAL:raise TransientBackendError("S3 completion confirmation mismatch")
        queue.clear_multipart(entry.id);return f"s3://{self.config.bucket}/{entry.remote_path}"
    def _multipart_basic(self,path,key,part_size,metadata,progress):
        response=self.client.create_multipart_upload(Bucket=self.config.bucket,Key=key,Metadata=metadata); uid=response["UploadId"]; parts=[]; uploaded=0
        try:
            with path.open("rb") as fh:
                number=1
                while data:=fh.read(part_size):
                    result=self.client.upload_part(Bucket=self.config.bucket,Key=key,UploadId=uid,PartNumber=number,Body=data);parts.append({"PartNumber":number,"ETag":result["ETag"]});uploaded+=len(data)
                    if progress:progress(uploaded*100/path.stat().st_size,uploaded)
                    number+=1
            self.client.complete_multipart_upload(Bucket=self.config.bucket,Key=key,UploadId=uid,MultipartUpload={"Parts":parts})
        except Exception:
            try:self.client.abort_multipart_upload(Bucket=self.config.bucket,Key=key,UploadId=uid)
            except Exception:pass
            raise
    def _translate(self,exc:Exception)->Exception:
        code=_code(exc); message=_safe_message(exc)
        if code in {"SlowDown","Throttling","ThrottlingException","RequestLimitExceeded"}:return QuotaBackendError(message)
        if code in {"ExpiredToken","RequestExpired","IDPCommunicationError"}:return TransientCredentialError(message)
        if code in {"InvalidAccessKeyId","SignatureDoesNotMatch","AccessDenied","InvalidToken"} or type(exc).__name__ in {"NoCredentialsError", "PartialCredentialsError"}:return AuthenticationBackendError(message)
        if code=="NoSuchUpload":return InvalidSessionError(message)
        if code in {"NoSuchBucket","InvalidBucketName","InvalidArgument"}:return ConfigurationBackendError(message)
        if any(x in type(exc).__name__.lower() for x in ("ssl","certificate")):return ConfigurationBackendError(message)
        return TransientBackendError(message)
