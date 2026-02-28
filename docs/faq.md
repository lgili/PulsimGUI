# FAQ e Troubleshooting

## O app abre, mas não simula

1. Verifique backend ativo em `Preferences → Simulation`.
2. Confirme `pulsim` instalado no Python correto:

```bash
python3 -c "import pulsim; print(pulsim.__version__)"
```

3. Reinstale/atualize backend para `v0.5.0` no runtime settings.

## Erro de convergência transitória

Ações recomendadas (ordem):

1. Reduzir `Step size`.
2. Ajustar `Max step` para valor próximo de `Step size`.
3. Aumentar `Max iterations`.
4. Habilitar `Enable robust transient retries`.
5. Revisar parâmetros extremos de chaveamento/componentes.

## Erro de plugin Qt no Linux

```bash
QT_QPA_PLATFORM=offscreen python3 -m pulsimgui
```

Se necessário, instale bibliotecas XCB/GL:

```bash
sudo apt-get install -y libxkbcommon-x11-0 libxcb-xinerama0 libxcb-cursor0 libegl1 libgl1
```

## Erro no macOS ao abrir app empacotado

- Abra o app pela primeira vez com botão direito → **Open**.
- Em builds locais, rode pela linha de comando para inspecionar logs.

## Como reportar bug de forma útil

Inclua no issue:

- Versão do PulsimGui.
- Versão do backend (`pulsim`).
- Sistema operacional.
- Passos para reproduzir.
- Projeto `.pulsim` mínimo e logs/traceback.
