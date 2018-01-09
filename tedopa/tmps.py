"""
Functions to calculate the time evolution of an operator.
This file contains functions which integrate the single site operators into the
ones acting on odd adjacent sites.
"""
from itertools import repeat

import numpy as np
from scipy.linalg import expm

import mpnum as mp


def _times_to_steps(times, num_trotter_slices):
    """
    ### NB: THIS FUNCTION MODIFIES times IN PLACE DESPITE RETURNING A VALUE! ###
    Convert the given times in evolve(), for which a state is requested, into
    steps (in place) and return tau, which is the maximal time from times
    divided by num_trotter_slices
    Args:
        times (list of float):
            The times for which the evolution should be computed
        num_trotter_slices (int):
            The number of time steps or Trotter slices for the time evolution
    Returns:
        (float):
            maximal t / num_trotter_slices
    """
    times.sort()
    tau = times[-1] / num_trotter_slices
    times[:] = [int(round(t / tau)) for t in times]
    return tau


def _trotter_slice(hamiltonians, tau, num_sites, trotter_order):
    """
    Calculate the time evolution operator u for the respective trotter order for
    one trotter slice.
    Args:
        hamiltonians (list):
            List of two lists of Hamiltonians, the Hamiltonians in the first
            acting on every single site, the Hamiltonians in the second acting
            on every pair of two adjacent sites
        tau (float):
            As defined in _times_to_steps()
        num_sites (int):
            Number of sites of the state to be evolved
        trotter_order (int):
            Order of trotter to be used
    Returns:
        mpnum.MPArray:
            The time evolution operator u for one Trotter slice
    """
    if trotter_order == 2:
        return _trotter_two(hamiltonians, tau, num_sites)
    if trotter_order == 4:
        return _trotter_four(hamiltonians, tau, num_sites)
    else:
        raise ValueError("Trotter order " + str(trotter_order) +
                         " is currently not implemented.")


def _trotter_two(hamiltonians, tau, num_sites):
    """
    Calculate the time evolution operator u, comprising even and odd terms, for
    one Trotter slice and Trotter of order 2.
    Args:
        hamiltonians (list):
            List of two lists of Hamiltonians, the Hamiltonians in the first
            acting on every single site, the Hamiltonians in the second acting
            on every pair of two  adjacent sites
        tau (float):
            As defined in _times_to_steps()
        num_sites (int):
            Number of sites of the state to be evolved
    Returns:
        mpnum.MPArray:
            The time evolution operator u for one Trotter slice
    """
    h_single, h_adjacent = _get_h_list(hs=hamiltonians, num_sites=num_sites)
    dims, u_odd, u_even = _get_u_list(h_single, h_adjacent, tau=tau)
    u_odd, u_even = _u_list_to_mpo(dims, u_odd, u_even)
    u = mp.dot(mp.dot(u_odd, u_even), u_odd)
    return u


def _trotter_four(hamiltonians, tau, num_sites):
    """
    Calculate the time evolution operator u, comprising even and odd terms, for
    one Trotter slice and Trotter of order 4.
    Args:
        hamiltonians (list):
            List of two lists of Hamiltonians, the Hamiltonians in the first
            acting on every single site, the Hamiltonians in the second acting
            on every pair of two adjacent sites
        tau (float): As defined in _times_to_steps()
        num_sites (int): Number of sites of the state to be evolved
    Returns:
        mpnum.MPArray:
            The time evolution operator u for one Trotter slice
    """
    taus = [tau / (4 - 4 ** (1 / 3)), tau / (4 - 4 ** (1 / 3)),
            tau - 4 * tau / (4 - 4 ** (1 / 3))]
    h_single, h_adjacent = _get_h_list(hs=hamiltonians, num_sites=num_sites)
    u_lists = [_get_u_list(h_single, h_adjacent, tau=tau) for tau in taus]
    u_mpos = [_u_list_to_mpo(*element) for element in u_lists]
    u_parts = [mp.dot(mp.dot(element[0], element[1]), element[0])
               for element in u_mpos]
    u = mp.dot(mp.dot(u_parts[0], u_parts[1]), u_parts[2])
    _compress(u, 'mpo')
    u = mp.dot(u, u_parts[1])
    u = mp.dot(u, u_parts[0])
    return u


def _get_h_list(hs, num_sites):
    """
    If only one Hamiltonian acting on every single site and one acting on every
    two adjacent sites is given, transform it into the form returned. If not,
    check whether the lengths of the lists match the number of sites.
    Args:
        hs (list):
            Hamiltonians as in evolve()
        num_sites (int):
            Number of sites of the state to be evolved
    Returns:
        (list):
            A list with two items: The first is a list of Hamiltonians acting
            on the single sites, like [h1, h2, h3, ...] and the second is a list
            of Hamiltonians acting on each two adjacent sites, like [h12, h23,
            h34, ...]
    """
    if type(hs[0]) is not list:
        hs = [list(repeat(hs[0], num_sites)),
              list(repeat(hs[1], num_sites - 1))]
    elif (len(hs[0]) != num_sites) or (len(hs[1]) != num_sites - 1):
        raise ValueError(
            "Number of given Hamiltonians does not match number of sites")
    return hs[0], hs[1]


def _get_u_list(h_single, h_adjacent, tau):
    """
    Calculate time evolution operators from Hamiltonians. The time evolution
    operators acting on odd sites contain a factor .5 for the second order
    Trotter.
    Args:
        h_single (list):
            The Hamiltonians acting on every single site
        h_adjacent (list):
            The Hamiltonians acting on every two adjacent sites
        tau (float):
            As defined in _times_to_steps()
    Returns:
        (list):
            A list with three items: (i) List of dimensions of each site and
            lists of time evolution operators. (ii) List of operators acting on
            odd adjacent sites, like [u12, u34, ...] (iii) List of operators
            acting on even adjacent sites, like [u23, u45, ...]
    """
    dims = [len(h_single[i]) for i in range(len(h_single))]
    h_2sites = [np.kron(h_single[i], np.identity(len(h_single[i + 1]))) +
                np.kron(np.identity(len(h_single[i])), h_single[i + 1])
                for i in range(0, len(h_single) - 1, 2)]
    u_odd = list(expm(-1j * tau / 2 * (h + h_2sites[i]))
                 for i, h in enumerate(h_adjacent[::2]))
    u_even = list(expm(-1j * tau * h) for h in h_adjacent[1::2])
    if len(u_odd) == len(u_even):
        u_odd = u_odd + [expm(-1j * tau / 2 * h_single[-1])]
    return dims, u_odd, u_even


def _u_list_to_mpo(dims, u_odd, u_even):
    """
    Transform the matrices for time evolution to operators acting on the full
    state
    Args:
        dims (list):
            List of dimensions of each site
        u_odd (list):
            List of time evolution operators acting on odd adjacent sites
        u_even (list):
            List of time evolution operators acting on even adjacent sites
    Returns:
        (list):
            A list of two mparrays. (i) The time evolution MPOs for the full
            state acting on odd adjacent sites (ii) The time evolution MPOs for
            the full state acting on even adjacent sites
    """
    if len(dims) % 2 == 1:
        last_h = u_odd[-1]
        u_odd = u_odd[:-1]
    odd = mp.chain(matrix_to_mpo(
        u, [[dims[2 * i]] * 2, [dims[2 * i + 1]] * 2])
        for i, u in enumerate(u_odd))
    even = mp.chain(matrix_to_mpo(
        u, [[dims[2 * i + 1]] * 2, [dims[2 * i + 2]] * 2])
        for i, u in enumerate(u_even))
    even = mp.chain([mp.eye(1, dims[0]), even])
    if len(u_odd) > len(u_even):
        even = mp.chain([even, mp.eye(1, dims[-1])])
    elif len(u_even) == len(u_odd):
        odd = mp.chain([odd, matrix_to_mpo(last_h, [[dims[-1]] * 2])])
    return odd, even


def matrix_to_mpo(matrix, shape):
    """
    Generates a MPO from a NxN matrix in global form (probably also works for
    MxN). The number of legs per site must be the same for all sites.
    Args:
        matrix (numpy.ndarray):
            The matrix to be transformed to an MPO
        shape (list):
            The shape the single sites of the resulting MPO should have, as used
            in mpnum. For example three sites with two legs each might look like
            [[3, 3], [2, 2], [2, 2]]
    Returns:
        mpnum.MPArray:
            The MPO representing the matrix
    """
    num_legs = len(shape[0])
    if not (np.array([len(shape[i]) for i in range(len(shape))]) == num_legs).all():
        raise ValueError("Not all sites have the same number of physical legs")
    newShape = []
    for i in range(num_legs):
        for j in range(len(shape)):
            newShape = newShape + [shape[j][i]]
    matrix = matrix.reshape(newShape)
    mpo = mp.MPArray.from_array_global(matrix, ndims=num_legs)
    _compress(mpo, 'mpo')
    return mpo
# Does this work, is state mutable and this operation in place?


def _compress(state, method):
    """
    Compress and normalize a state with a very small relative error. This is
    meant to get unnecessary ranks out of a state without losing information.
    Args:
        state (mpnum.MPArray):
            The state to be compressed
        method (str):
            Whether the state is MPO or PMPS
    Returns:
        (None)
    """
    state.compress(relerr=1e-20)
    state = _normalize(state, method)
# Does this work, is state mutable and this operation in place?


def _normalize(state, method):
    """
    Normalize a state (hopefully in place)
    Args:
        state (mpnum.MPArray): The state to be normalized
        method (str): Whether it is a MPO or PMPS state
    Returns: nothing
    """
    if method == 'pmps':
        state = state / mp.norm(state)
    if method == 'mpo':
        state = state / mp.trace(state)


def evolve(state, hamiltonians, ts, num_trotter_slices, method, compr, trotter_order=2):
    """
    Evolve a state using tMPS.
    Args:
        state (mpnum.MPArray):
            The state to be evolved in time(the density matrix, not state
            vector). The state has to be an MPO or PMPS, depending on w hich
            method is chosen
        hamiltonians (list):
            Either a list containing the Hamiltonian acting on every single site
            and the Hamiltonian acting on every two adjacents sites, like[H_i,
            H_ij], or a list containing a list of Hamiltonians acting on the
            single sites and a list of Hamiltonians acting on each two adjacent
            sites, like [[h1, h2, h3, ...], [h12, h23, h34, ...]]
        ts (list of float):
            The times in seconds for which the evolution should be computed. The
            algorithm will calculate the evolution for the largest number in t
            and on the way there store the evolved states for smaller times. NB:
            Beware of memory overload since len(t) mpnum.MPArrays will be stored
        num_trotter_slices (int):
            The number of trotter slices for the largest t.
        method (str):
            Which method to use. Either 'mpo' or 'pmps'.
        compr (dict):
            Compression parameters for the Trotter steps
        trotter_order (int):
            Order of trotter to be used. Currently only 2 and 4
            are implemented
    Returns:
        (list):
            A list of four items: (i) The list of times for which the density
            matrices have been computed (ii) The list of density matrices as MPO
            or PMPS as mpnum.MPArray, depending on the input "method" (iii) The
            errors due to compression during the procedure (iv) The order of
            error due to application of Trotter during the procedure
    """
    # ToDo: See if normalization is in fact in place
    # ToDo: Maybe add support for hamiltonians depending on time (if not too complicated)
    # ToDo: Make sure the hamiltonians are of the right dimension
    # ToDo: Implement tracking of errors properly
    _compress(state, method)
    if len(state) < 3:
        raise ValueError("State has too few sites")
    if (np.array(ts) == 0).all():
        raise ValueError(
            "No time evolution requested by the user. Check your input 't'")
    tau = _times_to_steps(ts, num_trotter_slices)
    u = _trotter_slice(hamiltonians=hamiltonians, tau=tau,
                       num_sites=len(state), trotter_order=trotter_order)
    _compress(u, method)
    return _time_evolution(state, u, ts, tau, method, compr)


def _time_evolution(state, u, ts, tau, method, compr):
    """
    Do the actual time evolution
    Args:
        state (mpnum.MPArray):
            The state to be evolved in time
        u (mpnum.MPArray):
            Time evolution operator acting on the state
        ts (list of int):
            List of time steps as generated by _times_to_steps()
        tau (float):
            As defined in _times_to_steps()
        method (str):
            Method to use as defined in evolve()
        compr (dict):
            Compression parameters for the Trotter steps
    Returns:
        (list):
            A list with four items: (i)The list of times for which the density
            matrices have been computed (ii) The list of density matrices as MPO
            or PMPS as mpnum.MPArray, depending on the input "method" (iii) The
            errors due to compression during the procedure (iv) The order of
            errors due to application of Trotter during the procedure
    """
    times = [0] if ts[0] == 0 else []
    states = [state] if ts[0] == 0 else []
    compr_errors = [0] if ts[0] == 0 else []
    trot_errors = [0] if ts[0] == 0 else []
    if method == 'mpo':
        u_dagger = u.T.conj()
    accumulated_overlap = 1
    accumulated_trotter_error = 0
    for i in range(ts[-1]):
        state = mp.dot(u, state)
        if method == 'mpo':
            state = mp.dot(state, u_dagger)
        _normalize(state, method)
        accumulated_overlap *= state.compress(**compr)
        accumulated_trotter_error += tau ** 3
        if i + 1 in ts:
            times.append(tau * (i + 1))
            states.append(state)
            compr_errors.append(accumulated_overlap)
            trot_errors.append(accumulated_trotter_error)
    return times, states, compr_errors, trot_errors
