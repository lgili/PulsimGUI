# FAQ and Troubleshooting

## The app opens but simulation does not run

1. Check the active backend in `Preferences → Simulation`.
2. Confirm `pulsim` is installed in the correct Python environment:

```bash
python3 -c "import pulsim; print(pulsim.__version__)"
```

3. Reinstall/update backend to `v0.5.3` from runtime settings.

## Transient convergence error

Recommended actions (in order):

1. Reduce `Step size`.
2. Set `Max step` closer to `Step size`.
3. Increase `Max iterations`.
4. Enable `Enable robust transient retries`.
5. Review extreme switching/component parameters.

## Qt plugin error on Linux

```bash
QT_QPA_PLATFORM=offscreen python3 -m pulsimgui
```

If needed, install XCB/GL libraries:

```bash
sudo apt-get install -y libxkbcommon-x11-0 libxcb-xinerama0 libxcb-cursor0 libegl1 libgl1
```

## Error opening packaged app on macOS

- Open the app once using right-click → **Open**.
- For local builds, launch from terminal to inspect logs.

## How to report a useful bug

Include in the issue:

- PulsimGui version.
- Backend (`pulsim`) version.
- Operating system.
- Reproduction steps.
- Minimal `.pulsim` project and traceback/logs.
