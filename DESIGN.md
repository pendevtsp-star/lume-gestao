---
name: Lume Gestao
description: Sistema clinico-operacional com linguagem calma, profissional e confiavel.
colors:
  primary: "#60724f"
  primary-soft: "#9aa57a"
  primary-tint: "#dfe7cf"
  neutral-app: "#eef1ec"
  neutral-page: "#f1eadc"
  neutral-surface: "#ffffff"
  neutral-surface-soft: "#f8f3e7"
  neutral-line: "#ded4bd"
  text-strong: "#263028"
  text-heading: "#2f3a2c"
  text-muted: "#6e7469"
  accent-sand: "#cdb48d"
  accent-sand-soft: "#efe2c9"
  accent-rose: "#b86d92"
  success: "#31705b"
  warning: "#a76d1b"
  danger: "#9f3d38"
typography:
  display:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "34px"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "0"
  headline:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "20px"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "0"
  title:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "15px"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "0"
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "14px"
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: "0"
  label:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "11px"
    fontWeight: 900
    lineHeight: 1.2
    letterSpacing: "0.08em"
rounded:
  sm: "8px"
  md: "10px"
  lg: "14px"
  xl: "18px"
  hero: "22px"
  pill: "999px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "18px"
  lg: "20px"
  xl: "28px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#fffdf4"
    typography: "{typography.title}"
    rounded: "12px"
    padding: "0 15px"
    height: "42px"
  button-secondary:
    backgroundColor: "#fffaf0"
    textColor: "{colors.text-strong}"
    typography: "{typography.title}"
    rounded: "12px"
    padding: "0 15px"
    height: "42px"
  panel-default:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.text-strong}"
    rounded: "{rounded.sm}"
    padding: "18px"
  input-default:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.text-strong}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "9px 11px"
    height: "42px"
  login-input:
    backgroundColor: "#fbfcfb"
    textColor: "{colors.text-strong}"
    typography: "{typography.body}"
    rounded: "12px"
    padding: "9px 11px"
    height: "52px"
  status-pill:
    backgroundColor: "{colors.neutral-surface-soft}"
    textColor: "{colors.text-muted}"
    typography: "{typography.title}"
    rounded: "{rounded.pill}"
    padding: "0 14px"
    height: "34px"
---

# Design System: Lume Gestao

## 1. Overview

**Creative North Star: "A mesa de operacao tranquila"**

Lume Gestao e um sistema de rotina clinica que precisa parecer estavel antes de parecer bonito. A interface parte de uma base clara, silenciosa e previsivel, com tons naturais controlados, superficies bem definidas e uma hierarquia que ajuda a equipe a agir rapido sem entrar em estado de alerta visual o tempo todo. O produto tem densidade real de sistema, mas organiza essa densidade com ritmo, blocos legiveis e acoes bem identificadas.

O sistema rejeita dois extremos: a frieza burocratica de software hospitalar e a plasticidade generica de templates SaaS. A linguagem visual precisa ser profissional sem ser impessoal, acolhedora sem ser leve demais, e madura sem parecer antiga. A sensacao correta e de um sistema que acompanha o trabalho da clinica, nao de um produto tentando vender a si mesmo em cada tela.

**Key Characteristics:**
- base clara com contraste suave e tinta escura confiavel
- acento verde-sage usado como direcao, nao como decoracao solta
- estruturas de painel, lista e formulario com leitura imediata
- densidade operacional em desktop com simplificacao responsiva em mobile
- consistencia entre modulos acima de exibicionismo visual

## 2. Colors

A paleta da Lume trabalha como um sistema de neutros aquecidos com acento herbal. O verde principal orienta foco, navegacao e acao primaria; os neutros fazem o trabalho pesado de legibilidade e organizacao.

### Primary
- **Sage operacional** (`#60724f`): cor principal de acoes, navegacao ativa, badges de contexto e pontos de orientacao. E a assinatura do sistema, mas nunca deve dominar a tela inteira.
- **Sage estrutural** (`#9aa57a`): apoio para gradientes leves, blocos destacados e superficies com prioridade secundaria.
- **Sage de apoio** (`#dfe7cf`): fundo de reforco suave para estados positivos, realces de selecao e zonas de leitura guiada.

### Secondary
- **Areia clinica** (`#cdb48d`): acento quente usado com parcimonia em detalhes de apoio, ritmo de superficie e conexao com a identidade fisica da clinica.
- **Areia suave** (`#efe2c9`): preenchimento leve para fundos auxiliares e atmosferas mais acolhedoras em modulos especificos.

### Tertiary
- **Rose editorial** (`#b86d92`): acento raro para pontos de contraste ou comunicacao secundaria. Nao deve competir com o verde principal.

### Neutral
- **Nuvem operacional** (`#eef1ec`): fundo geral do app shell. Carrega a pagina inteira sem virar branco estourado.
- **Papel aquecido** (`#f1eadc`): base externa e pagina de login. Introduz calor controlado sem cair em bege decorativo.
- **Superficie limpa** (`#ffffff`): paines, cards e areas de trabalho principais.
- **Superficie suave** (`#f8f3e7`): estados vazios, blocos auxiliares e superfícies de suporte.
- **Linha morna** (`#ded4bd`): bordas, separadores e estrutura silenciosa.
- **Tinta de leitura** (`#263028`): corpo, dados e textos operacionais.
- **Tinta de titulo** (`#2f3a2c`): headings e pontos de ancora.
- **Cinza de apoio** (`#6e7469`): metadados, explicacoes e texto secundario.

### Named Rules
**The One Calm Accent Rule.** O verde principal e a unica voz de acao do sistema. Se outra cor competir por prioridade na mesma tela, a tela esta errada.

**The Warmth Is Structural Rule.** O calor da interface vem do papel, da areia e da composicao. Nunca de um festival de cores quentes espalhadas em botoes e estados.

## 3. Typography

**Display Font:** Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
**Body Font:** Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
**Label/Mono Font:** o mesmo stack do corpo, sem familia paralela

**Character:** a tipografia da Lume e direta, compacta e funcional. Ela evita teatralidade de branding e se apoia em peso, espacamento e contraste de tamanho para organizar a operacao.

### Hierarchy
- **Display** (800, `34px`, line-height `1`): reservado a metricas e pontos de numero-chave. Serve para leitura imediata, nao para grandes manifestos visuais.
- **Headline** (800, `20px`, line-height `1.1`): usado em topbar, cabecalhos de painel e aberturas de pagina.
- **Title** (800, `15px`, line-height `1.1`): botoes, nomes curtos, rotulos de destaque e pequenas ancoras internas.
- **Body** (500, `14px`, line-height `1.5`): corpo textual principal, tabelas, resumos e textos corridos da interface.
- **Label** (900, `11px`, letter-spacing `0.08em`, uppercase): categorias, selos, tags de contexto e pequenos marcadores estruturais.

### Named Rules
**The No Heroics Rule.** Em Lume Gestao, titulo grande serve para orientar, nao para performar. Se uma tela parecer marketing, a tipografia passou do ponto.

**The Dense But Legible Rule.** Informacao pode ser densa, mas nunca comprimida. O peso resolve prioridade; o tamanho resolve ritmo; o espacamento resolve respiracao.

## 4. Elevation

Lume usa um sistema hibrido de borda visivel e sombra ambiente suave. A profundidade nao e dramatica; ela existe para separar camadas operacionais e tornar paines clicaveis ou focados mais confiaveis. A base da interface deve parecer assentada, e nao flutuando.

### Shadow Vocabulary
- **Ambient panel** (`0 18px 42px rgba(58, 70, 50, 0.10)`): sombra padrao de metricas e paines principais. E uma sombra de presenca, nao de efeito.
- **Card hover lift** (`0 16px 34px rgba(53, 66, 45, 0.12)`): usada em quick actions e elementos acionaveis que sobem um nivel na interacao.
- **Floating support** (`0 18px 42px rgba(32, 48, 28, 0.20)`): reservada a barras flutuantes e elementos de apoio persistente em mobile.

### Named Rules
**The Flat-At-Rest Rule.** Nenhum elemento deve parecer inflado por sombra pesada em repouso. Se a sombra chama mais atencao que a informacao, ela falhou.

## 5. Components

### Buttons
- **Shape:** retangulos suaves com canto controlado (`12px` no uso principal; `10px` em acoes menores; `999px` apenas em pílulas e flutuantes).
- **Primary:** fundo sage operacional (`#60724f`), texto claro (`#fffdf4`), peso forte e altura previsivel (`42px` ou `54px` no login).
- **Hover / Focus:** escurecimento do fundo primario para `#50583a` ou aumento leve de contraste; foco visivel por borda/sombra, nunca sumido.
- **Secondary / Ghost / Danger:** secundarios usam fundo claro aquecido e borda suave; ghost e contido e utilitario; danger trabalha com vermelho translúcido, nunca com vermelho saturado em bloco pesado.

### Chips
- **Style:** pills compactas (`34px` de altura, `999px` de raio) com tipografia forte e leitura instantanea.
- **State:** variantes de sucesso, aviso, perigo e neutro usam fundos bem claros e texto saturado suficiente para nao virar poeira visual.

### Cards / Containers
- **Corner Style:** cards-base em `8px`; superficies especiais sobem para `14px`, `18px` ou `22px` quando precisam separar momentos de jornada.
- **Background:** branco limpo em paines operacionais; quentes suaves em quick actions e estados vazios guiados.
- **Shadow Strategy:** sempre combinada com borda estrutural. Painel sem borda ou com sombra exagerada sai da linguagem do produto.
- **Border:** linha morna (`#ded4bd`) ou variantes translúcidas da familia sage.
- **Internal Padding:** faixa principal entre `18px` e `20px`, evitando componentes apertados.

### Inputs / Fields
- **Style:** campos com fundo claro, borda delicada e cantos suaves. No sistema geral, base de `42px`; no login, `52px` para mais conforto e clareza.
- **Focus:** borda puxando para o sage e halo leve de baixa opacidade. Foco precisa ser perceptivel sem parecer neon.
- **Error / Disabled:** erro usa vermelho controlado com mensagem clara; disabled reduz contraste e interatividade, sem apagar legibilidade.

### Navigation
- **Style:** sidebar clara com grupos nomeados, icones em caixas suaves, summaries expansivos e submenu com borda de continuidade.
- **State:** hover puxa o item para fundo branco; ativo deve parecer selecionado por presenca e contraste, nao por excesso de cor.
- **Mobile treatment:** a navegacao encolhe, mas o vocabulário visual permanece o mesmo. Nao existe uma “segunda interface” para mobile.

### Login Surface
- **Style:** split layout com painel de confiança à esquerda e autenticacao à direita, envolto por uma moldura única (`22px`).
- **Tone:** mais acolhedor que o restante do sistema, mas ainda com disciplina visual de produto.
- **Goal:** transformar uma tela fria de acesso em um ponto de entrada coerente com a marca, sem criar uma landing page paralela.

### Operational Feedback
- **Anatomia:** tres pontos curtos: leitura principal, atencao e proximo passo. O componente orienta decisao; nao repete o titulo da pagina.
- **Desktop / mobile:** tres colunas no desktop e uma coluna no celular, sem rolagem horizontal.
- **Uso:** relatorios, financeiro, checkout e modulos com fluxo menos frequente.

### Empty States
- **Anatomia:** resultado atual, contexto e uma acao recomendada quando houver algo util a fazer.
- **Sucesso:** confirma que nao existe pendencia sem transformar a ausencia em alerta.
- **Evitar:** linhas de tabela com apenas "nenhum registro" e sem explicar o proximo passo.

### Responsive Tables
- **Marcacao:** tabelas operacionais usam `responsive-table`; cada celula recebe `data-label` equivalente ao cabecalho.
- **Mobile:** cada linha vira um bloco legivel, preservando a ordem dos dados e mantendo a acao por ultimo.
- **Acoes:** ver, editar, receber, reagendar, confirmar e cancelar seguem esta ordem; a acao destrutiva nunca aparece como primaria.

### Status And Sensitive Flows
- **Badges:** verde para concluido/ativo, ambar para pendente/atencao, vermelho controlado para falha/cancelamento e neutro para estados informativos.
- **Erros:** toda mensagem sensivel informa problema, causa provavel e proximo passo.
- **Microcopy:** pagamento, remarcacao, presenca e integracoes dizem o que sera alterado antes da confirmacao.

### PWA
- **Instalacao:** o botao so aparece quando o navegador emite `beforeinstallprompt`; nunca prometa instalacao onde o recurso nao esta disponivel.
- **Cache:** apenas shell e ativos estaticos. Dados clinicos, financeiros e respostas autenticadas permanecem online-first e fora do cache persistente.
- **Continuidade:** o app instalado usa as mesmas rotas, permissoes e estados do navegador.

## 6. Do's and Don'ts

### Do:
- **Do** usar o verde sage principal (`#60724f`) como ancora de acao, selecao e foco.
- **Do** manter superficies brancas ou quase brancas para tarefas de leitura, cadastro e comparacao.
- **Do** usar labels pequenos em uppercase (`11px`, `0.08em`) para organizar contexto sem disputar com o conteudo principal.
- **Do** preservar a consistencia entre agenda, pacientes, financeiro, conteudo e integracoes, mesmo quando cada modulo tiver pequenos acentos proprios.
- **Do** priorizar estados vazios, resumos operacionais e paines de acao que ensinem o proximo passo.

### Don't:
- **Don't** deixar a Lume com cara de app generico de dashboard SaaS com cards infinitos e excesso de brilho.
- **Don't** empurrar o sistema para um visual hospitalar frio, burocratico ou cinza demais.
- **Don't** infantilizar a interface com excesso de arredondamento, decoracao fofa ou contrastes frágeis.
- **Don't** transformar telas internas em landing pages disfarçadas, com copy promocional e headings teatrais.
- **Don't** quebrar a unidade visual entre modulos; se uma area parecer outro produto, ela esta fora do sistema.
