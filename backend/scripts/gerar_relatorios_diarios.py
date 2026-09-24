"""Ponto de entrada executável do job diário de geração automática do
relatório de ação preventiva (Gestão Preventiva — Fase 1, execução
automática). Desacoplado do processo do FastAPI — chamado por um
agendador externo (cron do Railway, Task Scheduler, ou equivalente). Não
faz parte da aplicação web; roda como um script avulso, com sua própria
`Session`.

Idempotente por natureza, via
relatorio_acao_diaria_service.gerar_ou_obter (chamada internamente por
gerar_para_mercados_ativos): pode ser executado com a frequência que o
agendador externo definir (ex.: a cada 30 minutos) sem gerar relatórios
duplicados nem retroativos.

Uso: `python scripts/gerar_relatorios_diarios.py` (a partir de
`backend/`). Sai com código 1 se algum mercado falhou durante o
processamento (os demais são processados normalmente — ver
`app/services/relatorio_acao_diaria_service.py::gerar_para_mercados_ativos`),
0 caso contrário.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.services.relatorio_acao_diaria_service import gerar_para_mercados_ativos  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        resumo = gerar_para_mercados_ativos(db)
    finally:
        db.close()

    print(f"Mercados ativos com relatorio_diario_ativo: {resumo.total_mercados_ativos}")
    print(f"Relatorios gerados/obtidos nesta execucao: {resumo.total_processados}")
    print(f"Mercados aguardando o horario configurado: {resumo.total_aguardando_horario}")

    if resumo.mercados_sem_horario_configurado:
        print(
            f"Mercados com relatorio_diario_ativo=True mas sem horario_relatorio_diario "
            f"configurado ({len(resumo.mercados_sem_horario_configurado)}):"
        )
        for id_mercado in resumo.mercados_sem_horario_configurado:
            print(f"  - mercado {id_mercado}")

    if resumo.erros:
        print(f"Erros ({len(resumo.erros)}):")
        for erro in resumo.erros:
            print(f"  - {erro}")
        sys.exit(1)


if __name__ == "__main__":
    main()
