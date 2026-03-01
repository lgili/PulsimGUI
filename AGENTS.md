<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

## Diretrizes de Testes para Agentes de IA

Estas regras são obrigatórias ao criar ou modificar testes.

### NÃO fazer

- Não introduzir testes não determinísticos.
  - Não usar aleatoriedade sem seed fixa.
  - Não depender de timing frágil (`sleep` arbitrário) para sincronização de UI.
- Não depender de rede, internet, clock real, timezone local, ou recursos externos instáveis.
- Não usar caminhos absolutos de máquina local.
- Não criar testes de GUI que exijam display real no CI.
- Não mascarar regressões com `xfail`/`skip` genérico sem justificativa técnica.
- Não quebrar compatibilidade da matriz CI (Linux/macOS/Windows, Python 3.10+).
- Não aumentar custo da suíte padrão com cenários pesados sem segmentação.

### PODE fazer

- Criar testes determinísticos com asserts claros e dados de entrada explícitos.
- Usar fixtures e `tmp_path` para isolar estado e evitar vazamento entre testes.
- Em testes Qt, preferir `qtbot`/event loop ao invés de `sleep`.
- Manter testes GUI headless:
  - compatíveis com `QT_QPA_PLATFORM=offscreen` no CI.
- Isolar dependências opcionais com `skip` explícito e motivo documentado.
- Rodar validação local antes de commit (mínimo):
  - `PYTHONPATH=src QT_QPA_PLATFORM=offscreen pytest tests/`

### Regras de estabilidade específicas deste repositório

- Evitar imports que derrubem coleta da suíte quando backend opcional não estiver instalado.
- Ao alterar integração com `pulsim`, garantir fallback funcional para backend placeholder/test doubles.
- Quando mudar workflow de CI, atualizar testes que validam contratos de pipeline para evitar drift.
