# Configuração de Simulação

Esta página descreve os parâmetros reais expostos na janela **Simulation Settings** e no runtime de backend.

![Tela de Simulation Settings](../assets/images/simulation-settings.svg)

## Solver & Time

Parâmetros principais da análise transitória:

- `Integration method`:
  - `Auto (Backend default)`
  - `Trapezoidal`
  - `BDF1`, `BDF2`, `BDF3`, `BDF4`, `BDF5`
  - `Gear`, `TRBDF2`, `RosenbrockW`, `SDIRK2`
- `Step mode`: `Fixed step` ou `Variable step`
- `Start time`
- `Step size`
- `Stop time`
- `Max step`
- `Relative tolerance`
- `Absolute tolerance`

## Events & Output

- `Enable simulation event detection`
- `Max step retries`
- `Output points`
- `Effective step` (calculado automaticamente)
- Presets de duração: `1us` até `100ms`

## Advanced Section

### Transient Robustness

- `Max iterations` (Newton por passo)
- `Enable voltage limiting`
- `Max voltage step`
- `Enable robust transient retries`
- `Enable automatic regularization`

### DC Operating Point

- `Strategy`:
  - `Auto`
  - `Direct Newton`
  - `GMIN Stepping`
  - `Source Stepping`
  - `Pseudo-Transient`
- `GMIN initial` / `GMIN final` (quando `GMIN Stepping`)
- `Source steps` (quando `Source Stepping`)

## Backend Runtime (Preferences)

![Tela de Backend Runtime](../assets/images/backend-runtime.svg)

No caminho `Preferences → Simulation`:

- `Active backend`
- `Version`, `Status`, `Location`, `Capabilities`
- `Source`: `PyPI` ou `Local`
- `Target version`
- `Local path`
- `Auto-sync backend on startup`
- `Install / Update Backend`

## Perfil recomendado para começar

- Integração: `Auto`
- `Step mode`: `Fixed step`
- `Relative tolerance`: `1e-4`
- `Absolute tolerance`: `1e-6`
- `Output points`: `10000`
- Robustez transitória: habilitada
- Backend target: `v0.5.0`
