import torch
import torch.optim as optim
import os
from NGCF import NGCF
from utility.helper import *
from utility.batch_test import *
import warnings
warnings.filterwarnings('ignore')
from time import time

if __name__ == '__main__':
    args.device = torch.device('cuda:' + str(args.gpu_id))

    plain_adj, norm_adj, mean_adj = data_generator.get_adj_mat()

    args.node_dropout = eval(args.node_dropout)
    args.mess_dropout = eval(args.mess_dropout)

    model = NGCF(data_generator.n_users,
                 data_generator.n_items,
                 norm_adj,
                 args).to(args.device)

    t0 = time()
    
    # Création du répertoire parent pour les poids du modèle
    os.makedirs(args.weights_path, exist_ok=True)

    """
    *********************************************************
    Train.
    """
    cur_best_pre_0, stopping_step = 0, 0
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    loss_loger, pre_loger, rec_loger, ndcg_loger, hit_loger = [], [], [], [], []
    for epoch in range(args.epoch):
        t1 = time()
        loss= 0.
        n_batch = data_generator.n_train // args.batch_size + 1

        for idx in range(n_batch):
            users, pos_items, neg_items = data_generator.sample()
            u_g_embeddings, pos_i_g_embeddings, neg_i_g_embeddings = model(users,
                                                                           pos_items,
                                                                           neg_items,
                                                                           drop_flag=args.node_dropout_flag)

            batch_loss, batch_mf_loss, batch_emb_loss = model.create_bpr_loss(u_g_embeddings,
                                                                              pos_i_g_embeddings,
                                                                              neg_i_g_embeddings)
            optimizer.zero_grad()
            batch_loss.backward()
            optimizer.step()

            loss += batch_loss
            
        if (epoch + 1) % 10 != 0:
            if args.verbose > 0 and epoch % args.verbose == 0:
                perf_str = 'Epoch %d [%.1fs]: train==[%.5f]' % (
                    epoch, time() - t1, loss)
                print(perf_str)
            continue

        t2 = time()
        users_to_test = list(data_generator.test_set.keys())
        if epoch > 140 :
            ret = test(model, users_to_test, drop_flag=False)

            t3 = time()

            loss_loger.append(loss)
            rec_loger.append(ret['recall'])
            pre_loger.append(ret['precision'])
            ndcg_loger.append(ret['ndcg'])
            hit_loger.append(ret['hit_ratio'])

            if args.verbose > 0:
                perf_str = 'Epoch %d [%.1fs + %.1fs]: train==[%.5f], recall=[%.5f], ' \
                          'precision=[%.5f], hit=[%.5f], ndcg=[%.5f]' % \
                          (epoch, t2 - t1, t3 - t2, loss, ret['recall'][0],
                            ret['precision'][0], ret['hit_ratio'][0],
                            ret['ndcg'][0])
                print(perf_str)

            cur_best_pre_0, stopping_step, should_stop = early_stopping(ret['recall'][0], cur_best_pre_0,
                                                                    stopping_step, expected_order='acc', flag_step=5)

            # *********************************************************
            # early stopping when cur_best_pre_0 is decreasing for ten successive steps.
            if should_stop == True:
                break

            # *********************************************************
            # save the user & item embeddings for pretraining.
            if ret['recall'][0] == cur_best_pre_0 and args.save_flag == 1:
                if epoch == 300 : 
                    torch.save(model.state_dict(), args.weights_path + str(epoch) + '.pkl')
                    print('save the weights in path: ', args.weights_path + str(epoch) + '.pkl')
