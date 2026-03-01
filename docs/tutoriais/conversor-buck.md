# Exemplo de Conversor Buck

Este tutorial foca em validação de fluxo para topologia buck usando template do projeto.

## Objetivo

- Abrir o template buck.
- Ajustar parâmetros básicos de entrada/chaveamento/carga.
- Rodar simulação transitória.
- Ler `Vsw`, `Vout` e corrente no indutor.

## Passos

1. Abra `File → New from Template`.
2. Escolha **Buck Converter**.
3. Verifique os blocos principais:
   - Fonte de entrada (`Vin`)
   - Chave (MOSFET)
   - Diodo de roda livre
   - Indutor (`L1`)
   - Capacitor de saída (`Cout`)
   - Carga (`Rload`)
4. Abra `Simulation Settings` e use um perfil inicial:
   - `Stop time`: `10ms`
   - `Step size`: `2us`
   - `Output points`: `5000` a `10000`
   - Robustez transitória habilitada
5. Execute com **Run** (`F5`).
6. No viewer/scope, observe sinais como:
   - `V(SW)`
   - `V(VOUT)`
   - `I(L1)`

## O que analisar

- **Nó SW**: forma pulsada em alta frequência.
- **VOUT**: nível médio estabilizado com ripple.
- **I(L1)**: rampa triangular (modo contínuo ou descontínuo conforme carga/indutância).

## Ajustes úteis

- Ripple alto em `VOUT`: aumente `Cout` e/ou frequência de chaveamento.
- Corrente de indutor muito serrilhada: aumente `L1`.
- Convergência ruim: reduza `Step size`, mantenha robustez habilitada e revise parâmetros extremos.

## Referências internas

- Exemplos de projeto: [`examples/`](https://github.com/lgili/PulsimGUI/tree/main/examples)
- Configuração detalhada do solver: [Configuração de Simulação](../gui/configuracao-simulacao.md)
