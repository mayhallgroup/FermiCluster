import numpy as np
import scipy
import itertools
import time
from math import factorial
import copy as cp
import sys

from hubbard_fn import *

from Cluster import *
from ClusteredOperator import *
from ClusteredState import *
from tools import *
from bc_cipsi import *
import pyscf
ttt = time.time()

n_orb =  12 
U = 5.
beta = 1.0

h, g = get_hubbard_params(n_orb,beta,U,pbc=False)
np.random.seed(2)
#tmp = np.random.rand(h.shape[0],h.shape[1])*0.01
#h += tmp + tmp.T

if 0:
    Escf,orb,h,g,C = run_hubbard_scf(h,g,n_orb//2)

do_fci = 0
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
    e, ci = cisolver.kernel(h, g, h.shape[1], mol.nelectron, ecore=0)
    print(" FCI:        %12.8f"%e)

blocks = [[0,5],[1,4],[2,3]]
blocks = [[0],[1],[2],[3],[4],[5]]
blocks = [[0],[1],[2],[3],[4],[5],[6],[7]]
blocks = [[0,1],[2,3],[4,5],[6,7]]
blocks = [[0,1],[2,3]]
blocks = [[0,1],[2,3,4,5],[6,7]]
blocks = [[0,1,6,7],[2,3,4,5]]
blocks = [[0,1,2,3],[4,5],[6,7]]
blocks = [[0,1,2,3,4,5],[6,7,8,9,10,11]]
blocks = [[0,1,2],[3,4,5]]
blocks = [[0,1,2,3],[4,5],[6,7]]
blocks = [[0,1,2,3],[4,5,6,7]]
blocks = [[0,1,2,3],[4,5,6,7],[8,9,10,11]]
n_blocks = len(blocks)
clusters = []

for ci,c in enumerate(blocks):
    clusters.append(Cluster(ci,c))

ci_vector = ClusteredState(clusters)
#ci_vector.init(((2,2),(0,0)))
#ci_vector.init(((2,2),(2,2),(0,0)))
#ci_vector.init(((2,2),(2,2),(0,0),(0,0)))
#ci_vector.init(((2,2),(2,2)))
#ci_vector.init(((1,1),(1,1),(1,1)))
#ci_vector.init(((2,1),(1,2)))
#ci_vector.init(((1,1),(1,1),(1,1),(0,0),(0,0),(0,0)))
#ci_vector.init(((1,1),(1,1),(1,1),(1,1)))
#ci_vector.init(((2,2),(2,2),(0,0),(0,0)))
#ci_vector.init(((1,1),(1,1)))
#ci_vector.init(((2,2),(2,2),(0,0)))
#ci_vector.init(((3,3),(0,0)))
#ci_vector.init(((4,4),(0,0)))
#ci_vector.init(((4,4),(0,0),(0,0)))
ci_vector.init(((2,2),(2,2),(2,2)))
#ci_vector.init(((1,1),(1,1),(1,1),(1,1)))
#ci_vector.init(((2,2),(1,1),(1,1)))
#ci_vector.init(((3,3),(3,3)))
#ci_vector.init(((4,4),(2,2),(0,0)))
#ci_vector.init(((2,2),(2,2),(2,2)))
#ci_vector.init(((4,4),(4,4),(4,4),(0,0),(0,0),(0,0)))
#ci_vector.init(((1,1),(1,1),(1,1),(1,1),(0,0),(0,0),(0,0),(0,0)))
#ci_vector.init(((2,2),(2,2),(2,2),(2,2),(2,2),(2,2)))

print(" Clusters:")
[print(ci) for ci in clusters]

clustered_ham = ClusteredOperator(clusters)
print(" Add 1-body terms")
clustered_ham.add_1b_terms(h)
print(" Add 2-body terms")
clustered_ham.add_2b_terms(g)
#clustered_ham.combine_common_terms(iprint=1)

print(" Build cluster basis")
for ci_idx, ci in enumerate(clusters):
    assert(ci_idx == ci.idx)
    print(" Extract local operator for cluster",ci.idx)
    opi = clustered_ham.extract_local_operator(ci_idx)
    print()
    print()
    print(" Form basis by diagonalize local Hamiltonian for cluster: ",ci_idx)
    ci.form_eigbasis_from_local_operator(opi,max_roots=1000)


#clustered_ham.add_ops_to_clusters()
print(" Build these local operators")
for c in clusters:
    print(" Build mats for cluster ",c.idx)
    c.build_op_matrices()

#ci_vector.expand_to_full_space()
#ci_vector.expand_each_fock_space()

e_prev = 0
thresh_conv = 1e-8
ci_vector_ref = ci_vector.copy()
e_last = 0
for brdm_iter in range(20):
    ci_vector, pt_vector, e0, e2 = bc_cipsi(ci_vector_ref.copy(), clustered_ham, thresh_cipsi=1e-4, thresh_ci_clip=1e-4)
    print(" CIPSI: E0 = %12.8f E2 = %12.8f CI_DIM: %i" %(e0, e2, len(ci_vector)))
  
    if abs(e_prev-e2) < thresh_conv:
        print(" Converged BRDMs")
        break
    e_prev = e2
    pt_vector.add(ci_vector)
    for ci in clusters:
        print()
        rdms = build_brdm(pt_vector, ci.idx)
        #rdms = build_brdm(ci_vector, ci.idx)
        norm = 0
        rotations = {}
        for fspace,rdm in rdms.items():
            print(" Diagonalize RDM for Cluster %2i in Fock space:"%ci.idx, fspace,flush=True)
            n,U = np.linalg.eigh(rdm)
            idx = n.argsort()[::-1]
            n = n[idx]
            U = U[:,idx]
            norm += sum(n)
            for ni_idx,ni in enumerate(n):
                if abs(ni) > 1e-12:
                    print("   Rotated State %4i: %12.8f"%(ni_idx,ni))
            rotations[fspace] = U
        print(" Final norm: %12.8f"%norm)
    
        ci.rotate_basis(rotations)
    delta_e = e0 - e_last
    e_last = e0
    if abs(delta_e) < 1e-8:
        print(" Converged BRDM iterations")
        break
