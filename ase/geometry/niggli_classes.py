import itertools
import numpy as np
from ase.geometry.bravais import (bravais_lattices, UnconventionalLattice,
                                  bravais_names,
                                  get_bravais_lattice_from_reduced_form)
from ase.geometry import Cell

"""This module implements a crude method to recognize most Bravais lattices.

There are probably better methods."""


niggli_op_table = {  # Generated by generate_niggli_op_table()
 'BCC': [(1, 0, 0, 0, 1, 0, 0, 0, 1)],
 'BCT': [(1, 0, 0, 0, 1, 0, 0, 0, 1),
         (0, 1, 0, 0, 0, 1, 1, 0, 0),
         (0, 1, 0, 1, 0, 0, 1, 1, -1),
         (-1, 0, 1, 0, 1, 0, -1, 1, 0),
         (1, 1, 0, 1, 0, 0, 0, 0, -1)],
 'CUB': [(1, 0, 0, 0, 1, 0, 0, 0, 1)],
 'FCC': [(1, 0, 0, 0, 1, 0, 0, 0, 1)],
 'HEX': [(1, 0, 0, 0, 1, 0, 0, 0, 1), (0, 1, 0, 0, 0, 1, 1, 0, 0)],
 'ORC': [(1, 0, 0, 0, 1, 0, 0, 0, 1)],
 'ORCC': [(1, 0, 0, 0, 1, 0, 0, 0, 1),
          (1, 0, -1, 1, 0, 0, 0, -1, 0),
          (-1, 1, 0, -1, 0, 0, 0, 0, 1),
          (0, 1, 0, 0, 0, 1, 1, 0, 0),
          (0, -1, 1, 0, -1, 0, 1, 0, 0)],
 'ORCF': [(0, -1, 0, 0, 1, -1, 1, 0, 0), (-1, 0, 0, 1, 0, 1, 1, 1, 0)],
 'ORCI': [(0, 0, -1, 0, -1, 0, -1, 0, 0),
          (0, 0, 1, -1, 0, 0, -1, -1, 0),
          (0, 1, 0, 1, 0, 0, 1, 1, -1),
          (0, -1, 0, 1, 0, -1, 1, -1, 0)],
 'RHL': [(0, -1, 0, 1, 1, 1, -1, 0, 0),
         (1, 0, 0, 0, 1, 0, 0, 0, 1),
         (1, -1, 0, 1, 0, -1, 1, 0, 0)],
 'TET': [(1, 0, 0, 0, 1, 0, 0, 0, 1), (0, 1, 0, 0, 0, 1, 1, 0, 0)]
}


def lattice_loop(latcls, length_grid, angle_grid):
    param_grids = []
    for varname in latcls.parameters:
        # Actually we could choose one parameter, a, to always be 1,
        # reducing the dimension of the problem by 1.  The lattice
        # recognition code should do something like that as well, but
        # it doesn't.  This could affect the impact of the eps value
        # on lattice determination, so we just loop over the whole
        # thing in order not to worry.
        if varname in 'abc':
            values = length_grid
        elif varname == 'alpha':
            values = angle_grid
        else:
            raise ValueError(varname)
        param_grids.append(values)

    for latpars in itertools.product(*param_grids):
        kwargs = dict(zip(latcls.parameters, latpars))
        try:
            lat = latcls(**kwargs)
        except UnconventionalLattice:
            pass
        else:
            yield lat


def find_niggli_ops(latcls, length_grid, angle_grid):
    niggli_ops = {}

    for lat in lattice_loop(latcls, length_grid, angle_grid):
        cell = lat.tocell()
        rcell, op = cell.niggli_reduce()
        int_op = op.round().astype(int)
        op_integer_err = np.abs(op - int_op).max()
        assert op_integer_err < 1e-12, op_integer_err

        inv_op_float = np.linalg.inv(op)
        inv_op = inv_op_float.round().astype(int)
        inv_op_integer_err = np.abs(inv_op_float - inv_op).max()
        assert inv_op_integer_err < 1e-12, inv_op_integer_err

        op_key = tuple(int_op.flat[:].tolist())
        if op_key in niggli_ops:
            niggli_ops[op_key] += 1
        else:
            niggli_ops[op_key] = 1

        rcell_test = Cell(op.T @ cell)
        rcellpar_test = rcell_test.cellpar()
        rcellpar = rcell.cellpar()
        err = np.abs(rcellpar_test - rcellpar).max()
        assert err < 1e-7, err

    return niggli_ops


def find_all_niggli_ops(length_grid, angle_grid):
    all_niggli_ops = {}
    for latname in bravais_names:
        latcls = bravais_lattices[latname]
        if latcls.ndim < 3:
            continue

        if latname in ['MCL', 'MCLC', 'TRI']:
            continue

        print('Working on {}...'.format(latname))
        niggli_ops = find_niggli_ops(latcls, length_grid, angle_grid)
        print('Found {} ops for {}'.format(len(niggli_ops), latname))
        for key, count in niggli_ops.items():
            print('  {:>40}: {}'.format(str(np.array(key)), count))
        print()
        all_niggli_ops[latname] = niggli_ops
    return all_niggli_ops


def check_type(rcell, name):
    testlat = bravais_lattices[name]
    niggli_ops = niggli_op_table[name]
    results = []

    for op in niggli_ops:
        op = np.array(op, int).reshape(3, 3)
        candidate = Cell(np.linalg.inv(op.T) @ rcell)
        try:
            lat = get_bravais_lattice_from_reduced_form(candidate)
        except (AssertionError, UnconventionalLattice, RuntimeError) as err:
            continue
        if lat.name in ['TRI', 'MCL', 'MCLC']:
            continue
        results.append(lat)
    return results


def identify_lattice(cell):
    rcell, op = cell.niggli_reduce()
    results = []
    for testlat in bravais_names:
        if testlat in ['MCL', 'MCLC', 'TRI']:
            continue
        if bravais_lattices[testlat].ndim < 3:
            continue

        results = check_type(rcell, testlat)

        for name in bravais_names:
            for lat in results:
                if lat.name == name:
                    return lat

    xxxxx


def generate_niggli_op_table():
    length_grid = np.logspace(-0.5, 1.5, 50).round(3)
    angle_grid = np.linspace(10, 179, 50).round()
    all_niggli_ops_and_counts = find_all_niggli_ops(length_grid, angle_grid)

    niggli_op_table = {}
    for latname, ops in all_niggli_ops_and_counts.items():
        niggli_op_table[latname] = list(ops)

    print(pprint.pformat(niggli_op_table))


def test():
    length_grid = np.logspace(-0.5, 1.5, 11).round(3)
    angle_grid = np.linspace(10, 179, 11).round()

    for latname in bravais_names:
        if latname in ['MCL', 'MCLC', 'TRI']:
            continue
        latcls = bravais_lattices[latname]
        if latcls.ndim != 3:
            continue

        print('Check', latname)
        maxerr = 0.0

        for lat in lattice_loop(latcls, length_grid, angle_grid):
            cell = lat.tocell()
            out_lat = identify_lattice(cell)

            # Some lattices represent simpler lattices,
            # e.g. TET(a, a) is cubic.  What we need to check is that
            # the cell parameters are the same.
            cellpar = cell.cellpar()
            outcellpar = out_lat.tocell().cellpar()
            err = np.abs(outcellpar - cellpar).max()
            maxerr = max(err, maxerr)
            if lat.name != out_lat.name:
                print(repr(lat), '-->', repr(out_lat))
            assert err < 1e-8, (err, repr(lat), repr(out_lat))

        print('    OK.  Maxerr={}'.format(maxerr))

if __name__ == '__main__':
    test()
