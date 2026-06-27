# Modulo fiscal

## Resumo legal para a primeira versao

- Studios de pilates e fisioterapia prestam servicos. A emissao fiscal esperada, em regra, e NFS-e vinculada ao ISS do municipio da clinica.
- A Lei Complementar 116/2003 lista servicos sujeitos a ISS, incluindo atividades de saude e assistencia medica/paramedica. A prefeitura e o contador devem confirmar o item municipal correto para cada clinica.
- Cupom fiscal/NFC-e e voltado principalmente a operacoes de circulacao de mercadorias/ICMS. Para servicos, o modulo usa a nomenclatura "Cupom/recibo interno" e deixa claro que ele nao substitui NFS-e quando houver obrigacao fiscal.
- A autorizacao oficial de uma NFS-e depende do municipio, certificado/token, credenciamento e/ou provedor fiscal. O Lume registra e exporta documentos, mas so deve marcar emissao oficial quando a integracao estiver homologada.

## Integracoes recomendadas

- NFS-e Nacional ou portal da prefeitura: melhor quando o municipio ja oferece fluxo estavel e simples.
- Provedores como Focus NFe, PlugNotas, NFE.io e TecnoSpeed: bons candidatos quando a clinica precisa de API, homologacao, suporte a multiplos municipios, webhooks e ambiente de teste.
- Criterios para escolha: municipios atendidos, custo por nota, suporte a certificado/token, webhooks de autorizacao/cancelamento, sandbox, SLA e suporte ao regime tributario da clinica.

## O que foi implementado

- App `fiscal` com configuracao fiscal da clinica.
- Cadastro de documentos do tipo NFS-e ou cupom/recibo interno.
- Vinculo opcional com paciente, pagamento e cobranca.
- Calculo de ISS informativo.
- Emissao/registro controlado com referencia interna e codigo de verificacao.
- Exportacao em PDF.
- Envio por e-mail com PDF anexado.
- Envio de resumo por WhatsApp usando a integracao ja existente.
- Menu lateral com acesso ao modulo Fiscal.

## Proximo passo para emissao oficial

1. Confirmar com contador/prefeitura o codigo de servico, aliquota de ISS e exigencias do municipio.
2. Escolher provedor ou fluxo direto da prefeitura/NFS-e Nacional.
3. Configurar sandbox e credenciais reais.
4. Implementar transmissao, consulta, cancelamento e armazenamento do XML/retorno autorizado.

## Referencias

- Portal Nacional da NFS-e: https://www.gov.br/nfse/pt-br
- Lei Complementar 116/2003: https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp116.htm
- Tabela SPED com lista de servicos da LC 116/2003: https://sped.rfb.gov.br/pagina/show/1601
- Exemplo oficial de NFC-e como documento de varejo/ICMS: https://www.sef.sc.gov.br/saiba-mais/nfc-e-nota-fiscal-de-consumidor-eletronica
- Focus NFe NFS-e: https://focusnfe.com.br/produtos/nota-fiscal-servico-nfse/
- PlugNotas NFS-e: https://plugnotas.com.br/nfse/
- NFE.io NFS-e: https://nfe.io/docs/
