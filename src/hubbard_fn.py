import numpy as np
import scipy
import itertools as it
import time
from math import factorial
import copy as cp

def get_hubbard_params(n_site,beta,U,pbc=True):
# {{{
    #gets the interactions for linear hubbard
    print(" ---------------------------------------------------------")
    print("                       Hubbard model")
    print(" ---------------------------------------------------------")
    print(" nsite:%6d"%n_site)
    print(" beta :%10.6f"%beta)
    print(" U    :%10.6f"%U)

    t = np.zeros((n_site,n_site))

    for i in range(0,n_site-1):
        t[i,i+1] = 1 
        t[i+1,i] = 1 
    if pbc:
        t[n_site-1,0] = 1 
        t[0,n_site-1] = 1 

    h_local = -beta  * t 

    g_local = np.zeros((n_site,n_site,n_site,n_site))
    for i in range(0,n_site):
        g_local[i,i,i,i] = U
            
    return h_local,g_local
    # }}}

def run_hubbard_scf(h_local,g_local,closed_shell_nel,do_scf=True):
# {{{
    print()
    print(" ---------------------------------------------------------")
    print("                  Delocalized Mean-Field")
    print(" ---------------------------------------------------------")
    if do_scf:
        orb, C = np.linalg.eigh(h_local)
    else:
        C = np.eye(h_local.shape[0])
        orb = h_local.diagonal()
    #if np.sum(h_local) == 0:
    #    print("why")
    #    orbt, C = np.linalg.eigh(t)


    print("Orbital energies:\n",orb,"\n")

    h = C.T @ h_local @ C                             

    g = np.einsum("pqrs,pl->lqrs",g_local,C)
    g = np.einsum("lqrs,qm->lmrs",g,C)
    g = np.einsum("lmrs,rn->lmns",g,C)
    g = np.einsum("lmns,so->lmno",g,C)


    o = slice(0, closed_shell_nel)
    v = slice(closed_shell_nel, h_local.shape[0])

    Escf = 2*np.einsum('ii',h[o,o]) + 2*np.einsum('ppqq',g[o,o,o,o]) - np.einsum('pqqp',g[o,o,o,o])

    print("Mean Field Energy        :%16.12f" % (Escf))

    print(C)

    return Escf,orb,h,g,C
# }}}

def get_hubbard_1d(n_site, beta1, beta2, U, pbc=True):
# {{{
    print(n_site//2)
    assert(n_site%2==0)
    #gets the interactions for linear hubbard
    print(" ---------------------------------------------------------")
    print("                       Hubbard model")
    print(" ---------------------------------------------------------")
    print(" nsite :%6d"%n_site)
    print(" beta1 :%10.6f"%beta1)
    print(" beta2 :%10.6f"%beta2)
    print(" U     :%10.6f"%U)

    t = np.zeros((n_site,n_site))

    for i in range(0,n_site-1):
        if i%2==0:
            t[i,i+1] = -beta1 
            t[i+1,i] = -beta1
        else:
            t[i,i+1] = -beta2 
            t[i+1,i] = -beta2
    if pbc:
        t[n_site-1,0] = -beta2 
        t[0,n_site-1] = -beta2

    h_local = cp.deepcopy(t)

    g_local = np.zeros((n_site,n_site,n_site,n_site))
    for i in range(0,n_site):
        g_local[i,i,i,i] = U
            
    return h_local,g_local
    # }}}
