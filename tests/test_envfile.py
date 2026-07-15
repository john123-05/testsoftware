from pathlib import Path

from liftpic_sync.envfile import load_env_file, write_env_values


def test_write_env_values_preserves_comments_and_updates_existing_keys(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# keep this\n"
        "PARK_ID=old\n"
        "DEVICE_TOKEN=old-token\n",
        encoding="utf-8",
    )

    write_env_values(
        env_path,
        {
            "PARK_ID": "new",
            "DEVICE_TOKEN": "new-token",
            "CAMERA_CODE": "cam1",
        },
    )

    raw = env_path.read_text(encoding="utf-8")
    assert "# keep this" in raw
    assert "PARK_ID=new" in raw
    assert "DEVICE_TOKEN=new-token" in raw
    assert "CAMERA_CODE=cam1" in raw
    assert load_env_file(env_path)["PARK_ID"] == "new"
