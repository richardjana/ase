"""
Provides FixSymmetry class to preserve spacegroup symmetry during optimisation
"""
import sys
import numpy as np

from ase.constraints import (FixConstraint,
                             voigt_6_to_full_3x3_stress,
                             full_3x3_to_voigt_6_stress)

__all__ = ['refine', 'check_symmetry', 'FixSymmetry']

def refine(atoms, symprec=0.01, verbose=False):
    # test orig config with desired tol

    # check if we have access to get_spacegroup from spglib
    # https://atztogo.github.io/spglib/
    try:
        import spglib  # For version 1.9 or later
    except ImportError:
        from pyspglib import spglib  # For versions 1.8.x or before

    dataset = spglib.get_symmetry_dataset(atoms, symprec=symprec)
    if dataset is None:
        raise ValueError("refine failed to get initial symmetry dataset "+
                         spglib.get_error_message())
    if verbose:
        print(("symmetry.refine_symmetry: loose ({}) initial symmetry group number {}, "+
               "international (Hermann-Mauguin) {} Hall {}\n").format(symprec,
                                                                    dataset["number"],
                                                                    dataset["international"],
                                                                    dataset["hall"]))

    # set actual cell to symmetrized cell vectors by copying transformed and rotated standard cell
    std_cell = dataset['std_lattice']
    trans_std_cell = np.dot(dataset['transformation_matrix'].T, std_cell)
    rot_trans_std_cell = np.dot(trans_std_cell, dataset['std_rotation_matrix'])
    atoms.set_cell(rot_trans_std_cell, True)

    # get new dataset and primitive cell
    dataset = spglib.get_symmetry_dataset(atoms, symprec=symprec)
    if dataset is None:
        raise ValueError("refine failed to get symmetrized cell symmetry dataset "+
                         spglib.get_error_message())
    (prim_cell, prim_scaled_pos, prim_types) = spglib.find_primitive(atoms,
                                                                     symprec=symprec)

    # calculate offset between standard cell and actual cell
    std_cell = dataset['std_lattice']
    rot_std_cell = np.dot(std_cell, dataset['std_rotation_matrix'])
    rot_std_pos = np.dot(dataset['std_positions'], rot_std_cell)
    dp0 = (atoms.get_positions()[list(dataset['mapping_to_primitive']).index(0)] -
           rot_std_pos[list(dataset['std_mapping_to_primitive']).index(0)])

    # create aligned set of standard cell positions to figure out mapping
    rot_prim_cell = np.dot(prim_cell, dataset['std_rotation_matrix'])
    inv_rot_prim_cell = np.linalg.inv(rot_prim_cell)
    aligned_std_pos = rot_std_pos + dp0

    # find ideal positions from position of corresponding std cell atom +
    #    integer_vec . primitive cell vectors
    # here we are assuming that primitive vectors returned by find_primitive are
    #    compatible with std_lattice returned by get_symmetry_dataset
    mapping_to_primitive = list(dataset['mapping_to_primitive'])
    std_mapping_to_primitive = list(dataset['std_mapping_to_primitive'])
    p = atoms.get_positions()
    for i_at in range(len(atoms)):
        std_i_at = std_mapping_to_primitive.index(mapping_to_primitive[i_at])
        dp = aligned_std_pos[std_i_at] - p[i_at]
        dp_s = np.dot(dp, inv_rot_prim_cell)
        p[i_at] = aligned_std_pos[std_i_at] - np.dot(np.round(dp_s), rot_prim_cell)
    atoms.set_positions(p)

    # test final config with tight tol
    dataset = spglib.get_symmetry_dataset(atoms, symprec=1.0e-4)
    if dataset is None:
        raise ValueError("refine failed to get final symmetry dataset "+spglib.get_error_message())
    if verbose:
        print(("symmetry.refine_symmetry: precise ({}) symmetrized symmetry group number {}, "+
               "international (Hermann-Mauguin) {} Hall {}\n").format(1.0e-4,
                                                                      dataset["number"],
                                                                      dataset["international"],
                                                                      dataset["hall"]))

def check_symmetry(atoms, symprec=1.0e-6, verbose=False):
    """
    Check symmetry of `at` with precision `symprec` using `spglib`

    Prints a summary and returns result of `spglib.get_symmetry_dataset()`
    """
    # check if we have access to get_spacegroup from spglib
    # https://atztogo.github.io/spglib/
    try:
        import spglib  # For version 1.9 or later
    except ImportError:
        from pyspglib import spglib  # For versions 1.8.x or before
    dataset = spglib.get_symmetry_dataset(atoms, symprec=symprec)
    if verbose:
        print("ase.spacegroup.symmetrize.check_symmetry: prec", symprec,
              "got symmetry group number", dataset["number"],
              ", international (Hermann-Mauguin)", dataset["international"],
              ", Hall ",dataset["hall"])
    return dataset

def prep(atoms, symprec=1.0e-6):
    """
    Prepare `at` for symmetry-preserving minimisation at precision `symprec`

    Returns a tuple `(rotations, translations, symm_map)`
    """
    # check if we have access to get_spacegroup from spglib
    # https://atztogo.github.io/spglib/
    try:
        import spglib  # For version 1.9 or later
    except ImportError:
        from pyspglib import spglib  # For versions 1.8.x or before

    dataset = spglib.get_symmetry_dataset(atoms, symprec=symprec)
    print("symmetry.prep: symmetry group number",dataset["number"],
          ", international (Hermann-Mauguin)", dataset["international"],
          ", Hall", dataset["hall"])
    rotations = dataset['rotations'].copy()
    translations = dataset['translations'].copy()
    symm_map=[]
    scaled_pos = atoms.get_scaled_positions()
    for (r, t) in zip(rotations, translations):
        this_op_map = [-1] * len(atoms)
        for i_at in range(len(atoms)):
            new_p = np.dot(r, scaled_pos[i_at,:]) + t
            dp = scaled_pos - new_p
            dp -= np.round(dp)
            i_at_map = np.argmin(np.linalg.norm(dp,  axis=1))
            this_op_map[i_at] = i_at_map
        symm_map.append(this_op_map)
    return (rotations, translations, symm_map)

def symmetrize_rank1(lattice, inv_lattice, forces, rot, trans, symm_map):
    """
    Return symmetrized forces

    lattice vectors expected as row vectors (same as ASE get_cell() convention),
    inv_lattice is its matrix inverse (get_reciprocal_cell().T)
    """
    scaled_symmetrized_forces_T = np.zeros(forces.T.shape)

    scaled_forces_T = np.dot(inv_lattice.T,forces.T)
    for (r, t, this_op_map) in zip(rot, trans, symm_map):
        transformed_forces_T = np.dot(r, scaled_forces_T)
        scaled_symmetrized_forces_T[:,this_op_map[:]] += transformed_forces_T[:,:]
    scaled_symmetrized_forces_T /= len(rot)

    symmetrized_forces = np.dot(lattice.T, scaled_symmetrized_forces_T).T

    return symmetrized_forces

def symmetrize_rank2(lattice, lattice_inv, stress_3_3, rot):
    """
    Return symmetrized stress

    lattice vectors expected as row vectors (same as ASE get_cell() convention),
    inv_lattice is its matrix inverse (get_reciprocal_cell().T)
    """
    scaled_stress = np.dot(np.dot(lattice, stress_3_3), lattice.T)

    #NB print('orig', stress_3_3)
    symmetrized_scaled_stress = np.zeros((3,3))
    for r in rot:
        symmetrized_scaled_stress += np.dot(np.dot(r.T, scaled_stress), r)
    symmetrized_scaled_stress /= len(rot)

    sym = np.dot(np.dot(lattice_inv, symmetrized_scaled_stress),
                  lattice_inv.T)
    #NB print('sym', sym)
    return sym

class FixSymmetry(FixConstraint):
    """
    Constraint to preserve spacegroup symmetry during optimisation.

    Requires spglib package to be available.
    """
    def __init__(self, atoms, symprec=0.01, adjust_positions=True, adjust_cell=True):
        refine(atoms, symprec) # refine initial symmetry
        self.rotations, self.translations, self.symm_map = prep(atoms)
        self.do_adjust_positions = adjust_positions
        self.do_adjust_cell = adjust_cell

    def adjust_cell(self, atoms, cell):
        if not self.do_adjust_cell:
            return
        # symmetrize cell as a rank 2 tensor
        symmetrized_cell = symmetrize_rank2(atoms.get_cell(),
                                            atoms.get_reciprocal_cell().T,
                                            cell, self.rotations)
        # print('cell step', np.abs(step).max())
        # print('cell sym step', np.abs(symmetrized_step).max())
        # print('change in step', np.abs(symmetrized_step - step).max())
        cell[:] = cell #symmetrized_cell

    def adjust_positions(self, atoms, new):
        if not self.do_adjust_positions:
            return
        # symmetrize changes in position as rank 1 tensors
        step = new - atoms.positions
        symmetrized_step = symmetrize_rank1(atoms.get_cell(),
                                            atoms.get_reciprocal_cell().T,
                                            step,
                                            self.rotations,
                                            self.translations,
                                            self.symm_map)
        # print('pos step', np.abs(step).max())
        # print('pos sym step', np.abs(symmetrized_step).max())
        # print('change in step', np.abs(symmetrized_step - step).max())
        new[:] = atoms.positions + symmetrized_step

    def adjust_forces(self, atoms, forces):
        # symmetrize forces as rank 1 tensors
        #print('adjusting forces')
        forces[:] = symmetrize_rank1(atoms.get_cell(),
                                      atoms.get_reciprocal_cell().T,
                                      forces,
                                      self.rotations,
                                      self.translations,
                                      self.symm_map)

    def adjust_stress(self, atoms, stress):
        # symmetrize stress as rank 2 tensor
        #NB print('adjusting stress')
        raw_stress = voigt_6_to_full_3x3_stress(stress)
        symmetrized_stress = symmetrize_rank2(atoms.get_cell(),
                                               atoms.get_reciprocal_cell().T,
                                               raw_stress, self.rotations)
        stress[:] = full_3x3_to_voigt_6_stress(symmetrized_stress)
