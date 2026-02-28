# PulsimGui

Interface gráfica para modelagem e simulação de conversores de potência com backend **Pulsim**.

![Dashboard do PulsimGui](imgs/dashboard_moderndark.png)

## O que você consegue fazer

- Montar esquemas elétricos com componentes de eletrônica de potência.
- Executar simulações transitórias com configuração completa de solver.
- Acompanhar formas de onda em tempo real no viewer integrado.
- Validar topologias com exemplos prontos (RC, buck, boost e outros).

## Fluxo recomendado

1. Instale e execute o app em [Instalação e Execução](instalacao.md).
2. Rode o primeiro tutorial em [Primeiro Circuito RC](tutoriais/circuito-rc.md).
3. Evolua para o exemplo de [Buck](tutoriais/conversor-buck.md).
4. Ajuste solver e tolerâncias em [Configuração de Simulação](gui/configuracao-simulacao.md).

## Backend padrão do projeto

O runtime de simulação padrão está alinhado para **`pulsim v0.5.0`**.

!!! tip "Ambiente reprodutível"
    Em `Preferences → Simulation`, mantenha `Source = PyPI`, `Target version = v0.5.0` e `Auto-sync` habilitado para garantir consistência entre máquinas.

## Links úteis

- Repositório: [github.com/lgili/PulsimGui](https://github.com/lgili/PulsimGui)
- Releases: [github.com/lgili/PulsimGui/releases](https://github.com/lgili/PulsimGui/releases)
- Issues: [github.com/lgili/PulsimGui/issues](https://github.com/lgili/PulsimGui/issues)
