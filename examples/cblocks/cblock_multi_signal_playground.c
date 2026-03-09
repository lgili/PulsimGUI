#include "pulsim/v1/cblock_abi.h"
#include <math.h>
#include <stdlib.h>

typedef struct {
    int n_inputs;
    int n_outputs;
    double integ;
    double phase;
} PlaygroundState;

PULSIM_CBLOCK_EXPORT int pulsim_cblock_abi_version = PULSIM_CBLOCK_ABI_VERSION;

PULSIM_CBLOCK_EXPORT int pulsim_cblock_init(void** ctx_out, const PulsimCBlockInfo* info)
{
    if (ctx_out == NULL) return -1;

    PlaygroundState* st = (PlaygroundState*)malloc(sizeof(PlaygroundState));
    if (!st) return -1;

    st->n_inputs = (info != NULL && info->n_inputs > 0) ? info->n_inputs : 1;
    st->n_outputs = (info != NULL && info->n_outputs > 0) ? info->n_outputs : 1;
    st->integ = 0.0;
    st->phase = 0.0;
    *ctx_out = st;
    return 0;
}

static double in_or_zero(const PlaygroundState* st, const double* in, int idx)
{
    if (st == NULL || in == NULL) return 0.0;
    if (idx < 0 || idx >= st->n_inputs) return 0.0;
    return in[idx];
}

PULSIM_CBLOCK_EXPORT int pulsim_cblock_step(
    PulsimCBlockCtx* ctx,
    double t,
    double dt,
    const double* in,
    double* out)
{
    (void)t;
    const double PI = 3.14159265358979323846;
    const double TWO_PI = 6.28318530717958647692;

    PlaygroundState* st = (PlaygroundState*)ctx;
    if (!st) return -2;
    if (!out) return -3;

    /* Wiring expected in the demo file:
     * IN0 = Xsrc   (probe da entrada)
     * IN1 = Xout   (probe da saida RC)
     * IN2 = Kbias  (constante de offset)
     * IN3 = Gvout  (ganho aplicado na saida RC)
     * IN4 = Kth    (limiar do comparador)
     */
    const double vin = in_or_zero(st, in, 0);
    const double vout = in_or_zero(st, in, 1);
    const double kbias = in_or_zero(st, in, 2);
    const double gvout = in_or_zero(st, in, 3);
    const double kth = in_or_zero(st, in, 4);

    const double err = vin - vout;                       /* OUT0 */
    const double mix = 0.60 * vin + 0.40 * vout + kbias; /* OUT1 */

    const double dt_eff = (dt > 0.0) ? dt : 0.0;
    st->integ += err * dt_eff * 20.0;
    if (st->integ > 4.0) st->integ = 4.0;
    if (st->integ < -4.0) st->integ = -4.0;

    st->phase += TWO_PI * 45.0 * dt_eff;
    while (st->phase >= TWO_PI) st->phase -= TWO_PI;
    while (st->phase < 0.0) st->phase += TWO_PI;

    /* OUT4: portadora triangular em [-1, 1]. */
    const double tri_01 = (st->phase < PI) ? (st->phase / PI) : (2.0 - st->phase / PI);
    const double carrier = 2.0 * tri_01 - 1.0;

    /* OUT3: pulso logico a partir de comparacao err+gvout vs carrier+kth. */
    const double pulse = ((err + gvout) > (carrier + kth)) ? 1.0 : 0.0;

    if (st->n_outputs >= 1) out[0] = err;
    if (st->n_outputs >= 2) out[1] = mix;
    if (st->n_outputs >= 3) out[2] = st->integ;
    if (st->n_outputs >= 4) out[3] = pulse;
    if (st->n_outputs >= 5) out[4] = carrier;
    for (int i = 5; i < st->n_outputs; ++i) out[i] = 0.0;

    return 0;
}

PULSIM_CBLOCK_EXPORT void pulsim_cblock_destroy(PulsimCBlockCtx* ctx)
{
    free(ctx);
}
