import numpy as np
import scipy
import itertools
import copy as cp
from helpers import *
import opt_einsum as oe

from ClusteredOperator import *
from ClusteredState import *

def matvec1(h,v,term_thresh=1e-12):
    """
    Compute the action of H onto a sparse trial vector v
    returns a ClusteredState object. 

    """
# {{{
    print(" Compute matrix vector product:")
    clusters = h.clusters
    sigma = ClusteredState(clusters)
    sigma = v.copy() 
    sigma.zero()
   
    if 0:
        # use this to debug
        sigma.expand_to_full_space()


    for fock_ri, fock_r in enumerate(v.fblocks()):

        for terms in h.terms:
            fock_l= tuple([(terms[ci][0]+fock_r[ci][0], terms[ci][1]+fock_r[ci][1]) for ci in range(len(clusters))])
            good = True
            for c in clusters:
                if min(fock_l[c.idx]) < 0 or max(fock_l[c.idx]) > c.n_orb:
                    good = False
                    break
            if good == False:
                continue
            
            #print(fock_l, "<--", fock_r)
            
            if fock_l not in sigma.data:
                sigma.add_fockblock(fock_l)

            configs_l = sigma[fock_l] 
            
            for term in h.terms[terms]:
                #print(" term: ", term)
                for conf_ri, conf_r in enumerate(v[fock_r]):
                    #print("  ", conf_r)
                    
                    #if abs(v[fock_r][conf_r]) < 5e-2:
                    #    continue
                    # get state sign 
                    state_sign = 1
                    for oi,o in enumerate(term.ops):
                        if o == '':
                            continue
                        if len(o) == 1 or len(o) == 3:
                            for cj in range(oi):
                                state_sign *= (-1)**(fock_r[cj][0]+fock_r[cj][1])
                    
                    #print('state_sign ', state_sign)
                    opii = -1
                    mats = []
                    good = True
                    for opi,op in enumerate(term.ops):
                        if op == "":
                            continue
                        opii += 1
                        #print(opi,term.active)
                        ci = clusters[term.active[opii]]
                        try:
                            oi = ci.ops[op][(fock_l[ci.idx],fock_r[ci.idx])][:,conf_r[ci.idx],:]
                            mats.append(oi)
                        except KeyError:
                            good = False
                            break
                    if good == False:
                        continue                        
                        #break
                   
                    if len(mats) == 0:
                        continue
                    #print('mats:', end='')
                    #[print(m.shape,end='') for m in mats]
                    #print()
                    #print('ints:', term.ints.shape)
                    #print("contract_string       :", term.contract_string)
                    #print("contract_string_matvec:", term.contract_string_matvec)
                    
                    #tmp = oe.contract(term.contract_string_matvec, *mats, term.ints)
                    
                    tmp = np.einsum(term.contract_string_matvec, *mats, term.ints)
                    

                    v_coeff = v[fock_r][conf_r]
                    tmp = state_sign * tmp.ravel() * v_coeff

                    new_configs = [[i] for i in conf_r] 
                    for cacti,cact in enumerate(term.active):
                        new_configs[cact] = range(mats[cacti].shape[0])
                    for sp_idx, spi in enumerate(itertools.product(*new_configs)):
                        #print(" New config: %12.8f" %tmp[sp_idx], spi)
                        if abs(tmp[sp_idx]) > term_thresh:
                            if spi not in configs_l:
                                configs_l[spi] = tmp[sp_idx] 
                            else:
                                configs_l[spi] += tmp[sp_idx] 
    return sigma 
# }}}


def build_full_hamiltonian(clustered_ham,ci_vector,iprint=0):
    """
    Build hamiltonian in basis in ci_vector
    """
# {{{
    clusters = ci_vector.clusters
    H = np.zeros((len(ci_vector),len(ci_vector)))
    
    shift_l = 0 
    for fock_li, fock_l in enumerate(ci_vector.data):
        configs_l = ci_vector[fock_l]
        if iprint > 0:
            print(fock_l)
       
        for config_li, config_l in enumerate(configs_l):
            idx_l = shift_l + config_li 
            
            shift_r = 0 
            for fock_ri, fock_r in enumerate(ci_vector.data):
                configs_r = ci_vector[fock_r]
                delta_fock= tuple([(fock_l[ci][0]-fock_r[ci][0], fock_l[ci][1]-fock_r[ci][1]) for ci in range(len(clusters))])
                if fock_ri<fock_li:
                    shift_r += len(configs_r) 
                    continue
                try:
                    terms = clustered_ham.terms[delta_fock]
                except KeyError:
                    shift_r += len(configs_r) 
                    continue 
                
                for config_ri, config_r in enumerate(configs_r):        
                    idx_r = shift_r + config_ri
                    if idx_r<idx_l:
                        continue
                    
                    for term in terms:
                        me = term.matrix_element(fock_l,config_l,fock_r,config_r)
                        H[idx_l,idx_r] += me
                        if idx_r>idx_l:
                            H[idx_r,idx_l] += me
                        #print(" %4i %4i = %12.8f"%(idx_l,idx_r,me),"  :  ",config_l,config_r, " :: ", term)
                shift_r += len(configs_r) 
        shift_l += len(configs_l)
    return H
# }}}



def build_hamiltonian_diagonal(clustered_ham,ci_vector):
    """
    Build hamiltonian diagonal in basis in ci_vector
    """
# {{{
    clusters = ci_vector.clusters
    Hd = np.zeros((len(ci_vector)))
    
    shift = 0 
   
    idx = 0
    for fockspace, configs in ci_vector.items():
        for config, coeff in configs.items():
            delta_fock= tuple([(0,0) for ci in range(len(clusters))])
            terms = clustered_ham.terms[delta_fock]
            for term in terms:
                Hd[idx] += term.matrix_element(fockspace,config,fockspace,config)
            idx += 1

    return Hd

# }}}


