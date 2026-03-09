#include "pulsim/v1/cblock_abi.h"
#include <stdlib.h>

typedef struct {
    int n_inputs;
    int n_outputs;
    double integ_v;
    double integ_i;
    double vref_ramp;
    double t_prev;
    double fault_hold;
    int fault_latched;
} BoostCtrlState;

PULSIM_CBLOCK_EXPORT int pulsim_cblock_abi_version = PULSIM_CBLOCK_ABI_VERSION;

static double clamp_double(double x, double lo, double hi)
{
    if (x < lo) return lo;
    if (x > hi) return hi;
    return x;
}

static double read_input(const BoostCtrlState* st, const double* in, int idx)
{
    if (st == NULL || in == NULL) return 0.0;
    if (idx < 0 || idx >= st->n_inputs) return 0.0;
    return in[idx];
}

PULSIM_CBLOCK_EXPORT int pulsim_cblock_init(void** ctx_out, const PulsimCBlockInfo* info)
{
    if (ctx_out == NULL) return -1;

    BoostCtrlState* st = (BoostCtrlState*)malloc(sizeof(BoostCtrlState));
    if (!st) return -1;

    st->n_inputs = (info != NULL && info->n_inputs > 0) ? info->n_inputs : 1;
    st->n_outputs = (info != NULL && info->n_outputs > 0) ? info->n_outputs : 1;
    st->integ_v = 0.0;
    st->integ_i = 0.0;
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
    /* Tuned for this demo operating point:
     * - fsw = 10 kHz
     * - Vin = 5 V
     * - Vref = 10 V
     */
    const double kp_v = 0.25;
    const double ki_v = 140.0;
    const double kp_i = 0.07;
    const double ki_i = 20.0;
    const double ff_gain = 1.0;

    const double iref_min = 0.0;
    const double duty_min = 0.02;
    const double duty_max = 0.92;

    BoostCtrlState* st = (BoostCtrlState*)ctx;
    if (!st) return -2;
    if (!out) return -3;

    /* Inputs:
     * IN0 = VREF target (constant)
     * IN1 = Xout  (output voltage probe)
     * IN2 = X1    (inductor current probe channel)
     * IN3 = Xvin  (input voltage probe)
     * IN4 = ILIM  (current limit constant)
     * IN5 = SS_SLEW (soft-start slew in V/s)
     */
    const double vref_target = read_input(st, in, 0);
    const double vout = read_input(st, in, 1);
    const double i_l = read_input(st, in, 2);
    const double vin = read_input(st, in, 3);
    const double ilim_in = read_input(st, in, 4);
    const double slew_in = read_input(st, in, 5);

    const double ilim = (ilim_in > 0.2) ? ilim_in : 4.0;
    const double slew = (slew_in > 1.0) ? slew_in : 4000.0;

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
    double iref_lin = (kp_v * ev) + (ki_v * integ_v);
    double iref = clamp_double(iref_lin, iref_min, ilim);
    if (dt_eff > 0.0 && ki_v != 0.0 && iref != iref_lin) {
        integ_v = (iref - (kp_v * ev)) / ki_v;
    }
    st->integ_v = integ_v;

    const double ei = iref - i_l;

    double integ_i = st->integ_i;
    if (dt_eff > 0.0) integ_i += ei * dt_eff;

    double duty_ff = 0.0;
    if (st->vref_ramp > 0.5 && vin > 0.2) {
        duty_ff = 1.0 - (vin / (st->vref_ramp + 0.1));
    }
    duty_ff = clamp_double(duty_ff, -0.20, 0.85);

    double duty_lin = (ff_gain * duty_ff) + (kp_i * ei) + (ki_i * integ_i);
    double duty = clamp_double(duty_lin, duty_min, duty_max);
    if (dt_eff > 0.0 && ki_i != 0.0 && duty != duty_lin) {
        integ_i = (duty - (ff_gain * duty_ff) - (kp_i * ei)) / ki_i;
    }

    if (!st->fault_latched) {
        const double trip_current = 1.15 * ilim;
        if (t > 0.0004 && i_l > trip_current) {
            st->fault_latched = 1;
            st->fault_hold = 0.0;
        }
    } else {
        if (dt_eff > 0.0) st->fault_hold += dt_eff;
        duty = 0.0;
        st->integ_i = 0.0;
        if (i_l < (0.75 * ilim) && st->fault_hold > 0.0015) {
            st->fault_latched = 0;
            st->fault_hold = 0.0;
        }
    }

    st->integ_i = st->fault_latched ? 0.0 : integ_i;

    if (st->n_outputs >= 1) out[0] = duty;
    if (st->n_outputs >= 2) out[1] = iref;
    if (st->n_outputs >= 3) out[2] = ev;
    if (st->n_outputs >= 4) out[3] = ei;
    if (st->n_outputs >= 5) out[4] = st->vref_ramp;
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
