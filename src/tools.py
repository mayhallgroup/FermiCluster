import numpy as np
import scipy
import itertools
import copy as cp
from helpers import *
import opt_einsum as oe

from ClusteredOperator import *
from ClusteredState import *

import dask
import dask.delayed
import numba

import concurrent.futures
from dask.distributed import Client, progress

import ray

def matvec1(h,v,term_thresh=1e-12):
    """
    Compute the action of H onto a sparse trial vector v
    returns a ClusteredState object. 

    """
# {{{
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
                sigma.add_fockspace(fock_l)

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


def build_effective_operator(cluster_idx, clustered_ham, ci_vector,iprint=0):
    """
    Build effective operator, doing a partial trace over all clusters except cluster_idx
    
        H = sum_i o_i h_i
    """
# {{{
    clusters = ci_vector.clusters
    H = np.zeros((len(ci_vector),len(ci_vector)))
   
    new_op = ClusteredOperator(clustered_ham.clusters)
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
                        new_term = term.effective_cluster_operator(cluster_idx, fock_l, config_l, fock_r, config_r)
                shift_r += len(configs_r) 
        shift_l += len(configs_l)
    return new_op 
# }}}



def build_hamiltonian_diagonal_ray1(clustered_ham,ci_vector):
    """
    Build hamiltonian diagonal in basis in ci_vector
    """
# {{{
    clusters = ci_vector.clusters
    Hd = np.zeros((len(ci_vector)))
    
    shift = 0 
   
    idx = 0

    delta_fock= tuple([(0,0) for ci in range(len(clusters))])
    terms = clustered_ham.terms[delta_fock]
    
    #ray.put(terms) 
    #def get_element(fockspace, config, coeff):
    def get_element(args):
        fockspace = args[0]
        config = args[1]
        a = 0
        for term in terms:
            a += term.matrix_element(fockspace,config,fockspace,config)
        return a

    #@numba.jit
    @ray.remote
    def get_elements(states):
        m_elements = []
        for fockspace,config,coeff in states:
            a = 0
            for term in terms:
                a += term.diag_matrix_element(fockspace,config)
            m_elements.append(a)
        return m_elements 


    tasks = []
    flist = [] # fockspaces
    clist = [] # configs
    tlist = [] # tasks
    batch_size = 100 
    check = []
    
    print(" Submit jobs:",flush=True)
    batch_idx = 0
    results = []
    for fockspace,config,coeff in ci_vector:
        clist.append((fockspace,config,coeff))
        batch_idx+=1
        tmp = []
        if batch_idx == batch_size:
            tasks.append(get_elements.remote(clist))
            clist = []
            batch_idx = 0
    tasks.append(get_elements.remote(clist))
   
    print(" done.",flush=True)
    print(" Now compute tasks:",flush=True)
    results = []
    for t in tasks:
        results.append(ray.get(t))
    results = list(itertools.chain(*results))
    #results = list(itertools.chain(*client.gather(tasks)))
    #results = list(itertools.chain(*client.gather(tasks)))
    print(" done.",flush=True)
    
    Hd = np.asarray(results)
    
    return Hd

# }}}

def build_hamiltonian_diagonal_dask1(clustered_ham,ci_vector,client):
    """
    Build hamiltonian diagonal in basis in ci_vector
    """
# {{{
    clusters = ci_vector.clusters
    Hd = np.zeros((len(ci_vector)))
    
    shift = 0 
   
    idx = 0

    delta_fock= tuple([(0,0) for ci in range(len(clusters))])
    terms = clustered_ham.terms[delta_fock]
    
 
    #def get_element(fockspace, config, coeff):
    def get_element(args):
        fockspace = args[0]
        config = args[1]
        a = 0
        for term in terms:
            a += term.matrix_element(fockspace,config,fockspace,config)
        return a

    #@numba.jit
    def get_elements(states):
        m_elements = []
        for fockspace,config,coeff in states:
            a = 0
            for term in terms:
                a += term.diag_matrix_element(fockspace,config)
            m_elements.append(a)
        return m_elements 


    #pool = concurrent.futures.ThreadPoolExecutor(8)

    tasks = []
    flist = [] # fockspaces
    clist = [] # configs
    tlist = [] # tasks
    batch_size = 100 
    check = []
    
    print(" Define futures:",flush=True)
    batch_idx = 0
    results = []
    for fockspace,config,coeff in ci_vector:
        clist.append((fockspace,config,coeff))
        batch_idx+=1
        tmp = []
        if batch_idx == batch_size:
            #results.append(get_elements(clist))
            tasks.append(client.submit(get_elements,clist))
            clist = []
            batch_idx = 0

    tasks.append(client.submit(get_elements,clist))
    #results.append(get_elements(clist))
    print(" done.",flush=True)
    print(" Now compute tasks:",flush=True)
    results = list(itertools.chain(*client.gather(tasks)))
    #results = list(itertools.chain(*results))
    print(" done.",flush=True)
    
    Hd = np.asarray(results)
    
    return Hd

# }}}

def build_hamiltonian_diagonal_concurrent(clustered_ham,ci_vector,client):
    """
    Build hamiltonian diagonal in basis in ci_vector
    """
# {{{
    clusters = ci_vector.clusters
    Hd = np.zeros((len(ci_vector)))
    
    shift = 0 
   
    idx = 0

    delta_fock= tuple([(0,0) for ci in range(len(clusters))])
    terms = clustered_ham.terms[delta_fock]
    
 
    #def get_element(fockspace, config, coeff):
    def get_element(args):
        fockspace = args[0]
        config = args[1]
        a = 0
        for term in terms:
            a += term.matrix_element(fockspace,config,fockspace,config)
        return a

    #@numba.jit
    def get_elements(terms, fockspaces, configs):
        m_elements = []
        for i in range(len(configs)):
            fockspace = fockspaces[i]
            config = configs[i]
            a = 0
            for term in terms:
                a += term.matrix_element(fockspace,config,fockspace,config)
            m_elements.append(a)
        return m_elements 


    #pool = concurrent.futures.ThreadPoolExecutor(8)

    tasks = []
    flist = [] # fockspaces
    clist = [] # configs
    tlist = [] # tasks
    batch_size = 10000 
    check = []
    print(" Define futures:",flush=True)
#    for fockspace, config, coeff in ci_vector:
#        a = client.submit(get_element, *(terms,fockspace,config))
#        #a = client.submit(get_elements, *(terms,flist,clist))
#        tasks.append(a)
    print(" done.",flush=True)
   
#    with concurrent.futures.ProcessPoolExecutor() as executor:
#        for fockspace, config in zip(, executor.map(get_element, PRIMES)):
#            print('%d is prime: %s' % (number, prime))
        
    print(" Now compute tasks:",flush=True)
    #result = dask.compute(*tasks)
    #result = dask.compute(*tasks,scheduler='processes')
    #Hd = np.asarray(list(map(get_element, ci_vector)))
    with concurrent.futures.ProcessPoolExecutor() as executor:
        result = executor.map(get_element, ci_vector, chunksize=10000)
    Hd = np.asarray(list(result))

    #Hd = np.asarray(list(itertools.chain(*result)))

    #Hd = np.asarray(list(itertools.chain(*client.gather(tasks))))
    print(" done.",flush=True)
    return Hd

# }}}

def build_hamiltonian_diagonal(clustered_ham,ci_vector,client):
    """
    Build hamiltonian diagonal in basis in ci_vector
    """
# {{{
    clusters = ci_vector.clusters
    Hd = np.zeros((len(ci_vector)))
    
    shift = 0 
   
    idx = 0

 
    def get_element(terms, fockspace, config):
        a = 0
        for term in terms:
            a += term.matrix_element(fockspace,config,fockspace,config)
        return a

    #@numba.jit
    def get_elements(terms, fockspaces, configs):
        m_elements = []
        for i in range(len(configs)):
            fockspace = fockspaces[i]
            config = configs[i]
            a = 0
            for term in terms:
                a += term.matrix_element(fockspace,config,fockspace,config)
            m_elements.append(a)
        return m_elements 


    #pool = concurrent.futures.ThreadPoolExecutor(8)
    #client = Client(processes=False)
    #print(client)
    #future = client.submit(func, big_data)    # bad
    #big_future = client.scatter(big_data)     # good
    #future = client.submit(func, big_future)  # good

    tasks = []
    delta_fock= tuple([(0,0) for ci in range(len(clusters))])
    terms = clustered_ham.terms[delta_fock]
    
    print(" Scatter terms:",flush=True)
    terms_future = client.scatter(terms)     # good
    print(" done.",flush=True)
   
    flist = [] # fockspaces
    clist = [] # configs
    tlist = [] # tasks
    batch_size = 10000000 
    print(" Define futures:",flush=True)
    for fockspace, configs in ci_vector.items():
        for config, coeff in configs.items():
          
            flist.append(fockspace)
            clist.append(config)
           
            
            if len(clist) == batch_size:
                a = client.submit(get_elements, *(terms_future,flist,clist))
                tasks.append(a)
                clist = []
                flist = []
    
    a = client.submit(get_elements, *(terms_future,flist,clist))
    
    tasks.append(a)
    print(" done.",flush=True)
    print(" Now compute tasks:",flush=True)
    Hd = np.asarray(list(itertools.chain(*client.gather(tasks))))
    print(" done.",flush=True)
    return Hd

# }}}


def build_hamiltonian_diagonal_dask(clustered_ham,ci_vector):
    """
    Build hamiltonian diagonal in basis in ci_vector
    """
# {{{
    clusters = ci_vector.clusters
    Hd = np.zeros((len(ci_vector)))
    
    shift = 0 
   
    idx = 0

 
    def get_element(terms, fockspace, config):
        a = 0
        for term in terms:
            a += term.matrix_element(fockspace,config,fockspace,config)
        return a

    #@numba.jit
    def get_elements(terms, fockspaces, configs):
        m_elements = []
        for i in range(len(configs)):
            fockspace = fockspaces[i]
            config = configs[i]
            a = 0
            for term in terms:
                a += term.matrix_element(fockspace,config,fockspace,config)
            m_elements.append(a)
        return m_elements 

    tasks = []
    delta_fock= tuple([(0,0) for ci in range(len(clusters))])
    terms = clustered_ham.terms[delta_fock]
   
    flist = [] # fockspaces
    clist = [] # configs
    tlist = [] # tasks
    batch_size = 1000 
    check = []
    for fockspace, configs in ci_vector.items():
        for config, coeff in configs.items():
          
            flist.append(fockspace)
            clist.append(config)
           
            
            #a = dask.delayed(get_element)(terms,fockspace,config)
            if len(clist) == batch_size:
                a = dask.delayed(get_elements)(terms,flist,clist)
                tasks.append(a)
                check.append(clist)
                clist = []
                flist = []
            #Hd[idx] = get_element(terms,fockspace,config)
            #idx += 1
    a = dask.delayed(get_elements)(terms,flist,clist)
    tasks.append(a)
    check.append(clist)
    print(" Now compute tasks:",flush=True)
    result = dask.compute(*tasks)
    #result = dask.compute(*tasks,scheduler='processes')
    Hd = np.asarray(list(itertools.chain(*result)))
    print(" done.",flush=True)
    return Hd

# }}}


def update_hamiltonian_diagonal(clustered_ham,ci_vector,Hd_vector):
    """
    Build hamiltonian diagonal in basis in ci_vector, 
    Use already computed values if stored in Hd_vector, otherwise compute, updating Hd_vector 
    with new values.
    """
# {{{
    clusters = ci_vector.clusters
    Hd = np.zeros((len(ci_vector)))
    
    shift = 0 
   
    idx = 0
    for fockspace, configs in ci_vector.items():
        for config, coeff in configs.items():
            delta_fock= tuple([(0,0) for ci in range(len(clusters))])
            try:
                Hd[idx] += Hd_vector[fockspace][config]
            except KeyError:
                try:
                    Hd_vector[fockspace][config] = 0 
                except KeyError:
                    Hd_vector.add_fockspace(fockspace)
                    Hd_vector[fockspace][config] = 0 
                terms = clustered_ham.terms[delta_fock]
                
                # add diagonal energies
                for ci in clusters:
                    Hd[idx] += ci.energies[fockspace[ci.idx]][config[ci.idx]]
                for term in terms:
                    #Hd[idx] += term.matrix_element(fockspace,config,fockspace,config)
                    Hd[idx] += term.diag_matrix_element(fockspace,config)
                Hd_vector[fockspace][config] = Hd[idx] 
            idx += 1
    return Hd

# }}}

def precompute_cluster_basis_energies(clustered_ham):
    """
    For each cluster grab the local operator from clustered_ham, and store the expectation values 
    for each cluster state
    """
    # {{{
    for ci in clustered_ham.clusters:
        opi = clustered_ham.extract_local_operator(ci.idx)
        for t in opi.terms:
            assert(len(t.ops)==1)
            if len(t.ops[0]) == 2:
                for fspace_del in ci.ops[t.ops[0]]:
                    assert(fspace_del[0] == fspace_del[1])
                    D = ci.ops[t.ops[0]][fspace_del]
                    
                    # e(I) += D(I,I,pq) H(pq) 
                    e = np.einsum('iipq,pq->i',D,t.ints)
                    try:
                        ci.energies[fspace_del[0]] += e
                    except KeyError:
                        ci.energies[fspace_del[0]] = e
            elif len(t.ops[0]) == 4:
                for fspace_del in ci.ops[t.ops[0]]:
                    assert(fspace_del[0] == fspace_del[1])
                    D = ci.ops[t.ops[0]][fspace_del]
                    
                    # e(I) += D(I,I,pqrs) H(pqrs) 
                    e = np.einsum('iipqrs,pqrs->i',D,t.ints)
                    try:
                        ci.energies[fspace_del[0]] += e
                    except KeyError:
                        ci.energies[fspace_del[0]] = e
# }}}

def build_1rdm(ci_vector):
    """
    Build 1rdm C_{I,J,K}<IJK|p'q|LMN> C_{L,M,N}
    """
    # {{{
    dm_aa = np.zeros((ci_vector.n_orb,ci_vector.n_orb))
    dm_bb = np.zeros((ci_vector.n_orb,ci_vector.n_orb))


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

def build_brdm(ci_vector, ci_idx):
    """
    Build block reduced density matrix for cluster ci_idx
    """
    # {{{
    ci = ci_vector.clusters[ci_idx]
    rdms = OrderedDict()
    for fspace, configs in ci_vector.items():
        #print()
        #print("fspace:",fspace)
        #print()
        curr_dim = ci.basis[fspace[ci_idx]].shape[1]
        rdm = np.zeros((curr_dim,curr_dim))
        for configi,coeffi in configs.items():
            for cj in range(curr_dim):
                configj = list(cp.deepcopy(configi))
                configj[ci_idx] = cj
                configj = tuple(configj)
                #print(configi,configj,configi[ci_idx],configj[ci_idx])
                try:
                    #print(configi,configj,configi[ci_idx],configj[ci_idx],coeffi,configs[configj])
                    rdm[configi[ci_idx],cj] += coeffi*configs[configj]
                    #print(configi[ci_idx],cj,rdm[configi[ci_idx],cj])
                except KeyError:
                    pass
        try:
            rdms[fspace[ci_idx]] += rdm 
        except KeyError:
            rdms[fspace[ci_idx]] = rdm 

    return rdms
# }}}
