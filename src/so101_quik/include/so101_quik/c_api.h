// AGPL-3.0-only; see third_party/quik/LICENSE.
#ifndef SO101_QUIK_C_API_H_
#define SO101_QUIK_C_API_H_

#ifdef __cplusplus
extern "C" {
#endif

// All buffers must be valid double arrays; transforms are row-major 4x4.
// dh contains five [a, alpha, d, theta] rows. stock=0 selects the frozen
// weighted/damped profile, stock=1 selects the recorded stock initialization.
// The caller owns each context, serializes its calls and destroys it once.
// This raw numerical interface does not enforce a robot's limits/tolerances.
void* quik_create(const double* dh, const double* base, const double* tool, int stock);
void quik_destroy(void* context);
// q: five joints; out: sixteen transform elements. Return 0 on success, -1
// on a caught C++ exception. Invalid pointers/lifetimes violate this ABI.
int quik_fk(void* context, const double* q, double* out);
// target: sixteen elements; seed/out: five joints; error: six residuals.
// iterations/reason each point to one int. A successful numerical call is
// not a robot-level acceptance decision; check the resulting pose and limits.
int quik_solve(void* context, const double* target, const double* seed, double* out,
               double* error, int* iterations, int* reason);

#ifdef __cplusplus
}
#endif
#endif
