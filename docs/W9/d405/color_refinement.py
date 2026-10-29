"""Perceptual affine colour fitting with leave-one-patch-out validation.

Uses NumPy only. The 24-patch reference is generic, not a spectral measurement
of the user's chart. Cross-validation estimates interpolation across its colours.
"""
import numpy as np

from .color_calibration import (D65, RGB_XYZ, adapt_xyz, decode_srgb, lab_to_xyz,
                                linear_to_lab)


def _optimize(residual, initial, iterations=80):
    shape = initial.shape
    value = initial.ravel().copy()
    damping = .01
    error = residual(value)
    steps = np.eye(value.size)*1e-5
    for _ in range(iterations):
        jacobian = np.column_stack([(residual(value+step)-error)/1e-5 for step in steps])
        hessian = jacobian.T@jacobian
        delta = np.linalg.solve(hessian+damping*np.diag(np.maximum(np.diag(hessian), 1)),
                                -jacobian.T@error)
        candidate = residual(value+delta)
        if candidate@candidate < error@error:
            value += delta
            error = candidate
            damping = max(damping/3, 1e-8)
            if np.linalg.norm(delta) < 1e-7:
                break
        else:
            damping = min(damping*5, 1e8)
    return value.reshape(shape)


def _fit(measured, lab, white, power):
    target = adapt_xyz(lab_to_xyz(lab, white), white, D65)@np.linalg.inv(RGB_XYZ).T
    if np.linalg.matrix_rank(measured) < 3 or np.linalg.cond(measured) > 100:
        raise ValueError('Ill-conditioned chart samples.')
    features = np.column_stack([measured, np.ones(len(measured))])
    prior = np.zeros((4, 3))
    prior[:3] = np.linalg.lstsq(measured, target, rcond=None)[0]
    initial = np.linalg.solve(features.T@features+np.eye(4)*.001,
                              features.T@target+.001*prior)
    lower_bound = np.where(target < 0, -.1, .005)

    def residual(value):
        coefficients = value.reshape(4, 3)
        output = features@coefficients
        delta = linear_to_lab(output, white)-lab
        # Power 4 gives large patch errors more weight than squared Delta E.
        weights = np.maximum(np.linalg.norm(delta, axis=1), .1)**((power-2)/2)
        # Preserve room for pixel noise near white and saturated colour patches.
        # These are soft training-sample constraints, not a guarantee for unseen RGB.
        return np.r_[(delta*weights[:, None]).ravel(), (coefficients-prior).ravel(),
                     (np.minimum(output-lower_bound, 0)*100000).ravel(),
                     (np.maximum(output-.94, 0)*100000).ravel()]

    return _optimize(residual, initial)


def fit_affine(measured_rgb, reference_lab, white, power=4.):
    measured = decode_srgb(measured_rgb)
    lab = np.asarray(reference_lab, dtype=float)
    if measured.shape != (24, 3) or lab.shape != (24, 3):
        raise ValueError('Need 24 RGB and Lab patch values.')
    coefficients = _fit(measured, lab, white, power)
    target = adapt_xyz(lab_to_xyz(lab, white), white, D65)@np.linalg.inv(RGB_XYZ).T
    before = np.linalg.norm(linear_to_lab(measured, white)-lab, axis=1)
    after = np.linalg.norm(linear_to_lab(measured@coefficients[:3]+coefficients[3], white)-lab, axis=1)
    cross_validation = []
    for index in range(24):
        train = np.delete(np.arange(24), index)
        estimate = _fit(measured[train], lab[train], white, power)
        predicted = measured[index:index+1]@estimate[:3]+estimate[3]
        cross_validation.append(float(np.linalg.norm(linear_to_lab(predicted, white)-lab[index])))
    if np.mean(cross_validation) >= before.mean():
        raise ValueError('Leave-one-patch-out error did not improve over uncorrected RGB.')
    report = dict(deltaE_metric='CIE76, ICC D50; not CIEDE2000',
                  validation='24-fold leave-one-patch-out; final fit uses all 24 colours',
                  loss_power=power, all_mean_before=float(before.mean()),
                  sample_output_headroom_linear=[.005, .94],
                  headroom_note='Lower bound exempted for reference channels outside sRGB gamut; raw clipping is still rejected.',
                  reference_out_of_srgb_patch_indices=(np.flatnonzero(np.any((target < 0)|(target > 1), axis=1))+1).tolist(),
                  all_mean_after=float(after.mean()), all_max_after=float(after.max()),
                  cross_validation_mean=float(np.mean(cross_validation)),
                  cross_validation_max=float(max(cross_validation)),
                  cross_validation_deltaE76=cross_validation,
                  deltaE76_before=before.tolist(), deltaE76_after=after.tolist())
    return coefficients[:3], coefficients[3], report
