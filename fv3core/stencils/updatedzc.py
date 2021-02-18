import gt4py.gtscript as gtscript
from gt4py.gtscript import (
    BACKWARD,
    PARALLEL,
    computation,
    horizontal,
    interval,
    region,
)

import fv3core._config as spec
import fv3core.utils.global_constants as constants
import fv3core.utils.gt4py_utils as utils
from fv3core.decorators import gtstencil
from fv3core.stencils.basic_operations import copy
from fv3core.utils import corners


sd = utils.sd
DZ_MIN = constants.DZ_MIN


@gtscript.function
def p_weighted_average_top(vel, dp0):
    ratio = dp0 / (dp0 + dp0[0, 0, 1])
    return vel + (vel - vel[0, 0, 1]) * ratio


@gtscript.function
def p_weighted_average_bottom(vel, dp0):
    ratio = dp0[0, 0, -1] / (dp0[0, 0, -2] + dp0[0, 0, -1])
    return vel[0, 0, -1] + (vel[0, 0, -1] - vel[0, 0, -2]) * ratio


@gtscript.function
def p_weighted_average_domain(vel, dp0):
    int_ratio = 1.0 / (dp0[0, 0, -1] + dp0)
    return (dp0 * vel[0, 0, -1] + dp0[0, 0, -1] * vel) * int_ratio


@gtscript.function
def xy_flux(gz_x, gz_y, xfx, yfx):
    fx = xfx * (gz_x[-1, 0, 0] if xfx > 0.0 else gz_x)
    fy = yfx * (gz_y[0, -1, 0] if yfx > 0.0 else gz_y)
    return fx, fy


@gtstencil()
def update_dz_c_stencil(
    area: sd,
    dp_ref: sd,
    zs: sd,
    ut: sd,
    vt: sd,
    gz: sd,
    ws: sd,
    dt2: float,
):
    from __externals__ import local_is, local_ie, local_js, local_je
    with computation(PARALLEL), interval(...):
        gz_x = gz
        gz_x = corners.fill_corners_2cells_mult_x(gz_x, gz_x, 1.0, 1.0, 1.0, 1.0)
        gz_y = gz_x
        gz_y = corners.fill_corners_2cells_mult_y(gz_y, gz_y, 1.0, 1.0, 1.0, 1.0)
    with computation(PARALLEL):
        with interval(0, 1):
            xfx = p_weighted_average_top(ut, dp_ref)
            yfx = p_weighted_average_top(vt, dp_ref)
        with interval(1, -1):
            xfx = p_weighted_average_domain(ut, dp_ref)
            yfx = p_weighted_average_domain(vt, dp_ref)
        with interval(-1, None):
            xfx = p_weighted_average_bottom(ut, dp_ref)
            yfx = p_weighted_average_bottom(vt, dp_ref)
    with computation(PARALLEL), interval(...):
        fx, fy = xy_flux(gz_x, gz_y, xfx, yfx)
        with horizontal(region[local_is - 1:local_ie+2, local_js - 1:local_je+2]):
            gz = (gz_y * area + fx - fx[1, 0, 0] + fy - fy[0, 1, 0]) / (
                area + xfx - xfx[1, 0, 0] + yfx - yfx[0, 1, 0]
            )
    with computation(PARALLEL), interval(-1, None):
        rdt = 1.0 / dt2
        with horizontal(region[local_is - 1:local_ie+2, local_js - 1:local_je+2]):
            ws = (zs - gz) * rdt
    with computation(BACKWARD), interval(0, -1):
        with horizontal(region[local_is - 1:local_ie+2, local_js - 1:local_je+2]):
            gz_kp1 = gz[0, 0, 1] + DZ_MIN
            gz = gz if gz > gz_kp1 else gz_kp1
