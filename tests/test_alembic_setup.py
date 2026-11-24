import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData

from app.core.config import settings
from app.infrastructure.database.base import Base, NAMING_CONVENTION

BACKEND_DIR = Path(__file__).resolve().parents[1]


class AlembicSetupTests(unittest.TestCase):
    def test_alembic_config_does_not_store_a_database_url(self) -> None:
        config = Config(str(BACKEND_DIR / "alembic.ini"))

        self.assertEqual(config.get_main_option("sqlalchemy.url"), "")
        self.assertEqual(
            Path(config.get_main_option("script_location")).resolve(),
            BACKEND_DIR / "alembic",
        )

    def test_migration_environment_loads_secret_url_from_settings(self) -> None:
        env_path = BACKEND_DIR / "alembic" / "env.py"
        source = env_path.read_text(encoding="utf-8")

        self.assertIn("settings.database_url.get_secret_value()", source)
        self.assertNotIn("postgresql+asyncpg://", source)

    def test_base_metadata_uses_stable_constraint_names(self) -> None:
        self.assertIsInstance(Base.metadata, MetaData)
        self.assertEqual(Base.metadata.naming_convention, NAMING_CONVENTION)

    def test_offline_migration_rendering_does_not_disclose_database_url(self) -> None:
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        output = io.StringIO()
        config.output_buffer = output

        with redirect_stdout(output):
            command.upgrade(config, "head", sql=True)

        self.assertNotIn(settings.database_url.get_secret_value(), output.getvalue())
