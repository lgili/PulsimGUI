# Configuração de Simulação

Esta página documenta os campos reais disponíveis hoje na GUI.

## Janela `Simulation Settings`

![Tela de Simulation Settings](../assets/images/simulation-settings.svg)

### Aba `Transient`

- `Start time`: início da simulação.
- `Stop time`: fim da simulação.
- `Time step`: passo base.
- `Quick Presets`: atalhos de duração (`1µs` a `100ms`).

### Aba `Solver`

#### Integration Method

- `Auto`
- `RK4 (Fixed Step)`
- `RK45 (Adaptive)`
- `BDF (Stiff)`

#### Newton Solver

- `Max iterations`
- `Enable voltage limiting`
- `Max voltage step`

#### DC Operating Point Strategy

- `Auto`
- `Direct Newton`
- `GMIN Stepping`:
  - `GMIN initial`
  - `GMIN final`
- `Source Stepping`
- `Pseudo-Transient`

#### Tolerances

- `Max step size`
- `Relative tolerance`
- `Absolute tolerance`

### Aba `Output`

- `Output points`
- `Effective step` (calculado automaticamente)
- `Save all node voltages`
- `Save branch currents`
- `Save power dissipation`

## Janela `Preferences > Simulation`

![Tela de Backend Runtime](../assets/images/backend-runtime.svg)

### Backend

- `Active backend`
- `Version`
- `Status`
- `Location`
- `Capabilities`

### Backend Runtime

- `Source`: `PyPI` ou `Local PulsimCore checkout`
- `Target version`: versão alvo do backend
- `Local path`: caminho do checkout local quando `Source=Local`
- `Auto-sync backend on startup`
- `Install / Update Backend`
- `Runtime status`

## Versão padrão do backend

No estado atual do projeto, o default é:

- `target_version = v0.4.0`

Isso é aplicado quando não existe valor salvo em settings.

## Recomendação prática

Para ter reprodutibilidade entre máquinas:

1. Manter `Source = PyPI`.
2. Fixar `Target version = v0.4.0` (ou versão aprovada do release).
3. Ativar `Auto-sync backend on startup` em ambientes de validação.
