# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""Float64 FK/residual loops; matrix products retain the NumPy execution path.

The checked-in C file is generated with Cython 3.3.0. Building the package needs
the C compiler and Python headers, but does not need Cython at runtime or build time.
"""

import numpy as np
from libc.math cimport sin, cos, acos


cdef class NumericKernel:
    cdef tuple origins, indices, crosses, squares
    cdef int joint_count

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

    cdef object motion(self, int index, double angle):
        cdef const double[:, ::1] cross = self.crosses[index]
        cdef const double[:, ::1] square = self.squares[index]
        cdef double s = sin(angle), c = 1.0 - cos(angle), a, b
        cdef int i, j
        out = np.empty((4, 4))
        cdef double[:, ::1] matrix = out
        for i in range(4):
            for j in range(4):
                matrix[i, j] = 1.0 if i == j else 0.0
        for i in range(3):
            for j in range(3):
                a = s * cross[i, j]
                b = c * square[i, j]
                matrix[i, j] = (matrix[i, j] + a) + b
        return out

    def matrix_with_prefixes(self, const double[:] positions):
        if positions.shape[0] != self.joint_count:
            raise ValueError("invalid FK position count")
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
        rotation = target_rotation @ matrix[:3, :3].T
        cdef const double[:, :] r = rotation
        # Retain NumPy's trace reduction, including its summation order.
        cdef double cosine = min(1.0, max(-1.0, (float(np.trace(rotation)) - 1.0) / 2.0))
        cdef double angle = acos(cosine), divisor
        cdef int i
        out = np.empty(6)
        cdef double[::1] result = out
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
        return out

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
