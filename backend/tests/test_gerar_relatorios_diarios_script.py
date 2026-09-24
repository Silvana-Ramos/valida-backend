"""Testes unitários de scripts/gerar_relatorios_diarios.py — SessionLocal
e gerar_para_mercados_ativos são totalmente mockados via patch no próprio
módulo do script; nenhum teste aqui abre conexão real com o banco, nem
executa o script como processo externo (o script é importado e main() é
chamado diretamente, em processo)."""

from unittest.mock import MagicMock, patch

import pytest

import scripts.gerar_relatorios_diarios as script
from app.services.relatorio_acao_diaria_service import ResumoGeracaoDiaria


def _resumo(**overrides) -> ResumoGeracaoDiaria:
    base = dict(
        total_mercados_ativos=0,
        total_processados=0,
        total_aguardando_horario=0,
        mercados_sem_horario_configurado=[],
        erros=[],
    )
    base.update(overrides)
    return ResumoGeracaoDiaria(**base)


def test_sessionlocal_e_criada():
    db_mock = MagicMock(name="db")
    with (
        patch.object(script, "SessionLocal", return_value=db_mock) as session_local_mock,
        patch.object(script, "gerar_para_mercados_ativos", return_value=_resumo()),
    ):
        script.main()

    session_local_mock.assert_called_once_with()


def test_gerar_para_mercados_ativos_chamada_exatamente_uma_vez_com_a_sessao():
    db_mock = MagicMock(name="db")
    with (
        patch.object(script, "SessionLocal", return_value=db_mock),
        patch.object(script, "gerar_para_mercados_ativos", return_value=_resumo()) as gerar_mock,
    ):
        script.main()

    gerar_mock.assert_called_once_with(db_mock)


def test_db_close_e_chamado_sempre_em_execucao_normal():
    db_mock = MagicMock(name="db")
    with (
        patch.object(script, "SessionLocal", return_value=db_mock),
        patch.object(script, "gerar_para_mercados_ativos", return_value=_resumo()),
    ):
        script.main()

    db_mock.close.assert_called_once()


def test_execucao_sem_erros_termina_normalmente_sem_system_exit(capsys):
    db_mock = MagicMock(name="db")
    resumo = _resumo(total_mercados_ativos=2, total_processados=2)
    with (
        patch.object(script, "SessionLocal", return_value=db_mock),
        patch.object(script, "gerar_para_mercados_ativos", return_value=resumo),
    ):
        script.main()  # não deve levantar SystemExit

    saida = capsys.readouterr().out
    assert "Mercados ativos com relatorio_diario_ativo: 2" in saida
    assert "Relatorios gerados/obtidos nesta execucao: 2" in saida


def test_resumo_com_erros_imprime_erros_e_levanta_systemexit_1(capsys):
    db_mock = MagicMock(name="db")
    resumo = _resumo(erros=["mercado 7: falha simulada"])
    with (
        patch.object(script, "SessionLocal", return_value=db_mock),
        patch.object(script, "gerar_para_mercados_ativos", return_value=resumo),
    ):
        with pytest.raises(SystemExit) as exc_info:
            script.main()

    assert exc_info.value.code == 1
    saida = capsys.readouterr().out
    assert "Erros (1):" in saida
    assert "mercado 7: falha simulada" in saida
    db_mock.close.assert_called_once()  # fechou a sessão mesmo saindo com erro


def test_excecao_geral_inesperada_fecha_sessao_e_propaga():
    db_mock = MagicMock(name="db")
    with (
        patch.object(script, "SessionLocal", return_value=db_mock),
        patch.object(
            script, "gerar_para_mercados_ativos", side_effect=RuntimeError("falha geral")
        ),
    ):
        with pytest.raises(RuntimeError, match="falha geral"):
            script.main()

    db_mock.close.assert_called_once()


def test_resumo_mostra_mercados_aguardando_horario(capsys):
    db_mock = MagicMock(name="db")
    resumo = _resumo(total_mercados_ativos=1, total_aguardando_horario=1)
    with (
        patch.object(script, "SessionLocal", return_value=db_mock),
        patch.object(script, "gerar_para_mercados_ativos", return_value=resumo),
    ):
        script.main()

    saida = capsys.readouterr().out
    assert "Mercados aguardando o horario configurado: 1" in saida


def test_resumo_lista_mercados_sem_horario_configurado(capsys):
    db_mock = MagicMock(name="db")
    resumo = _resumo(total_mercados_ativos=2, mercados_sem_horario_configurado=[3, 8])
    with (
        patch.object(script, "SessionLocal", return_value=db_mock),
        patch.object(script, "gerar_para_mercados_ativos", return_value=resumo),
    ):
        script.main()

    saida = capsys.readouterr().out
    assert "sem horario_relatorio_diario" in saida
    assert "mercado 3" in saida
    assert "mercado 8" in saida
