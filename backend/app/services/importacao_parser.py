"""Parser de arquivo para a pipeline de importação de vendas (RN07, item 6
de "Ordem de implementação" em docs/modelo-dados.md).

Só CSV no MVP (biblioteca padrão, sem dependência nova) — Excel fica para
quando uma biblioteca de leitura (ex.: openpyxl) for explicitamente
autorizada; PDF nunca entra aqui, é sempre um fluxo assistido separado
(Documento Mestre V1.2, seção 9).

Erros de leitura do arquivo em si (vazio, ilegível, sem cabeçalho, sem as
colunas obrigatórias) são críticos e abortam a importação inteira antes de
qualquer linha ser processada — não confundir com erros de linha
(produto/lote não encontrado, saldo insuficiente), que são tratados linha
a linha pelo serviço de orquestração, ainda não implementado.
"""

import csv
import io

COLUNAS_OBRIGATORIAS = ("referencia_externa", "produto", "quantidade")


class ArquivoInvalido(Exception):
    pass


def parsear_csv(conteudo: bytes) -> list[dict[str, str]]:
    """Lê um CSV de importação de vendas e retorna as linhas de dados, na
    ordem do arquivo, como dicts (nome da coluna -> valor bruto). O
    `numero_linha` de cada uma é a posição na lista retornada (1-based),
    atribuído por quem chama — este parser não o embute."""
    if not conteudo:
        raise ArquivoInvalido("Arquivo vazio.")

    try:
        # utf-8-sig: tolera o BOM que planilhas costumam gravar na frente
        # de um CSV exportado, sem exigir que quem gerou o arquivo saiba
        # disso.
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ArquivoInvalido("Arquivo não está em UTF-8 válido.") from exc

    leitor = csv.DictReader(io.StringIO(texto))
    if leitor.fieldnames is None:
        raise ArquivoInvalido("Arquivo sem cabeçalho.")

    colunas_presentes = {nome.strip() for nome in leitor.fieldnames if nome}
    colunas_faltando = [
        coluna for coluna in COLUNAS_OBRIGATORIAS if coluna not in colunas_presentes
    ]
    if colunas_faltando:
        raise ArquivoInvalido(
            f"Colunas obrigatórias ausentes: {', '.join(colunas_faltando)}."
        )

    linhas = [dict(linha) for linha in leitor]
    if not linhas:
        raise ArquivoInvalido("Arquivo sem nenhuma linha de dados.")

    return linhas
