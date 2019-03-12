# BigGAN-PyTorch
The author's authorized and officially unofficial PyTorch BigGAN implementation.

![Dogball? Dogball!](imgs/header_image.jpg?raw=true "Header")


This repo contains code for replicating select results from [Large Scale GAN Training for High Fidelity Natural Image Synthesis](https://arxiv.org/abs/1809.11096) by Andrew Brock, Jeff Donahue, and Karen Simonyan.

This code is by Andy Brock and Alex Andonian.

## How to use this code:
You will need:

- [PyTorch](https://pytorch.org/), version 1.0
- tqdm, scipy, and h5py
- The ImageNet training set

First, you (optionally) need to prepare a pre-processed HDF5 version of your target dataset for faster I/O, and the Inception moments needed calculate FID. This can be done by modifying and running

```sh
sh scripts/prepare_data.sh
```

Which by default assumes your ImageNet training set is downloaded into the root folder "data" in this directory, and will prepare the cached HDF5 at 128x128 pixel resolution.

Now, in order to run experiments on CIFAR or ImageNet, edit the desired .sh files to point towards the root directory where you want your weights/data/samples contained (or edit the logs_root, weights_root, samples_root, and dataset_root arguments individually).

There are also scripts to run SA-GAN and SN-GAN on ImageNet. The SA-GAN code assumes you have 4xTitanX (or equivalent in terms of GPU RAM) and will run with a batch size of 128 and 2 gradient accumulations.

The main script for training on ImageNet at 128x128 is currently "launch_I128_A.sh." This is a script that runs the SA-GAN baseline (no self-attention) with the slight modification of using shared embeddings (helps memory consumption since I run these on shared servers). 

Training scripts will output logs with training metrics and test metrics, will save multiple copies of the model weights/optimizer weights and will produce samples and interpolations every time it saves weights.

If you wish to resume interrupted training, run the same launch script but with the `--resume` arguments added.

See the docs folder for more detailed markdown files describing the rest of this codebase, or check the comments in the code.

After training, one can use `sample.py` to produce additional samples and interpolations, test with different truncation values, batch sizes, number of standing stat accumulations, etc. See a `sample_BigGAN_A.sh` script for an example.

## Using your own dataset
You will need to modify utils.py

-using your own training function: either modify train_fns.GAN_training_function or add a new train fn and modify the train = whichtrainfn line in train.py

-You should probably use FID instead of IS for any dataset other than ImageNet. 

## Neat things about this code
--Contains an accelerated FID calculation--the original scipy version can require upwards of 10 minutes to calculate the matrix sqrt, this version uses an accelerated pytorch version to calculate it in under a second.
--accelerated ortho reg
--also effectively contains implementations of SA-GAN and SN-GAN

## Key differences between this code and the original BigGAN
-no sync BN
-Gradient accumulation means that we update the SV estimates and the BN statistics 8x as much. This means that the BN stats are much closer to standing stats (hence why we can get away with running the EMA'd G in eval mode),
and that the singular value estimates tend to be more accurate. This could also conceivably result in 
-this code uses the pytorch in-built inception network to calculate IS and FID. 
These scores are different from the scores you would get using the official TF inception code, and are only for monitoring purposes!
 IS using the pytorch net tends to be 5-10% lower than using the official TF net.
Run sample.py on your model, with the --sample_npz argument, then run inception_tf13 to calculate the actual TF IS.

-At the moment these pretrained models were not trained with orthogonal regularization. Training without ortho reg seems to increase the probability that models will not be amenable to truncation,
but it seems to be okay here. Regardless, we provide two highly optimized (fast and minimal memory consumption) ortho reg implementations which directly compute the ortho reg. gradients.


## Saved info to be integrated into docs later
See [This directory](https://gist.github.com/yrevar/942d3a0ac09ec9e5eb3a) for ImageNet labels.


## Feature requests
Want to work on or improve this code? There are a couple things this repo would benefit from, but which we haven't gotten working.

- Synchronized BatchNorm (AKA Cross-Replica BatchNorm). We tried out two variants of this, but for some unknown reason our nets did not train with this on. 
  We have not tried the [apex](https://github.com/NVIDIA/apex) SyncBN as my school's servers are on ancient NVIDIA drivers that don't support it--apex would probably be a good place to start.
  
- Mixed precision training and making use of tensorcores. This repo includes a naive mixed-precision Adam implementation which works early in training but leads to early collapse, and doesn't do anything to activate tensorcores (it just reduces memory consumption.
  As above, integrating [apex](https://github.com/NVIDIA/apex) into this code and employing its mixed-precision training techniques to take advantage of tensorcores and reduce memory consumption could yield substantial speed gains.

## To-do:
- Flesh out this readme
- Writeup design doc
- Write acks

## Acknowledgments
We would like to thank Jiahui Yu and Ming-Yu Liu of NVIDIA for helping run experiments. Thanks to Google for the generous cloud credit donations.

[Progress bar](https://github.com/Lasagne/Recipes/tree/master/papers/densenet) originally from Jan Schlüter

Test metrics logger from [VoxNet](https://github.com/dimatura/voxnet)

pytorch [implementation of cov](https://discuss.pytorch.org/t/covariance-and-gradient-support/16217/2) from Modar M. Alfadly

PyTorch [fast Matrix Sqrt](https://github.com/msubhransu/matrix-sqrt) for FID from Tsung-Yu Lin and Subhransu Maji

TensorFlow Inception Score code from [OpenAI's Improved-GAN](https://github.com/openai/improved-gan)

