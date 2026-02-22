# Instalação e Execução

## Requisitos

- Python `>= 3.10`
- `pip`
- Ambiente virtual recomendado (`venv`)

## Instalar a partir do PyPI

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

## Rodar localmente a partir do repositório

```bash
git clone https://github.com/lgili/PulsimGui.git
cd PulsimGui
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"
python3 -m pulsimgui
```

## Diagnóstico rápido de ambiente

Se quiser validar o backend instalado no mesmo Python:

```bash
python3 -c "import pulsim; print(pulsim.__version__)"
```

## Problemas comuns

### Erro de plugin Qt

Se ocorrer erro de plataforma Qt, execute com plugin explícito:

```bash
QT_QPA_PLATFORM=cocoa python3 -m pulsimgui
```

No Linux headless:

```bash
QT_QPA_PLATFORM=offscreen python3 -m pulsimgui
```

### Backend não encontrado

Abra `Preferences > Simulation > Backend Runtime` e rode **Install / Update Backend** com alvo `v0.4.0`.
