import numpy as np
import scipy
import itertools
import time
from math import factorial
import copy as cp
import sys

from tpsci import *
from pyscf_helper import *
import pyscf
ttt = time.time()
np.set_printoptions(suppress=True, precision=3, linewidth=1500)
print("GITHUB TREE")
import subprocess
label = subprocess.check_output(["git","rev-parse", "HEAD"]).strip()
print(label)

###     PYSCF INPUT
r0 = 2.0
molecule = '''
C  -4.308669   0.197146   0.000000
C   4.308669  -0.197146   0.000000
C  -3.110874  -0.411353   0.000000
C   3.110874   0.411353   0.000000
H  -4.394907   1.280613   0.000000
H   4.394907  -1.280613   0.000000
H  -5.234940  -0.367304   0.000000
H   5.234940   0.367304   0.000000
H  -3.069439  -1.500574   0.000000
H   3.069439   1.500574   0.000000
C  -1.839087   0.279751   0.000000
C   1.839087  -0.279751   0.000000
C  -0.634371  -0.341144   0.000000
C   0.634371   0.341144   0.000000
H  -1.871161   1.369551   0.000000
H   1.871161  -1.369551   0.000000
H  -0.607249  -1.431263   0.000000
H   0.607249   1.431263   0.000000
'''
charge = 0
spin  = 0
basis_set = 'sto-3g'

npoly = 4
na = npoly
nb = npoly

###     TPSCI BASIS INPUT
orb_basis = 'PM'
cas_nel = 2*npoly
cas_norb = 2*npoly

#Integrals from pyscf
import pyscf
from pyscf import gto, scf, ao2mo, molden, lo
pyscf.lib.num_threads(1)  #with degenerate states and multiple processors there can be issues
#PYSCF inputs

mol = gto.Mole()
mol.atom = molecule

mol.max_memory = 1000 # MB
mol.symmetry = True
mol.charge = charge
mol.spin = spin
mol.basis = basis_set
mol.build()
print("symmertry")
print(mol.topgroup)

#SCF 

#mf = scf.RHF(mol).run(init_guess='atom')
mf = scf.RHF(mol).run()
#C = mf.mo_coeff #MO coeffs
enu = mf.energy_nuc()

if mol.symmetry == True:
    from pyscf import symm
    mo = symm.symmetrize_orb(mol, mf.mo_coeff)
    osym = symm.label_orb_symm(mol, mol.irrep_name, mol.symm_orb, mo)
    #symm.addons.symmetrize_space(mol, mo, s=None, check=True, tol=1e-07)
    for i in range(len(osym)):
        print("%4d %8s %16.8f"%(i+1,osym[i],mf.mo_energy[i]))

mo_occ = mf.mo_occ>0
mo_vir = mf.mo_occ==0
print(mo_occ)
print(mo_vir)
mo_occ = np.where(mf.mo_occ>0)[0]
mo_vir = np.where(mf.mo_occ==0)[0]
print(mo_occ)
print(mo_vir)

from pyscf import mo_mapping
s_pop = mo_mapping.mo_comps('C 2pz', mol, mf.mo_coeff)
print(s_pop)
cas_list = s_pop.argsort()[-cas_norb:]
print('cas_list', np.array(cas_list))
print('s population for active space orbitals', s_pop[cas_list])


focc_list = list(set(mo_occ)-set(cas_list))
print(focc_list)
fvir_list = list(set(mo_vir)-set(cas_list))
print(fvir_list)


def get_eff_for_casci(focc_list,cas_list,h,g):
# {{{

    cas_dim = len(cas_list)
    const = 0
    for i in focc_list:
        const += 2 * h[i,i]
        for j in focc_list:
            const += 2 * g[i,i,j,j] -  g[i,j,i,j]

    eff = np.zeros((cas_dim,cas_dim))
    for L,l in enumerate(cas_list):
        for M,m in enumerate(cas_list):
            for j in focc_list:
                eff[L,M] += 2 * g[l,m,j,j] -  g[l,j,j,m]
    return const, eff
# }}}

def reorder_integrals(idx,h,g):
# {{{
    h = h[:,idx] 
    h = h[idx,:] 

    g = g[:,:,:,idx] 
    g = g[:,:,idx,:] 
    g = g[:,idx,:,:] 
    g = g[idx,:,:,:] 
    return h,g
# }}}

local = False
local = True
if local:
    cl_c = mf.mo_coeff[:, focc_list]
    cl_a = lo.Boys(mol, mf.mo_coeff[:, cas_list]).kernel(verbose=4)
    cl_v = mf.mo_coeff[:, fvir_list]
    C = np.column_stack((cl_c, cl_a, cl_v))
else:
    cl_c = mf.mo_coeff[:, focc_list]
    cl_a = mf.mo_coeff[:, cas_list]
    cl_v = mf.mo_coeff[:, fvir_list]
    C = np.column_stack((cl_c, cl_a, cl_v))

from pyscf import mo_mapping
s_pop = mo_mapping.mo_comps('C 2pz', mol, C)
print(s_pop)
cas_list = s_pop.argsort()[-cas_norb:]
print('cas_list', np.array(cas_list))
print('s population for active space orbitals', s_pop[cas_list])
focc_list = list(set(mo_occ)-set(cas_list))
print(focc_list)
fvir_list = list(set(mo_vir)-set(cas_list))
print(fvir_list)



h = C.T.dot(mf.get_hcore()).dot(C)
g = ao2mo.kernel(mol,C,aosym='s4',compact=False).reshape(4*((h.shape[0]),))
const,eff = get_eff_for_casci(focc_list,cas_list,h,g)


focc_list = list(set(mo_occ)-set(cas_list))
print(focc_list)
fvir_list = list(set(mo_vir)-set(cas_list))
print(fvir_list)

ecore = enu + const
h,g = reorder_integrals(cas_list,h,g)
h = h + eff
C = C[:,cas_list]
molden.from_mo(mol, 'h8.molden', C)

#h = C.T.dot(mf.get_hcore()).dot(C)
#g = ao2mo.kernel(mol,C,aosym='s4',compact=False).reshape(4*((h.shape[0]),))


from pyscf import fci
#efci, ci = fci.direct_spin1.kernel(h, g, h.shape[0], nelec,ecore=ecore, verbose=5) #DO NOT USE 
cisolver = fci.direct_spin1.FCI()
efci, ci = cisolver.kernel(h, g, h.shape[1], nelec=(na,nb), ecore=ecore,nroots =1,verbose=100)
#d1 = cisolver.make_rdm1(ci, h.shape[1], nelec)
#print(d1)
print("FCIS%10.8f"%(efci))

cisolver = fci.direct_spin1.FCI()
efci2, ci = cisolver.kernel(h, g, h.shape[1], nelec=(na+1,nb-1), ecore=ecore,nroots =1,verbose=100)
fci_dim = ci.shape[0] * ci.shape[1]

print("FCIT%10.8f"%(efci2))
print("%10.6f"%(627.5*(efci2-efci)))
fcist = efci2-efci

do_hci = 1
if do_hci:
    ehcis, hci_dim = run_hci_pyscf(h,g,(na,nb),ecore=ecore,select_cutoff=1e-3,ci_cutoff=1e-3)
    ehcit, hci_dim = run_hci_pyscf(h,g,(na+1,nb-1),ecore=ecore,select_cutoff=1e-3,ci_cutoff=1e-3)
    print(627.5*(ehcit-ehcis))
###     TPSCI CLUSTER INPUT
#blocks = [[1,2,6,9],[3,4,5,8],[0,7]]
#blocks = [range(0,3),range(3,7),range(7,10)]
#init_fspace = ((3, 3),(2, 2),(0, 0))
#print(blocks)
#idx = np.argsort(np.diag(h))
#print(idx)
#h,g = reorder_integrals(idx,h,g)
#print(h)

if local:
    idx = e1_order(h,1e-1)
    h,g = reorder_integrals(idx,h,g)
    print(h)
    C = C[:,idx]
    molden.from_mo(mol, 'h8.molden', C)
    #blocks = [range(0,2),range(2,4),range(4,6),range(6,8)]
    #init_fspace = ((1, 1),(1, 1),(1, 1),(1, 1))
    blocks = [range(0,2),range(2,6),range(6,8)]
    init_fspace = ((1, 1),(2, 2),(1, 1))
    blocks = [range(0,4),range(4,8)]
    init_fspace = ((2, 2),(2, 2))
else:
    idx  = np.argsort(np.diag(h))
    print(idx)
    h,g = reorder_integrals(idx,h,g)
    C = C[:,idx]
    molden.from_mo(mol, 'h8.molden', C)
    print(h)
    blocks = [range(0,2),range(2,6),range(6,8)]
    init_fspace = ((2, 2),(2, 2),(0, 0))

do_tci = 1
do_tci2 = 1
if do_tci:
    #ci_vector, pt_vector, etci, etci2 = run_tpsci(h,g,blocks,init_fspace,ecore=ecore,
    #    thresh_ci_clip=1e-3,thresh_cipsi=1e-6,max_tucker_iter=20,max_cipsi_iter=20)
    #ci_vector.print_configs()
    #tci_dim = len(ci_vector)
    max_cipsi_iter=20
    n_blocks = len(blocks)

    clusters = []

    for ci,c in enumerate(blocks):
        clusters.append(Cluster(ci,c))

    ci_vector = ClusteredState(clusters)
    ci_vector.init(init_fspace)

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
    #ci_vector.add_single_excitonic_states()
    #ci_vector.print_configs()

    edps = build_hamiltonian_diagonal(clustered_ham,ci_vector)

    ci_vector, pt_vector, etci, etci2, t_conv = bc_cipsi_tucker(ci_vector.copy(), clustered_ham,thresh_cipsi=1e-2, thresh_ci_clip=0, max_tucker_iter=3,asci_clip=0)
    ci_vector, pt_vector, etci, etci2, t_conv = bc_cipsi_tucker(ci_vector.copy(), clustered_ham,thresh_cipsi=1e-3, thresh_ci_clip=0, max_tucker_iter=3,asci_clip=0)
    ci_vector, pt_vector, etci, etci2, t_conv = bc_cipsi_tucker(ci_vector.copy(), clustered_ham,thresh_cipsi=1e-4, thresh_ci_clip=5e-3, max_tucker_iter=3,asci_clip=0.05)
    ci_vector, pt_vector, etci, etci2, t_conv = bc_cipsi_tucker(ci_vector.copy(), clustered_ham,thresh_cipsi=1e-5, thresh_ci_clip=1e-3, max_tucker_iter=3,asci_clip=0.05)
    ci_vector, pt_vector, etci, etci2, t_conv = bc_cipsi_tucker(ci_vector.copy(), clustered_ham,thresh_cipsi=1e-6, thresh_ci_clip=5e-4, max_tucker_iter=3,asci_clip=0.05)

    print(" TPSCI:          %12.8f      Dim:%6d" % (etci+ecore, len(ci_vector)))
    print(" TPSCI(2):       %12.8f      Dim:%6d" % (etci2+ecore,len(pt_vector)))
    ci_vector.print_configs()
    tci_dim = len(ci_vector)
    etci = etci+ecore
    etci2 = etci2+ecore
print("  rad      FCI          Dim          HCI       Dim      TPSCI-0      Dim       TPSCI-0(2)")
print(" %4.2f  %12.9f   %6d     %12.9f  %6d %12.9f"%(r0,efci,fci_dim,etci,tci_dim,etci2))

etcis = etci
etcispt = etci2

if do_tci2:
    #ci_vector, pt_vector, etci, etci2 = run_tpsci(h,g,blocks,init_fspace,ecore=ecore,
    #    thresh_ci_clip=1e-3,thresh_cipsi=1e-6,max_tucker_iter=20,max_cipsi_iter=20)
    #ci_vector.print_configs()
    #tci_dim = len(ci_vector)
    max_cipsi_iter=20
    n_blocks = len(blocks)

    clusters = []

    for ci,c in enumerate(blocks):
        clusters.append(Cluster(ci,c))

    ci_vector = ClusteredState(clusters)
    ci_vector.init(((2, 2),(3, 1)))
    ci_vector.init(((3, 1),(2, 2)))

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
    #ci_vector.add_single_excitonic_states()
    #ci_vector.print_configs()

    edps = build_hamiltonian_diagonal(clustered_ham,ci_vector)
    ci_vector, pt_vector, etci, etci2, t_conv = bc_cipsi_tucker(ci_vector.copy(), clustered_ham,thresh_cipsi=1e-2, thresh_ci_clip=0, max_tucker_iter=3,asci_clip=0)
    ci_vector, pt_vector, etci, etci2, t_conv = bc_cipsi_tucker(ci_vector.copy(), clustered_ham,thresh_cipsi=1e-3, thresh_ci_clip=0, max_tucker_iter=3,asci_clip=0)
    ci_vector, pt_vector, etci, etci2, t_conv = bc_cipsi_tucker(ci_vector.copy(), clustered_ham,thresh_cipsi=1e-4, thresh_ci_clip=5e-3, max_tucker_iter=3,asci_clip=0.05)
    ci_vector, pt_vector, etci, etci2, t_conv = bc_cipsi_tucker(ci_vector.copy(), clustered_ham,thresh_cipsi=1e-5, thresh_ci_clip=1e-3, max_tucker_iter=3,asci_clip=0.05)
    ci_vector, pt_vector, etci, etci2, t_conv = bc_cipsi_tucker(ci_vector.copy(), clustered_ham,thresh_cipsi=1e-6, thresh_ci_clip=5e-4, max_tucker_iter=3,asci_clip=0.05)

    print(" TPSCI:          %12.8f      Dim:%6d" % (etci+ecore, len(ci_vector)))
    print(" TPSCI(2):       %12.8f      Dim:%6d" % (etci2+ecore,len(pt_vector)))
    ci_vector.print_configs()
    tci_dim = len(ci_vector)
    etci = etci+ecore
    etci2 = etci2+ecore

etcit = etci
etcitpt = etci2
print("ST: %10.8f"%(627.5*(etcit-etcis)))
print("ST: %10.8f"%(627.5*(etcitpt-etcispt)))
print("FCI ST: %10.8f"%(627.5*(fcist)))
print("HCI ST: %10.8f"%(627.5*(ehcit-ehcis)))
print(hci_dim)

print("TCI ST: %10.8f"%(27.2114*(etcit-etcis)))
print("TCI ST: %10.8f"%(27.2114*(etcitpt-etcispt)))
print("FCI ST: %10.8f"%(27.2114*(fcist)))
print("HCI ST: %10.8f"%(27.2114*(ehcit-ehcis)))
