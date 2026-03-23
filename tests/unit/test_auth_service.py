import os
import tempfile

from click.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.web_api.services.auth_service import AuthService
from cli.apikey import apikey
from core.models import Base


def _make_temp_session():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    return session, engine, db_fd, db_path


def test_auth_service_create_and_verify():
    session, engine, db_fd, db_path = _make_temp_session()
    try:
        service = AuthService()

        key, api_key = service.create_api_key(
            session,
            name="joinremotes",
            project="joinremotes",
        )

        verified = service.verify_key(session, key, project="joinremotes")

        assert getattr(api_key, "name") == "joinremotes"
        assert verified is not None
        assert getattr(verified, "id") == getattr(api_key, "id")
    finally:
        session.close()
        engine.dispose()
        os.close(db_fd)
        os.unlink(db_path)


def test_apikey_create_command_writes_local_record(tmp_path, monkeypatch):
    session, engine, db_fd, db_path = _make_temp_session()
    runner = CliRunner()
    module = __import__("cli.apikey", fromlist=["apikey"])

    try:
        monkeypatch.setattr(module, "SessionLocal", lambda: session)
        monkeypatch.setattr(module, "DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setattr(
            AuthService, "generate_api_key", staticmethod(lambda: "sk_test_secret_1234")
        )

        result = runner.invoke(apikey, ["create", "joinremotes", "--project", "joinremotes"])

        assert result.exit_code == 0
        assert "sk_test_secret_1234" not in result.output
        assert "Preview: sk_tes...1234" in result.output

        record_path = (
            tmp_path / "data" / "credentials" / "api-keys" / "joinremotes" / "joinremotes.env"
        )
        assert record_path.exists()
        assert "SCRAPAI_API_KEY=sk_test_secret_1234" in record_path.read_text(encoding="utf-8")
    finally:
        session.close()
        engine.dispose()
        os.close(db_fd)
        os.unlink(db_path)
