"""Normalização de número de WhatsApp para o formato E.164 sem `+`
(ex.: `5511999998888`) — o mesmo formato que a Cloud API da Meta envia em
`messages[].from` nos webhooks (fase futura). Usada nos validadores de
`schemas/mercado.py` e `schemas/usuario.py` para que `telefone_whatsapp`
já seja gravado normalizado, permitindo casar o número recebido no
webhook com uma busca direta por igualdade de string.

Regra estrita, aprovada explicitamente: exige o DDI 55 informado — não
tenta adivinhar/completar o código do país quando ausente, para não
gravar silenciosamente um número errado.
"""

import re

PADRAO_TELEFONE_NORMALIZADO = re.compile(r"55\d{10,11}")


def normalizar_telefone(telefone: str) -> str:
    digitos = re.sub(r"\D", "", telefone)
    if not PADRAO_TELEFONE_NORMALIZADO.fullmatch(digitos):
        raise ValueError(
            "Telefone inválido: informe o número completo com código do país, "
            "ex.: 5511999998888 (DDI 55 + DDD + número)."
        )
    return digitos
