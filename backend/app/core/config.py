from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configurações básicas da aplicação.

    Nenhuma credencial de integração externa (WhatsApp, Meta, provedor de
    IA) é definida aqui ainda — isso entra em fases posteriores, mediante
    confirmação explícita.
    """

    app_name: str = "Valida"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg2://valida:valida@localhost:5432/valida"

    # Solução mínima para o piloto (sem alteração de banco/migration):
    # mapeia uma chave secreta por mercado -> id_mercado. Configurada só no
    # servidor, via variável de ambiente MERCADO_API_KEYS (JSON, ex.:
    # {"chave-secreta-mercado-1": 1}). O cliente nunca informa id_mercado
    # diretamente — só a chave, convertida internamente em app/core/security.py.
    # Mecanismo transitório: quando o webhook da Meta existir, o número de
    # WhatsApp verificado passa a ser a fonte de confiança principal.
    mercado_api_keys: dict[str, int] = {}

    # Chave única de administrador, para os endpoints admin-only de
    # onboarding de mercado (POST/PATCH /mercados, e o bootstrap do
    # primeiro usuário de um mercado novo). Configurada só no servidor,
    # via variável de ambiente ADMIN_API_KEY. `None` por padrão — nesse
    # caso, nenhuma requisição é autenticada como admin (falha fechada:
    # ver app/core/security.py).
    admin_api_key: Optional[str] = None

    class Config:
        env_file = ".env"


settings = Settings()
