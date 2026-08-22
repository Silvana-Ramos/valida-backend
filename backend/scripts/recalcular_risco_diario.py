"""Ponto de entrada executável do job diário de recálculo de risco
(RN03). Desacoplado do processo do FastAPI — chamado por um agendador
externo (cron, Task Scheduler, ou o cron da hospedagem, ainda a
definir). Não faz parte da aplicação web; roda como um script avulso,
com sua própria `Session`.

Uso: `python scripts/recalcular_risco_diario.py` (a partir de
`backend/`). Sai com código 1 se algum lote falhou durante o
processamento (os demais são processados normalmente — ver
`app/services/recalculo_risco_service.py`), 0 caso contrário.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.services.recalculo_risco_service import recalcular_todos  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        resumo = recalcular_todos(db)
    finally:
        db.close()

    print(f"Lotes processados: {resumo.total_processados}")
    print(f"Lotes que mudaram de faixa de risco: {resumo.total_mudaram_faixa}")
    if resumo.erros:
        print(f"Erros ({len(resumo.erros)}):")
        for erro in resumo.erros:
            print(f"  - {erro}")
        sys.exit(1)


if __name__ == "__main__":
    main()
