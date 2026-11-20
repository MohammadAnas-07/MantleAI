"""What indexing treats as a secret, and what it must not. No database, no files.

Every secret-shaped value is built at runtime from pieces, so this file holds no string that
another secret scanner would flag. None of them is a real credential.
"""

# The tables below are fixture data, one case per line, easier to read unwrapped.
# ruff: noqa: E501

import pytest

from app.modules.rag.secret_scan import looks_like_secret, sensitive_spec


def j(*parts: str) -> str:
    return "".join(parts)


A40 = "Ab3dE6gH9jKm2nPq5sTv8wXy1zB4cD7fG0hJ3kL6"  # 40 mixed characters, no meaning
HEX32 = "9f86d081884c7d659a2feaa0c55ad015"
JWT = j("ey", "JhbGciOiJIUzI1NiJ9", ".", "ey", "JzdWIiOiIxMjM0NTY3ODkwIn0", ".",
        "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U")  # fmt: skip

# (label, file name, text): each must make the whole file a "possible secret".
SECRETS = [
    ("private key block", "a.py", j("-----BEGIN ", "RSA PRIVATE KEY-----\nMIIE")),
    ("encrypted private key", "a.txt", j("-----BEGIN ", "ENCRYPTED PRIVATE KEY-----")),
    ("OpenSSH private key", "a.txt", j("-----BEGIN ", "OPENSSH PRIVATE KEY-----")),
    ("PuTTY key", "a.txt", j("PuTTY-User-", "Key-File-3: ssh-ed25519")),
    (
        "GCP service account",
        "sa.json",
        j('{"private_key": "-----BEGIN ', 'PRIVATE KEY-----\\nMII"}'),
    ),
    ("AWS access key id", "a.py", j("key = 'AK", "IA", "Q" * 16, "'")),
    ("AWS secret, any name", "a.py", j("AWS_SECRET = '", A40, "'")),
    ("AWS secret, standard name", "a.ini", j("aws_secret_access_key = ", A40)),
    ("GitHub token", "a.py", j("t = 'gh", "p_", "a" * 36, "'")),
    ("GitHub fine-grained", "a.py", j("github", "_pat_", "B" * 30)),
    ("OpenAI-style key", "a.ts", j("const k = 'sk-", "proj-", "C" * 40, "'")),
    ("Anthropic-style key", "a.ts", j("const k = 'sk-", "ant-api03-", "D" * 40, "'")),
    ("Google API key", "a.js", j("k='AI", "za", "e" * 35, "'")),
    ("Google OAuth secret", "a.json", j('{"x": "GOC', "SPX-", "f" * 28, '"}')),
    ("Slack token", "a.py", j("x = 'xo", "xb-", "1234567890-abcdefghij'")),
    (
        "Slack webhook",
        "a.md",
        j("https://hooks.slack.com/services/", "T0A1B2C3D/B0A1B2C3D/", "g" * 24),
    ),
    ("Stripe live key", "a.py", j("k = 'sk_", "live_", "h" * 24, "'")),
    ("Stripe test key", "a.py", j("k = 'sk_", "test_", "h" * 24, "'")),
    ("Stripe webhook secret", "a.py", j("k = 'wh", "sec_", "i" * 32, "'")),
    ("GitLab token", "a.yml", j("token_value: gl", "pat-", "j" * 20)),
    ("Hugging Face token", "a.py", j("t = 'h", "f_", "k" * 34, "'")),
    ("npm token", "a.txt", j("np", "m_", "L" * 36)),
    ("SendGrid key", "a.py", j("k = 'S", "G.", "m" * 22, ".", "n" * 43, "'")),
    (
        "Azure storage key",
        "a.json",
        j('{"c": "DefaultEndpointsProtocol=https;AccountKey=', "o" * 86, '==;"}'),
    ),
    ("JWT", "a.py", j("token = '", JWT, "'")),
    ("JWT in a header", "a.http", j("Authorization: Bearer ", JWT)),
    (
        "Postgres URL",
        "a.py",
        j("DATABASE_URL = 'postgresql://app:", "S3cretPassw0rd", "@db.example.com:5432/app'"),
    ),
    (
        "Postgres + driver URL",
        "a.toml",
        j('url = "postgresql+asyncpg://app:', "S3cretPassw0rd", '@db/app"'),
    ),
    ("MySQL URL", "a.yaml", j("url: mysql://root:", "Tr0ub4dor", "@10.0.0.2/shop")),
    (
        "MongoDB SRV URL",
        "a.js",
        j("const u = 'mongodb+srv://admin:", "Mong0Pass!", "@c0.mongodb.net/db'"),
    ),
    ("Redis URL", "a.env.txt", j("REDIS=redis://:", "R3disPassw0rd", "@cache:6379/0")),
    ("AMQP URL", "a.py", j("BROKER = 'amqps://user:", "Rabb1tPass", "@mq.example.com/vhost'")),
    (
        "ADO.NET connection string",
        "appsettings.json",
        j('{"Db": "Server=sql1;Database=shop;User Id=app;Password=', "Sql5erverPw", ';"}'),
    ),
    ("password in Python", "a.py", j("PASSWORD = '", "correct-horse-battery-staple", "'")),
    ("password in YAML", "a.yaml", j("db:\n  password: ", "Yaml5ecretPw", "\n")),
    (
        "password in docker-compose",
        "docker-compose.yml",
        j("services:\n  db:\n    environment:\n      POSTGRES_PASSWORD: ", "C0mposePw", "\n"),
    ),
    ("password in INI", "a.ini", j("[db]\npassword = ", "Ini5ecretPw", "\n")),
    ("password in TOML", "a.toml", j('[db]\npassword = "', "T0ml5ecretPw", '"\n')),
    ("password in JSON", "a.json", j('{"password": "', "Js0nSecretPw", '"}')),
    ("camelCase secret in TS", "a.ts", j("const config = { clientSecret: '", A40, "' };")),
    ("api_key in Python", "a.py", j("api_key = '", HEX32, "'")),
    ("apiKey in JS", "a.js", j('const apiKey = "', A40, '";')),
    (
        "token in terraform",
        "main.tf",
        j('variable "x" {\n  default = "a"\n}\napi_token = "', A40, '"'),
    ),
    ("secret_key in settings", "settings.py", j("SECRET_KEY = '", "django-insecure-", A40, "'")),
    ("Fernet key in config", "a.cfg", j("MASTER_ENCRYPTION_KEY=", "a" * 20, "B" * 23, "=")),
    ("high-entropy value next to a key name", "a.py", j("STRIPE_KEY = '", A40, "'")),
    ("npm auth token in yarnrc", ".yarnrc.yml", j("npmAuthToken: ", A40)),
]


@pytest.mark.parametrize(("label", "name", "text"), SECRETS, ids=[s[0] for s in SECRETS])
def test_secret_content_is_detected(label: str, name: str, text: str) -> None:
    assert looks_like_secret(text, name), label


# (label, file name, text): ordinary code and data that must stay indexable.
NOT_SECRETS = [
    (
        "sha256 digest",
        "a.py",
        'EXPECTED = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"',
    ),
    (
        "sha256 as a cache key",
        "a.py",
        'cache_key = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"',
    ),
    ("UUID", "a.py", 'user_id = "123e4567-e89b-12d3-a456-426614174000"'),
    ("UUID as a key id", "a.py", 'api_key_id = "123e4567-e89b-12d3-a456-426614174000"'),
    (
        "base64 image fixture",
        "a.py",
        'PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="',
    ),
    ("long test data", "a.py", "DATA = '" + "lorem ipsum dolor sit amet " * 50 + "'"),
    (
        "lock-file integrity hash",
        "a.json",
        '{"integrity": "sha512-z4PhNX7vuL3xVChQ1m2AB9Yg5AULVxXcg/SpIdNs6c5H0NE8XYXysP+DGNKHfuwvY7kxvUdBeoGlODJ6+SfaPg=="}',
    ),
    ("placeholder key", "a.py", 'api_key = "your-key-here"'),
    ("placeholder in angle brackets", "a.env.txt", "API_KEY=<your api key>"),
    ("empty value", "a.ini", "password =\n"),
    ("variable reference", "a.yml", "password: ${DB_PASSWORD}"),
    ("template reference", "a.yml", 'password: "{{ vault_db_password }}"'),
    ("environment lookup", "a.py", 'token = os.environ["GITHUB_TOKEN"]'),
    ("process.env lookup", "a.ts", "const apiKey = process.env.API_KEY;"),
    ("form field", "a.py", 'password = request.form["password"]'),
    (
        "type annotation",
        "a.py",
        "def login(user: str, password: str, token: str | None = None) -> None: ...",
    ),
    ("TS type", "a.ts", "interface Creds { password: string; apiKey: string }"),
    ("JSON schema", "a.json", '{"password": {"type": "string", "minLength": 12}}'),
    ("changeme", "a.py", 'SECRET_KEY = "changeme"'),
    ("password named password", "a.py", 'password = "password"'),
    ("tokenizer name", "a.py", 'tokenizer = "cl100k_base"'),
    ("token type", "a.py", 'token_type = "bearer"'),
    ("token URL", "a.py", 'TOKEN_URL = "https://oauth2.googleapis.com/token"'),
    ("number next to a token name", "a.json", '{"access_token_expires_in": 3600}'),
    ("placeholder DB URL", "a.md", "DATABASE_URL=postgresql://user:password@localhost:5432/app"),
    ("DB URL without password", "a.py", 'URL = "postgresql://localhost/app"'),
    ("DB URL with variables", "a.yml", "url: postgres://${PGUSER}:${PGPASSWORD}@db/app"),
    ("prose about passwords", "a.md", "Choose a password: it must have 12 characters or more."),
    ("short sk- word", "a.md", "Use sk-learn for this."),
]


@pytest.mark.parametrize(("label", "name", "text"), NOT_SECRETS, ids=[s[0] for s in NOT_SECRETS])
def test_ordinary_content_is_not_flagged(label: str, name: str, text: str) -> None:
    assert not looks_like_secret(text, name), label


SENSITIVE_NAMES = [
    ".env", ".env.local", "config/.env.production", "prod.env", ".envrc",
    "server.pem", "tls.key", "cert.crt", "cert.cer", "ca.der", "bundle.p7b", "cert.pfx",
    "store.p12", "keystore.jks", "app.keystore", "vault.kdbx", "key.ppk", "key.gpg",
    "id_rsa", "id_ed25519", "id_ecdsa.pub",
    "credentials", "credentials.json", ".aws/credentials", ".aws/config",
    "application_default_credentials.json", "gcp-credentials.json", "service-account.json",
    "service_account_key.json", "secrets.yaml", "config/secrets.json",
    ".netrc", ".npmrc", ".pypirc", ".htpasswd", ".git-credentials", ".pgpass", ".my.cnf",
    ".docker/config.json", ".dockercfg", "kubeconfig", ".kube/config", "client.ovpn",
    "terraform.tfvars", "prod.auto.tfvars", "terraform.tfstate", "terraform.tfstate.backup",
    "local.settings.json", "wp-config.php",
]  # fmt: skip


@pytest.mark.parametrize("path", SENSITIVE_NAMES)
def test_sensitive_names(path: str) -> None:
    assert sensitive_spec().match_file(path), path


@pytest.mark.parametrize(
    "path",
    ["app/config.py", "README.md", "docker-compose.yml", "id.py", "keys_test.py",
     "src/secret_scan.py", "appsettings.json", "main.tf"],
)  # fmt: skip
def test_ordinary_names_are_not_sensitive(path: str) -> None:
    assert not sensitive_spec().match_file(path), path
