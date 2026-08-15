from pathlib import Path
import pytest
from freefox.config import CollectorConfig


def write(tmp_path, extra):
    f=tmp_path/"config.yaml"; f.write_text("robot_id: r\nwatch:\n  directory: /tmp/bags\nstorage:\n  backend: s3\n"+extra); return f

def test_s3_defaults_and_custom_endpoint(tmp_path):
    c=CollectorConfig.from_yaml(write(tmp_path,"s3:\n  bucket: bags\n  endpoint_url: https://minio.example\n"))
    assert c.storage.backend=="s3" and c.s3.addressing_style=="path" and c.s3.object_prefix==""

def test_s3_requires_bucket(tmp_path):
    with pytest.raises(ValueError,match="bucket"):CollectorConfig.from_yaml(write(tmp_path,"s3: {}\n"))

def test_s3_rejects_inline_secret(tmp_path):
    with pytest.raises(ValueError,match="secrets"):CollectorConfig.from_yaml(write(tmp_path,"s3:\n  bucket: bags\n  secret_key: nope\n"))

def test_s3_rejects_bad_prefix_and_endpoint(tmp_path):
    with pytest.raises(ValueError):CollectorConfig.from_yaml(write(tmp_path,"s3:\n  bucket: bags\n  object_prefix: a/../b\n"))
    with pytest.raises(ValueError):CollectorConfig.from_yaml(write(tmp_path,"s3:\n  bucket: bags\n  endpoint_url: minio\n"))

def test_non_s3_does_not_require_bucket(tmp_path):
    f=tmp_path/"c.yaml";f.write_text("robot_id: r\nwatch:\n  directory: /tmp/bags\n")
    assert CollectorConfig.from_yaml(f).storage.backend=="gdrive"
