# Guia do Desenvolvedor

Guia para contribuir com código, testes e documentação no PulsimGui.

## Estrutura do projeto

```text
src/pulsimgui/
  commands/      # undo/redo
  models/        # dados de circuito/projeto
  services/      # simulação, backend, persistência
  views/         # interface Qt (janelas, painéis, viewer)
  presenters/    # integração de fluxos UI
  utils/         # utilitários
  resources/     # temas, ícones e branding

docs/            # documentação MkDocs Material
examples/        # projetos .pulsim de referência
tests/           # suíte pytest
```

## Setup de desenvolvimento

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"
```

## Executar aplicação local

```bash
python3 -m pulsimgui
```

## Qualidade e testes

```bash
ruff check src tests
pytest
```

Para ambientes sem display:

```bash
QT_QPA_PLATFORM=offscreen pytest
```

## Documentação local

```bash
python3 -m pip install -r docs/requirements.txt
mkdocs serve
mkdocs build --strict
```

## Convenções práticas

- Prefira mudanças pequenas e rastreáveis por PR.
- Sempre incluir teste de regressão em correções de bug.
- Evite acoplar lógica de simulação diretamente à camada de view.
- Ao alterar fluxo de simulação, valide exemplos em `examples/`.

## Pipeline de docs (GitHub Pages)

- Build de docs em PR e em `main`.
- Deploy automático em `main`/`workflow_dispatch` usando GitHub Pages Actions.
- Ponto de entrada: `.github/workflows/docs-pages.yml`.
