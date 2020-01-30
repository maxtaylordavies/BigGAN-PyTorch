#!/bin/bash

#PBS -l walltime=00:10:00
#PBS -l select=1:ncpus=32:mem=192gb:ngpus=8:gpu_type=RTX6000

module load anaconda3/personal
source activate biggan

cd $PBS_O_WORKDIR
./launch_BigGAN_bs256x8.sh

