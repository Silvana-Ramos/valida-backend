"""Testes unitários de app/core/telefone.py — regra estrita aprovada:
exige DDI 55, sem tentar completar/adivinhar o código do país."""

import pytest

from app.core.telefone import normalizar_telefone


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("5511999998888", "5511999998888"),
        ("+55 11 99999-8888", "5511999998888"),
        ("55 (11) 99999-8888", "5511999998888"),
        ("55-11-99999-8888", "5511999998888"),
        ("551199998888", "551199998888"),  # fixo, 8 dígitos + DDD
    ],
)
def test_normaliza_formatos_validos(entrada, esperado):
    assert normalizar_telefone(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    [
        "11999998888",  # sem DDI
        "5511999998",  # curto demais
        "551199999888899",  # longo demais
        "",
        "abcdefg",
        "+1 555 123 4567",  # DDI de outro país
    ],
)
def test_rejeita_formatos_invalidos(entrada):
    with pytest.raises(ValueError):
        normalizar_telefone(entrada)
