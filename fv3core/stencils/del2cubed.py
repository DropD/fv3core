import dace
from gt4py.gtscript import PARALLEL, computation, interval

import fv3core._config as spec
import fv3core.utils.gt4py_utils as utils
from fv3core.decorators import FrozenStencil, computepath_function, computepath_method
from fv3core.utils.grid import axis_offsets
from fv3core.utils.typing import FloatField, FloatFieldIJ


#
# Flux value stencils
# ---------------------
def compute_zonal_flux(flux: FloatField, a_in: FloatField, del_term: FloatFieldIJ):
    with computation(PARALLEL), interval(...):
        flux = del_term * (a_in[-1, 0, 0] - a_in)


def compute_meridional_flux(flux: FloatField, a_in: FloatField, del_term: FloatFieldIJ):
    with computation(PARALLEL), interval(...):
        flux = del_term * (a_in[0, -1, 0] - a_in)


#
# Q update stencil
# ------------------
def update_q(
    q: FloatField, rarea: FloatFieldIJ, fx: FloatField, fy: FloatField, cd: float
):
    with computation(PARALLEL), interval(...):
        q = q + cd * rarea * (fx - fx[1, 0, 0] + fy - fy[0, 1, 0])



class HyperdiffusionDamping:
    """
    Fortran name is del2_cubed
    """

    def __init__(self, grid, nmax: int):
        """
        Args:
            grid: fv3core grid object
        """
        self.grid = spec.grid
        origin = self.grid.full_origin()
        domain = self.grid.domain_shape_full()
        ax_offsets = axis_offsets(spec.grid, origin, domain)
        self._fx = utils.make_storage_from_shape(
            self.grid.domain_shape_full(add=(1, 1, 1)), origin=origin
        )
        self._fy = utils.make_storage_from_shape(
            self.grid.domain_shape_full(add=(1, 1, 1)), origin=origin
        )

        self._ntimes = min(3, nmax)

        # n = 0
        nt = self._ntimes - 1
        origin = (self.grid.is_ - nt, self.grid.js - nt, 0)
        nx = self.grid.nic + 2 * nt
        ny = self.grid.njc + 2 * nt
        domain_x = (nx + 1, ny, self.grid.npz)
        domain_y = (nx, ny + 1, self.grid.npz)
        domain = (nx, ny, self.grid.npz)
        self._compute_zonal_flux1 = FrozenStencil(
            compute_zonal_flux,
            origin,
            domain_x,
        )
        self._compute_meridional_flux1 = FrozenStencil(
            compute_meridional_flux,
            origin,
            domain_y,
        )
        self._update_q1 = FrozenStencil(
            update_q,
            origin,
            domain,
        )
        # n = 1
        nt = self._ntimes - 2
        origin = (self.grid.is_ - nt, self.grid.js - nt, 0)
        nx = self.grid.nic + 2 * nt
        ny = self.grid.njc + 2 * nt
        domain_x = (nx + 1, ny, self.grid.npz)
        domain_y = (nx, ny + 1, self.grid.npz)
        domain = (nx, ny, self.grid.npz)
        self._compute_zonal_flux2 = FrozenStencil(
            compute_zonal_flux,
            origin,
            domain_x,
        )
        self._compute_meridional_flux2 = FrozenStencil(
            compute_meridional_flux,
            origin,
            domain_y,
        )
        self._update_q2 = FrozenStencil(
            update_q,
            origin,
            domain,
        )
        # n = 2
        nt = self._ntimes - 3
        origin = (self.grid.is_ - nt, self.grid.js - nt, 0)
        nx = self.grid.nic + 2 * nt
        ny = self.grid.njc + 2 * nt
        domain_x = (nx + 1, ny, self.grid.npz)
        domain_y = (nx, ny + 1, self.grid.npz)
        domain = (nx, ny, self.grid.npz)
        self._compute_zonal_flux3 = FrozenStencil(
            compute_zonal_flux,
            origin,
            domain_x,
        )
        self._compute_meridional_flux3 = FrozenStencil(
            compute_meridional_flux,
            origin,
            domain_y,
        )
        self._update_q3 = FrozenStencil(
            update_q,
            origin,
            domain,
        )

    @computepath_method
    def __call__(self, qdel, cd: float):

        """
        Perform hyperdiffusion damping/filtering

        Args:
            qdel (inout): Variable to be filterd
            nmax: Number of times to apply filtering
            cd: Damping coeffcient
        """
        # n = 0
        nt = self._ntimes - 1

        self._compute_zonal_flux1(
            self._fx,
            qdel,
            self.grid.del6_v,
        )
        self._compute_meridional_flux1(
            self._fy,
            qdel,
            self.grid.del6_u,
        )

        self._update_q1(
            qdel,
            self.grid.rarea,
            self._fx,
            self._fy,
            cd,
        )
        if self._ntimes == 1:
            return

        # n = 1
        nt = self._ntimes - 2

        self._compute_zonal_flux2(
            self._fx,
            qdel,
            self.grid.del6_v,
        )

        self._compute_meridional_flux2(
            self._fy,
            qdel,
            self.grid.del6_u,
        )

        self._update_q2(
            qdel,
            self.grid.rarea,
            self._fx,
            self._fy,
            cd,
        )
        # n = 2
        nt = self._ntimes - 3

        self._compute_zonal_flux3(
            self._fx,
            qdel,
            self.grid.del6_v,
        )

        self._compute_meridional_flux3(
            self._fy,
            qdel,
            self.grid.del6_u,
        )

        self._update_q3(
            qdel,
            self.grid.rarea,
            self._fx,
            self._fy,
            cd,
        )
