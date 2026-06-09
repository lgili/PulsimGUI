/* === Switched CMC, Venturini-PWM, current-direction-aware (9 gates) ===
 *
 * The 9 matrix cells are true 4-quadrant BIDIRECTIONAL switches
 * (pulsim ``add_switch`` — a symmetric conductance, NO body diode), so
 * each cell blocks both polarities when OFF and conducts both
 * directions when ON. That is what makes a safe Conventional Matrix
 * Converter (CMC): there is no rectifier path to clamp the output.
 *
 * inputs  : in[0..2] = filtered input phase voltages v_a, v_b, v_c
 *                      (from the 3 VOLTAGE_PROBE_GND on Va/Vb/Vc_FILT)
 *           in[3..5] = output phase currents i_A, i_B, i_C
 *                      (the user's "precisa da saida tambem" — the
 *                      modulator must see the OUTPUT to commutate the
 *                      inductive load safely). Each is delivered as the
 *                      voltage across the load resistor referenced to
 *                      ground (node LRMID_j = i_j * R_load), so
 *                      sign(in[3+j]) == sign(i_out[j]).
 * outputs : out[0..8] = gate drives for the 9-switch matrix in
 *           ROW-MAJOR (input, output) order:
 *               out[0]=g_aA  out[1]=g_aB  out[2]=g_aC
 *               out[3]=g_bA  out[4]=g_bB  out[5]=g_bC
 *               out[6]=g_cA  out[7]=g_cB  out[8]=g_cC
 *
 * Algorithm: Venturini's optimum modulation. For each output phase j
 * we have three time-fractions m_aj, m_bj, m_cj summing to 1; within
 * each PWM period we connect output j to one input phase at a time —
 * exactly ONE cell in column j conducts at any instant ("exactly one
 * input per output" CMC constraint, enforced by construction).
 *
 *     m_ij(t) = (1/3) * [1 + 2*q*cos(theta_o - phi_out_j) * cos(theta_i - phi_in_i)]
 *
 * phi_out = {0, -120, +120} deg matches the positive-sequence load
 * reference. phi_in = {0, +120, -120} deg is the CONJUGATE input
 * reference required so that cos(theta_i - phi_in_i) tracks the
 * physical positive-sequence grid voltage of phase i (a=0, b=-120,
 * c=+120): with the naive phi_in = {0, -120, +120} the duty-weighted
 * output collapses to ~0 V fundamental (the b/c references cancel the
 * rotation). theta_i is the live input voltage vector angle (Clarke
 * transform of in[0..2], robust to grid drift) and theta_o = omega_o*t.
 *
 * Current-direction-aware commutation
 * -----------------------------------
 * A matrix converter feeding an INDUCTIVE load must never open every
 * cell in a column (the load current would have no path and the
 * inductor voltage would spike). Because the cells are bidirectional
 * we keep exactly one cell ON per column at all times, and we ORDER the
 * segment sequence within each PWM period by the sign of the load
 * current so the transition between two input phases hands the current
 * off in a defined direction:
 *
 *   - i_out[j] >= 0 : sweep frac_t low->high as input a, b, c
 *                     (ascending duty-cumsum order).
 *   - i_out[j] <  0 : sweep the segments in the reverse order so the
 *                     newly-closing cell takes over the (negative) load
 *                     current cleanly before the old cell opens.
 *
 * The per-segment DURATIONS are identical either way (so the
 * duty-weighted average — hence the 25 Hz output fundamental — is
 * unchanged); only the WITHIN-PERIOD ORDER flips with current sign.
 *
 * The 5 us C_BLOCK firing rate is 10x finer than the 50 us PWM period,
 * so the within-period segment progression is correctly resolved.
 */
const double PI       = 3.14159265358979323846;
const double TWO_PI   = 6.28318530717958647692;
const double DEG120   = 2.09439510239319549231;
const double SQRT3_2  = 0.86602540378443864676;
const double TWO_3    = 0.66666666666666666667;

double q     = 0.45;         /* modulation index (<= 0.5, Venturini max) */
double f_o   = 25.0;
double T_pwm = 5e-5;         /* 50 us = 20 kHz */
double V_on  = 15.0;
double V_off = 0.0;

double omega_o = TWO_PI * f_o;
double theta_o = omega_o * t;

double va = in[0], vb = in[1], vc = in[2];

/* Output phase currents (sign carriers for current-direction-aware
   commutation). in[3+j] is delivered as i_out[j] * R_load, so only its
   SIGN matters here. */
double i_out[3] = {in[3], in[4], in[5]};

/* Clarke-transform the input vector to recover theta_i live (so the
   modulator self-adapts if the grid frequency drifts a bit). */
double v_alpha = TWO_3 * (va - 0.5 * vb - 0.5 * vc);
double v_beta  = TWO_3 * (SQRT3_2 * vb - SQRT3_2 * vc);
double theta_i = atan2(v_beta, v_alpha);

/* Where are we in the current PWM period? Normalised to [0, 1). */
double frame  = fmod(t, T_pwm);
if (frame < 0) frame += T_pwm;
double frac_t = frame / T_pwm;

double phi_out[3] = {0.0,    -DEG120, +DEG120};
double phi_in[3]  = {0.0,    +DEG120, -DEG120};   /* CONJUGATE input ref */

/* For each output phase j, compute the 3 Venturini duty fractions and
   pick which input phase is conducting RIGHT NOW based on frac_t. */
for (int j = 0; j < 3; j++) {
    double m[3];
    double sum = 0.0;
    for (int i = 0; i < 3; i++) {
        double m_ij = (1.0/3.0) * (1.0
            + 2.0 * q * cos(theta_o - phi_out[j])
                      * cos(theta_i - phi_in[i]));
        if (m_ij < 0.0) m_ij = 0.0;
        if (m_ij > 1.0) m_ij = 1.0;
        m[i] = m_ij;
        sum += m_ij;
    }
    /* Normalise (Venturini's formula sums to ~1 but rounding/clamping
       can drift; renormalise so exactly one switch conducts per PWM
       period). */
    if (sum > 1e-9) {
        m[0] /= sum;
        m[1] /= sum;
        m[2] /= sum;
    } else {
        m[0] = 1.0;  /* degenerate: bond output to input a */
        m[1] = 0.0;
        m[2] = 0.0;
    }

    /* Current-direction-aware segment order. Build the visiting order
       of the 3 input phases for this column: ascending {a,b,c} when the
       load current is >= 0, reversed {c,b,a} when it is negative. The
       segment DURATIONS (m[]) are unchanged, so the duty-weighted
       average output is identical — only the order in which the
       BIDIRECTIONAL cells hand off the load current flips. */
    int order[3];
    if (i_out[j] >= 0.0) {
        order[0] = 0; order[1] = 1; order[2] = 2;
    } else {
        order[0] = 2; order[1] = 1; order[2] = 0;
    }

    /* Walk the ordered segments and find which input is conducting at
       frac_t. */
    int conducting_input = order[2];
    double cum = 0.0;
    for (int s = 0; s < 3; s++) {
        cum += m[order[s]];
        if (frac_t < cum) {
            conducting_input = order[s];
            break;
        }
    }

    /* Set the 3 gates of column j: one on, two off. The CMC "exactly
       one input per output" constraint is enforced HERE — never two
       gates in a column ON simultaneously, and never zero (the
       inductive load always has a defined path through a bidirectional
       cell). */
    for (int i = 0; i < 3; i++) {
        out[i * 3 + j] = (i == conducting_input) ? V_on : V_off;
    }
}
