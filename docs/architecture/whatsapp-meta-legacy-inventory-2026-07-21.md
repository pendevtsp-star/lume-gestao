# Inventario legado da Meta no modulo WhatsApp

Data da revisao: 21/07/2026.

## Estado operacional atual

O canal operacional exposto pelo Lume e o WhatsApp Web. A interface de integracoes, os testes controlados e a fila devem tratar esse canal como a unica jornada ativa. Este inventario apenas registra referencias historicas da integracao oficial; nenhuma credencial, coluna, migration ou dado foi removido nesta fase.

## Referencias encontradas

### Configuracao de ambiente

- `config/settings.py`: nomes de variaveis `WHATSAPP_META_API_VERSION`, `WHATSAPP_META_ACCESS_TOKEN` e `WHATSAPP_META_PHONE_NUMBER_ID`.
- Arquivos `.env` e valores de producao nao foram lidos, alterados ou documentados.

### Modelo e historico de banco

- `core/models.py`: opcao legada de provedor `meta` e campos de nome/idioma de template Meta.
- `core/migrations/0003_*`, `0009_*`, `0010_*`, `0011_*` e `0016_*`: historico necessario para reconstruir o schema existente.
- Essas migrations nao devem ser editadas ou apagadas.

### Runtime preservado

- `core/integrations/whatsapp.py`: implementacao historica do provedor oficial.
- `core/services/whatsapp_automation.py`: orquestracao da fila e protecoes de envio.
- Ambos ficaram fora do escopo desta fase e nao foram alterados.

### Compatibilidade e testes

- `core/tests.py`: cenarios que garantem que configuracoes antigas da Meta nao retomem controle da interface ou do envio por engano.
- Esses testes sao uma barreira de regressao e devem permanecer enquanto houver dados legados.

### Documentacao desatualizada

- `docs/WHATSAPP.md`: ainda recomenda Meta Cloud API e Embedded Signup como fluxo principal.
- O documento deve ser reescrito em uma fase propria, preservando uma secao historica de migracao e sem publicar exemplos de segredos reais.

## Condicoes para remocao futura

Antes de remover qualquer referencia, deve existir:

1. backup validado do banco de producao;
2. levantamento de registros que ainda usam `provider=meta` ou campos `meta_template_*`;
3. migration nova e reversivel para normalizar os registros;
4. confirmacao de que nenhum ambiente depende das variaveis Meta;
5. testes de fila, conexao e envio real pelo WhatsApp Web;
6. janela de deploy com rollback testado.

Enquanto esses requisitos nao forem cumpridos, o legado permanece armazenado, mas nao e apresentado como jornada operacional ao usuario.
