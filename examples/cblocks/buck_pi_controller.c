#include "pulsim/v1/cblock_abi.h"
#include <stdlib.h>

typedef struct {
    int n_inputs;
    double integral;
    double t_prev;
} BuckPIState;

PULSIM_CBLOCK_EXPORT int pulsim_cblock_abi_version = PULSIM_CBLOCK_ABI_VERSION;

PULSIM_CBLOCK_EXPORT int pulsim_cblock_init(void** ctx_out, const PulsimCBlockInfo* info)
{
    BuckPIState* st = (BuckPIState*)malloc(sizeof(BuckPIState));
    if (!st) return -1;

    st->n_inputs = (info != NULL && info->n_inputs > 0) ? info->n_inputs : 1;
    st->integral = 0.0;
    st->t_prev = -1.0;

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
    const double kp = 0.08;
    const double ki = 100.0;
    const double out_min = 0.0;
    const double out_max = 0.95;

    BuckPIState* st = (BuckPIState*)ctx;
    if (!st) return -2;

    // IN0 = vref, IN1 = vout (preferred).
    // Keep backward compatibility with 1-input error-only wiring.
    double error = 0.0;
    if (in != NULL) {
        error = in[0];
        if (st->n_inputs >= 2) {
            error -= in[1];
        }
    }
    const double dt_eff = (st->t_prev < 0.0) ? 0.0 : ((dt > 0.0) ? dt : 0.0);
    double integral = st->integral + (error * dt_eff);
    double u = (kp * error) + (ki * integral);

    if (u < out_min) u = out_min;
    if (u > out_max) u = out_max;

    // Anti-windup back-calculation aligned with PI reference implementation.
    if (ki != 0.0 && dt_eff > 0.0) {
        const double linear_u = (kp * error) + (ki * integral);
        if (linear_u != u) {
            integral = (u - (kp * error)) / ki;
        }
    }

    st->integral = integral;
    st->t_prev = t;
    out[0] = u;
    return 0;
}

PULSIM_CBLOCK_EXPORT void pulsim_cblock_destroy(PulsimCBlockCtx* ctx)
{
    free(ctx);
}
