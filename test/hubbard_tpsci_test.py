import sys, os
import numpy as np
import scipy
import itertools
import time
from math import factorial
import copy as cp
import sys

from fermicluster import *
from pyscf_helper import *

import pyscf
ttt = time.time()

def run(beta, U, pbc=True,scf=True): 
# {{{
    n_orb = 6 

    h, g = get_hubbard_params(n_orb,beta,U,pbc=True)
    np.random.seed(2)
    #tmp = np.random.rand(h.shape[0],h.shape[1])*0.01
    #h += tmp + tmp.T

    if scf==True:
        Escf,orb,h,g,C = run_hubbard_scf(h,g,n_orb//2)
        init_fspace = ((3,3),(0,0))
    else:
        init_fspace = ((2,1),(1,2))

    do_fci = 1
    if do_fci:
        # FCI
        from pyscf import gto, scf, ao2mo, fci, cc
        pyscf.lib.num_threads(1)
        mol = gto.M(verbose=3)
        mol.nelectron = n_orb
        # Setting incore_anyway=True to ensure the customized Hamiltonian (the _eri
        # attribute) to be used in the post-HF calculations.  Without this parameter,
        # some post-HF method (particularly in the MO integral transformation) may
        # ignore the customized Hamiltonian if memory is not enough.
        mol.incore_anyway = True
        cisolver = fci.direct_spin1.FCI(mol)
        #e, ci = cisolver.kernel(h1, eri, h1.shape[1], 2, ecore=mol.energy_nuc())
        efci, ci = cisolver.kernel(h, g, h.shape[1], mol.nelectron, ecore=0)
        print(" FCI:        %12.8f"%efci)

    blocks = [[0,1,2],[3,4,5]]
    n_blocks = len(blocks)
    
    ecore = 0.0 
    clusters, clustered_ham, ci_vector, cmf_out = system_setup(h, g, ecore, blocks, init_fspace,
                                                                cmf_maxiter = 10
                                                                )

    ci_vector_ref = ci_vector.copy()
    ci_vector, pt_vector, e0, e2 = tp_cipsi(ci_vector_ref.copy(), clustered_ham, thresh_cipsi=1e-12, thresh_ci_clip=1e-12)
    print(" TPSCI: E0 = %12.8f E2 = %12.8f CI_DIM: %i" %(e0, e2, len(ci_vector)))
    if abs(e0 - efci)<1e-7:
        return True
    else:
        return False
# }}}

def test_1():
    assert(run(1,10,pbc=True,scf=False))
def test_2():
    assert(run(1,10,pbc=True,scf=False))

if __name__== "__main__":
    test_1() 
