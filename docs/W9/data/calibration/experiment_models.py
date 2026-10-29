import json
from pathlib import Path
import numpy as np
from docs.W9.d405.color_calibration import decode_srgb, linear_to_lab, lab_to_xyz, adapt_xyz, RGB_XYZ, D65


def features(x, kind):
    r, g, b = np.moveaxis(x, -1, 0)
    if kind == 'linear':
        return x
    if kind == 'affine':
        return np.concatenate([x, np.ones(x.shape[:-1]+(1,))], axis=-1)
    roots = np.stack([r, g, b, np.sqrt(r*g), np.sqrt(r*b), np.sqrt(g*b)], axis=-1)
    if kind == 'root6':
        return roots
    return np.concatenate([roots, np.ones(x.shape[:-1]+(1,))], axis=-1)


def lm(fun, initial, iterations=60):
    v = initial.copy().ravel()
    mu = .01
    err = fun(v)
    for _ in range(iterations):
        jac = np.column_stack([(fun(v+np.eye(1, len(v), k)[0]*1e-5)-err)/1e-5 for k in range(len(v))])
        h = jac.T@jac
        delta = np.linalg.solve(h + mu*np.diag(np.maximum(np.diag(h), 1)), -jac.T@err)
        next_err = fun(v+delta)
        if next_err@next_err < err@err:
            v += delta
            err = next_err
            mu = max(mu/3, 1e-8)
            if np.linalg.norm(delta) < 1e-7:
                break
        else:
            mu = min(mu*5, 1e8)
    return v.reshape(initial.shape)


def fit(x, lab, white, kind, ridge=1., power=2., iterations=60):
    f = features(x, kind)
    y = adapt_xyz(lab_to_xyz(lab, white), white, D65)@np.linalg.inv(RGB_XYZ).T
    base = np.zeros((f.shape[-1], 3))
    base[:3] = np.linalg.lstsq(x, y, rcond=None)[0]
    start = np.linalg.solve(f.T@f+np.eye(f.shape[-1])*.001, f.T@y+.001*base)
    def residual(v):
        c = v.reshape(base.shape)
        d = linear_to_lab(f@c, white)-lab
        weights = np.maximum(np.linalg.norm(d, axis=1), .1)**((power-2)/2)
        return np.r_[(d*weights[:, None]).ravel(), (np.sqrt(ridge)*(c-base)).ravel()]
    return lm(residual, start, iterations)


if __name__ == '__main__':
    p = json.loads(Path('docs/W9/data/calibration/classic_mini.json').read_text())
    x = decode_srgb(p['measured_rgb']); lab = np.array(p['reference']['patches_lab_row_major']); white = np.array(p['reference']['lab_white_xyz'])
    hold = np.array([0,7,13,17,20,22]); train = np.array([i for i in range(24) if i not in hold])
    results=[]
    for kind in ['linear', 'affine', 'root6', 'root7']:
        for ridge in [0.1, 1, 10]:
            for power in [2., 4.]:
                c=fit(x[train],lab[train],white,kind,ridge,power)
                e=np.linalg.norm(linear_to_lab(features(x,kind)@c,white)-lab,axis=1)
                row=dict(kind=kind,ridge=ridge,power=power,mean=float(e.mean()),maximum=float(e.max()),holdout=float(e[hold].mean()),coefficients=c.tolist())
                results.append(row); print(kind,ridge,power,'mean',round(e.mean(),3),'max',round(e.max(),3),'heldout',round(e[hold].mean(),3),flush=True)
    Path('docs/W9/data/calibration/model_experiments.json').write_text(json.dumps(results,indent=2))
