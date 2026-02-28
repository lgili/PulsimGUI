# Manual do Usuário

Guia operacional do PulsimGui para uso diário.

## 1. Criar e editar esquemas

### Inserção de componentes

- Arraste da biblioteca para a área central.
- Ou use atalhos de teclado quando disponíveis (ex.: `R`, `C`, `L`, `V`, `G`).

### Conexões

- Ative ferramenta de fio (`W`).
- Clique no pino de origem, roteie e finalize no pino de destino.
- Use junções para derivar nós.

### Edição rápida

- Seleção múltipla: `Ctrl + clique` ou caixa de seleção.
- Mover: arraste.
- Rotacionar: comando de rotação no esquema.
- Excluir: `Delete`.

## 2. Configurar parâmetros dos componentes

- Selecione o componente.
- Edite no **Properties Panel**.
- Use notação com prefixos SI quando aplicável (`k`, `m`, `u`, `n`).

## 3. Executar simulação

1. Abra `Simulation Settings`.
2. Configure janela de tempo, método de integração e tolerâncias.
3. Clique em **Run** (`F5`).
4. Acompanhe progresso na barra de status.

## 4. Analisar formas de onda

- Plote sinais de tensão/corrente no viewer.
- Use zoom e pan para inspeção local.
- Use cursores para medições de delta de tempo e amplitude.
- Compare múltiplos sinais para análise de fase e dinâmica.

## 5. Gerenciar projetos

- `File → Save` para persistir `.pulsim`.
- Use exemplos como base para novos estudos.
- Mantenha nomes de componentes/nós descritivos para facilitar debugging.

## 6. Boas práticas

- Comece com topologia mínima e valide progressivamente.
- Evite alterar muitos parâmetros de uma vez.
- Ao investigar convergência, ajuste primeiro `step size`, `max step` e robustez transitória.
- Mantenha backend fixado em `v0.5.0` em ambientes compartilhados.
