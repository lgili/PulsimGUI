# Backend Adapter

Visão técnica de como o PulsimGui converte o esquema da GUI e executa simulações no backend Pulsim.

## Arquitetura

```text
MainWindow
  -> SimulationService
      -> convert_gui_circuit()
      -> BackendLoader
          -> PulsimBackend | PlaceholderBackend
              -> CircuitConverter
              -> run_transient()
```

## Responsabilidades principais

### `SimulationService`

- Mantém `SimulationSettings` em memória.
- Converte projeto GUI para formato de simulação.
- Executa simulação em worker thread.
- Emite progresso, streaming de pontos e resultado final.

### `BackendLoader`

- Descobre backends disponíveis.
- Ativa backend preferido salvo em settings.
- Cai para backend de placeholder quando Pulsim não está disponível.

### `CircuitConverter`

- Mapeia componentes da GUI para `pulsim.Circuit`.
- Resolve nós elétricos e aliases.
- Ignora componentes apenas de instrumentação visual.
- Traduz parâmetros de waveform (incluindo chaves legadas como `td/tr/tf/pw/per`).

## Contratos de dados

### `BackendInfo`

Metadados para UI e seleção de backend: `identifier`, `version`, `status`, `capabilities`, `message`.

### `BackendCallbacks`

Hooks de execução:

- `progress(value, message)`
- `data_point(time, signals)`
- `check_cancelled()`
- `wait_if_paused()`

### `BackendRunResult`

Resultado normalizado:

- `time: list[float]`
- `signals: dict[str, list[float]]`
- `statistics: dict[str, Any]`
- `error_message: str`

## Boas práticas de operação

- Use backend fixado em `v0.5.0` para reprodutibilidade.
- Mantenha `Auto-sync` habilitado em ambientes de validação.
- Em falha de convergência, ajuste primeiro `step size`, `max step`, `max iterations` e robustez transitória.
