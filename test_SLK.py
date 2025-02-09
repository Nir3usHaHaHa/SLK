from __future__ import print_function,division
from IPython import get_ipython
def __reset__(): get_ipython().magic('reset -sf')
import os,sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),'.','src/')))
import scipy.io as sio
import numpy as np
from SLK_iterative import SLK_iterative
from SLK import SLK, normalizefea, km_init
from sklearn.metrics.cluster import normalized_mutual_info_score as nmi
from util import get_accuracy
import util
import timeit
import ipdb
# if __name__ == '__main__':

#    dataset = 'mnist_200'
dataset = 'gan_mnist'


# SLK options SLK-BO/SLK-MS
SLK_option = 'SLK-MS'
# SLK_option = 'SLK-BO'

#  Save?
mode_images = False #  save mode images in a directory?
saveresult = False  #  save results?

#   Give data matrix in samples by feature format ( N X D) or read in efficent memmap file for bigger dataset

X_org = sio.loadmat('./data/MNIST.mat')['X']*255.0 # Original image intensities for mode visualization

data = sio.loadmat('./data/'+dataset+'.mat')
X = data['X']                               # data features
gnd_labels = data['gnd_labels'].squeeze()   # Groundtruth for evaluation
    
if gnd_labels.min() != 0:         # Start labels from 0
    gnd_labels = gnd_labels -1

# Normalize Features
X =normalizefea(X)

N,D =X.shape
K = len(np.unique(gnd_labels)) # Number of clusters

# Given sigma for gaussian kernel in Mode estimation

#    sigma = None    
sigma = 0.3859

#####Validation Set for tuning lambda and initial K-means++ seed. 
#### However you can set value of lambda and initial seed empirically and skip validation set #######

val_path = './data/'+ dataset + '_val_set.npz'

if not os.path.exists(val_path): 
    X_val,gnd_val,val_ind,imbalance = util.validation_set(X,gnd_labels,K,0.1)
    np.savez(val_path, X_val = X_val, gnd_val = gnd_val, val_ind = val_ind)
else:        
    data_val = np.load(val_path)
    X_val = data_val['X_val']
    gnd_val = data_val['gnd_val']
    val_ind = data_val['val_ind']

##    # Build the knn kernel
knn = 5 
start_time = timeit.default_timer()

aff_path = './data/W_'+str(knn)+'_'+dataset+'.mat'
#    sig = None
##    sig = estimate_median_sigma(X,1024, knn)
# ipdb.set_trace()
alg = "flann"
if not os.path.exists(aff_path):
    W = util.create_affinity(X, knn, scale = None, alg = alg, savepath = aff_path, W_path = None)
else:
    W = util.create_affinity(X, knn, W_path = aff_path)

elapsed = timeit.default_timer() - start_time
print(elapsed)

###### Run SLK#################################


if SLK_option == 'SLK-MS': 
    SLK_option = 'MS'
    
bound_ = True # Setting False only runs K-modes


if sigma is None:
    sigma = util.estimate_sigma(X,W,knn,N)
#        sigma = util.estimate_median_sigma(X,knn) # Or this (much faster)
    
sigma = max(0.1,sigma)
# Initial seed path from kmeans++ seed
init_C_path = './data/'+dataset+'_C_init.npy'

if not os.path.exists(init_C_path):
    
    elapsetimes = []
    bestnmi = -1
    bestacc = -1
    lmbdas = np.arange(0.5,5,0.1).tolist()
    t = len(lmbdas)
    trivial = [0]*t # Take count on any missing cluster 
    
    for count,lmbda in enumerate(lmbdas):
        print('Inside Lambda ',lmbda)
        print('Inside Sigma ',sigma)
        
        C_init,_ = km_init(X,K,'kmeans_plus')
        

        if N>=5000:
            if D<=50 and SLK_option == 'MS': # if dimension is less use iterative meanshift
                C,l,elapsed,mode_index,z,_,ts = SLK_iterative(X, sigma, K, W, bound_, SLK_option, C_init,
                                                               bound_lambda = lmbda, bound_iterations=200)
            else:
                C,l,elapsed,mode_index,z,_,ts = SLK(X, sigma, K, W, bound_, SLK_option, C_init, 
                                                     bound_lambda = lmbda, bound_iterations=200)
        else:
            C,l,elapsed,mode_index,z,_,ts = SLK_iterative(X, sigma, K, W, bound_, SLK_option,C_init, 
                                                           bound_lambda = lmbda, bound_iterations = 200)

        if ts:
            trivial[count] = 1
            continue

        # Evaluate the performance on validation set
        current_nmi = nmi(gnd_val,l[val_ind])
        acc,_ = get_accuracy(gnd_val,l[val_ind])

        print('lambda = ',lmbda, ' : NMI= %0.4f' %current_nmi)
        print('accuracy %0.4f' %acc)

        if current_nmi>bestnmi:
            bestnmi = current_nmi
            best_lambda_nmi = lmbda

        if acc>bestacc:
            bestacc = acc
            best_lambda_acc = lmbda
            best_C_init = C_init.copy()

        print('Best result: NMI= %0.4f' %bestnmi,'|NMI lambda = ', best_lambda_nmi)
        print('Best Accuracy %0.4f' %bestacc,'|Acc lambda = ', best_lambda_acc)
        elapsetimes.append(elapsed)

    avgelapsed = sum(elapsetimes)/len(elapsetimes)
    print ('avg elapsed ',avgelapsed)
    # save best initialization
    np.save(init_C_path,best_C_init)
    
    ### Run with best Lambda and assess accuracy over whole dataset
    best_lambda = best_lambda_acc # or best_lambda_nmi
    if N>=5000:
        if D<=50 and SLK_option =='MS': #if dimension is less use iterative meanshift
            C,l,elapsed,mode_index,z,_,_ = SLK_iterative(X,sigma,K,W,bound_,SLK_option,best_C_init, 
                                                          bound_lambda = best_lambda, bound_iterations=200)
        else:
            C,l,elapsed,mode_index,z,_,_ = SLK(X,sigma,K,W,bound_,SLK_option,best_C_init, 
                                                bound_lambda = best_lambda, bound_iterations=200)
    else:
        C,l,elapsed,mode_index,z,_,_ = SLK_iterative(X,sigma,K,W,bound_,SLK_option,best_C_init, 
                                                      bound_lambda = best_lambda, bound_iterations=200)
    # Evaluate the performance on dataset
    
    print('Elapsed time for SLK = %0.5f seconds' %elapsed)
    nmi_ = nmi(gnd_labels,l)
    acc_,_ = get_accuracy(gnd_labels,l)
    
    print('Result: NMI= %0.4f' %nmi_)
    print('        Accuracy %0.4f' %acc_)
    best_lambda = best_lambda_acc
    if saveresult:
        saveresult_path = './data/Result_'+dataset+'.mat'
        sio.savemat(saveresult_path,{'lmbda':best_lambda,'l':l,'C':C,'z':z})
        
    if mode_images:
        if SLK_option == 'SLK-BO':  
            mode_images_path = './data/'+dataset+'_modes'
            original_image_size = (28,28)
            util.mode_nn(mode_index,X,K,C,l,6,X_org,mode_images_path, original_image_size)
        else:
            print('\n For Mode images change option to -- SLK-BO')
else:
   ### Run with best Lambda and assess accuracy over whole dataset
    C_init = np.load(init_C_path) # Load initial seeds
    best_lambda_acc = 1.31 # best lambda got for MNIST gan features
    best_lambda = best_lambda_acc

    if N>=5000:
        if D<=50 and SLK_option == 'MS': #if dimension is less use iterative meanshift
            C,l,elapsed,mode_index,z,_,_ = SLK_iterative(X,sigma,K,W,bound_,SLK_option,C_init, 
                                                          bound_lambda = best_lambda, bound_iterations=200)
        else:
            C,l,elapsed,mode_index,z,_,_ = SLK(X,sigma,K,W,bound_,SLK_option,C_init, 
                                                bound_lambda = best_lambda, bound_iterations=200)
    else:
        C,l,elapsed,mode_index,z,_,_ = SLK_iterative(X,sigma,K,W,bound_,SLK_option,C_init, 
                                                      bound_lambda = best_lambda, bound_iterations=200)        
                # Evaluate the performance on dataset
    print('Elapsed time for SLK = %0.5f seconds' %elapsed)
    nmi_ = nmi(gnd_labels,l)
    acc_,_ = get_accuracy(gnd_labels,l)
    
    print('Result: NMI= %0.4f' %nmi_)
    print('        Accuracy %0.4f' %acc_)
    
    # ipdb.set_trace()
    if saveresult:
        saveresult_path = './data/Result_'+dataset+'_'+SLK_option+'.npz'
        np.savez(saveresult_path,lmbda = best_lambda,l = l,C = C, z = z, mode_index = mode_index)
        
    if mode_images:
        if 'SLK-BO' in SLK_option:
            mode_images_path = './data/'+dataset+'_modes'
            original_image_size = (28,28)
            util.mode_nn(mode_index,X,K,C,l,6,X_org,mode_images_path, original_image_size)
        else:
            print('\n For Mode images change SLK_option to -- SLK-BO')
