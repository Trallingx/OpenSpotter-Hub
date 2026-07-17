"""Module launcher for ``python -m app`` and the installed GUI command."""


def main() -> None:
    """Start OpenSpotter Control without importing Tk during package discovery."""
    from .main_v3 import main as run_application

    run_application()


if __name__ == "__main__":
    main()
