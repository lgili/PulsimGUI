#include "pulsim/v1/cblock_abi.h"
#include <math.h>
#include <stdlib.h>

typedef struct {
    int n_inputs;
    int n_outputs;
    double integ_v;
    double integ_i;
    double i_filt;
    double duty_prev;
    double vref_ramp;
    double t_prev;
    double fault_hold;
    int fault_latched;
} BoostPfcState;

PULSIM_CBLOCK_EXPORT int pulsim_cblock_abi_version = PULSIM_CBLOCK_ABI_VERSION;

static double clamp_double(double x, double lo, double hi)
{
    if (x < lo) return lo;
    if (x > hi) return hi;
    return x;
}

static double read_input(const BoostPfcState* st, const double* in, int idx)
{
    if (st == NULL || in == NULL) return 0.0;
    if (idx < 0 || idx >= st->n_inputs) return 0.0;
    return in[idx];
}

PULSIM_CBLOCK_EXPORT int pulsim_cblock_init(void** ctx_out, const PulsimCBlockInfo* info)
{
    if (ctx_out == NULL) return -1;

    BoostPfcState* st = (BoostPfcState*)malloc(sizeof(BoostPfcState));
    if (!st) return -1;

    st->n_inputs = (info != NULL && info->n_inputs > 0) ? info->n_inputs : 1;
    st->n_outputs = (info != NULL && info->n_outputs > 0) ? info->n_outputs : 1;
    st->integ_v = 0.0;
    st->integ_i = 0.0;
    st->i_filt = 0.0;
    st->duty_prev = 0.0;
    st->vref_ramp = 0.0;
    st->t_prev = -1.0;
    st->fault_hold = 0.0;
    st->fault_latched = 0;

    *ctx_out = st;
    return 0;
}

PULSIM_CBLOCK_EXPORT int pulsim_cblock_step(
    PulsimCBlockCtx* ctx,
    double t,
    double dt,
    const double* in,
    double* out)
{
    /* Cascaded PFC design (example target):
     * - Vac = 220 Vrms, f_line = 60 Hz
     * - Vout = 400 Vdc
     * - Pout ~= 100 W
     * - Outer loop regulates Vout and generates conductance command (A/V)
     * - Inner loop tracks inductor current with i_ref = g_cmd * |Vac|
     */
    const double kp_v = 1.0e-5;
    const double ki_v = 1.2e-3;
    const double g_min = 0.0;
    const double g_max = 3.5e-3;

    const double kp_i = 0.03;
    const double ki_i = 25.0;
    const double duty_min = 0.01;
    const double duty_max = 0.92;
    const double line_enable_threshold = 25.0;

    BoostPfcState* st = (BoostPfcState*)ctx;
    if (!st) return -2;
    if (!out) return -3;

    /* Inputs:
     * IN0 = VREF     (output voltage target)
     * IN1 = Xout     (output voltage)
     * IN2 = X1       (inductor current)
     * IN3 = Xvin     (AC line voltage, before bridge)
     * IN4 = ILIM     (current limit)
     * IN5 = SS_SLEW  (soft-start slew in V/s)
     */
    const double vref_target = read_input(st, in, 0);
    const double vout = read_input(st, in, 1);
    const double i_l = read_input(st, in, 2);
    const double vac = read_input(st, in, 3);
    const double ilim_in = read_input(st, in, 4);
    const double slew_in = read_input(st, in, 5);

    const double ilim = (ilim_in > 0.2) ? ilim_in : 1.1;
    const double slew = (slew_in > 1.0) ? slew_in : 2000.0;
    const double vac_abs = fabs(vac);

    const double dt_eff = (st->t_prev < 0.0 || dt <= 0.0) ? 0.0 : dt;
    st->t_prev = t;

    if (dt_eff > 0.0) {
        const double dv = slew * dt_eff;
        if (st->vref_ramp < vref_target) {
            st->vref_ramp += dv;
            if (st->vref_ramp > vref_target) st->vref_ramp = vref_target;
        } else {
            st->vref_ramp = vref_target;
        }
    }

    const double ev = st->vref_ramp - vout;

    double integ_v = st->integ_v;
    if (dt_eff > 0.0) integ_v += ev * dt_eff;
    double g_lin = (kp_v * ev) + (ki_v * integ_v);
    double g_cmd = clamp_double(g_lin, g_min, g_max);
    if (dt_eff > 0.0 && ki_v != 0.0 && g_cmd != g_lin) {
        integ_v = (g_cmd - (kp_v * ev)) / ki_v;
    }
    st->integ_v = integ_v;

    double iref = g_cmd * vac_abs;
    iref = clamp_double(iref, 0.0, ilim);

    /* Low-pass the inductor current so the digital PI does not chase switching ripple. */
    const double tau_i = 80e-6;
    const double alpha_i = (dt_eff > 0.0) ? clamp_double(dt_eff / (tau_i + dt_eff), 0.0, 1.0) : 0.0;
    st->i_filt += alpha_i * (i_l - st->i_filt);
    /* Use magnitude so control remains stable if current-probe polarity is inverted. */
    const double i_ctrl = fabs(st->i_filt);
    const double ei = iref - i_ctrl;

    double integ_i = st->integ_i;
    if (dt_eff > 0.0) integ_i += ei * dt_eff;

    double duty_ff = 0.0;
    if (vout > (vac_abs + 10.0) && vac_abs > 1.0) {
        duty_ff = 1.0 - (vac_abs / (vout + 0.1));
    }
    duty_ff = clamp_double(duty_ff, 0.0, 0.95);

    double duty_lin = duty_ff + (kp_i * ei) + (ki_i * integ_i);
    double duty_cmd = clamp_double(duty_lin, duty_min, duty_max);
    if (dt_eff > 0.0 && ki_i != 0.0 && duty_cmd != duty_lin) {
        integ_i = (duty_cmd - duty_ff - (kp_i * ei)) / ki_i;
    }

    if (vac_abs < line_enable_threshold) {
        duty_cmd = 0.0;
        integ_i = 0.0;
        st->duty_prev = 0.0;
    }
    if (i_ctrl > ilim) {
        duty_cmd = 0.0;
        integ_i = 0.0;
        st->duty_prev = 0.0;
    }

    if (!st->fault_latched) {
        const double trip_current = 1.20 * ilim;
        if (t > 0.001 && i_ctrl > trip_current) {
            st->fault_latched = 1;
            st->fault_hold = 0.0;
        }
    } else {
        if (dt_eff > 0.0) st->fault_hold += dt_eff;
        duty_cmd = 0.0;
        integ_i = 0.0;
        if (i_ctrl < (0.7 * ilim) && st->fault_hold > 0.003) {
            st->fault_latched = 0;
            st->fault_hold = 0.0;
        }
    }

    st->integ_i = integ_i;

    /* Duty slew limiter to avoid hard discontinuities that hurt Newton convergence. */
    if (dt_eff > 0.0) {
        const double duty_slew_per_sec = 40000.0;
        const double max_delta = duty_slew_per_sec * dt_eff;
        const double delta = duty_cmd - st->duty_prev;
        if (delta > max_delta) duty_cmd = st->duty_prev + max_delta;
        else if (delta < -max_delta) duty_cmd = st->duty_prev - max_delta;
    }
    duty_cmd = clamp_double(duty_cmd, 0.0, duty_max);
    st->duty_prev = duty_cmd;

    if (st->n_outputs >= 1) out[0] = duty_cmd;
    if (st->n_outputs >= 2) out[1] = iref;
    if (st->n_outputs >= 3) out[2] = ev;
    if (st->n_outputs >= 4) out[3] = ei;
    if (st->n_outputs >= 5) out[4] = g_cmd;
    if (st->n_outputs >= 6) out[5] = st->fault_latched ? 1.0 : 0.0;
    for (int i = 6; i < st->n_outputs; ++i) {
        out[i] = 0.0;
    }

    return 0;
}

PULSIM_CBLOCK_EXPORT void pulsim_cblock_destroy(PulsimCBlockCtx* ctx)
{
    free(ctx);
}
