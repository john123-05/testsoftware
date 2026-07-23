import pytest

from liftpic_sync.envfile import load_env_file

CONTENT = (
    "APP_NAME=liftpic-sync\r\n"
    "SUPABASE_FUNCTIONS_URL=https://x.supabase.co/functions/v1\r\n"
    "DEVICE_TOKEN=abc\r\n"
)


@pytest.mark.parametrize("encoding", ["ascii", "utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"])
def test_load_env_file_handles_encoding(tmp_path, encoding):
    p = tmp_path / ".env"
    p.write_bytes(CONTENT.encode(encoding))

    values = load_env_file(p)

    assert values["APP_NAME"] == "liftpic-sync"
    assert values["SUPABASE_FUNCTIONS_URL"] == "https://x.supabase.co/functions/v1"
    assert values["DEVICE_TOKEN"] == "abc"
