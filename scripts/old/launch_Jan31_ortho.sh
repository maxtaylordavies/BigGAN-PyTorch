# --fp16  --SN_eps 1e-4 --BN_eps 1e-4 --adam_eps 1e-4 
CUDA_VISIBLE_DEVICES=0,1,2,3 python train.py \
--G_eval_mode \
--dataset I128_hdf5 --parallel --shuffle  --num_workers 8 --batch_size 256  \
--num_G_accumulations 1 --num_D_accumulations 1 \
--num_D_steps 1 --G_lr 1e-4 --D_lr 4e-4 --D_B2 0.999 --G_B2 0.999 \
--G_attn 64 --D_attn 64 \
--G_nl inplace_relu --D_nl inplace_relu \
--fp16  --SN_eps 1e-4 --BN_eps 1e-4 --adam_eps 1e-4 \
--G_ortho 0.0 \
--G_shared \
--G_init ortho --D_init ortho \
--num_G_SVs 1 --num_D_SVs 1 --sv_log_interval 10 \
--test_every 2000 --save_every 1000 --num_best_copies 5 --num_save_copies 2 --seed 0 \
--name_suffix jan31_attn_ortho \
--base_root /home/s1580274/scratch