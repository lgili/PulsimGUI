# Instalação e Execução

## Requisitos

- Python `>= 3.10`
- `pip`
- Ambiente virtual recomendado (`venv`)

## Opção 1: Release (recomendado)

Baixe o pacote da sua plataforma em [Releases](https://github.com/lgili/PulsimGui/releases/latest).

## Opção 2: Instalação via pip

```bash
python3 -m pip install --upgrade pip
python3 -m pip install pulsimgui
```

Executar:

```bash
pulsimgui
```

ou:

```bash
python3 -m pulsimgui
```

## Opção 3: Rodar do código-fonte

```bash
git clone https://github.com/lgili/PulsimGui.git
cd PulsimGui
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"
python3 -m pulsimgui
```

## Validar backend ativo

```bash
python3 -c "import pulsim; print(pulsim.__version__)"
```

Valor esperado no projeto: `0.5.0`.

## Configuração recomendada no app

Abra `Preferences → Simulation → Backend Runtime`:

- `Source`: `PyPI`
- `Target version`: `v0.5.0`
- `Auto-sync backend on startup`: habilitado

## Problemas comuns

### Erro de plugin Qt

```bash
QT_QPA_PLATFORM=cocoa python3 -m pulsimgui
```

No Linux headless:

```bash
QT_QPA_PLATFORM=offscreen python3 -m pulsimgui
```

### Backend indisponível

- Confirme a instalação do `pulsim` no mesmo Python usado pelo app.
- Reabra o app e use `Install / Update Backend` na tela de runtime.
