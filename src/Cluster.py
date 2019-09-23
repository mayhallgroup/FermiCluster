import numpy as np
import scipy
import itertools as it

import opt_einsum as oe

from ci_string import *
from Hamiltonian import *
from davidson import *

class Cluster(object):

    def __init__(self,idx,bl):
        """
        input: 
            bl  = a list of spatial orbital indices
            idx = index of the cluster

        data:
            self.block_states:      dict connecting (na,nb) quantum numbers to ndarray
                                    self.block_states[(3,4)] = ndarray(determinant, cluster state)

            self.ops:               dict holding matrices of operators
                                    keys = strings denoting operator A/B creation a/b annihilation
                                    values = dicts of keys=(Na_bra, Nb_bra, Na_ket, Nb_ket) 
                                                      with values being the tensor representation
                                    e.g., self.ops = {
                                            'Aab':{  [(0,0),(0,1)]:D(I,J,p,q,r) 
                                                     [(0,1),(0,2)]:D(I,J,p,q,r) 
                                                     ...
                                                  }
                                            'Aa' :{  [(0,0),(0,0)]:D(I,J,p,q,r) 
                                                     [(0,1),(0,1)]:D(I,J,p,q,r) 
                                                     ...
                                                  }
                                            'aa' :{  [(0,0),(3,0)]:D(I,J,p,q,r) 
                                                     [(1,1),(3,1)]:D(I,J,p,q,r) 
                                                     ...
                                                  }
                                            ...

        """
        self.idx = idx 
        self.orb_list = bl

        self.n_orb = len(bl)    
        self.dim_tot = 2**(2*self.n_orb)    # total size of hilbert space
        self.dim = self.dim_tot             # size of basis         
        self.basis = {}                     # organized as basis = { (na,nb):v(IJ,s), (na',nb'):v(IJ,s), ...} 
                                            #       where IJ is alpha,beta string indices
        self.ops    = {}

    def __len__(self):
        return len(self.orb_list) 
    def __str__(self):
        has = ""
        for si in self.orb_list:
            has = has + "%03i|"%si
        if len(self.orb_list) == 0:
            has = "|"
        return "IDX%03i:DIM%04i:%s" %(self.idx, self.dim, has)

    def add_operator(self,op):
        if op in self.ops:
            return
        else:
            self.ops[op] = {}
    
    def form_eigbasis_from_local_operator(self,local_op,max_roots=1000):
        h = np.zeros([self.n_orb]*2)
        v = np.zeros([self.n_orb]*4)
        for t in local_op.terms:
            if t.ops[0] == "Aa":
                h = t.ints 
            if t.ops[0] == "AAaa":
                v = t.ints 
        
        H = Hamiltonian()
        H.S = np.eye(h.shape[0])
        H.C = H.S
        H.t = h
        H.V = v
        self.basis = {}
        print(" Do CI for each particle number block")
        for na in range(self.n_orb+1):
            for nb in range(self.n_orb+1):
                ci = ci_solver()
                ci.algorithm = "direct"
                ci.init(H,na,nb,max_roots)
                print(ci)
                ci.run()
                #self.basis[(na,nb)] = np.eye(ci.results_v.shape[0])
                self.basis[(na,nb)] = ci.results_v
            
                
    def build_op_matrices(self):
        """
        build all operators needed
        """
        self.ops['A'] = {}
        self.ops['a'] = {}
        self.ops['B'] = {}
        self.ops['b'] = {}
        self.ops['Aa'] = {}
        self.ops['Bb'] = {}
        self.ops['Ab'] = {}
        self.ops['Ba'] = {}
        self.ops['AAaa'] = {}
        self.ops['BBbb'] = {}
        self.ops['ABba'] = {}
        self.ops['BAab'] = {}
        self.ops['AA'] = {}
        self.ops['BB'] = {}
        self.ops['AB'] = {}
        self.ops['BA'] = {}
        self.ops['aa'] = {}
        self.ops['bb'] = {}
        self.ops['ba'] = {}
        self.ops['ab'] = {}

        #  a, A 
        for na in range(1,self.n_orb+1):
            for nb in range(0,self.n_orb+1):
                self.ops['a'][(na-1,nb),(na,nb)] = build_annihilation(self.n_orb, (na-1,nb),(na,nb),self.basis)
                self.ops['A'][(na,nb),(na-1,nb)] = cp.deepcopy(np.swapaxes(self.ops['a'][(na-1,nb),(na,nb)],0,1))
                # note:
                #   I did a deepcopy instead of reference. This increases memory requirements and 
                #   basis transformation costs, but simplifies later manipulations. Later I need to 
                #   remove the redundant storage by manually handling the transpositions from a to A
        
        #  b, B 
        for na in range(0,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                self.ops['b'][(na,nb-1),(na,nb)] = build_annihilation(self.n_orb, (na,nb-1),(na,nb),self.basis)
                self.ops['B'][(na,nb),(na,nb-1)] = cp.deepcopy(np.swapaxes(self.ops['b'][(na,nb-1),(na,nb)],0,1))
                # note:
                #   I did a deepcopy instead of reference. This increases memory requirements and 
                #   basis transformation costs, but simplifies later manipulations. Later I need to 
                #   remove the redundant storage by manually handling the transpositions from a to A

        #  Aa,Bb
        for na in range(0,self.n_orb+1):
            for nb in range(0,self.n_orb+1):
                self.ops['Aa'][(na,nb),(na,nb)] = build_ca_ss(self.n_orb, (na,nb),(na,nb),self.basis,'a')
                self.ops['Bb'][(na,nb),(na,nb)] = build_ca_ss(self.n_orb, (na,nb),(na,nb),self.basis,'b')
               
        #  Ab,Ba
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                self.ops['Ab'][(na,nb-1),(na-1,nb)] = build_ca_os(self.n_orb, (na,nb-1),(na-1,nb),self.basis,'ab')
                self.ops['Ba'][(na-1,nb),(na,nb-1)] = build_ca_os(self.n_orb, (na-1,nb),(na,nb-1),self.basis,'ba')
               
#        #  AAaa,BBbb
#        for na in range(0,self.n_orb+1):
#            for nb in range(0,self.n_orb+1):
#                self.ops['AAaa'][(na,nb),(na,nb)] = build_ccaa_ss(self.n_orb, (na,nb),(na,nb),self.basis,'a')
#                self.ops['BBbb'][(na,nb),(na,nb)] = build_ccaa_ss(self.n_orb, (na,nb),(na,nb),self.basis,'b')
#                #print(self.ops['BBbb'][(na,nb),(na,nb)])
#        
        #  AAaa
        for na in range(2,self.n_orb+1):
            for nb in range(0,self.n_orb+1):
                a2 = self.ops['a'][(na-1,nb),(na,nb)]
                a1 = self.ops['a'][(na-2,nb),(na-1,nb)]
                A2 = self.ops['A'][(na-1,nb),(na-2,nb)]
                A1 = self.ops['A'][(na,nb),(na-1,nb)]
               
                # <IJ|p'q'rs|KL>
                self.ops['AAaa'][(na,nb),(na,nb)] = oe.contract('abp,bcq,cdr,des->aepqrs',A1,A2,a1,a2)
        #  BBbb
        for na in range(0,self.n_orb+1):
            for nb in range(2,self.n_orb+1):
                b2 = self.ops['b'][(na,nb-1),(na,nb)]
                b1 = self.ops['b'][(na,nb-2),(na,nb-1)]
                B2 = self.ops['B'][(na,nb-1),(na,nb-2)]
                B1 = self.ops['B'][(na,nb),(na,nb-1)]
               
                # <IJ|p'q'rs|KL>
                self.ops['BBbb'][(na,nb),(na,nb)] = oe.contract('abp,bcq,cdr,des->aepqrs',B1,B2,b1,b2)
        #  ABba
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                a = self.ops['a'][(na-1,nb),(na,nb)]
                b = self.ops['b'][(na-1,nb-1),(na-1,nb)]
                B = self.ops['B'][(na-1,nb),(na-1,nb-1)]
                A = self.ops['A'][(na,nb),(na-1,nb)]
               
                # <IJ|p'q'rs|KL>
                self.ops['ABba'][(na,nb),(na,nb)] = oe.contract('abp,bcq,cdr,des->aepqrs',A,B,b,a)
        #  BAab
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                b = self.ops['b'][(na,nb-1),(na,nb)]
                a = self.ops['a'][(na-1,nb-1),(na,nb-1)]
                A = self.ops['A'][(na,nb-1),(na-1,nb-1)]
                B = self.ops['B'][(na,nb),(na,nb-1)]
               
                # <IJ|p'q'rs|KL>
                self.ops['BAab'][(na,nb),(na,nb)] = oe.contract('abp,bcq,cdr,des->aepqrs',B,A,a,b)
        
        
        #  AA
        for na in range(2,self.n_orb+1):
            for nb in range(0,self.n_orb+1):
                A1 = self.ops['A'][(na-1,nb),(na-2,nb)]
                A2 = self.ops['A'][(na,nb),(na-1,nb)]
                self.ops['AA'][(na,nb),(na-2,nb)] = oe.contract('abp,bcq->acpq',A2,A1)
        
        #  aa
        for na in range(2,self.n_orb+1):
            for nb in range(0,self.n_orb+1):
                a1 = self.ops['a'][(na-1,nb),(na,nb)]
                a2 = self.ops['a'][(na-2,nb),(na-1,nb)]
                self.ops['aa'][(na-2,nb),(na,nb)] = oe.contract('abp,bcq->acpq',a2,a1)

        #  BB
        for na in range(0,self.n_orb+1):
            for nb in range(2,self.n_orb+1):
                B1 = self.ops['B'][(na,nb-1),(na,nb-2)]
                B2 = self.ops['B'][(na,nb),(na,nb-1)]
                self.ops['BB'][(na,nb),(na,nb-2)] = oe.contract('abp,bcq->acpq',B2,B1)
        
        #  bb
        for na in range(0,self.n_orb+1):
            for nb in range(2,self.n_orb+1):
                b1 = self.ops['b'][(na,nb-1),(na,nb)]
                b2 = self.ops['b'][(na,nb-2),(na,nb-1)]
                self.ops['bb'][(na,nb-2),(na,nb)] = oe.contract('abp,bcq->acpq',b2,b1)
        #  AB
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                B = self.ops['B'][(na-1,nb),(na-1,nb-1)]
                A = self.ops['A'][(na,nb),(na-1,nb)]
                self.ops['AB'][(na,nb),(na-1,nb-1)] = oe.contract('abp,bcq->acpq',A,B)
        
        #  BA
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                A = self.ops['A'][(na,nb-1),(na-1,nb-1)]
                B = self.ops['B'][(na,nb),(na,nb-1)]
                self.ops['BA'][(na,nb),(na-1,nb-1)] = oe.contract('abp,bcq->acpq',B,A)
        
        #  ba
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                b = self.ops['b'][(na,nb-1),(na,nb)]
                a = self.ops['a'][(na-1,nb-1),(na,nb-1)]
                self.ops['ba'][(na-1,nb-1),(na,nb)] = oe.contract('abp,bcq->acpq',a,b)
        
        #  ab
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                try:
                    b = self.ops['b'][(na,nb-1),(na,nb)]
                    a = self.ops['a'][(na-1,nb-1),(na,nb-1)]
                    self.ops['ab'][(na-1,nb-1),(na,nb)] = oe.contract('abp,bcq->acpq',b,a)
                except:
                    pass 
        

        #  AAa
        for na in range(2,self.n_orb+1):
            for nb in range(0,self.n_orb+1):
                a  = self.ops['a'][(na-2,nb),(na-1,nb)]
                A1 = self.ops['A'][(na-1,nb),(na-2,nb)]
                A2 = self.ops['A'][(na,nb),(na-1,nb)]
                self.ops['AAa'][(na,nb),(na-1,nb)] = oe.contract('abp,bcq,cdr->adpqr',A2,A1,a)
        
        #  BBb
        for na in range(0,self.n_orb+1):
            for nb in range(2,self.n_orb+1):
                b  = self.ops['b'][(na,nb-2),(na,nb-1)]
                B1 = self.ops['B'][(na,nb-1),(na,nb-2)]
                B2 = self.ops['B'][(na,nb),(na,nb-1)]
                self.ops['BBb'][(na,nb),(na,nb-1)] = oe.contract('abp,bcq,cdr->adpqr',B2,B1,b)
        
        #  ABa
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                a = self.ops['a'][(na-1,nb-1),(na,nb-1)]
                B = self.ops['B'][(na-1,nb),(na-1,nb-1)]
                A = self.ops['A'][(na,nb),(na-1,nb)]
                self.ops['ABa'][(na,nb),(na,nb-1)] = oe.contract('abp,bcq,cdr->adpqr',A,B,a)

        #  ABb
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                b = self.ops['b'][(na-1,nb-1),(na-1,nb)]
                B = self.ops['B'][(na-1,nb),(na-1,nb-1)]
                A = self.ops['A'][(na,nb),(na-1,nb)]
                self.ops['ABb'][(na,nb),(na-1,nb)] = oe.contract('abp,bcq,cdr->adpqr',A,B,b)
        
        #  BAa
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                a = self.ops['a'][(na-1,nb-1),(na,nb-1)]
                A = self.ops['A'][(na,nb-1),(na-1,nb-1)]
                B = self.ops['B'][(na,nb),(na,nb-1)]
                self.ops['BAa'][(na,nb),(na,nb-1)] = oe.contract('abp,bcq,cdr->adpqr',B,A,a)
        
        #  BAb
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                b = self.ops['b'][(na-1,nb-1),(na-1,nb)]
                A = self.ops['A'][(na,nb-1),(na-1,nb-1)]
                B = self.ops['B'][(na,nb),(na,nb-1)]
                self.ops['BAb'][(na,nb),(na-1,nb)] = oe.contract('abp,bcq,cdr->adpqr',B,A,b)


        
        #  Aaa
        for na in range(2,self.n_orb+1):
            for nb in range(0,self.n_orb+1):
                a1 = self.ops['a'][(na-1,nb),(na,nb)]
                a2 = self.ops['a'][(na-2,nb),(na-1,nb)]
                A  = self.ops['A'][(na-1,nb),(na-2,nb)]
                self.ops['Aaa'][(na-1,nb),(na,nb)] = oe.contract('abp,bcq,cdr->adpqr',A,a2,a1)
        
        #  Bbb
        for na in range(0,self.n_orb+1):
            for nb in range(2,self.n_orb+1):
                b1 = self.ops['b'][(na,nb-1),(na,nb)]
                b2 = self.ops['b'][(na,nb-2),(na,nb-1)]
                B  = self.ops['B'][(na,nb-1),(na,nb-2)]
                self.ops['Bbb'][(na,nb-1),(na,nb)] = oe.contract('abp,bcq,cdr->adpqr',B,b2,b1)
        
        #  Aba
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                a = self.ops['a'][(na-1,nb),(na,nb)]
                b = self.ops['b'][(na-1,nb-1),(na-1,nb)]
                A = self.ops['A'][(na,nb-1),(na-1,nb-1)]
                self.ops['Aba'][(na,nb-1),(na,nb)] = oe.contract('abp,bcq,cdr->adpqr',A,b,a)
        
        #  Aab
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                b = self.ops['b'][(na,nb-1),(na,nb)]
                a = self.ops['a'][(na-1,nb-1),(na,nb-1)]
                A = self.ops['A'][(na,nb-1),(na-1,nb-1)]
                self.ops['Aab'][(na,nb-1),(na,nb)] = oe.contract('abp,bcq,cdr->adpqr',A,a,b)
        
        #  Bba
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                a = self.ops['a'][(na-1,nb),(na,nb)]
                b = self.ops['b'][(na-1,nb-1),(na-1,nb)]
                B = self.ops['B'][(na-1,nb),(na-1,nb-1)]
                self.ops['Bba'][(na-1,nb),(na,nb)] = oe.contract('abp,bcq,cdr->adpqr',B,b,a)
        
        #  Bab
        for na in range(1,self.n_orb+1):
            for nb in range(1,self.n_orb+1):
                b = self.ops['b'][(na,nb-1),(na,nb)]
                a = self.ops['a'][(na-1,nb-1),(na,nb-1)]
                B = self.ops['B'][(na-1,nb),(na-1,nb-1)]
                self.ops['Bab'][(na-1,nb),(na,nb)] = oe.contract('abp,bcq,cdr->adpqr',B,a,b)
        
        #Add remaining operators ....



###################################################################################################################

    def read_block_states(self, vecs, n_a, n_b):
        self.block_states[n_a,n_b] = vecs
        #todo assert number of rows == dimension suggested by (n_a,n_b)
        assert(vecs.shape[0]>=vecs.shape[1])
        assert(n_a<=self.n_orb and n_a >= 0)
        assert(n_b<=self.n_orb and n_b >= 0)


    def read_tdms(self,mat,string,n_a,n_b):
        self.tdm_a[string,n_a,n_b] = mat


    def read_ops(self,tens,string,Ina,Inb,Jna,Jnb):
        """
        input:
            tens = ndarray(vecI,vecJ,p,q,r,...)
            string = operator class:
                    e.g., "Aab" for creation(alpha), annihilation(alpha), annihilation(beta)
            Ina,Inb = quantum numbers for ket
            Jna,Jnb = quantum numbers for bra
        """
        self.ops[string][(Ina,Inb),(Jna,Jnb)] = tens