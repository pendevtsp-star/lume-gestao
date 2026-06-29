# Fisioterapia em Casa

Modulo de videos sob assinatura para pacientes da clinica. O MVP usa a mesma instancia Django da clinica, mantendo banco e dominio isolados por cliente.

## Rotas

- Painel interno: `/conteudos/`
- Portal do assinante: `/pilates-em-casa/`
- Biblioteca autenticada: `/pilates-em-casa/biblioteca/`
- Webhook Asaas: `/conteudos/webhooks/asaas/`

No host publico, `clinicafisiolume.com.br/pilates-em-casa/` fica disponivel quando `HOMECARE_PUBLIC_ENABLED=True`.

## Flags de ativacao

Use essas flags para separar instalacao, homologacao e operacao real:

```text
HOMECARE_ENABLED=True
HOMECARE_INTERNAL_ENABLED=True
HOMECARE_PUBLIC_ENABLED=True
HOMECARE_CHECKOUT_ENABLED=False
HOMECARE_WEBHOOK_ENABLED=False
HOMECARE_UPLOAD_WORKER_ENABLED=True
```

Modo recomendado agora:

- `HOMECARE_ENABLED=True`: tabelas, codigo e rotas protegidas prontos.
- `HOMECARE_INTERNAL_ENABLED=True`: equipe consegue preparar categorias, planos, videos e liberacoes manuais.
- `HOMECARE_PUBLIC_ENABLED=True`: portal publico disponivel para usuarios autenticados.
- `HOMECARE_CHECKOUT_ENABLED=False`: nenhuma venda online aparece ou processa.
- `HOMECARE_WEBHOOK_ENABLED=False`: webhook externo bloqueado ate fase de gateway.
- `ASAAS_DRY_RUN=True` e `BUNNY_STREAM_DRY_RUN=True`: nenhuma cobranca real e nenhum envio real ao Bunny.
- `HOMECARE_VIDEO_PROVIDER=local`: videos ficam em area protegida da VPS nesta fase inicial.

## Permissoes

- Profissional: cadastra e edita apenas os proprios videos.
- Administracao/Gerencia: gerenciam videos, categorias, planos, assinaturas e eventos de pagamento.
- Paciente ativo: acessa a biblioteca sem assinatura durante a fase inicial da clinica.
- Paciente inativo: nao acessa a biblioteca sem assinatura ativa.
- Compras, assinaturas e liberacoes manuais do canal continuam no codigo para uso comercial futuro, mas o checkout permanece desligado nesta fase.

## Videos Na VPS Agora

O upload pelo painel salva o arquivo temporariamente em `/media/homecare/uploads/`. O `worker` executa `process_homecare_uploads`, move o arquivo final para `/media/homecare/private/videos/` e remove o temporario quando conclui.

Os arquivos finais nao devem ficar publicos por `/media/`. Em producao, o Nginx bloqueia `/media/homecare/uploads/` e `/media/homecare/private/`. A reproducao passa por `/pilates-em-casa/videos/<slug>/assistir/`, onde o Django valida login, acesso, publicacao e lancamento programado antes de liberar o arquivo por `X-Accel-Redirect`.

Variaveis:

```text
HOMECARE_VIDEO_PROVIDER=local
HOMECARE_LOCAL_VIDEO_ACCEL_REDIRECT=True
HOMECARE_LOCAL_VIDEO_ACCEL_PREFIX=/protected-homecare-media/
HOMECARE_MAX_UPLOAD_MB=1024
HOMECARE_UPLOAD_BATCH_SIZE=3
```

## Bunny Stream Futuro

O Bunny Stream continua preservado no codigo para a fase comercial. Para migrar no futuro, troque `HOMECARE_VIDEO_PROVIDER=bunny`, configure as chaves e execute uma rotina de migracao dos arquivos locais para a biblioteca Bunny.

Variaveis:

```text
BUNNY_STREAM_DRY_RUN=True
BUNNY_STREAM_API_KEY=
BUNNY_STREAM_LIBRARY_ID=
BUNNY_STREAM_TIMEOUT=60
```

Mantenha `BUNNY_STREAM_DRY_RUN=True` enquanto a estrategia for local. Desative apenas quando Bunny for contratado/configurado.

## Asaas

O codigo usa uma camada de provider para permitir troca futura de gateway. O primeiro adapter implementado e o Asaas.

Variaveis:

```text
HOMECARE_PAYMENT_PROVIDER=asaas
ASAAS_DRY_RUN=True
ASAAS_BASE_URL=https://sandbox.asaas.com/api/v3
ASAAS_API_KEY=
ASAAS_WEBHOOK_TOKEN=
ASAAS_TIMEOUT=20
```

Configure no Asaas um webhook para:

```text
https://sistema.clinicafisiolume.com.br/conteudos/webhooks/asaas/
```

Use um token forte em `ASAAS_WEBHOOK_TOKEN`. Eventos repetidos sao tratados por `event_id` para evitar processamento duplicado.

## Sincronizacao financeira

Quando o webhook Asaas recebe `PAYMENT_CONFIRMED` ou `PAYMENT_RECEIVED`, o modulo:

1. Ativa/renova a assinatura do paciente.
2. Cria automaticamente uma receita recebida em `Financeiro > Cobrancas`.
3. Vincula a receita ao evento de pagamento do canal.
4. Reaproveita a mesma receita quando o mesmo pagamento aparecer em mais de um evento.

Essa receita usa `Charge` porque o pagamento do canal nao depende de uma mensalidade presencial da clinica.

## Pendencias combinadas

- Nao executar compra teste agora se puder gerar custo.
- Lembrar de fazer uma compra teste ao final da implementacao do modulo, preferencialmente em sandbox. Se o provedor exigir ambiente real, validar antes com o cliente e usar valor minimo.

## Deploy

Para homologacao inicial, com portal disponivel apenas para usuarios autenticados:

1. Fazer backup da VPS.
2. Aplicar migracoes.
3. Configurar as flags de homologacao acima.
4. Executar:

```bash
python manage.py bootstrap_homecare_homologation
```

5. Para liberar acesso manual a um paciente especifico, caso seja necessario testar uma assinatura futura:

```bash
python manage.py bootstrap_homecare_homologation --patient-id ID_DO_PACIENTE --access-days 30
```

Use `--patient-email email@dominio.com` apenas se o cadastro tiver e-mail unico e revisado.

Antes de liberar dados reais:

1. Fazer backup da VPS.
2. Aplicar migracoes.
3. Validar `/healthz/`.
4. Testar painel interno em `/conteudos/`.
5. Testar upload com `HOMECARE_VIDEO_PROVIDER=local`.
6. Liberar manualmente um paciente de homologacao.
7. Testar login no portal com paciente ativo e com profissional/gestao.
8. Testar webhook Asaas em sandbox somente quando `HOMECARE_WEBHOOK_ENABLED=True`.
9. Fazer compra teste do canal apenas no fim da implementacao, evitando custo agora.
10. Migrar para Bunny e remover dry-run somente depois de confirmar volume, custos, upload, assinatura, financeiro e acesso.

O Nginx possui limite maior apenas para `/conteudos/videos/`, preservando limite menor no restante da aplicacao, e bloqueia acesso direto aos arquivos de video do modulo.
