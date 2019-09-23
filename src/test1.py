import numpy as np
import scipy
import itertools
import time
from math import factorial
import copy as cp
import sys

from hubbard_fn import *
from ci_fn import *

from Cluster import *
from ClusteredOperator import *
from ClusteredState import *

import pyscf
ttt = time.time()

n_orb = 4
U = 1.0
beta = 1.0

h, g = get_hubbard_params(n_orb,beta,U,pbc=False)
np.random.seed(2)
tmp = np.random.rand(h.shape[0],h.shape[1])*0.01
h += tmp + tmp.T
#tmp = np.random.rand(v.shape)*0.01
#h += .11
#h[0,2] = 0
#h[0,3] = 0
#h[1,2] = 0
#h[1,3] = 0
#h[2,0] = 0
#h[3,0] = 0
#h[2,1] = 0
#h[3,1] = 0

print(h)
if 1:
    Escf,orb,h,g,C = run_hubbard_scf(h,g,n_orb//2)



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
    e, ci = cisolver.kernel(h, g, h.shape[1], mol.nelectron, ecore=0)
    print(" FCI:        %12.8f"%e)

#blocks = [[0,2],[1,3]]
#blocks = [[0,1],[2,3]]
blocks = [[0,1,2,3]]
#blocks = [[0,1,2,3],[4,5]]
#blocks = [[0,1,2,3],[4,5,6,7]]
#blocks = [[0,1],[2,3],[4,5]]
#blocks = [[0,1],[2,3],[4,5]]
#blocks = [[0,1,2,3],[4,5,6,7]]
#blocks = [[0,1],[2,3,4,5],[6],[7]]
n_blocks = len(blocks)
clusters = []

# check blocks
seen = [0]*n_orb
for b in blocks:
    for bi in b:
        seen[bi] += 1
for b in seen:
    assert(b==1) 
        
for ci,c in enumerate(blocks):
    clusters.append(Cluster(ci,c))

print(" Clusters:")
[print(ci) for ci in clusters]

clustered_ham = ClusteredOperator(clusters)
print(" Add 1-body terms")
clustered_ham.add_1b_terms(h)
clustered_ham.add_2b_terms(g)


print(" Build cluster basis")
for ci_idx, ci in enumerate(clusters):
    assert(ci_idx == ci.idx)
    print(" Extract local operator for cluster",ci.idx)
    opi = clustered_ham.extract_local_operator(ci_idx)
    print()
    print()
    print(" Form basis by diagonalize local Hamiltonian for cluster: ",ci_idx)
    ci.form_eigbasis_from_local_operator(opi,max_roots=1000)

clustered_ham.add_ops_to_clusters()
print(" Build these local operators")
for c in clusters:
    print(" Build mats for cluster ",c.idx)
    c.build_op_matrices()


for c in clusters:
    print(c)
    for k in c.ops.keys():
        print(" ", k)
        for f in c.ops[k].keys():
            print("   ", f)
#print("a")
#print(clusters[0].ops['a'][((1,2),(2,2))][0,0,:] )
#print("A")
#print(clusters[0].ops['A'][((2,2),(1,2))][0,0,:] )
#print(np.trace(clusters[0].ops['Aa'][((2,2),(2,2))][0,0,:] ))
#exit()


ci_vector = ClusteredState(clusters)
#ci_vector.init(((2,2),(2,2),(0,0)))
#ci_vector.init(((2,2),(2,2),(0,0),(0,0)))
#ci_vector.init(((3,3),(0,0)))
#ci_vector.init(((2,2),(2,2)))
ci_vector.init(((2,2),))
#ci_vector.init(((2,2),(1,1)))
#ci_vector.init(((2,2),(0,0)))
#ci_vector.init(((1,1),(1,1)))
#ci_vector.init(((1,1),(1,1),(1,1)))
#ci_vector.init(((1,1),(1,1),(1,1),(1,1)))
#ci_vector.init(((2,2),(2,2)))




           
if 1:
    # create full space for each fock block defined
    print("\n Create FCI space")
    ns = []
    na = 0
    nb = 0
    for fblock,configs in ci_vector.items():
        for c in fblock:
            na += c[0]
            nb += c[1]
        break

    for c in ci_vector.clusters:
        nsi = []
        for nai in range(c.n_orb+1):
            for nbi in range(c.n_orb+1):
                nsi.append((nai,nbi))
        ns.append(nsi)
    for newfock in itertools.product(*ns):
        nacurr = 0
        nbcurr = 0
        for c in newfock:
            nacurr += c[0]
            nbcurr += c[1]
        if nacurr == na and nbcurr == nb:
            ci_vector.add_fockblock(newfock) 


    print("\n Make each Fock-Block the full space")
    # create full space for each fock block defined
    for fblock,configs in ci_vector.items():
        dims = []
        for c in ci_vector.clusters:
            # get number of vectors for current fock space
            dims.append(range(c.basis[fblock[c.idx]].shape[1]))
        for newconfig_idx, newconfig in enumerate(itertools.product(*dims)):
            ci_vector[fblock][newconfig] = 0 
ci_vector.print()





#fock_l = ((2,2),)
#fock_r = ((2,2),)
#conf_l = (0,)
#conf_r = (0,)
##me = term_Aa.matrix_element(fock_l, conf_l, fock_r, conf_r)
#me = 0
#for term_label,term in clustered_ham.terms.items():
#    print(term_label)
#    [print(t) for t in term]
# 
#for t in clustered_ham.terms[((0,0),)]:
#    met = t.matrix_element(fock_l, conf_l, fock_r, conf_r)
#    print(t,met)
#    me += met
#print(me)
#exit()

#fock_l = ((2,2),(0,0))
#fock_r = ((2,2),(0,0))
#conf_l = (0,0)
#conf_r = (0,0)
#me = 0
#for term_label,term in clustered_ham.terms.items():
#    print(term_label)
#    [print(t) for t in term]
#
#for t in clustered_ham.terms[((0,0),(0,0))]:
#    met = t.matrix_element(fock_l, conf_l, fock_r, conf_r)
#    print(t,met)
#    me += met
#print(me)
#exit()






print(" Build full Hamiltonian")
print(" Total dimension of CI space", len(ci_vector))
sys.stdout.flush()

H = np.zeros((len(ci_vector),len(ci_vector)))

#[print(c.ops.keys()) for c in clusters]
shift_l = 0 
for fock_li, fock_l in enumerate(ci_vector.data):
    configs_l = ci_vector[fock_l]
    print(fock_l)
   
    for config_li, config_l in enumerate(configs_l):
        idx_l = shift_l + config_li 
        
        shift_r = 0 
        for fock_ri, fock_r in enumerate(ci_vector.data):
            configs_r = ci_vector[fock_r]
            delta_fock= tuple([(fock_l[ci][0]-fock_r[ci][0], fock_l[ci][1]-fock_r[ci][1]) for ci in range(len(clusters))])
            try:
                terms = clustered_ham.terms[delta_fock]
            except KeyError:
                shift_r += len(configs_r) 
                continue 
            #print(" Get terms for fock block: ", fock_l,"|",fock_r)
            #[print(t) for t in terms]
            
            for config_ri, config_r in enumerate(configs_r):        
                idx_r = shift_r + config_ri
                #print("Here: ", "<",fock_l,config_l, " <-> ", fock_r,config_r, " : ", idx_l, idx_r)
                
                #print(" %4i %4i"%(idx_l,idx_r))
                #if idx_l > idx_r:
                #    continue
                for term in terms:
                    me = term.matrix_element(fock_l,config_l,fock_r,config_r)
                    H[idx_l,idx_r] += me
                    #print(" %4i %4i = %12.8f"%(idx_l,idx_r,me),"  :  ",config_l,config_r, " :: ", term)
            shift_r += len(configs_r) 
    shift_l += len(configs_l)
   

#print_mat(H)
#print()
#print_mat(H-H.T)
print(" Diagonalize Hamiltonian Matrix:")
e,v = np.linalg.eigh(H)
idx = e.argsort()   
e = e[idx]
v = v[:,idx]
v0 = v[:,0]
print(" Ground state of CI:                 %12.8f  CI Dim: %4i "%(e[0].real,len(ci_vector)))

