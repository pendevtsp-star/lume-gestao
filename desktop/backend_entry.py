import os
import sys
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ.setdefault("DB_ENGINE", "sqlite")
    os.environ.setdefault("LUME_DESKTOP", "True")

    data_dir = Path(os.environ.get("LUME_DATA_DIR", Path.cwd() / ".lume-data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "media").mkdir(parents=True, exist_ok=True)

    import django
    from django.core.management import call_command
    from waitress import serve

    django.setup()
    call_command("migrate", interactive=False, verbosity=1)
    call_command("collectstatic", interactive=False, verbosity=0)

    if os.environ.get("LUME_SEED_DEMO", "False") == "True":
        call_command("seed_demo")

    port = os.environ.get("LUME_PORT", "18780")
    host = os.environ.get("LUME_HOST", "127.0.0.1")
    from config.wsgi import application

    serve(application, host=host, port=int(port), threads=8)


if __name__ == "__main__":
    main()
