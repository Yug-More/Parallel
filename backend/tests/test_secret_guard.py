import importlib.util
from pathlib import Path


def test_guard_detects_provider_literals_without_requiring_real_credentials():
    path = Path(__file__).resolve().parents[2] / "scripts" / "check_secrets.py"
    spec = importlib.util.spec_from_file_location("secret_guard", path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    assert guard.suspicious_lines("key = '" + "sk-" + "a" * 32 + "'") == [1]
    assert guard.suspicious_lines("api_key = os.getenv('OPENAI_API_KEY')") == []
    assert guard.suspicious_lines("secret_key='test-only-non-provider-signing-key'") == []
