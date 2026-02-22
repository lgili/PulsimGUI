# Circuito RC de Teste

Este tutorial cria um circuito **RC passa-baixa** para validar:

- conexões no editor
- envio correto do circuito ao backend
- configuração da simulação
- visualização da resposta no viewer

![Exemplo de saída RC](../assets/images/rc-waveform.svg)

## Topologia

- Fonte de tensão (`Vin`)
- Resistor `R1 = 1k`
- Capacitor `C1 = 1u`
- Terra `GND`

Conexões:

1. `Vin+ -> R1`
2. `R1 -> Vout`
3. `Vout -> C1`
4. `C1 -> GND`
5. `Vin- -> GND`

## Passo a passo na GUI

1. Crie projeto novo.
2. Arraste `Voltage Source`, `Resistor`, `Capacitor` e `Ground`.
3. Faça as ligações conforme a topologia.
4. Configure parâmetros:
   - `R1 = 1k`
   - `C1 = 1u`
   - Fonte: degrau/pulso para enxergar transitório.
5. Abra `Simulation Settings`:
   - `t_start = 0`
   - `t_stop = 10ms`
   - `t_step = 1us`
   - `solver = auto` (ou `rk45`)
   - `output_points = 10000`
6. Clique em **Run**.
7. No viewer, plote `V(vout)` e `V(vin)`.

## Resultado esperado

- `V(vout)` sobe de forma exponencial.
- Constante de tempo aproximada:
  - `tau = R * C = 1k * 1u = 1ms`
- Em ~`5 ms`, a saída deve estar próxima do valor final (para entrada em degrau).

## Checklist de validação rápida

- Sem erro de parse de netlist/circuito.
- Simulação completa sem `Simulation failed`.
- Curva de `V(vout)` coerente com resposta de 1ª ordem.
- Alterar `R` ou `C` muda `tau` como esperado.
