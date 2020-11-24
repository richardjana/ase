import numpy as np
import ase.units as un

class siesta_lrtddft:
    """Calculator interface for linear response TDDFT for Siesta via
    [PyNAO](https://mbarbry.website.fr.to/pynao/doc/html/)
    """
    def __init__(self, initialize=False, **kw):
        """
        Parameters
        ----------
        initialize: bool
            To initialize the tddft calculations before calculating the polarizability
            Can be useful to calculate multiple frequency range without the need
            to recalculate the kernel
        kw: dictionary
            keywords for the tddft_iter function from PyNAO
        """

        try:
            from pynao import tddft_iter
        except RuntimeError:
            raise RuntimeError("running lrtddft with Siesta calculator requires pynao package")

        self.initialize=initialize
        self.lrtddft_params = kw
        self.tddft = None

        # convert iter_broadening to Ha
        if "iter_broadening" in self.lrtddft_params.keys():
            self.lrtddft_params["iter_broadening"] /= un.Ha

        if self.initialize:
            self.tddft = tddft_iter(**self.lrtddft_params)

    def get_polarizability(self, omega, Eext=np.array([1.0, 1.0, 1.0]), inter=True):
        """
        Calculate the polarizability of a molecule via linear response TDDFT
        calculation.

        Parameters
        ----------
        omega: float or array like
            frequency range for which the polarizability should be computed, in eV

        Returns
        -------
            Add to the self.results dict the following items:
        freq range: array like
            array of dimension (nff) containing the frequency range in eV.

        polarizability nonin: array like (complex)
            array of dimension (nff, 3, 3) with nff the frequency number,
            the second and third dimension are the matrix elements of the
            non-interactive polarizability::

                P_xx, P_xy, P_xz, Pyx, .......
                
        Returns
        -------
        polarizability tensor with unit (e^2 Angstrom^2 / eV).
        Multiply with Bohr * Ha to get (Angstrom^3)


        polarizability: array like (complex)
            array of dimension (nff, 3, 3) with nff the frequency number,
            the second and third dimension are the matrix elements of the
            interactive polarizability::

                P_xx, P_xy, P_xz, Pyx, .......

        density change nonin: array like (complex)
            contains the non interacting density change in product basis

        density change inter: array like (complex)
            contains the interacting density change in product basis

        References
        ----------
        https://gitlab.com/mbarbry/pynao

        Example
        -------

        import numpy as np
        import matplotlib.pyplot as plt

        from ase.build import molecule
        from ase.calculators.siesta import Siesta
        from ase.calculators.siesta.siesta_lrtddft import siesta_lrtddft
        from ase.units import Ry, eV, Ha

        atoms = molecule("CH4")

        siesta = Siesta(
              mesh_cutoff=250 * Ry,
              basis_set='DZP',
              pseudo_qualifier='gga',
              xc="PBE",
              energy_shift=(25 * 10**-3) * eV,
              fdf_arguments={
                'SCFMustConverge': False,
                'COOP.Write': True,
                'WriteDenchar': True,
                'PAO.BasisType': 'split',
                'DM.Tolerance': 1e-4,
                'DM.MixingWeight': 0.01,
                "MD.NumCGsteps": 0,
                "MD.MaxForceTol": (0.02, "eV/Ang"),
                'MaxSCFIterations': 10000,
                'DM.NumberPulay': 4,
                'XML.Write': True,
                "WriteCoorXmol": True})

        atoms.set_calculator(siesta)

        e = atoms.get_potential_energy()
        print("DFT potential energy", e)

        freq = np.arange(0.0, 25.0, 0.05)
        lr = siesta_lrtddft(label="siesta", jcutoff=7, iter_broadening=0.15,
                            xc_code='LDA,PZ', tol_loc=1e-6, tol_biloc=1e-7)
        pmat = lr.get_polarizability(freq)

        # plot polarizability
        plt.plot(freq, pmat[0, 0, :].imag)
        plt.show()
        """
        from pynao import tddft_iter

        if not self.initialize:
            self.tddft = tddft_iter(**self.lrtddft_params)

        if isinstance(omega, float):
            freq = np.array([omega])
        elif isinstance(omega, list):
            freq = np.array([omega])
        elif isinstance(omega, np.ndarray):
            freq = omega
        else:
            raise ValueError("omega soulf")

        freq_cmplx = freq/un.Ha + 1j * self.tddft.eps
        if inter:
            pmat = -self.tddft.comp_polariz_inter_Edir(freq_cmplx, Eext=Eext)
            self.dn = self.tddft.dn
        else:
            pmat = -self.tddft.comp_polariz_nonin_Edir(freq_cmplx, Eext=Eext)
            self.dn = self.tddft.dn0

        return pmat

class siesta_raman(siesta_lrtddft):
    """Raman interface for Siesta calculator
    """
    def __init__(self, omega=0.0, **kw):

        self.omega = omega
        super().__init__(**kw)


    def __call__(self, *args, **kwargs):
        """Shorthand for calculate"""
        return self.calculate(*args, **kwargs)

    def calculate(self, atoms):
        """
        Calculate the polarizability for frequency omega


        Parameters
        ----------
        atoms: atoms class
            The atoms definition of the system. Not used but required by Raman
            calculator
        """
        pmat = self.get_polarizability(self.omega, Eext=np,array([1.0, 1.0, 1.0]))

        # take care about units, please
        # Specific for raman calls, it expects just the tensor for a single
        # frequency and need only the real part
        # For static raman, imaginary part is zero??
        # Convert from atomic units to e**2 Ang**2/eV
        return pmat[:, :, 0].real * (un.Bohr**2) / un.Ha
 
def pol2cross_sec(p, omg):
    """
    Convert the polarizability in au to cross section in nm**2

    Input parameters:
    -----------------
    p (np array): polarizability from mbpt_lcao calc
    omg (np.array): frequency range in eV

    Output parameters:
    ------------------
    sigma (np array): cross section in nm**2
    """
    from ase.units import Ha, Bohr, alpha

    c = 1 / alpha                           # speed of the light in au
    omg = omg / Ha                          # to convert from eV to Hartree
    sigma = 4 * np.pi * omg * p / (c)       # bohr**2
    return sigma * (0.1 * Bohr)**2          # nm**2
