"""Classes for linear optimization constraints.

Linear objective functions must be of the form `A*x-b`, where:
    - `A` is a constant matrix that can be pre-computed
    - `x` is a vector of one or more arguments included in `compute.arg_order`
    - `b` is the desired vector set by `objective.target`
"""

import warnings
from abc import ABC

import numpy as np
from termcolor import colored

from desc.backend import jnp
from desc.basis import zernike_radial, zernike_radial_coeffs

from .normalization import compute_scaling_factors
from .objective_funs import _Objective

# TODO: need dim_x attribute


class FixBoundaryR(_Objective):
    """Boundary condition on the R boundary parameters.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : float, ndarray, optional
        Boundary surface coefficients to fix. If None, uses surface coefficients.
    bounds : tuple, optional
        Lower and upper bounds on the objective. Overrides target.
        len(bounds[0]) and len(bounds[1]) must be equal to Objective.dim_f
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(weight) must be equal to Objective.dim_f
    normalize : bool
        Whether to compute the error in physical units or non-dimensionalize.
    normalize_target : bool
        Whether target should be normalized before comparing to computed values.
        if `normalize` is `True` and the target is in physical units, this should also
        be set to True.
    fixed_boundary : bool, optional
        True to enforce the boundary condition on flux surfaces,
        or False to fix the boundary surface coefficients (default).
    modes : ndarray, optional
        Basis modes numbers [l,m,n] of boundary modes to fix.
        len(target) = len(weight) = len(modes).
        If True/False uses all/none of the profile modes.
    surface_label : float
        Surface to enforce boundary conditions on. Defaults to Equilibrium.surface.rho
    name : str
        Name of the objective function.


    Notes
    -----
    If specifying particular modes to fix, the rows of the resulting constraint `A`
    matrix and `target` vector will be re-sorted according to the ordering of
    `basis.modes` which may be different from the order that was passed in.
    """

    _scalar = False
    _linear = True
    _fixed = False  # TODO: can we dynamically detect this instead?
    _units = "(m)"
    _print_value_fmt = "R boundary error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        bounds=None,
        weight=1,
        normalize=True,
        normalize_target=True,
        fixed_boundary=False,
        modes=True,
        surface_label=None,
        name="lcfs R",
    ):

        self._fixed_boundary = fixed_boundary
        self._modes = modes
        self._surface_label = surface_label
        self._args = ["R_lmn"] if self._fixed_boundary else ["Rb_lmn"]
        super().__init__(
            eq=eq,
            target=target,
            bounds=bounds,
            weight=weight,
            normalize=normalize,
            normalize_target=normalize_target,
            name=name,
        )

    def build(self, eq, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium, optional
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        if self._modes is False or self._modes is None:  # no modes
            modes = np.array([[]], dtype=int)
            idx = np.array([], dtype=int)
        elif self._modes is True:  # all modes
            modes = eq.surface.R_basis.modes
            idx = np.arange(eq.surface.R_basis.num_modes)
        else:  # specified modes
            modes = np.atleast_2d(self._modes)
            dtype = {
                "names": ["f{}".format(i) for i in range(3)],
                "formats": 3 * [modes.dtype],
            }
            _, idx, modes_idx = np.intersect1d(
                eq.surface.R_basis.modes.astype(modes.dtype).view(dtype),
                modes.view(dtype),
                return_indices=True,
            )
            # rearrange modes to match order of eq.surface.R_basis.modes
            # and eq.surface.R_lmn,
            # necessary so that the A matrix rows match up with the target b
            modes = np.atleast_2d(eq.surface.R_basis.modes[idx, :])

            if idx.size < modes.shape[0]:
                warnings.warn(
                    colored(
                        "Some of the given modes are not in the surface, "
                        + "these modes will not be fixed.",
                        "yellow",
                    )
                )

        self._dim_f = idx.size
        if self.target is not None:  # rearrange given target to match modes order
            if self._modes is True or self._modes is False:
                raise RuntimeError(
                    "Attempting to provide target for R boundary modes without "
                    + "providing modes array!"
                    + "You must pass in the modes corresponding to the"
                    + "provided target"
                )
            self.target = self.target[modes_idx]

        if self._fixed_boundary:  # R_lmn -> Rb_lmn boundary condition
            self._A = np.zeros((self._dim_f, eq.R_basis.num_modes))
            for i, (l, m, n) in enumerate(eq.R_basis.modes):
                if eq.bdry_mode == "lcfs":
                    j = np.argwhere((modes[:, 1:] == [m, n]).all(axis=1))
                    surf = (
                        eq.surface.rho
                        if self._surface_label is None
                        else self._surface_label
                    )
                    self._A[j, i] = zernike_radial(surf, l, m)

        else:  # Rb_lmn -> Rb optimization space
            self._A = np.eye(eq.surface.R_basis.num_modes)[idx, :]

        # use surface parameters as target if needed
        if self.target is None:
            self.target = eq.surface.R_lmn[idx]

        if self._normalize:
            scales = compute_scaling_factors(eq)
            self._normalization = scales["a"]

        super().build(eq=eq, use_jit=use_jit, verbose=verbose)

    def compute(self, *args, **kwargs):
        """Compute deviation from desired boundary."""
        if len(args):
            x = kwargs.get(self.args[0], args[0])
        else:
            x = kwargs.get(self.args[0])
        return jnp.dot(self._A, x)

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "Rb_lmn"


class FixBoundaryZ(_Objective):
    """Boundary condition on the Z boundary parameters.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : float, ndarray, optional
        Boundary surface coefficients to fix. If None, uses surface coefficients.
    bounds : tuple, optional
        Lower and upper bounds on the objective. Overrides target.
        len(bounds[0]) and len(bounds[1]) must be equal to Objective.dim_f
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(weight) must be equal to Objective.dim_f
    normalize : bool
        Whether to compute the error in physical units or non-dimensionalize.
    normalize_target : bool
        Whether target should be normalized before comparing to computed values.
        if `normalize` is `True` and the target is in physical units, this should also
        be set to True.
    fixed_boundary : bool, optional
        True to enforce the boundary condition on flux surfaces,
        or False to fix the boundary surface coefficients (default).
    modes : ndarray, optional
        Basis modes numbers [l,m,n] of boundary modes to fix.
        len(target) = len(weight) = len(modes).
        If True/False uses all/none of the surface modes.
    surface_label : float
        Surface to enforce boundary conditions on. Defaults to Equilibrium.surface.rho
    name : str
        Name of the objective function.


    Notes
    -----
    If specifying particular modes to fix, the rows of the resulting constraint `A`
    matrix and `target` vector will be re-sorted according to the ordering of
    `basis.modes` which may be different from the order that was passed in.
    """

    _scalar = False
    _linear = True
    _fixed = False
    _units = "(m)"
    _print_value_fmt = "Z boundary error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        bounds=None,
        weight=1,
        normalize=True,
        normalize_target=True,
        fixed_boundary=False,
        modes=True,
        surface_label=None,
        name="lcfs Z",
    ):

        self._fixed_boundary = fixed_boundary
        self._modes = modes
        self._surface_label = surface_label
        self._args = ["Z_lmn"] if self._fixed_boundary else ["Zb_lmn"]
        super().__init__(
            eq=eq,
            target=target,
            bounds=bounds,
            weight=weight,
            normalize=normalize,
            normalize_target=normalize_target,
            name=name,
        )

    def build(self, eq, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium, optional
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        if self._modes is False or self._modes is None:  # no modes
            modes = np.array([[]], dtype=int)
            idx = np.array([], dtype=int)
        elif self._modes is True:  # all modes
            modes = eq.surface.Z_basis.modes
            idx = np.arange(eq.surface.Z_basis.num_modes)
        else:  # specified modes
            modes = np.atleast_2d(self._modes)
            dtype = {
                "names": ["f{}".format(i) for i in range(3)],
                "formats": 3 * [modes.dtype],
            }
            _, idx, modes_idx = np.intersect1d(
                eq.surface.Z_basis.modes.astype(modes.dtype).view(dtype),
                modes.view(dtype),
                return_indices=True,
            )
            # rearrange modes to match order of eq.surface.Z_basis.modes
            # and eq.surface.Z_lmn,
            # necessary so that the A matrix rows match up with the target b
            modes = np.atleast_2d(eq.surface.Z_basis.modes[idx, :])

            if idx.size < modes.shape[0]:
                warnings.warn(
                    colored(
                        "Some of the given modes are not in the surface, "
                        + "these modes will not be fixed.",
                        "yellow",
                    )
                )

        self._dim_f = idx.size
        if self.target is not None:  # rearrange given target to match modes order
            if self._modes is True or self._modes is False:
                raise RuntimeError(
                    "Attempting to provide target for Z boundary modes without "
                    + "providing modes array!"
                    + "You must pass in the modes corresponding to the"
                    + "provided target"
                )
            self.target = self.target[modes_idx]

        if self._fixed_boundary:  # Z_lmn -> Zb_lmn boundary condition
            self._A = np.zeros((self._dim_f, eq.Z_basis.num_modes))
            for i, (l, m, n) in enumerate(eq.Z_basis.modes):
                if eq.bdry_mode == "lcfs":
                    j = np.argwhere((modes[:, 1:] == [m, n]).all(axis=1))
                    surf = (
                        eq.surface.rho
                        if self._surface_label is None
                        else self._surface_label
                    )
                    self._A[j, i] = zernike_radial(surf, l, m)
        else:  # Zb_lmn -> Zb optimization space
            self._A = np.eye(eq.surface.Z_basis.num_modes)[idx, :]

        # use surface parameters as target if needed
        if self.target is None:
            self.target = eq.surface.Z_lmn[idx]

        if self._normalize:
            scales = compute_scaling_factors(eq)
            self._normalization = scales["a"]

        super().build(eq=eq, use_jit=use_jit, verbose=verbose)

    def compute(self, *args, **kwargs):
        """Compute deviation from desired boundary."""
        if len(args):
            x = kwargs.get(self.args[0], args[0])
        else:
            x = kwargs.get(self.args[0])
        return jnp.dot(self._A, x)

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "Zb_lmn"


class FixLambdaGauge(_Objective):
    """Fixes gauge freedom for lambda: lambda(rho=0)=0 and lambda(theta=0,zeta=0)=0.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : float, ndarray, optional
        Value to fix lambda to at rho=0 and (theta=0,zeta=0)
    bounds : tuple, optional
        Lower and upper bounds on the objective. Overrides target.
        len(bounds[0]) and len(bounds[1]) must be equal to Objective.dim_f
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(weight) must be equal to Objective.dim_f
    normalize : bool
        Whether to compute the error in physical units or non-dimensionalize.
        Note: has no effect for this objective.
    normalize_target : bool
        Whether target should be normalized before comparing to computed values.
        if `normalize` is `True` and the target is in physical units, this should also
        be set to True.
        Note: has no effect for this objective.
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = False
    _units = "(radians)"
    _print_value_fmt = "lambda gauge error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=0,
        bounds=None,
        weight=1,
        normalize=False,
        normalize_target=False,
        name="lambda gauge",
    ):

        super().__init__(
            eq=eq,
            target=target,
            bounds=bounds,
            weight=weight,
            normalize=normalize,
            normalize_target=normalize_target,
            name=name,
        )

    def build(self, eq, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium, optional
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        L_basis = eq.L_basis

        if L_basis.sym:
            self._A = np.zeros((0, L_basis.num_modes))
        else:
            # l(rho,0,0) = 0
            # at theta=zeta=0, basis for lamba reduces to just a polynomial in rho
            # what this constraint does is make all the coefficients of each power
            # of rho equal to zero
            # i.e. if lambda = (L_200 + 2*L_310) rho**2 + (L_100 + 2*L_210)*rho
            # this constraint will make
            # L_200 + 2*L_310 = 0
            # L_100 + 2*L_210 = 0
            L_modes = L_basis.modes
            mnpos = np.where((L_modes[:, 1:] >= [0, 0]).all(axis=1))[0]
            l_lmn = L_modes[mnpos, :]
            if len(l_lmn) > 0:
                c = zernike_radial_coeffs(l_lmn[:, 0], l_lmn[:, 1])
            else:
                c = np.zeros((0, 0))

            A = np.zeros((c.shape[1], L_basis.num_modes))
            A[:, mnpos] = c.T
            self._A = A

        self._dim_f = self._A.shape[0]

        super().build(eq=eq, use_jit=use_jit, verbose=verbose)

    def compute(self, L_lmn, **kwargs):
        """Compute lambda gauge symmetry errors.

        Parameters
        ----------
        L_lmn : ndarray
            Spectral coefficients of L(rho,theta,zeta) -- poloidal stream function.

        Returns
        -------
        f : ndarray
            Lambda gauge symmetry errors.

        """
        return jnp.dot(self._A, L_lmn)


class FixThetaSFL(_Objective):
    """Fixes lambda=0 so that poloidal angle is the SFL poloidal angle.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : float, ndarray, optional
        Value to fix lambda to (always is zero)
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(weight) must be equal to Objective.dim_f
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = True
    _units = "(radians)"
    _print_value_fmt = "Theta - Theta SFL error: {:10.3e} "

    def __init__(self, eq=None, target=0, weight=1, name="Theta SFL"):

        super().__init__(eq=eq, target=target, weight=weight, name=name)

    def build(self, eq, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium, optional
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        idx = np.arange(eq.L_basis.num_modes)
        modes_idx = idx
        self._idx = idx

        self._dim_f = modes_idx.size

        self.target = np.zeros_like(modes_idx)

        super().build(eq=eq, use_jit=use_jit, verbose=verbose)

    def compute(self, L_lmn, **kwargs):
        """Compute Theta SFL errors.

        Parameters
        ----------
        L_lmn : ndarray
            Spectral coefficients of L(rho,theta,zeta) -- poloidal stream function.

        Returns
        -------
        f : ndarray
            Theta - Theta SFL errors.

        """
        fixed_params = L_lmn[self._idx]
        return fixed_params

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "L_lmn"


# TODO: make base class for FixAxis?
class FixAxisR(_Objective):
    """Fixes magnetic axis R coefficients.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : float, ndarray, optional
        Magnetic axis coefficients to fix. If None, uses Equilibrium axis coefficients.
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(weight) must be equal to Objective.dim_f
    modes : ndarray, optional
        Basis modes numbers [l,m,n] of axis modes to fix.
        len(target) = len(weight) = len(modes).
        If True/False uses all/none of the axis modes.
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = False
    _units = "(m)"
    _print_value_fmt = "R axis error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        weight=1,
        modes=True,
        normalize=True,
        normalize_target=True,
        name="axis R",
    ):

        self._modes = modes
        super().__init__(
            eq=eq,
            target=target,
            weight=weight,
            name=name,
            normalize=normalize,
            normalize_target=normalize_target,
        )

    def build(self, eq, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium, optional
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        R_basis = eq.R_basis

        if self._modes is False or self._modes is None:  # no modes
            modes = np.array([[]], dtype=int)
            idx = np.array([], dtype=int)
        elif self._modes is True:  # all modes
            modes = eq.axis.R_basis.modes
            idx = np.arange(eq.axis.R_basis.num_modes)
        else:  # specified modes
            modes = np.atleast_1d(self._modes)
            dtype = {
                "names": ["f{}".format(i) for i in range(3)],
                "formats": 3 * [modes.dtype],
            }
            _, idx, modes_idx = np.intersect1d(
                eq.axis.R_basis.modes.astype(modes.dtype).view(dtype),
                modes.view(dtype),
                return_indices=True,
            )
            # rearrange modes to match order of eq.axis.R_basis.modes
            # and eq.axis.R_n,
            # necessary so that the A matrix rows match up with the target b
            modes = np.atleast_2d(eq.axis.R_basis.modes[idx, :])

            if idx.size < modes.shape[0]:
                warnings.warn(
                    colored(
                        "Some of the given modes are not in the axis, "
                        + "these modes will not be fixed.",
                        "yellow",
                    )
                )

        if modes.size > 0:
            ns = modes[:, 2]
        else:
            ns = np.array([[]], dtype=int)
        # we need A to be M x N where N is number of modes in R_basis
        # and M is the number of modes in the axis (that we are fixing)
        self._A = np.zeros((ns.size, R_basis.num_modes))
        self._dim_f = ns.size

        for i, (l, m, n) in enumerate(R_basis.modes):
            if m != 0:
                continue
            if (l // 2) % 2 == 0:
                j = np.argwhere(n == ns)
                self._A[j, i] = 1
            else:
                j = np.argwhere(n == ns)
                self._A[j, i] = -1

        # use axis parameters as target if needed
        if self.target is None:
            self.target = np.zeros(self._dim_f)
            for n, Rn in zip(eq.axis.R_basis.modes[:, 2], eq.axis.R_n):
                j = np.argwhere(ns == n)
                self.target[j] = Rn
        else:  # rearrange given target to match modes order
            if self._modes is True or self._modes is False:
                raise RuntimeError(
                    "Attempting to provide target for R axis modes without "
                    + "providing modes array!"
                    + "You must pass in the modes corresponding to the"
                    + "provided target axis"
                )
            self.target = self.target[modes_idx]

        super().build(eq=eq, use_jit=use_jit, verbose=verbose)

    def compute(self, R_lmn, **kwargs):
        """Compute axis R errors.

        Parameters
        ----------
        R_lmn : ndarray
            Spectral coefficients of R(rho,theta,zeta)

        Returns
        -------
        f : ndarray
            Axis R errors.

        """
        f = jnp.dot(self._A, R_lmn)
        return f


class FixAxisZ(_Objective):
    """Fixes magnetic axis Z coefficients.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : float, ndarray, optional
        Magnetic axis coefficients to fix. If None, uses Equilibrium axis coefficients.
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(weight) must be equal to Objective.dim_f
    modes : ndarray, optional
        Basis modes numbers [l,m,n] of axis modes to fix.
        len(target) = len(weight) = len(modes).
        If True/False uses all/none of the axis modes.
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = False
    _units = "(m)"
    _print_value_fmt = "Z axis error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        weight=1,
        modes=True,
        name="axis Z",
        normalize=True,
        normalize_target=True,
    ):

        self._modes = modes
        super().__init__(
            eq=eq,
            target=target,
            weight=weight,
            name=name,
            normalize=normalize,
            normalize_target=normalize_target,
        )

    def build(self, eq, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium, optional
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        Z_basis = eq.Z_basis

        if self._modes is False or self._modes is None:  # no modes
            modes = np.array([[]], dtype=int)
            idx = np.array([], dtype=int)
        elif self._modes is True:  # all modes
            modes = eq.axis.Z_basis.modes
            idx = np.arange(eq.axis.Z_basis.num_modes)
        else:  # specified modes
            modes = np.atleast_1d(self._modes)
            dtype = {
                "names": ["f{}".format(i) for i in range(3)],
                "formats": 3 * [modes.dtype],
            }
            _, idx, modes_idx = np.intersect1d(
                eq.axis.Z_basis.modes.astype(modes.dtype).view(dtype),
                modes.view(dtype),
                return_indices=True,
            )
            # rearrange modes to match order of eq.axis.Z_basis.modes
            # and eq.axis.Z_n,
            # necessary so that the A matrix rows match up with the target b
            modes = np.atleast_2d(eq.axis.Z_basis.modes[idx, :])

            if idx.size < modes.shape[0]:
                warnings.warn(
                    colored(
                        "Some of the given modes are not in the axis, "
                        + "these modes will not be fixed.",
                        "yellow",
                    )
                )

        if modes.size > 0:
            ns = modes[:, 2]
        else:
            ns = np.array([[]], dtype=int)
        self._A = np.zeros((ns.size, Z_basis.num_modes))
        self._dim_f = ns.size

        for i, (l, m, n) in enumerate(Z_basis.modes):
            if m != 0:
                continue
            if (l // 2) % 2 == 0:
                j = np.argwhere(n == ns)
                self._A[j, i] = 1
            else:
                j = np.argwhere(n == ns)
                self._A[j, i] = -1

        # use axis parameters as target if needed
        if self.target is None:
            self.target = np.zeros(self._dim_f)
            for n, Zn in zip(eq.axis.Z_basis.modes[:, 2], eq.axis.Z_n):
                j = np.argwhere(ns == n)
                self.target[j] = Zn
        else:  # rearrange given target to match modes order
            if self._modes is True or self._modes is False:
                raise RuntimeError(
                    "Attempting to provide target for Z axis modes without "
                    + "providing modes array!"
                    + "You must pass in the modes corresponding to the"
                    + "provided target axis"
                )
            self.target = self.target[modes_idx]

        super().build(eq=eq, use_jit=use_jit, verbose=verbose)

    def compute(self, Z_lmn, **kwargs):
        """Compute axis Z errors.

        Parameters
        ----------
        Z_lmn : ndarray
            Spectral coefficients of Z(rho,theta,zeta) .

        Returns
        -------
        f : ndarray
            Axis Z errors.

        """
        f = jnp.dot(self._A, Z_lmn)
        return f


class FixModeR(_Objective):
    """Fixes Fourier-Zernike R coefficients.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : float, ndarray, optional
        Fourier-Zernike R coefficient target values. If None,
         uses Equilibrium's R coefficients.
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(weight) must be equal to Objective.dim_f
    modes : ndarray, optional
        Basis modes numbers [l,m,n] of Fourier-Zernike modes to fix.
        len(target) = len(weight) = len(modes).
        If True uses all of the Equilibrium's modes.
        Must be either True or specified as an array
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = True
    _units = "(m)"
    _print_value_fmt = "Fixed-R modes error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        weight=1,
        modes=True,
        name="Fix Mode R",
        normalize=True,
        normalize_target=True,
    ):

        self._modes = modes
        if modes is None or modes is False:
            raise ValueError(
                f"modes kwarg must be specified or True with FixModeR! got {modes}"
            )
        super().__init__(
            eq=eq,
            target=target,
            weight=weight,
            name=name,
            normalize=normalize,
            normalize_target=normalize_target,
        )

    def build(self, eq, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium, optional
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        if self._modes is True:  # all modes
            modes = eq.R_basis.modes
            idx = np.arange(eq.R_basis.num_modes)
            modes_idx = idx
        else:  # specified modes
            modes = np.atleast_2d(self._modes)
            dtype = {
                "names": ["f{}".format(i) for i in range(3)],
                "formats": 3 * [modes.dtype],
            }
            _, idx, modes_idx = np.intersect1d(
                eq.R_basis.modes.astype(modes.dtype).view(dtype),
                modes.view(dtype),
                return_indices=True,
            )
            self._idx = idx
            if idx.size < modes.shape[0]:
                warnings.warn(
                    colored(
                        "Some of the given modes are not in the basis, "
                        + "these modes will not be fixed.",
                        "yellow",
                    )
                )

        self._dim_f = modes_idx.size

        # use current eq's coefficients as target if needed
        if self.target is None:
            self.target = eq.R_lmn[self._idx]
        else:  # rearrange given target to match modes order
            if self._modes is True or self._modes is False:
                raise RuntimeError(
                    "Attempting to provide target for R fixed modes without "
                    + "providing modes array!"
                    + "You must pass in the modes corresponding to the"
                    + "provided target modes"
                )
            self.target = self.target[modes_idx]

        super().build(eq=eq, use_jit=use_jit, verbose=verbose)

    def compute(self, R_lmn, **kwargs):
        """Compute Fixed mode R errors.

        Parameters
        ----------
        R_lmn : ndarray
            Spectral coefficients of R(rho,theta,zeta) .

        Returns
        -------
        f : ndarray
            Fixed mode R errors.

        """
        fixed_params = R_lmn[self._idx]
        return fixed_params

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "R_lmn"


class FixModeZ(_Objective):
    """Fixes Fourier-Zernike Z coefficients.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : float, ndarray, optional
        Fourier-Zernike Z coefficient target values. If None,
         uses Equilibrium's Z coefficients.
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(weight) must be equal to Objective.dim_f
    modes : ndarray, optional
        Basis modes numbers [l,m,n] of Fourier-Zernike modes to fix.
        len(target) = len(weight) = len(modes).
        If True uses all of the Equilibrium's modes.
        Must be either True or specified as an array
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = True
    _units = "(m)"
    _print_value_fmt = "Fixed-Z modes error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        weight=1,
        modes=True,
        name="Fix Mode Z",
        normalize=True,
        normalize_target=True,
    ):

        self._modes = modes
        if modes is None or modes is False:
            raise ValueError(
                f"modes kwarg must be specified or True with FixModeZ! got {modes}"
            )

        super().__init__(
            eq=eq,
            target=target,
            weight=weight,
            name=name,
            normalize=normalize,
            normalize_target=normalize_target,
        )

    def build(self, eq, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium, optional
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        if self._modes is True:  # all modes
            modes = eq.Z_basis.modes
            idx = np.arange(eq.Z_basis.num_modes)
            modes_idx = idx
        else:  # specified modes
            modes = np.atleast_2d(self._modes)
            dtype = {
                "names": ["f{}".format(i) for i in range(3)],
                "formats": 3 * [modes.dtype],
            }
            _, idx, modes_idx = np.intersect1d(
                eq.Z_basis.modes.astype(modes.dtype).view(dtype),
                modes.view(dtype),
                return_indices=True,
            )
            self._idx = idx
            if idx.size < modes.shape[0]:
                warnings.warn(
                    colored(
                        "Some of the given modes are not in the basis, "
                        + "these modes will not be fixed.",
                        "yellow",
                    )
                )

        self._dim_f = modes_idx.size

        # use current eq's coefficients as target if needed
        if self.target is None:
            self.target = eq.Z_lmn[self._idx]
        else:  # rearrange given target to match modes order
            if self._modes is True or self._modes is False:
                raise RuntimeError(
                    "Attempting to provide target for Z fixed modes without "
                    + "providing modes array!"
                    + "You must pass in the modes corresponding to the"
                    + "provided target modes"
                )
            self.target = self.target[modes_idx]

        super().build(eq=eq, use_jit=use_jit, verbose=verbose)

    def compute(self, Z_lmn, **kwargs):
        """Compute Fixed mode Z errors.

        Parameters
        ----------
        Z_lmn : ndarray
            Spectral coefficients of Z(rho,theta,zeta) .

        Returns
        -------
        f : ndarray
            Fixed mode Z errors.

        """
        fixed_params = Z_lmn[self._idx]
        return fixed_params

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "Z_lmn"


class FixSumModesR(_Objective):
    """Fixes a linear sum of Fourier-Zernike R coefficients.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : float, size-1 ndarray, optional
        Fourier-Zernike R coefficient target sum. If None,
         uses current sum of Equilibrium's R coefficients.
         len(target)=1
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(weight) must be equal to Objective.dim_f
    sum_weight : float, ndarray, optional
        Weights on the coefficients in the sum, should be same length as modes.
         Defaults to 1 i.e. target = 1*R_111 + 1*R_222...
    modes : ndarray, optional
        Basis modes numbers [l,m,n] of Fourier-Zernike modes to fix sum of.
         len(weight) = len(modes).
        If True uses all of the Equilibrium's modes.
        Must be either True or specified as an array
    surface_label : float
        Surface to enforce boundary conditions on. Defaults to Equilibrium.surface.rho
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = False
    _units = "(m)"
    _print_value_fmt = "Fixed-R sum modes error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        weight=1,
        sum_weights=None,
        modes=True,
        name="Fix Sum Modes R",
        normalize=True,
        normalize_target=True,
    ):

        self._modes = modes
        if modes is None or modes is False:
            raise ValueError(
                f"modes kwarg must be specified or True with FixSumModesR! got {modes}"
            )
        self._sum_weights = sum_weights
        if target is not None:
            if target.size > 1:
                raise ValueError(
                    "FixSumModesR only accepts 1 target value, please use multiple"
                    + " FixSumModesR objectives if you wish to have multiple"
                    + " sets of constrained mode sums!"
                )
        super().__init__(
            eq=eq,
            target=target,
            weight=weight,
            name=name,
            normalize=normalize,
            normalize_target=normalize_target,
        )

    def build(self, eq, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium, optional
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        if self._modes is True:  # all modes
            modes = eq.R_basis.modes
            idx = np.arange(eq.R_basis.num_modes)
        else:  # specified modes
            modes = np.atleast_2d(self._modes)
            dtype = {
                "names": ["f{}".format(i) for i in range(3)],
                "formats": 3 * [modes.dtype],
            }
            _, idx, modes_idx = np.intersect1d(
                eq.R_basis.modes.astype(modes.dtype).view(dtype),
                modes.view(dtype),
                return_indices=True,
            )
            self._idx = idx
            # rearrange modes and weights to match order of eq.R_basis.modes
            # and eq.R_lmn,
            # necessary so that the A matrix rows match up with the target b
            modes = np.atleast_2d(eq.R_basis.modes[idx, :])
            if self._sum_weights is not None:
                self._sum_weights = np.atleast_1d(self._sum_weights)
                self._sum_weights = self._sum_weights[modes_idx]
            if idx.size < modes.shape[0]:
                warnings.warn(
                    colored(
                        "Some of the given modes are not in the basis, "
                        + "these modes will not be fixed.",
                        "yellow",
                    )
                )
        if self._sum_weights is None:
            sum_weights = np.ones(modes.shape[0])
        else:
            sum_weights = np.atleast_1d(self._sum_weights)
        self._dim_f = np.array([1])

        self._A = np.zeros((1, eq.R_basis.num_modes))
        for i, (l, m, n) in enumerate(modes):
            j = eq.R_basis.get_idx(L=l, M=m, N=n)
            self._A[0, j] = sum_weights[i]

        # use current sum as target if needed
        if self.target is None:
            self.target = np.dot(sum_weights.T, eq.R_lmn[self._idx])

        super().build(eq=eq, use_jit=use_jit, verbose=verbose)

    def compute(self, R_lmn, **kwargs):
        """Compute Sum mode R errors.

        Parameters
        ----------
        R_lmn : ndarray
            Spectral coefficients of R(rho,theta,zeta) .

        Returns
        -------
        f : ndarray
            Fixed sum mode R errors.

        """
        f = jnp.dot(self._A, R_lmn)
        return f

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "R_lmn"


class FixSumModesZ(_Objective):
    """Fixes a linear sum of Fourier-Zernike Z coefficients.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : float, ndarray, optional
        Fourier-Zernike Z coefficient target sum. If None,
         uses current sum of Equilibrium's Z coefficients.
         len(target)=1
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(weight) must be equal to Objective.dim_f
    sum_weight : float, ndarray, optional
        Weights on the coefficients in the sum, should be same length as modes.
         Defaults to 1 i.e. target = 1*Z_111 + 1*Z_222...
    modes : ndarray, optional
        Basis modes numbers [l,m,n] of Fourier-Zernike modes to fix sum of.
         len(weight) = len(modes).
        If True uses all of the Equilibrium's modes.
        Must be either True or specified as an array
    surface_label : float
        Surface to enforce boundary conditions on. Defaults to Equilibrium.surface.rho
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = False
    _units = "(m)"
    _print_value_fmt = "Fixed-Z sum modes error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        weight=1,
        sum_weights=None,
        modes=True,
        name="Fix Sum Modes Z",
        normalize=True,
        normalize_target=True,
    ):

        self._modes = modes
        if modes is None or modes is False:
            raise ValueError(
                f"modes kwarg must be specified or True with FixSumModesZ! got {modes}"
            )
        self._sum_weights = sum_weights
        if target is not None:
            if target.size > 1:
                raise ValueError(
                    "FixSumModesZ only accepts 1 target value, please use multiple"
                    + " FixSumModesZ objectives if you wish to have multiple sets of"
                    + " constrained mode sums!"
                )
        super().__init__(
            eq=eq,
            target=target,
            weight=weight,
            name=name,
            normalize=normalize,
            normalize_target=normalize_target,
        )

    def build(self, eq, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium, optional
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        if self._modes is True:  # all modes
            modes = eq.Z_basis.modes
            idx = np.arange(eq.Z_basis.num_modes)
        else:  # specified modes
            modes = np.atleast_2d(self._modes)
            dtype = {
                "names": ["f{}".format(i) for i in range(3)],
                "formats": 3 * [modes.dtype],
            }
            _, idx, modes_idx = np.intersect1d(
                eq.Z_basis.modes.astype(modes.dtype).view(dtype),
                modes.view(dtype),
                return_indices=True,
            )
            self._idx = idx
            # rearrange modes and weights to match order of eq.Z_basis.modes
            # and eq.Z_lmn,
            # necessary so that the A matrix rows match up with the target b
            modes = np.atleast_2d(eq.Z_basis.modes[idx, :])
            if self._sum_weights is not None:
                self._sum_weights = np.atleast_1d(self._sum_weights)
                self._sum_weights = self._sum_weights[modes_idx]

            if idx.size < modes.shape[0]:
                warnings.warn(
                    colored(
                        "Some of the given modes are not in the basis, "
                        + "these modes will not be fixed.",
                        "yellow",
                    )
                )
        if self._sum_weights is None:
            sum_weights = np.ones(modes.shape[0])
        else:
            sum_weights = np.atleast_1d(self._sum_weights)
        self._dim_f = np.array([1])

        self._A = np.zeros((1, eq.Z_basis.num_modes))
        for i, (l, m, n) in enumerate(modes):
            j = eq.Z_basis.get_idx(L=l, M=m, N=n)
            self._A[0, j] = sum_weights[i]

        # use current sum as target if needed
        if self.target is None:
            self.target = np.dot(sum_weights.T, eq.Z_lmn[self._idx])

        super().build(eq=eq, use_jit=use_jit, verbose=verbose)

    def compute(self, Z_lmn, **kwargs):
        """Compute Sum mode Z errors.

        Parameters
        ----------
        Z_lmn : ndarray
            Spectral coefficients of Z(rho,theta,zeta) .

        Returns
        -------
        f : ndarray
            Fixed sum mode Z errors.

        """
        f = jnp.dot(self._A, Z_lmn)
        return f

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "Z_lmn"


class _FixProfile(_Objective, ABC):
    """Fixes profile coefficients (or values, for SplineProfile).

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : tuple, float, ndarray, optional
        Target value(s) of the objective.
        len(target) = len(weight) = len(modes). If None, uses Profile.params.
        e.g. for PowerSeriesProfile these are profile coefficients, and for
        SplineProfile they are values at knots.
    bounds : tuple, optional
        Lower and upper bounds on the objective. Overrides target.
        len(bounds[0]) and len(bounds[1]) must be equal to Objective.dim_f
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(target) = len(weight) = len(modes)
    normalize : bool
        Whether to compute the error in physical units or non-dimensionalize.
    normalize_target : bool
        Whether target should be normalized before comparing to computed values.
        if `normalize` is `True` and the target is in physical units, this should also
        be set to True.
    profile : Profile, optional
        Profile containing the radial modes to evaluate at.
    indices : ndarray or Bool, optional
        indices of the Profile.params array to fix.
        (e.g. indices corresponding to modes for a PowerSeriesProfile or indices
        corresponding to knots for a SplineProfile).
        Must have len(target) = len(weight) = len(modes).
        If True/False uses all/none of the Profile.params indices.
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = True
    _print_value_fmt = "Fix-profile error: {:.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        bounds=None,
        weight=1,
        normalize=True,
        normalize_target=True,
        profile=None,
        indices=True,
        name="",
    ):

        self._profile = profile
        self._indices = indices
        super().__init__(
            eq=eq,
            target=target,
            bounds=bounds,
            weight=weight,
            normalize=normalize,
            normalize_target=normalize_target,
            name=name,
        )

    def build(self, eq, profile=None, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium
            Equilibrium that will be optimized to satisfy the Objective.
        profile : Profile, optional
            profile to fix
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        if self._profile is None or self._profile.params.size != eq.L + 1:
            self._profile = profile

        # find indices to fix
        if self._indices is False or self._indices is None:  # no indices to fix
            self._idx = np.array([], dtype=int)
        elif self._indices is True:  # all indices of Profile.params
            self._idx = np.arange(np.size(self._profile.params))
        else:  # specified indices
            self._idx = np.atleast_1d(self._indices)

        self._dim_f = self._idx.size
        # use profile parameters as target if needed
        if self.target is None:
            self.target = self._profile.params[self._idx]

        super().build(eq=eq, use_jit=use_jit, verbose=verbose)


class FixPressure(_FixProfile):
    """Fixes pressure coefficients.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : tuple, float, ndarray, optional
        Target value(s) of the objective.
        len(target) = len(weight) = len(modes). If None, uses profile coefficients.
    bounds : tuple, optional
        Lower and upper bounds on the objective. Overrides target.
        len(bounds[0]) and len(bounds[1]) must be equal to Objective.dim_f
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(target) = len(weight) = len(modes)
    normalize : bool
        Whether to compute the error in physical units or non-dimensionalize.
    normalize_target : bool
        Whether target should be normalized before comparing to computed values.
        if `normalize` is `True` and the target is in physical units, this should also
        be set to True.
    profile : Profile, optional
        Profile containing the radial modes to evaluate at.
    indices : ndarray or bool, optional
        indices of the Profile.params array to fix.
        (e.g. indices corresponding to modes for a PowerSeriesProfile or indices
        corresponding to knots for a SplineProfile).
        Must have len(target) = len(weight) = len(modes).
        If True/False uses all/none of the Profile.params indices.
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = True
    _units = "(Pa)"
    _print_value_fmt = "Fixed-pressure profile error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        bounds=None,
        weight=1,
        normalize=True,
        normalize_target=True,
        profile=None,
        indices=True,
        name="fixed-pressure",
    ):

        super().__init__(
            eq=eq,
            target=target,
            bounds=bounds,
            weight=weight,
            normalize=normalize,
            normalize_target=normalize_target,
            profile=profile,
            indices=indices,
            name=name,
        )

    def build(self, eq, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        if eq.pressure is None:
            raise RuntimeError(
                "Attempting to fix pressure on an equilibrium with no "
                + "pressure profile assigned"
            )
        profile = eq.pressure
        if self._normalize:
            scales = compute_scaling_factors(eq)
            self._normalization = scales["p"]
        super().build(eq, profile, use_jit, verbose)

    def compute(self, p_l, **kwargs):
        """Compute fixed pressure profile errors.

        Parameters
        ----------
        p_l : ndarray
            parameters of the pressure profile (Pa).

        Returns
        -------
        f : ndarray
            Fixed profile errors.

        """
        return p_l[self._idx]

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "p_l"


class FixIota(_FixProfile):
    """Fixes rotational transform coefficients.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : tuple, float, ndarray, optional
        Target value(s) of the objective.
        len(target) = len(weight) = len(modes). If None, uses profile coefficients.
    bounds : tuple, optional
        Lower and upper bounds on the objective. Overrides target.
        len(bounds[0]) and len(bounds[1]) must be equal to Objective.dim_f
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(target) = len(weight) = len(modes)
    normalize : bool
        Whether to compute the error in physical units or non-dimensionalize.
        Note: has no effect for this objective.
    normalize_target : bool
        Whether target should be normalized before comparing to computed values.
        if `normalize` is `True` and the target is in physical units, this should also
        be set to True.
        Note: has no effect for this objective.
    profile : Profile, optional
        Profile containing the radial modes to evaluate at.
    indices : ndarray or bool, optional
        indices of the Profile.params array to fix.
        (e.g. indices corresponding to modes for a PowerSeriesProfile or indices.
        corresponding to knots for a SplineProfile).
        Must len(target) = len(weight) = len(modes).
        If True/False uses all/none of the Profile.params indices.
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = True
    _units = "(dimensionless)"
    _print_value_fmt = "Fixed-iota profile error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        bounds=None,
        weight=1,
        normalize=False,
        normalize_target=False,
        profile=None,
        indices=True,
        name="fixed-iota",
    ):

        super().__init__(
            eq=eq,
            target=target,
            bounds=bounds,
            weight=weight,
            normalize=normalize,
            normalize_target=normalize_target,
            profile=profile,
            indices=indices,
            name=name,
        )

    def build(self, eq, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        if eq.iota is None:
            raise RuntimeError(
                "Attempt to fix rotational transform on an equilibrium with no "
                + "rotational transform profile assigned"
            )
        profile = eq.iota
        super().build(eq, profile, use_jit, verbose)

    def compute(self, i_l, **kwargs):
        """Compute fixed iota errors.

        Parameters
        ----------
        i_l : ndarray
            parameters of the iota profile.

        Returns
        -------
        f : ndarray
            Fixed profile errors.

        """
        return i_l[self._idx]

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "i_l"


class FixCurrent(_FixProfile):
    """Fixes toroidal current profile coefficients.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : tuple, float, ndarray, optional
        Target value(s) of the objective.
        len(target) = len(weight) = len(modes). If None, uses profile coefficients.
    bounds : tuple, optional
        Lower and upper bounds on the objective. Overrides target.
        len(bounds[0]) and len(bounds[1]) must be equal to Objective.dim_f
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(target) = len(weight) = len(modes)
    normalize : bool
        Whether to compute the error in physical units or non-dimensionalize.
    normalize_target : bool
        Whether target should be normalized before comparing to computed values.
        if `normalize` is `True` and the target is in physical units, this should also
        be set to True.
    profile : Profile, optional
        Profile containing the radial modes to evaluate at.
    indices : ndarray or bool, optional
        indices of the Profile.params array to fix.
        (e.g. indices corresponding to modes for a PowerSeriesProfile or indices
        corresponding to knots for a SplineProfile).
        Must have len(target) = len(weight) = len(modes).
        If True/False uses all/none of the Profile.params indices.
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = True
    _units = "(A)"
    _print_value_fmt = "Fixed-current profile error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        bounds=None,
        weight=1,
        normalize=True,
        normalize_target=True,
        profile=None,
        indices=True,
        name="fixed-current",
    ):

        super().__init__(
            eq=eq,
            target=target,
            bounds=bounds,
            weight=weight,
            normalize=normalize,
            normalize_target=normalize_target,
            profile=profile,
            indices=indices,
            name=name,
        )

    def build(self, eq, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        if eq.current is None:
            raise RuntimeError(
                "Attempting to fix toroidal current on an equilibrium with no "
                + "current profile assigned"
            )
        profile = eq.current
        if self._normalize:
            scales = compute_scaling_factors(eq)
            self._normalization = scales["I"]
        super().build(eq, profile, use_jit, verbose)

    def compute(self, c_l, **kwargs):
        """Compute fixed current errors.

        Parameters
        ----------
        c_l : ndarray
            parameters of the current profile (A).

        Returns
        -------
        f : ndarray
            Fixed profile errors.

        """
        return c_l[self._idx]

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "c_l"


class FixElectronTemperature(_FixProfile):
    """Fixes electron temperature profile coefficients.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : tuple, float, ndarray, optional
        Target value(s) of the objective.
        len(target) = len(weight) = len(modes). If None, uses profile coefficients.
    bounds : tuple, optional
        Lower and upper bounds on the objective. Overrides target.
        len(bounds[0]) and len(bounds[1]) must be equal to Objective.dim_f
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(target) = len(weight) = len(modes)
    normalize : bool
        Whether to compute the error in physical units or non-dimensionalize.
    normalize_target : bool
        Whether target should be normalized before comparing to computed values.
        if `normalize` is `True` and the target is in physical units, this should also
        be set to True.
    profile : Profile, optional
        Profile containing the radial modes to evaluate at.
    indices : ndarray or bool, optional
        indices of the Profile.params array to fix.
        (e.g. indices corresponding to modes for a PowerSeriesProfile or indices
        corresponding to knots for a SplineProfile).
        Must have len(target) = len(weight) = len(modes).
        If True/False uses all/none of the Profile.params indices.
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = True
    _units = "(eV)"
    _print_value_fmt = "Fixed-electron-temperature profile error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        bounds=None,
        weight=1,
        normalize=True,
        normalize_target=True,
        profile=None,
        indices=True,
        name="fixed-electron-temperature",
    ):

        super().__init__(
            eq=eq,
            target=target,
            bounds=bounds,
            weight=weight,
            normalize=normalize,
            normalize_target=normalize_target,
            profile=profile,
            indices=indices,
            name=name,
        )

    def build(self, eq, use_jit=True, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        if eq.electron_temperature is None:
            raise RuntimeError(
                "Attempting to fix electron temperature on an equilibrium with no "
                + "electron temperature profile assigned"
            )
        profile = eq.electron_temperature
        if self._normalize:
            scales = compute_scaling_factors(eq)
            self._normalization = scales["T"]
        super().build(eq, profile, use_jit, verbose)

    def compute(self, Te_l, **kwargs):
        """Compute fixed electron temperature errors.

        Parameters
        ----------
        Te_l : ndarray
            parameters of the electron temperature profile (eV).

        Returns
        -------
        f : ndarray
            Fixed profile errors.

        """
        return Te_l[self._idx]

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "Te_l"


class FixElectronDensity(_FixProfile):
    """Fixes electron density profile coefficients.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : tuple, float, ndarray, optional
        Target value(s) of the objective.
        len(target) = len(weight) = len(modes). If None, uses profile coefficients.
    bounds : tuple, optional
        Lower and upper bounds on the objective. Overrides target.
        len(bounds[0]) and len(bounds[1]) must be equal to Objective.dim_f
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(target) = len(weight) = len(modes)
    normalize : bool
        Whether to compute the error in physical units or non-dimensionalize.
    normalize_target : bool
        Whether target should be normalized before comparing to computed values.
        if `normalize` is `True` and the target is in physical units, this should also
        be set to True.
    profile : Profile, optional
        Profile containing the radial modes to evaluate at.
    indices : ndarray or bool, optional
        indices of the Profile.params array to fix.
        (e.g. indices corresponding to modes for a PowerSeriesProfile or indices
        corresponding to knots for a SplineProfile).
        Must have len(target) = len(weight) = len(modes).
        If True/False uses all/none of the Profile.params indices.
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = True
    _units = "(m^-3)"
    _print_value_fmt = "Fixed-electron-density profile error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        bounds=None,
        weight=1,
        normalize=True,
        normalize_target=True,
        profile=None,
        indices=True,
        name="fixed-electron-density",
    ):

        super().__init__(
            eq=eq,
            target=target,
            bounds=bounds,
            weight=weight,
            normalize=normalize,
            normalize_target=normalize_target,
            profile=profile,
            indices=indices,
            name=name,
        )

    def build(self, eq, use_jit=True, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        if eq.electron_density is None:
            raise RuntimeError(
                "Attempting to fix electron density on an equilibrium with no "
                + "electron density profile assigned"
            )
        profile = eq.electron_density
        if self._normalize:
            scales = compute_scaling_factors(eq)
            self._normalization = scales["n"]
        super().build(eq, profile, use_jit, verbose)

    def compute(self, ne_l, **kwargs):
        """Compute fixed electron density errors.

        Parameters
        ----------
        ne_l : ndarray
            parameters of the electron density profile (1/m^3).

        Returns
        -------
        f : ndarray
            Fixed profile errors.

        """
        return ne_l[self._idx]

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "ne_l"


class FixIonTemperature(_FixProfile):
    """Fixes ion temperature profile coefficients.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : tuple, float, ndarray, optional
        Target value(s) of the objective.
        len(target) = len(weight) = len(modes). If None, uses profile coefficients.
    bounds : tuple, optional
        Lower and upper bounds on the objective. Overrides target.
        len(bounds[0]) and len(bounds[1]) must be equal to Objective.dim_f
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(target) = len(weight) = len(modes)
    normalize : bool
        Whether to compute the error in physical units or non-dimensionalize.
    normalize_target : bool
        Whether target should be normalized before comparing to computed values.
        if `normalize` is `True` and the target is in physical units, this should also
        be set to True.
    profile : Profile, optional
        Profile containing the radial modes to evaluate at.
    indices : ndarray or bool, optional
        indices of the Profile.params array to fix.
        (e.g. indices corresponding to modes for a PowerSeriesProfile or indices
        corresponding to knots for a SplineProfile).
        Must have len(target) = len(weight) = len(modes).
        If True/False uses all/none of the Profile.params indices.
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = True
    _units = "(eV)"
    _print_value_fmt = "Fixed-ion-temperature profile error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        bounds=None,
        weight=1,
        normalize=True,
        normalize_target=True,
        profile=None,
        indices=True,
        name="fixed-ion-temperature",
    ):

        super().__init__(
            eq=eq,
            target=target,
            bounds=bounds,
            weight=weight,
            normalize=normalize,
            normalize_target=normalize_target,
            profile=profile,
            indices=indices,
            name=name,
        )

    def build(self, eq, use_jit=True, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        if eq.ion_temperature is None:
            raise RuntimeError(
                "Attempting to fix ion temperature on an equilibrium with no "
                + "ion temperature profile assigned"
            )
        profile = eq.ion_temperature
        if self._normalize:
            scales = compute_scaling_factors(eq)
            self._normalization = scales["T"]
        super().build(eq, profile, use_jit, verbose)

    def compute(self, Ti_l, **kwargs):
        """Compute fixed ion temperature errors.

        Parameters
        ----------
        Ti_l : ndarray
            parameters of the ion temperature profile (eV).

        Returns
        -------
        f : ndarray
            Fixed profile errors.

        """
        return Ti_l[self._idx]

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "Ti_l"


class FixAtomicNumber(_FixProfile):
    """Fixes effective atomic number profile coefficients.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : tuple, float, ndarray, optional
        Target value(s) of the objective.
        len(target) = len(weight) = len(modes). If None, uses profile coefficients.
    bounds : tuple, optional
        Lower and upper bounds on the objective. Overrides target.
        len(bounds[0]) and len(bounds[1]) must be equal to Objective.dim_f
    weight : float, ndarray, optional
        Weighting to apply to the Objective, relative to other Objectives.
        len(target) = len(weight) = len(modes)
    normalize : bool
        Whether to compute the error in physical units or non-dimensionalize.
        Note: has no effect for this objective.
    normalize_target : bool
        Whether target should be normalized before comparing to computed values.
        if `normalize` is `True` and the target is in physical units, this should also
        be set to True.
        Note: has no effect for this objective.
    profile : Profile, optional
        Profile containing the radial modes to evaluate at.
    indices : ndarray or bool, optional
        indices of the Profile.params array to fix.
        (e.g. indices corresponding to modes for a PowerSeriesProfile or indices
        corresponding to knots for a SplineProfile).
        Must have len(target) = len(weight) = len(modes).
        If True/False uses all/none of the Profile.params indices.
    name : str
        Name of the objective function.

    """

    _scalar = False
    _linear = True
    _fixed = True
    _units = "(dimensionless)"
    _print_value_fmt = "Fixed-atomic-number profile error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        bounds=None,
        weight=1,
        normalize=False,
        normalize_target=False,
        profile=None,
        indices=True,
        name="fixed-atomic-number",
    ):

        super().__init__(
            eq=eq,
            target=target,
            bounds=bounds,
            weight=weight,
            normalize=normalize,
            normalize_target=normalize_target,
            profile=profile,
            indices=indices,
            name=name,
        )

    def build(self, eq, use_jit=True, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        if eq.atomic_number is None:
            raise RuntimeError(
                "Attempting to fix atomic number on an equilibrium with no "
                + "atomic number profile assigned"
            )
        profile = eq.atomic_number
        super().build(eq, profile, use_jit, verbose)

    def compute(self, Zeff_l, **kwargs):
        """Compute fixed atomic number errors.

        Parameters
        ----------
        Zeff_l : ndarray
            parameters of the current profile.

        Returns
        -------
        f : ndarray
            Fixed profile errors.

        """
        return Zeff_l[self._idx]

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "Zeff_l"


class FixPsi(_Objective):
    """Fixes total toroidal magnetic flux within the last closed flux surface.

    Parameters
    ----------
    eq : Equilibrium, optional
        Equilibrium that will be optimized to satisfy the Objective.
    target : float, optional
        Target value(s) of the objective. If None, uses Equilibrium value.
    bounds : tuple, optional
        Lower and upper bounds on the objective. Overrides target.
    normalize : bool
        Whether to compute the error in physical units or non-dimensionalize.
    normalize_target : bool
        Whether target should be normalized before comparing to computed values.
        if `normalize` is `True` and the target is in physical units, this should also
        be set to True.
    weight : float, optional
        Weighting to apply to the Objective, relative to other Objectives.
    name : str
        Name of the objective function.

    """

    _scalar = True
    _linear = True
    _fixed = True
    _units = "(Wb)"
    _print_value_fmt = "Fixed-Psi error: {:10.3e} "

    def __init__(
        self,
        eq=None,
        target=None,
        bounds=None,
        weight=1,
        normalize=True,
        normalize_target=True,
        name="fixed-Psi",
    ):

        super().__init__(
            eq=eq,
            target=target,
            bounds=bounds,
            weight=weight,
            normalize=normalize,
            normalize_target=normalize_target,
            name=name,
        )

    def build(self, eq, use_jit=False, verbose=1):
        """Build constant arrays.

        Parameters
        ----------
        eq : Equilibrium, optional
            Equilibrium that will be optimized to satisfy the Objective.
        use_jit : bool, optional
            Whether to just-in-time compile the objective and derivatives.
        verbose : int, optional
            Level of output.

        """
        self._dim_f = 1

        if self.target is None:
            self.target = eq.Psi

        if self._normalize:
            scales = compute_scaling_factors(eq)
            self._normalization = scales["Psi"]

        super().build(eq=eq, use_jit=use_jit, verbose=verbose)

    def compute(self, Psi, **kwargs):
        """Compute fixed-Psi error.

        Parameters
        ----------
        Psi : float
            Total toroidal magnetic flux within the last closed flux surface (Wb).

        Returns
        -------
        f : ndarray
            Total toroidal magnetic flux error (Wb).

        """
        return Psi

    @property
    def target_arg(self):
        """str: Name of argument corresponding to the target."""
        return "Psi"
