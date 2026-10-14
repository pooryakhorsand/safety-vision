"""
Django settings for the web application.

Secrets and machine-specific values (database, paths, tokens) come from the
.env file. Customer-specific values (language, time zone,
branding, retention) come from the active profile in profiles/<SITE_PROFILE>/.
"""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# --- Paths -------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # .../web
PROJECT_ROOT = BASE_DIR.parent  # the folder that holds VERSION, profiles/, engine/, web/

# Installed desktop app: everything the system writes lives in APP_DATA_DIR (config, database,
# snapshots, logs, models). Development: APP_DATA_DIR is not set and the project folder is used.
APP_DATA_DIR = Path(os.environ["APP_DATA_DIR"]).resolve() if os.environ.get("APP_DATA_DIR") else None

load_dotenv((APP_DATA_DIR / "config" if APP_DATA_DIR else PROJECT_ROOT) / ".env")

from apps.core.profile_loader import get_profile  # noqa: E402  (needs .env loaded first)

SITE_PROFILE = get_profile()

# One version for the whole product: the VERSION file in the project root.
_version_file = PROJECT_ROOT / "VERSION"
APP_VERSION = _version_file.read_text(encoding="utf-8").strip() if _version_file.is_file() else "0.0.0"

# Runtime data written by the system (snapshots, clips, backups).
# Keep it outside the code folder so updates never touch it.
DATA_DIR = APP_DATA_DIR or Path(os.environ.get("DATA_DIR") or PROJECT_ROOT / "data").resolve()


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# --- Security ----------------------------------------------------------------
DEBUG = env_bool("DJANGO_DEBUG", False)

MIN_SECRET_LENGTH = 32
PLACEHOLDER_SECRETS = {"", "change-me", "change-me-engine-token", "dev-engine-token"}


def require_secret(name: str, value: str) -> None:
    """Outside development a secret must be set, not a known placeholder, and long enough."""
    if value in PLACEHOLDER_SECRETS or len(value) < MIN_SECRET_LENGTH:
        raise ImproperlyConfigured(
            f"{name} must be a random string of at least {MIN_SECRET_LENGTH} characters. "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(50))"'
        )


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if DEBUG:
    SECRET_KEY = SECRET_KEY if SECRET_KEY not in PLACEHOLDER_SECRETS else "dev-only-insecure-key"
else:
    require_secret("DJANGO_SECRET_KEY", SECRET_KEY)

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()
]

# --- Applications ------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Project apps (see README "Project map")
    "apps.core",
    "apps.accounts",
    "apps.cameras",
    "apps.vision_modules",
    "apps.people",
    "apps.events",
    "apps.dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves static files without a separate web server
    "django.contrib.sessions.middleware.SessionMiddleware",
    "apps.core.middleware.DefaultLanguageMiddleware",  # language chosen at first run, for new visitors
    "django.middleware.locale.LocaleMiddleware",  # picks fa / en per user
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.core.middleware.FirstRunMiddleware",  # no user yet -> /setup/
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "web_config.urls"
WSGI_APPLICATION = "web_config.wsgi.application"
ASGI_APPLICATION = "web_config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.brand_context",
            ],
        },
    },
]

# --- Database ----------------------------------------------------------------
# One line in .env chooses the database:
#   (empty)                                     -> SQLite file web/db.sqlite3 (development)
#   DATABASE_URL=postgres://user:pass@host:5432/name  -> PostgreSQL (production)
DATABASES = {
    "default": dj_database_url.parse(
        os.environ.get("DATABASE_URL")
        or f"sqlite:///{((DATA_DIR / 'db' / 'db.sqlite3') if APP_DATA_DIR else (BASE_DIR / 'db.sqlite3')).as_posix()}",
        conn_max_age=60,
        conn_health_checks=True,
    )
}

if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    Path(DATABASES["default"]["NAME"]).parent.mkdir(parents=True, exist_ok=True)
    # WAL mode lets the dashboard read while events are being written.
    DATABASES["default"]["OPTIONS"] = {
        "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        "transaction_mode": "IMMEDIATE",
    }
    DATABASES["default"]["CONN_MAX_AGE"] = 0

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Event storage, retention and backups -------------------------------------
# Snapshots and clips are files on disk; the database stores only their paths.
# They are served through a login-protected view, never as public files.
MEDIA_ROOT = DATA_DIR / "media"
MEDIA_URL = "/media/"  # not routed publicly (see apps/events/views.py)

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR") or DATA_DIR / "backups").resolve()
BACKUP_KEEP = int(os.environ.get("BACKUP_KEEP", "14"))  # number of daily backups kept

EVENT_RETENTION_DAYS = SITE_PROFILE.retention_days  # from profile.yaml

# --- Engine connection --------------------------------------------------------
# The engine (separate process) sends events to /api/events/ with this token:
#   Authorization: Bearer <ENGINE_API_TOKEN>
ENGINE_API_TOKEN = os.environ.get("ENGINE_API_TOKEN", "")
if not DEBUG:
    require_secret("ENGINE_API_TOKEN", ENGINE_API_TOKEN)

# The engine reports it is alive with POST /api/engine/heartbeat/ every few seconds.
# No heartbeat for this long = "Engine offline" in the status bar.
ENGINE_HEARTBEAT_TIMEOUT_SECONDS = int(os.environ.get("ENGINE_HEARTBEAT_TIMEOUT_SECONDS", "20"))

# Where the browser finds the engine's live pictures (MJPEG): <img src="<this>/stream/<camera id>">.
# Use an address the OPERATOR's browser can reach (not 127.0.0.1 when the console is opened from another PC).
ENGINE_STREAM_URL = os.environ.get("ENGINE_STREAM_URL", "http://127.0.0.1:8765").rstrip("/")

# The last heartbeat is kept in a small file cache shared by all web processes.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": str(DATA_DIR / "cache"),
    }
}

# Largest snapshot the engine may upload (bytes).
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# --- Authentication ----------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:overview"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# A control-room shift is long: keep the session for 12 hours.
SESSION_COOKIE_AGE = 12 * 60 * 60

# --- Languages (fa = right-to-left, en = left-to-right) -----------------------
LANGUAGE_CODE = SITE_PROFILE.default_language
LANGUAGES = [
    ("fa", "فارسی"),
    ("en", "English"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True

TIME_ZONE = SITE_PROFILE.time_zone
USE_TZ = True

# --- Static files ------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [
    BASE_DIR / "static",
    ("profile", SITE_PROFILE.assets_dir),  # served as /static/profile/<file>
]
STATIC_ROOT = BASE_DIR / "staticfiles"  # filled by "manage.py collectstatic" when the app is built

# --- Logging -----------------------------------------------------------------
# Console plus a rotating file (10 MB x 5) in <data folder>/logs/web.log.
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "plain",
            "filename": str(LOG_DIR / "web.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
        },
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
}
