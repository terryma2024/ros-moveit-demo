# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""Float64 FK/residual loops; matrix products retain the NumPy execution path.

The checked-in C file is generated with Cython 3.3.0. Building the package needs
the C compiler and Python headers, but does not need Cython at runtime or build time.
"""

import numpy as np
import math
from libc.math cimport sin, cos, acos, isfinite
from libc.stdint cimport uintptr_t
from cpython.pycapsule cimport PyCapsule_GetPointer, PyCapsule_IsValid

cdef extern from "fenv.h":
    int FE_DIVBYZERO, FE_OVERFLOW, FE_INVALID, FE_UNDERFLOW
    int feclearexcept(int)
    int fetestexcept(int)

ctypedef int (*_StridedLoop)(void *, char **, const Py_ssize_t *,
                            const Py_ssize_t *, void *) except -1

ctypedef struct _CallInfo:
    _StridedLoop strided_loop
    void *context
    void *auxdata
    unsigned char requires_pyapi
    unsigned char no_floatingpoint_errors


cdef class NumericKernel:
    cdef tuple origins, indices, crosses, squares
    cdef tuple origin_views
    cdef int joint_count
    cdef object product_capsule
    cdef _CallInfo *product_info
    cdef readonly bint direct_matmul

    def __init__(self, origins, indices, crosses, squares):
        if len(origins) != len(indices) or len(crosses) != len(squares):
            raise ValueError("invalid FK kernel layout")
        if any(np.shape(value) != (4, 4) for value in origins):
            raise ValueError("invalid FK origin shape")
        if any(np.shape(value) != (3, 3) for value in (*crosses, *squares)):
            raise ValueError("invalid FK axis shape")
        if any(index < -1 or index >= len(crosses) for index in indices):
            raise ValueError("invalid FK joint index")
        self.origins = tuple(origins)
        self.indices = tuple(indices)
        self.crosses = tuple(crosses)
        self.squares = tuple(squares)
        self.joint_count = len(crosses)
        self.product_info = NULL
        self.direct_matmul = False
        self.origin_views = ()
        # NumPy explicitly versions this experimental capsule ABI. Use only the
        # two minor releases independently validated on our supported platforms;
        # every other release retains normal NumPy dispatch.
        version = np.__version__.split('.')
        independent_layout = sorted(index for index in self.indices if index >= 0) == list(
            range(self.joint_count))
        if (version[:2] in (['1', '26'], ['2', '4']) and len(version) >= 3
                and version[2].isdigit() and independent_layout):
            try:
                _, capsule = np.matmul._resolve_dtypes_and_context((np.dtype('float64'),) * 3)
                np.matmul._get_strided_loop(capsule, fixed_strides=(None, None, None))
                if PyCapsule_IsValid(capsule, b'numpy_1.24_ufunc_call_info'):
                    self.product_capsule = capsule  # owns context/auxdata lifetime
                    self.product_info = <_CallInfo *>PyCapsule_GetPointer(
                        capsule, b'numpy_1.24_ufunc_call_info')
            except (AttributeError, TypeError, ValueError, RuntimeError):
                self.product_info = NULL
        cdef const double[:, :] origin_view
        views = []
        if self.product_info != NULL:
            try:
                for origin in self.origins:
                    if type(origin) is not np.ndarray:
                        raise TypeError('custom FK origin requires NumPy dispatch')
                    origin_view = origin
                    views.append(origin_view)
                self.origin_views = tuple(views)
                self.direct_matmul = self.product_info.strided_loop != NULL
            except (TypeError, ValueError, BufferError):
                self.product_info = NULL

    cdef void product_into(self, const double[:, :] a, const double[:, :] b,
                           double[:, :] out, Py_ssize_t rows, Py_ssize_t inner,
                           Py_ssize_t columns, bint transpose_b=False):
        cdef char *data[3]
        cdef Py_ssize_t dimensions[4]
        cdef Py_ssize_t strides[9]
        cdef int flags = FE_DIVBYZERO | FE_OVERFLOW | FE_INVALID | FE_UNDERFLOW
        cdef bint fallback = not self.direct_matmul
        if rows == 0 or inner == 0 or columns == 0:
            fallback = True
        if not fallback:
            data[0] = <char *>&a[0, 0]
            data[1] = <char *>&b[0, 0]
            data[2] = <char *>&out[0, 0]
            if (<uintptr_t>data[0] | <uintptr_t>data[1] | <uintptr_t>data[2]) % sizeof(double):
                fallback = True
        if not fallback:
            dimensions[0] = 1
            dimensions[1] = rows
            dimensions[2] = inner
            dimensions[3] = columns
            strides[0] = strides[1] = strides[2] = 0
            strides[3] = a.strides[0]
            strides[4] = a.strides[1]
            strides[5] = b.strides[1] if transpose_b else b.strides[0]
            strides[6] = b.strides[0] if transpose_b else b.strides[1]
            strides[7] = out.strides[0]
            strides[8] = out.strides[1]
            feclearexcept(flags)
            self.product_info.strided_loop(self.product_info.context, data,
                                           dimensions, strides, self.product_info.auxdata)
            # Replay exceptional arithmetic through normal dispatch, which owns
            # the current thread's np.seterr/warning/callback policy.
            fallback = fetestexcept(flags) != 0
        if fallback:
            left = np.asarray(a)[:rows, :inner]
            right = np.asarray(b).T if transpose_b else np.asarray(b)
            out[:, :] = left @ right[:inner, :columns]

    def matmul_into(self, a, b, out):
        """Validated product probe; internal workspace products are disjoint."""
        cdef const double[:, :] av = a
        cdef const double[:, :] bv = b
        cdef double[:, :] ov = out
        if (av.shape[1] != bv.shape[0] or ov.shape[0] != av.shape[0]
                or ov.shape[1] != bv.shape[1]):
            raise ValueError('invalid matrix product shape')
        if np.shares_memory(a, out) or np.shares_memory(b, out):
            out[:, :] = a @ b
            return
        self.product_into(av, bv, ov, av.shape[0], av.shape[1], bv.shape[1])

    cdef object motion(self, int index, double angle):
        out = np.empty((4, 4))
        cdef double[:, ::1] matrix = out
        self.motion_into(index, angle, matrix)
        return out

    cdef void motion_into(self, int index, double angle, double[:, ::1] matrix):
        cdef const double[:, ::1] cross = self.crosses[index]
        cdef const double[:, ::1] square = self.squares[index]
        cdef double s = sin(angle), c = 1.0 - cos(angle), a, b
        cdef int i, j
        for i in range(4):
            for j in range(4):
                matrix[i, j] = 1.0 if i == j else 0.0
        for i in range(3):
            for j in range(3):
                a = s * cross[i, j]
                b = c * square[i, j]
                matrix[i, j] = (matrix[i, j] + a) + b

    def matrix_with_prefixes(self, const double[:] positions):
        if positions.shape[0] != self.joint_count:
            raise ValueError("invalid FK position count")
        return self.base_matrix(positions)

    cdef tuple base_matrix(self, const double[:] positions):
        cdef int chain_index, index
        result = np.eye(4)
        prefixes = [None] * self.joint_count
        motions = [None] * self.joint_count
        for chain_index in range(len(self.origins)):
            result = result @ self.origins[chain_index]
            index = self.indices[chain_index]
            if index >= 0:
                prefixes[index] = result
                motion = self.motion(index, positions[index])
                motions[index] = motion
                result = result @ motion
        return result, prefixes, motions

    def perturbed_matrices(self, const double[:] positions, double epsilon,
                          prefixes, motions):
        if (positions.shape[0] != self.joint_count
                or len(prefixes) != self.joint_count or len(motions) != self.joint_count):
            raise ValueError("invalid FK perturbation layout")
        cdef int index, chain_index, tail_index
        cdef bint started
        result_matrices = []
        for index in range(self.joint_count):
            result = prefixes[index] @ self.motion(index, positions[index] + epsilon)
            started = False
            for chain_index in range(len(self.origins)):
                tail_index = self.indices[chain_index]
                if not started:
                    if tail_index == index:
                        started = True
                    continue
                result = result @ self.origins[chain_index]
                if tail_index >= 0:
                    result = result @ motions[tail_index]
            result_matrices.append(result)
        return result_matrices

    def residual(self, matrix, target_position, target_rotation):
        cdef const double[:, :] m = matrix
        cdef const double[:] t = target_position
        if (m.shape[0] != 4 or m.shape[1] != 4 or t.shape[0] != 3
                or np.shape(target_rotation) != (3, 3)):
            raise ValueError("invalid IK residual shape")
        return self.residual_unchecked(matrix, target_position, target_rotation)

    cdef object residual_unchecked(self, matrix, const double[:] t, target_rotation):
        out = np.empty(6)
        cdef double[::1] result = out
        self.residual_into(matrix, t, target_rotation, result)
        return out

    cdef void residual_into(self, matrix, const double[:] t, target_rotation,
                            double[::1] result, rotation=None,
                            double[:, :] rotation_view=None,
                            const double[:, :] target_view=None):
        cdef const double[:, :] m = matrix
        cdef const double[:, :] r
        if self.direct_matmul and rotation is not None:
            self.product_into(target_view, m, rotation_view, 3, 3, 3, True)
            r = rotation_view
        else:
            rotation = target_rotation @ matrix[:3, :3].T
            r = rotation
        # Retain NumPy's trace reduction, including its summation order.
        cdef double cosine = min(1.0, max(-1.0, (float(rotation.trace()) - 1.0) / 2.0))
        cdef double angle = acos(cosine), divisor
        cdef int i
        for i in range(3):
            result[i] = t[i] - m[i, 3]
        if angle < 1e-8:
            result[3] = 0.08 * (0.5 * (r[2, 1] - r[1, 2]))
            result[4] = 0.08 * (0.5 * (r[0, 2] - r[2, 0]))
            result[5] = 0.08 * (0.5 * (r[1, 0] - r[0, 1]))
        else:
            divisor = 2.0 * sin(angle)
            result[3] = 0.08 * (((r[2, 1] - r[1, 2]) / divisor) * angle)
            result[4] = 0.08 * (((r[0, 2] - r[2, 0]) / divisor) * angle)
            result[5] = 0.08 * (((r[1, 0] - r[0, 1]) / divisor) * angle)

    cdef tuple matrix_workspace(self, int count):
        owner = np.empty((count, 4, 4))
        arrays = [owner[index] for index in range(count)]
        views = []
        cdef double[:, :] view
        for array in arrays:
            view = array
            views.append(view)
        return arrays, views

    cdef object base_into(self, const double[:] positions, prefixes, motions,
                          motion_views, identity, slots, slot_views, prefix_views):
        cdef int chain_index, index, slot = 0
        cdef const double[:, :] result_view = identity
        result = identity
        for chain_index in range(len(self.origins)):
            if self.direct_matmul:
                self.product_into(result_view, self.origin_views[chain_index],
                                   slot_views[slot], 4, 4, 4)
                result = slots[slot]
                result_view = slot_views[slot]
                slot += 1
            else:
                result = result @ self.origins[chain_index]
            index = self.indices[chain_index]
            if index >= 0:
                prefixes[index] = result
                if self.direct_matmul:
                    prefix_views[index] = slot_views[slot - 1]
                self.motion_into(index, positions[index], motion_views[index])
                if self.direct_matmul:
                    self.product_into(result_view, motion_views[index], slot_views[slot], 4, 4, 4)
                    result = slots[slot]
                    result_view = slot_views[slot]
                    slot += 1
                else:
                    result = result @ motions[index]
        return result

    cdef void jacobian_into(self, const double[:] positions, prefixes, motions, motion_views,
                            perturbation, double[:, ::1] perturbation_view,
                            const double[:] target_position, target_rotation,
                            const double[:] base_residual, double[::1] candidate,
                            double[:, ::1] result, prefix_views, matrix_arrays,
                            matrix_views, rotation, double[:, :] rotation_view,
                            const double[:, :] target_view):
        cdef int index, chain_index, tail_index, row, slot
        cdef bint started
        cdef const double[:, :] current_view
        for index in range(self.joint_count):
            self.motion_into(index, positions[index] + 1e-5, perturbation_view)
            if self.direct_matmul:
                self.product_into(prefix_views[index], perturbation_view, matrix_views[0], 4, 4, 4)
                matrix = matrix_arrays[0]
                current_view = matrix_views[0]
                slot = 1
            else:
                matrix = prefixes[index] @ perturbation
            started = False
            for chain_index in range(len(self.origins)):
                tail_index = self.indices[chain_index]
                if not started:
                    if tail_index == index:
                        started = True
                    continue
                if self.direct_matmul:
                    self.product_into(current_view, self.origin_views[chain_index], matrix_views[slot], 4, 4, 4)
                    matrix = matrix_arrays[slot]
                    current_view = matrix_views[slot]
                    slot = 1 - slot
                else:
                    matrix = matrix @ self.origins[chain_index]
                if tail_index >= 0:
                    if self.direct_matmul:
                        self.product_into(current_view, motion_views[tail_index], matrix_views[slot], 4, 4, 4)
                        matrix = matrix_arrays[slot]
                        current_view = matrix_views[slot]
                        slot = 1 - slot
                    else:
                        matrix = matrix @ motions[tail_index]
            self.residual_into(matrix, target_position, target_rotation, candidate,
                               rotation, rotation_view, target_view)
            for row in range(6):
                result[row, index] = (candidate[row] - base_residual[row]) / 1e-5

    def forward_positions(self, const double[:, :] vectors, pose_from_matrix):
        """Batch the original FK products; path checks do not consume orientation."""
        cdef int point, row, column
        cdef const double[:, :] matrix_view
        cdef double[:, ::1] motion_view
        if vectors.shape[1] != self.joint_count:
            raise ValueError("invalid FK position count")
        identity = np.eye(4)
        prefixes = [None] * self.joint_count
        motions = [np.empty((4, 4)) for _ in range(self.joint_count)]
        motion_views = []
        for motion in motions:
            motion_view = motion
            motion_views.append(motion_view)
        slots, slot_views = self.matrix_workspace(2 * len(self.origins) + 1)
        prefix_views = [None] * self.joint_count
        result = []
        for point in range(vectors.shape[0]):
            matrix = self.base_into(vectors[point], prefixes, motions, motion_views,
                                    identity, slots, slot_views, prefix_views)
            matrix_view = matrix
            for row in range(4):
                for column in range(4):
                    if not isfinite(matrix_view[row, column]):
                        pose_from_matrix(matrix)
            result.append((matrix_view[0, 3], matrix_view[1, 3], matrix_view[2, 3]))
        return tuple(result)

    def solve(self, positions, target_position, target_rotation, target,
              lower, upper, double position_tolerance, double orientation_tolerance,
              pose_from_matrix, orientation_error):
        """Own the iteration loop; retain NumPy products, solve and clipping."""
        cdef const double[:] q = positions
        cdef const double[:, :] m
        cdef double distance, norm
        cdef int iteration, row, column
        cdef bint finite
        if q.shape[0] != self.joint_count:
            raise ValueError("invalid FK position count")
        cdef const double[:] t = target_position
        cdef const double[:, :] target_view = target_rotation
        if t.shape[0] != 3 or target_view.shape[0] != 3 or target_view.shape[1] != 3:
            raise ValueError("invalid IK residual shape")
        identity = np.eye(4)
        damping = 1e-5 * np.eye(self.joint_count)
        prefixes = [None] * self.joint_count
        motions = [np.empty((4, 4)) for _ in range(self.joint_count)]
        cdef double[:, ::1] motion_view
        motion_views = []
        for motion in motions:
            motion_view = motion
            motion_views.append(motion_view)
        perturbation = np.empty((4, 4))
        cdef double[:, ::1] perturbation_view = perturbation
        residual = np.empty(6)
        cdef double[::1] residual_view = residual
        candidate_array = np.empty(6)
        cdef double[::1] candidate = candidate_array
        jacobian = np.empty((6, self.joint_count))
        cdef double[:, ::1] jacobian_view = jacobian
        slots, slot_views = self.matrix_workspace(2 * len(self.origins) + 1)
        prefix_views = [None] * self.joint_count
        matrix_arrays, matrix_views = self.matrix_workspace(2)
        rotation = np.empty((3, 3))
        cdef double[:, :] rotation_view = rotation
        for iteration in range(200):
            matrix = self.base_into(q, prefixes, motions, motion_views, identity,
                                    slots, slot_views, prefix_views)
            self.residual_into(matrix, t, target_rotation, residual_view,
                               rotation, rotation_view, target_view)
            m = matrix
            finite = True
            for row in range(4):
                for column in range(4):
                    if not isfinite(m[row, column]):
                        finite = False
            # Keep the original evidence validation boundary for invalid FK data.
            if not finite:
                pose_from_matrix(matrix)
            distance = math.dist((m[0, 3], m[1, 3], m[2, 3]), target.position_m)
            if distance <= position_tolerance:
                actual = pose_from_matrix(matrix)
                if orientation_error(actual, target) <= orientation_tolerance:
                    return True, positions
            self.jacobian_into(q, prefixes, motions, motion_views, perturbation, perturbation_view,
                               t, target_rotation, residual_view, candidate, jacobian_view,
                               prefix_views, matrix_arrays, matrix_views,
                               rotation, rotation_view, target_view)
            step = -np.linalg.solve(
                jacobian.T @ jacobian + damping,
                jacobian.T @ residual,
            )
            norm = float(np.linalg.norm(step))
            if norm > 0.20:
                step *= 0.20 / norm
            positions = np.clip(positions + step, lower, upper)
            q = positions
        return False, positions

    def jacobian(self, matrices, target_position, target_rotation,
                 const double[:] base_residual, double epsilon):
        if (len(matrices) != self.joint_count or base_residual.shape[0] != 6
                or epsilon == 0.0):
            raise ValueError("invalid IK Jacobian layout")
        out = np.empty((6, self.joint_count))
        cdef double[:, ::1] result = out
        cdef const double[:] candidate
        cdef int row, index
        for index in range(self.joint_count):
            candidate = self.residual(matrices[index], target_position, target_rotation)
            for row in range(6):
                result[row, index] = (candidate[row] - base_residual[row]) / epsilon
        return out
