import secrets
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Security
    api_key: str = secrets.token_hex(32)
    api_title: str = "RadiusManager API"
    api_version: str = "1.0.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # FreeRADIUS
    freeradius_dir: str = "/etc/freeradius/3.0"
    fr_user: str = "freerad"
    fr_group: str = "freerad"
    fr_schema: str = "/etc/freeradius/3.0/mods-config/sql/main/mysql/schema.sql"

    # MariaDB / MySQL
    db_host: str = "localhost"
    db_port: int = 53360
    db_socket: str = "/var/run/mysqld/mysqld.sock"
    db_root_user: str = "root"
    db_root_password: str = ""
    db_remote_host: str = "%"
    allow_remote_db: bool = True

    # Port auto-assign (FreeRADIUS)
    port_auth_start: int = 11000
    port_auth_step: int = 10

    # Script
    radius_manager_script: str = "./radius-manager.sh"

    # Instance API deployment
    api_instances_dir: str = "/root"
    api_git_repo: str = "https://github.com/heirro/freeradius-api/"
    api_port_start: int = 9100
    api_port_registry: str = "/root/.api_port_registry"


@lru_cache
def get_settings() -> Settings:
    return Settings()
